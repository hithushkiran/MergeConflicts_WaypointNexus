"""Synthetic API acceptance: created orders → recovery → synced POD → store receipt.

Run only against the isolated Compose project described in docs/T09_VERIFICATION.md.
Creates explicit local planning references for the orders returned by the store API;
it never edits database state, official CSVs, or the planner's production rules.
"""
import argparse
import csv
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from shutil import copyfile
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4


class HttpAPI:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def __call__(self, method, path, headers=None, body=None, expected=200):
        request = Request(self.base_url + path, method=method,
                          headers={"Content-Type": "application/json", **(headers or {})},
                          data=json.dumps(body).encode() if body is not None else None)
        try:
            with urlopen(request, timeout=60) as response:
                status, result = response.status, json.loads(response.read())
        except HTTPError as error:
            status, result = error.code, json.loads(error.read())
        assert status == expected, f"{method} {path}: expected {expected}, got {status}: {result}"
        return result


def write_rows(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def configure_references(root: Path, orders: list[dict], planning_date: date):
    root.mkdir(parents=True, exist_ok=True)
    demo = Path(__file__).resolve().parents[1] / "demo-data"
    for name in ("vehicles.csv", "district_travel.csv"):
        copyfile(demo / name, root / name)
    with (demo / "service_allowance.csv").open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fields = reader.fieldnames
    # DEMO-OUT001 is explicitly labeled DEMO FRESH in the ordinary development seed.
    fresh = next(row for row in rows if row["brand"] == "Fresh" and row["dock_type"] == "STANDARD")
    rows.append({**fresh, "brand": "DEMO FRESH"})
    write_rows(root / "service_allowance.csv", fields, rows)
    write_rows(root / "calendar.csv", ["date", "is_operating"], [{"date": str(planning_date), "is_operating": 1}])
    write_rows(root / "task2b_peak_day_fleet.csv", ["scenario", "vehicle_id", "status"], [
        {"scenario": "T09-SYNTHETIC", "vehicle_id": f"DEMO-VEH00{index}", "status": "available" if index == 3 else "workshop"}
        for index in range(1, 5)
    ])
    fields = ["scenario", "order_ref", "outlet_id", "requested_delivery_date", "depot", "brand", "district",
              "temp_requirement", "parking_constraint", "order_weight_kg", "order_volume_m3", "units",
              "dock_type", "window_open_time", "window_close_time", "prior_day_deferral"]
    write_rows(root / "task2b_peak_day_scenarios.csv", fields, [
        {"scenario": "T09-SYNTHETIC", "order_ref": order["reference"], "outlet_id": order["outlet_id"],
         "requested_delivery_date": str(planning_date), "depot": "Peliyagoda", "brand": "DEMO FRESH", "district": "Colombo",
         "temp_requirement": order["temperature_requirement"].lower(), "parking_constraint": "none",
         "order_weight_kg": order["weight_kg"], "order_volume_m3": order["volume_m3"], "units": order["units"],
         "dock_type": "STANDARD", "window_open_time": "", "window_close_time": "", "prior_day_deferral": 0}
        for order in orders
    ])


def run_golden_path(api, reference_dir: Path, planning_date: date | None = None, prepare_only: bool = False):
    def login(role):
        result = api("POST", "/api/v1/auth/login", body={"email": f"{role}@waypoint.local", "password": "waypoint-local-demo"})
        return {"Authorization": f"Bearer {result['access_token']}"}

    store, dispatch, loader, driver = (login(role) for role in ("store.manager", "dispatcher", "loader", "driver"))
    eligibility = api("GET", "/api/v1/store/orders/eligibility", store)
    planning_date = planning_date or date.fromisoformat(eligibility["next_eligible_delivery_date"]) + timedelta(days=1)
    prefix = "t09-" + str(uuid4())

    def command(role, key):
        return {**role, "Idempotency-Key": f"{prefix}-{key}"}

    orders = [api("POST", "/api/v1/store/orders", command(store, temperature),
                  {"requested_delivery_date": str(planning_date), "temperature_requirement": temperature,
                   "units": units, "weight_kg": weight, "volume_m3": volume,
                   "notes": "Clearly synthetic T09 golden-path acceptance"}, expected=201)
              for temperature, units, weight, volume in (("AMBIENT", 32, 320, 2.4), ("CHILLED", 18, 180, 1.4))]
    configure_references(reference_dir, orders, planning_date)
    plan = api("POST", "/api/v1/dispatcher/plans", command(dispatch, "plan"), {"planning_date": str(planning_date)}, expected=201)["plan"]
    assert len(plan["trips"]) == 1 and all(row["decision"] == "served" for row in plan["orders"])
    publish = api("POST", f"/api/v1/dispatcher/plans/{plan['id']}/publish", command(dispatch, "publish"), {"reason": "T09 synthetic review"})
    assert publish["served_orders"] == 2
    trip_id = plan["trips"][0]["id"]
    driver_id = api("GET", "/api/v1/dispatcher/drivers", dispatch)["items"][0]["id"]
    api("POST", f"/api/v1/dispatcher/trips/{trip_id}/assign", dispatch, {"driver_id": driver_id})
    trip = next(item for item in api("GET", "/api/v1/loader/trips", loader)["items"] if item["id"] == trip_id)
    chilled = orders[1]
    checked = api("POST", f"/api/v1/loader/trips/{trip_id}/checks", loader, {"manifest_version": 1, "lines": [
        {"order_id": line["order_id"], "status": "MISSING" if line["order_id"] == chilled["id"] else "LOADED",
         "quantity": 2 if line["order_id"] == chilled["id"] else line["expected_quantity"], "notes": "20 kg chilled missing"}
        for line in trip["manifest"]["lines"]
    ]})
    assert checked["trip_status"] == "DISPATCH_HOLD"
    blocked = api("POST", f"/api/v1/driver/trips/{trip_id}/depart", command(driver, "held"), expected=409)
    assert blocked["detail"]["code"] == "DEPARTURE_BLOCKED"
    shortfall = next(item for item in api("GET", "/api/v1/dispatcher/shortfalls", dispatch)["items"] if item["trip_id"] == trip_id)
    resolution = api("POST", f"/api/v1/dispatcher/shortfalls/{shortfall['id']}/resolve", dispatch,
                     {"action": "PARTIAL_FULFILLMENT", "quantity": 16, "reason": "Approve the 160 kg available chilled stock"})
    manifest = resolution["manifest"]
    assert manifest["version_number"] == 2
    assert sum(line["expected_quantity"] * 10 for line in manifest["lines"]) == 480
    stale = api("POST", f"/api/v1/loader/trips/{trip_id}/checks", loader,
                {"manifest_version": 1, "lines": [{"order_id": chilled["id"], "status": "LOADED", "quantity": 18}]}, expected=409)
    assert stale["detail"]["code"] == "STALE_MANIFEST"
    ready = api("POST", f"/api/v1/loader/manifests/{manifest['id']}/acknowledge", loader)
    assert ready["trip_status"] == "READY"
    my_trip = next(item for item in api("GET", "/api/v1/driver/trips", driver)["items"] if item["id"] == trip_id)
    assert my_trip["manifest_version"] == 2
    api("POST", f"/api/v1/driver/trips/{trip_id}/depart", command(driver, "depart"))
    if prepare_only:
        return {"planning_date": str(planning_date), "trip_id": trip_id,
                "order_refs": [order["reference"] for order in orders], "result": "READY_FOR_BROWSER_OFFLINE_CHECK"}
    # Commands represent work saved while offline. Original event time and stable IDs replay on sync.
    for index, stop in enumerate(my_trip["stops"]):
        occurred = datetime.now(UTC).isoformat()
        api("POST", f"/api/v1/driver/stops/{stop['id']}/arrive", {**command(driver, f"arrive-{index}"), "X-Command-Id": f"{prefix}-arrive-{index}"}, {"occurred_at": occurred})
        body = {"outcome": "DELIVERED", "receiver_name": "Synthetic receiving team", "notes": "Saved offline and synced", "occurred_at": occurred}
        headers = {**command(driver, f"pod-{index}"), "X-Command-Id": f"{prefix}-pod-{index}"}
        completed = api("POST", f"/api/v1/driver/stops/{stop['id']}/complete", headers, body)
        assert completed["proof_recorded"]
        duplicate = api("POST", f"/api/v1/driver/stops/{stop['id']}/complete", headers, body)
        assert duplicate["replayed"]
    deliveries = api("GET", "/api/v1/store/deliveries", store)["items"]
    assert next(item for item in deliveries if item["order_id"] == chilled["id"])["dispatched_quantity"] == 16
    dry_url = f"/api/v1/store/orders/{orders[0]['id']}/receipt"
    dry_body = {"receiver_name": "Synthetic store manager", "received_quantity": 32}
    dry_receipt = api("POST", dry_url, command(store, "receipt"), dry_body, expected=201)
    assert dry_receipt["order_status"] == "RECEIVED"
    assert api("POST", dry_url, command(store, "receipt"), dry_body, expected=201) == dry_receipt
    issue_url = f"/api/v1/store/orders/{chilled['id']}/issues"
    issue_body = {"receiver_name": "Synthetic store manager", "received_quantity": 16, "issue_type": "MISSING_QUANTITY",
                  "affected_quantity": 2, "notes": "Received 160 kg chilled against the original 180 kg request; partial dispatch approved."}
    issue = api("POST", issue_url, command(store, "issue"), issue_body, expected=201)
    assert issue["receipt"]["status"] == "DISPUTED" and issue["order_status"] == "DELIVERED"
    assert api("POST", issue_url, command(store, "issue"), issue_body, expected=201) == issue
    assert api("POST", issue_url, command(store, "second-issue"), issue_body, expected=409)["detail"]["code"] == "RECEIPT_ALREADY_RECORDED"
    issue_id = issue["issue"]["id"]
    for status in ("IN_REVIEW", "RESOLVED"):
        closed = api("POST", f"/api/v1/dispatcher/delivery-issues/{issue_id}/review", command(dispatch, status),
                     {"status": status, "reason": "Reviewed and accepted the recorded partial intake; no replacement promised"})
    assert closed["receipt"]["status"] == "PARTIAL" and closed["order_status"] == "RECEIVED"
    assert api("GET", f"/api/v1/store/orders/{chilled['id']}/receipt", store)["received_quantity"] == 16
    return {"planning_date": str(planning_date), "plan_id": plan["id"], "trip_id": trip_id,
            "order_ids": [order["id"] for order in orders], "order_refs": [order["reference"] for order in orders],
            "issue_id": issue_id, "manifest_version": 2, "initial_kg": 500, "revised_kg": 480,
            "dry_receipt": dry_receipt["receipt"]["id"], "chilled_receipt": closed["receipt"]["id"], "result": "PASSED"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://localhost:8001")
    parser.add_argument("--reference-dir", type=Path, required=True)
    parser.add_argument("--planning-date", type=date.fromisoformat)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--prepare-only", action="store_true", help="Stop after departure for manual browser offline acceptance")
    args = parser.parse_args()
    result = run_golden_path(HttpAPI(args.api_url), args.reference_dir, args.planning_date, args.prepare_only)
    if args.output:
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
