"""Deterministic development data import; run with `python -m app.seed`."""
import csv
from datetime import date
from pathlib import Path

from sqlalchemy import select

from app.infrastructure.database import get_session_factory
from app.infrastructure.persistence import Depot, Order, Outlet, PlanningRun, Role, User, Vehicle

DATA_DIR = Path("/app/local-data") if Path("/app/local-data").exists() else Path(__file__).parents[2] / "local-data"
DEMO_PLANNING_DATE = date(2026, 3, 16)
DEMO_ORDERS = [
    ("DEMO-ORD-FRESH-AMBIENT", "OUT001", "AMBIENT", 24, 120.0, 1.2),
    ("DEMO-ORD-FRESH-CHILLED", "OUT001", "CHILLED", 12, 80.0, 0.8),
    ("DEMO-ORD-STYLE", "OUT015", "AMBIENT", 18, 90.0, 1.0),
    ("DEMO-ORD-TECH", "OUT021", "AMBIENT", 8, 60.0, 0.6),
]


def rows(name: str, required: set[str]) -> list[dict[str, str]]:
    path = DATA_DIR / name
    if not path.exists():
        raise RuntimeError(f"Official dataset missing: {path}")
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise RuntimeError(f"Invalid {name}: required columns are missing")
        result = list(reader)
    key = "outlet_id" if name == "outlets.csv" else "vehicle_id"
    if len({row[key] for row in result}) != len(result) or any(not row[key] for row in result):
        raise RuntimeError(f"Invalid {name}: duplicate or blank {key}")
    if name == "vehicles.csv":
        try:
            for row in result:
                for field in ("weight_cap_kg", "volume_cap_m3", "km_per_l", "weekly_fuel_quota_l"):
                    if float(row[field]) <= 0:
                        raise ValueError(field)
        except (KeyError, ValueError) as error:
            raise RuntimeError(f"Invalid {name}: invalid numeric capacity/value") from error
    return result


def seed() -> None:
    outlets = rows("outlets.csv", {"outlet_id", "brand", "district", "depot", "dock_type", "parking_constraint", "mall_window", "window_open_time", "window_close_time"})
    vehicles = rows("vehicles.csv", {"vehicle_id", "type", "temp", "weight_cap_kg", "volume_cap_m3", "fuel_type", "km_per_l", "weekly_fuel_quota_l", "depot"})
    if len(outlets) != 120 or len(vehicles) != 60:
        raise RuntimeError("Official dataset count mismatch (expected 120 outlets and 60 vehicles)")
    session = get_session_factory()()
    try:
        for code, name in [("STORE_MANAGER", "Store Manager"), ("DISPATCHER", "Dispatcher"), ("LOADER", "Loader"), ("DRIVER", "Driver")]:
            if not session.scalar(select(Role).where(Role.code == code)): session.add(Role(code=code, name=name))
        for code, name in [("Peliyagoda", "Peliyagoda"), ("Kandy", "Kandy")]:
            if not session.get(Depot, code): session.add(Depot(code=code, name=name))
        session.flush()
        for row in outlets:
            if not session.get(Outlet, row["outlet_id"]): session.add(Outlet(outlet_id=row["outlet_id"], brand=row["brand"].upper(), district=row["district"], depot_code=row["depot"], dock_type=row["dock_type"], parking_constraint=row["parking_constraint"], mall_window=row["mall_window"] or None, window_open_time=row["window_open_time"] or None, window_close_time=row["window_close_time"] or None))
        for row in vehicles:
            if not session.get(Vehicle, row["vehicle_id"]): session.add(Vehicle(vehicle_id=row["vehicle_id"], type=row["type"].upper(), temp=row["temp"].upper(), weight_cap_kg=float(row["weight_cap_kg"]), volume_cap_m3=float(row["volume_cap_m3"]), fuel_type=row["fuel_type"], km_per_l=float(row["km_per_l"]), weekly_fuel_quota_l=float(row["weekly_fuel_quota_l"]), depot_code=row["depot"]))
        session.flush()
        roles = {role.code: role.id for role in session.scalars(select(Role)).all()}
        for email, name, role, outlet, depot in [("store.manager@waypoint.local", "Development Store Manager", "STORE_MANAGER", outlets[0]["outlet_id"], None), ("dispatcher@waypoint.local", "Development Dispatcher", "DISPATCHER", None, None), ("loader@waypoint.local", "Development Loader", "LOADER", None, "Peliyagoda"), ("driver@waypoint.local", "Development Driver", "DRIVER", None, "Peliyagoda")]:
            if not session.scalar(select(User).where(User.email == email)): session.add(User(email=email, display_name=name, role_id=roles[role], outlet_id=outlet, depot_code=depot))
        for reference, outlet_id, temperature, units, weight, volume in DEMO_ORDERS:
            if not session.scalar(select(Order).where(Order.reference == reference)):
                session.add(Order(reference=reference, outlet_id=outlet_id, requested_delivery_date=DEMO_PLANNING_DATE, temperature_requirement=temperature, units=units, weight_kg=weight, volume_m3=volume, status="CONFIRMED", notes="Deterministic FND-03 development fixture"))
        if not session.scalar(select(PlanningRun).where(PlanningRun.planning_date == DEMO_PLANNING_DATE, PlanningRun.snapshot_hash == "demo-2026-03-16")):
            session.add(PlanningRun(planning_date=DEMO_PLANNING_DATE, snapshot_hash="demo-2026-03-16", status="DRAFT", runtime_metadata={"fixture": "FND-03"}))
        session.commit()
    except Exception:
        session.rollback(); raise
    finally: session.close()


if __name__ == "__main__":
    seed()
