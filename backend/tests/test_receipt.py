"""Receipt acceptance against the existing planning/loading/delivery API path."""
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.infrastructure.persistence import AuditEvent, DeliveryEvent, DeliveryIssue, Order, ProofOfDelivery, Receipt, Role, User
from test_dispatcher import PLANNING_DATE, auth, dispatcher_factory  # noqa: F401


@pytest.fixture
def delivered_order(dispatcher_factory):
    client, factory = dispatcher_factory
    dispatch, loader, driver, store = (auth(client, email) for email in (
        "dispatcher@test.local", "loader@test.local", "driver@test.local", "store@test.local"))
    plan = client.post("/api/v1/dispatcher/plans", headers={**dispatch, "Idempotency-Key": "plan"},
                       json={"planning_date": str(PLANNING_DATE)}).json()["plan"]
    assert client.post(f"/api/v1/dispatcher/plans/{plan['id']}/publish", json={},
                       headers={**dispatch, "Idempotency-Key": "publish"}).status_code == 200
    outlet = client.get("/api/v1/auth/me", headers=store).json()["outlet_id"]
    trip = next(item for item in client.get("/api/v1/loader/trips", headers=loader).json()["items"]
                if any(line["outlet_id"] == outlet for line in item["manifest"]["lines"]))
    driver_id = client.get("/api/v1/dispatcher/drivers", headers=dispatch).json()["items"][0]["id"]
    assert client.post(f"/api/v1/dispatcher/trips/{trip['id']}/assign", json={"driver_id": driver_id}, headers=dispatch).status_code == 200
    assert client.post(f"/api/v1/loader/trips/{trip['id']}/checks", headers=loader, json={"manifest_version": 1, "lines": [
        {"order_id": line["order_id"], "status": "LOADED", "quantity": line["expected_quantity"]} for line in trip["manifest"]["lines"]
    ]}).status_code == 200
    assert client.post(f"/api/v1/loader/manifests/{trip['manifest']['id']}/acknowledge", headers=loader).status_code == 200
    driver_trip = client.get("/api/v1/driver/trips", headers=driver).json()["items"][0]
    assert client.post(f"/api/v1/driver/trips/{trip['id']}/depart", headers={**driver, "Idempotency-Key": "depart"}).status_code == 200
    target_id = None
    for index, stop in enumerate(driver_trip["stops"]):
        assert client.post(f"/api/v1/driver/stops/{stop['id']}/arrive", headers={**driver, "Idempotency-Key": f"arrive-{index}"}).status_code == 200
        assert client.post(f"/api/v1/driver/stops/{stop['id']}/complete", headers={**driver, "Idempotency-Key": f"complete-{index}"},
                           json={"outcome": "DELIVERED", "receiver_name": "Dock team"}).status_code == 200
        if stop["outlet_id"] == outlet:
            target_id = stop["order_id"]
    assert target_id
    return client, factory, store, dispatch, target_id


def receipt_body(client, store, order_id, difference=0):
    delivery = client.get(f"/api/v1/store/orders/{order_id}/delivery", headers=store)
    assert delivery.status_code == 200, delivery.text
    return {"receiver_name": "Store receiver", "received_quantity": delivery.json()["dispatched_quantity"] - difference,
            "notes": "Two units missing at intake" if difference else None}


@pytest.mark.parametrize("difference,status", [(0, "CONFIRMED"), (2, "PARTIAL"), (30, "PARTIAL")])
def test_receipt_persists_quantity_receiver_time_and_atomic_order_transition(delivered_order, difference, status):
    client, factory, store, _dispatch, order_id = delivered_order
    body = receipt_body(client, store, order_id, difference)
    headers = {**store, "Idempotency-Key": "receipt"}
    created = client.post(f"/api/v1/store/orders/{order_id}/receipt", json=body, headers=headers)
    assert created.status_code == 201, created.text
    receipt = created.json()["receipt"]
    assert created.json()["order_status"] == "RECEIVED"
    assert receipt["status"] == status
    assert receipt["receiver_name"] == "Store receiver"
    assert receipt["received_quantity"] == body["received_quantity"]
    assert datetime.fromisoformat(receipt["confirmed_at"]).utcoffset().total_seconds() == 0
    assert client.get(f"/api/v1/store/orders/{order_id}/receipt", headers=store).json() == receipt
    assert client.get("/api/v1/store/deliveries", headers=store).json()["items"][0]["receipt"] == receipt
    assert client.post(f"/api/v1/store/orders/{order_id}/receipt", json=body, headers=headers).json() == created.json()
    duplicate = client.post(f"/api/v1/store/orders/{order_id}/receipt", json=body, headers={**store, "Idempotency-Key": "another"})
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "RECEIPT_ALREADY_RECORDED"
    conflict = client.post(f"/api/v1/store/orders/{order_id}/receipt", json={**body, "receiver_name": "Someone else"}, headers=headers)
    assert conflict.status_code == 409 and conflict.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    with factory() as session:
        assert session.get(Order, UUID(order_id)).status == "RECEIVED"
        assert session.scalar(select(func.count()).select_from(Receipt)) == 1
        assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "RECEIPT_CONFIRMED")) == 1


def test_discrepancy_tracks_review_and_resolution_without_overwriting_receipt_facts(delivered_order):
    client, factory, store, dispatch, order_id = delivered_order
    body = {**receipt_body(client, store, order_id, 2), "issue_type": "MISSING_QUANTITY", "affected_quantity": 2}
    headers = {**store, "Idempotency-Key": "issue"}
    reported = client.post(f"/api/v1/store/orders/{order_id}/issues", headers=headers, json=body)
    assert reported.status_code == 201, reported.text
    case = reported.json()
    assert case["order_status"] == "DELIVERED" and case["receipt"]["status"] == "DISPUTED"
    issue_id = case["issue"]["id"]
    assert client.get("/api/v1/store/issues", headers=store).json()["items"][0]["id"] == issue_id
    assert client.get("/api/v1/dispatcher/delivery-issues", headers=dispatch).json()["items"][0]["receipt"]["received_quantity"] == 28
    assert client.post(f"/api/v1/store/orders/{order_id}/issues", headers={**store, "Idempotency-Key": "duplicate"}, json=body).status_code == 409
    review_url = f"/api/v1/dispatcher/delivery-issues/{issue_id}/review"
    assert client.post(review_url, headers={**dispatch, "Idempotency-Key": "direct-close"}, json={"status": "RESOLVED", "reason": "skip review"}).status_code == 409
    for status in ("IN_REVIEW", "RESOLVED"):
        review_body = {"status": status, "reason": "Reviewed the intake count with the store"}
        review_headers = {**dispatch, "Idempotency-Key": f"review-{status}"}
        response = client.post(review_url, headers=review_headers, json=review_body)
        assert response.status_code == 200, response.text
        assert response.json()["issue"]["status"] == status
        assert client.post(review_url, headers=review_headers, json=review_body).json() == response.json()
    assert response.json()["receipt"]["status"] == "PARTIAL"
    assert response.json()["order_status"] == "RECEIVED"
    assert response.json()["issue"]["resolved_at"] and response.json()["issue"]["resolved_by_id"]
    assert response.json()["receipt"]["received_quantity"] == 28
    assert client.post(f"/api/v1/store/orders/{order_id}/issues", headers=headers, json=body).json() == case
    assert client.post(review_url, headers={**dispatch, "Idempotency-Key": "reopen"}, json={"status": "IN_REVIEW", "reason": "reopen"}).status_code == 409
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(DeliveryIssue)) == 1
        assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action.in_(("DELIVERY_ISSUE_REPORTED", "DELIVERY_ISSUE_REVIEWED", "DELIVERY_ISSUE_RESOLVED")))) == 3


@pytest.mark.parametrize("changes", [
    {"received_quantity": -1}, {"received_quantity": 31}, {"received_quantity": 1.5},
    {"received_quantity": True}, {"receiver_name": "  "}, {"notes": "x" * 1001},
    {"received_quantity": 29, "notes": "  "}, {"outlet_id": "another"},
])
def test_invalid_receipt_does_not_change_order_or_create_records(delivered_order, changes):
    client, factory, store, _dispatch, order_id = delivered_order
    body = {**receipt_body(client, store, order_id), **changes}
    response = client.post(f"/api/v1/store/orders/{order_id}/receipt", headers={**store, "Idempotency-Key": "invalid"}, json=body)
    assert response.status_code == 422, response.text
    with factory() as session:
        assert session.get(Order, UUID(order_id)).status == "DELIVERED"
        assert session.scalar(select(Receipt)) is None


@pytest.mark.parametrize("changes", [
    {"affected_quantity": 0}, {"affected_quantity": 1}, {"notes": " "},
    {"issue_type": "UNKNOWN"}, {"issue_type": "DAMAGED", "affected_quantity": 31},
])
def test_issue_validation_is_atomic(delivered_order, changes):
    client, factory, store, _dispatch, order_id = delivered_order
    body = {**receipt_body(client, store, order_id, 2), "issue_type": "MISSING_QUANTITY", "affected_quantity": 2, **changes}
    response = client.post(f"/api/v1/store/orders/{order_id}/issues", headers={**store, "Idempotency-Key": "invalid"}, json=body)
    assert response.status_code == 422, response.text
    with factory() as session:
        assert session.scalar(select(Receipt)) is None and session.scalar(select(DeliveryIssue)) is None


def test_outlet_scope_role_guards_and_missing_scope_apply_to_reads_writes_and_replays(delivered_order):
    client, factory, store, dispatch, order_id = delivered_order
    with factory() as session:
        role = session.scalar(select(Role).where(Role.code == "STORE_MANAGER"))
        from app.modules.identity.security import hash_password
        for email, outlet in (("other@test.local", "DEMO-OUT015"), ("unscoped@test.local", None)):
            session.add(User(email=email, display_name="Other store", role_id=role.id, outlet_id=outlet,
                             password_hash=hash_password("test-password")))
        session.commit()
    other, unscoped = auth(client, "other@test.local"), auth(client, "unscoped@test.local")
    body = receipt_body(client, store, order_id)
    for endpoint in ("delivery", "receipt"):
        url = f"/api/v1/store/orders/{order_id}/{endpoint}"
        assert client.get(url).status_code == 401
        assert client.get(url, headers=dispatch).status_code == 403
        assert client.get(url, headers=other).status_code == 404
        assert client.get(url, headers=unscoped).status_code == 403
    for endpoint in ("receipt", "issues"):
        payload = body if endpoint == "receipt" else {**body, "issue_type": "DAMAGED", "affected_quantity": 1, "notes": "Damage found"}
        url = f"/api/v1/store/orders/{order_id}/{endpoint}"
        assert client.post(url, json=payload, headers={**dispatch, "Idempotency-Key": "key"}).status_code == 403
        assert client.post(url, json=payload, headers={**other, "Idempotency-Key": "key"}).status_code == 404
        assert client.post(url, json=payload, headers={**unscoped, "Idempotency-Key": "key"}).status_code == 403
    assert client.get("/api/v1/store/deliveries", headers=other).json()["items"] == []
    assert client.get("/api/v1/store/issues", headers=other).json()["items"] == []
    assert client.get("/api/v1/dispatcher/delivery-issues", headers=store).status_code == 403
    assert client.post(f"/api/v1/dispatcher/delivery-issues/{uuid4()}/review", headers={**store, "Idempotency-Key": "review"}, json={"status": "IN_REVIEW", "reason": "review"}).status_code == 403


def test_receipt_requires_successful_server_delivery_and_idempotency_key(dispatcher_factory):
    client, factory = dispatcher_factory
    store = auth(client, "store@test.local")
    order_id = client.get("/api/v1/store/orders", headers=store).json()["items"][0]["id"]
    body = {"receiver_name": "Receiver", "received_quantity": 1}
    url = f"/api/v1/store/orders/{order_id}/receipt"
    assert client.post(url, headers=store, json=body).status_code == 422
    assert client.post(url, headers={**store, "Idempotency-Key": "  "}, json=body).status_code == 422
    assert client.post(url, headers={**store, "Idempotency-Key": "early"}, json=body).status_code == 409
    with factory() as session:
        order = session.get(Order, UUID(order_id))
        order.status = "DELIVERY_FAILED"
        session.commit()
    assert client.post(url, headers={**store, "Idempotency-Key": "failed"}, json=body).status_code == 409
    assert client.get("/api/v1/store/deliveries", headers=store).json()["items"] == []


def test_delivery_uses_the_pod_manifest_snapshot(delivered_order):
    client, factory, store, _dispatch, order_id = delivered_order
    before = client.get(f"/api/v1/store/orders/{order_id}/delivery", headers=store).json()
    with factory() as session:
        from app.infrastructure.persistence import ManifestCheck
        line = session.scalar(select(ManifestCheck).where(ManifestCheck.order_id == UUID(order_id)))
        line.loaded_quantity = 1  # A later manifest edit cannot rewrite the historical delivery.
        session.commit()
    after = client.get(f"/api/v1/store/orders/{order_id}/delivery", headers=store).json()
    assert before["dispatched_quantity"] == after["dispatched_quantity"] == 30


def test_legacy_pod_falls_back_to_acknowledged_manifest(delivered_order):
    client, factory, store, _dispatch, order_id = delivered_order
    with factory() as session:
        event = session.scalar(select(DeliveryEvent).join(ProofOfDelivery, ProofOfDelivery.delivery_event_id == DeliveryEvent.id)
                               .where(DeliveryEvent.event_type == "DELIVERED"))
        event.metadata_ = {"receiver_name": "Legacy receiver"}
        session.commit()
    assert client.get(f"/api/v1/store/orders/{order_id}/delivery", headers=store).status_code == 200
