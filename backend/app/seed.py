"""Deterministic development data import; run with `python -m app.seed`."""
import csv
from datetime import date
from pathlib import Path

from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.infrastructure.database import get_session_factory
from app.infrastructure.persistence import Depot, Order, Outlet, PlanningRun, Role, User, Vehicle
from app.modules.identity.security import hash_password
from app.modules.planning.reference_data import load_planning_reference_data

DATA_DIR = Path("/app/local-data") if Path("/app/local-data").exists() else Path(__file__).parents[2] / "local-data"
DEMO_DATA_DIR = Path("/app/demo-data") if Path("/app/demo-data").exists() else Path(__file__).parents[1] / "demo-data"
DEMO_PLANNING_DATE = date(2026, 3, 16)
DEMO_FND03_ORDER_DATE = date(2026, 3, 17)
DEMO_ORDERS = [
    ("DEMO-ORD-FRESH-AMBIENT", "OUT001", "DEMO-OUT001", "AMBIENT", 24, 120.0, 1.2),
    ("DEMO-ORD-FRESH-CHILLED", "OUT001", "DEMO-OUT001", "CHILLED", 12, 80.0, 0.8),
    ("DEMO-ORD-STYLE", "OUT015", "DEMO-OUT015", "AMBIENT", 18, 90.0, 1.0),
    ("DEMO-ORD-TECH", "OUT021", "DEMO-OUT021", "AMBIENT", 8, 60.0, 0.6),
]


def rows(name: str, required: set[str], data_dir: Path | None = None) -> list[dict[str, str]]:
    path = (data_dir or DATA_DIR) / name
    if not path.exists():
        raise RuntimeError(f"Dataset file missing: {path}")
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


def select_dataset(demo_only: bool = False) -> tuple[Path, bool]:
    official_files = [DATA_DIR / "outlets.csv", DATA_DIR / "vehicles.csv"]
    official_present = [path.exists() for path in official_files]
    if demo_only:
        if get_settings().app_env.lower() != "development":
            raise RuntimeError("Synthetic demo data can only be seeded when APP_ENV=development")
        return DEMO_DATA_DIR, True
    if all(official_present):
        return DATA_DIR, False
    if any(official_present):
        raise RuntimeError("Official seed data is incomplete: both outlets.csv and vehicles.csv are required")
    if get_settings().app_env.lower() == "development":
        return DEMO_DATA_DIR, True
    raise RuntimeError("Official seed data is missing and synthetic data is disabled outside development")


def seed_development_accounts() -> None:
    """Create the local role accounts without inventing official outlet data."""
    settings = get_settings()
    if settings.app_env.lower() != "development" or not settings.dev_seed_password:
        raise RuntimeError("Bootstrap-only seeding requires APP_ENV=development and DEV_SEED_PASSWORD")

    session = get_session_factory()()
    try:
        for code, name in [
            ("STORE_MANAGER", "Store Manager"),
            ("DISPATCHER", "Dispatcher"),
            ("LOADER", "Loader"),
            ("DRIVER", "Driver"),
        ]:
            if not session.scalar(select(Role).where(Role.code == code)):
                session.add(Role(code=code, name=name))
        for code, name in [("Peliyagoda", "Peliyagoda"), ("Kandy", "Kandy")]:
            if not session.get(Depot, code):
                session.add(Depot(code=code, name=name))
        session.flush()
        roles = {role.code: role.id for role in session.scalars(select(Role)).all()}
        _ensure_development_users(session, roles, None, settings.dev_seed_password)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _ensure_development_users(
    session,
    roles: dict[str, int],
    default_outlet_id: str | None,
    seed_password: str | None,
) -> None:
    users = [
        ("store.manager@waypoint.local", "Development Store Manager", "STORE_MANAGER", default_outlet_id, None),
        ("dispatcher@waypoint.local", "Development Dispatcher", "DISPATCHER", None, None),
        ("loader@waypoint.local", "Development Loader", "LOADER", None, "Peliyagoda"),
        ("driver@waypoint.local", "Development Driver", "DRIVER", None, "Peliyagoda"),
    ]
    for email, name, role, outlet, depot in users:
        user = session.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, display_name=name, role_id=roles[role], outlet_id=outlet, depot_code=depot)
            session.add(user)
        elif role == "STORE_MANAGER" and user.outlet_id is None and outlet is not None:
            user.outlet_id = outlet
        if user.password_hash is None and seed_password:
            user.password_hash = hash_password(seed_password)


def seed(demo_only: bool = False) -> None:
    data_dir, is_demo = select_dataset(demo_only=demo_only)
    outlets = rows("outlets.csv", {"outlet_id", "brand", "district", "depot", "dock_type", "parking_constraint", "mall_window", "window_open_time", "window_close_time"}, data_dir)
    vehicles = rows("vehicles.csv", {"vehicle_id", "type", "temp", "weight_cap_kg", "volume_cap_m3", "fuel_type", "km_per_l", "weekly_fuel_quota_l", "depot"}, data_dir)
    if is_demo:
        if {"DEMO-OUT001", "DEMO-OUT015", "DEMO-OUT021"} - {row["outlet_id"] for row in outlets}:
            raise RuntimeError("Synthetic demo outlet fixtures are incomplete")
        if len(vehicles) != 4:
            raise RuntimeError("Synthetic demo vehicle fixture count mismatch (expected 4)")
        print("Seeding clearly labeled synthetic development data.")
    elif len(outlets) != 120 or len(vehicles) != 60:
        raise RuntimeError("Official dataset count mismatch (expected 120 outlets and 60 vehicles)")
    session = get_session_factory()()
    try:
        for code, name in [("STORE_MANAGER", "Store Manager"), ("DISPATCHER", "Dispatcher"), ("LOADER", "Loader"), ("DRIVER", "Driver")]:
            if not session.scalar(select(Role).where(Role.code == code)): session.add(Role(code=code, name=name))
        for code, name in [("Peliyagoda", "Peliyagoda"), ("Kandy", "Kandy")]:
            if not session.get(Depot, code): session.add(Depot(code=code, name=name))
        session.flush()
        for row in outlets:
            values = {
                "brand": row["brand"].upper(), "district": row["district"],
                "depot_code": row["depot"], "dock_type": row["dock_type"].upper(),
                "parking_constraint": row["parking_constraint"].upper(),
                "mall_window": row["mall_window"] or None,
                "window_open_time": row["window_open_time"] or None,
                "window_close_time": row["window_close_time"] or None,
            }
            outlet = session.get(Outlet, row["outlet_id"])
            if outlet is None:
                session.add(Outlet(outlet_id=row["outlet_id"], **values))
            elif is_demo:
                for key, value in values.items():
                    setattr(outlet, key, value)
        for row in vehicles:
            values = {
                "type": row["type"].upper(), "temp": row["temp"].upper(),
                "weight_cap_kg": float(row["weight_cap_kg"]),
                "volume_cap_m3": float(row["volume_cap_m3"]),
                "fuel_type": row["fuel_type"], "km_per_l": float(row["km_per_l"]),
                "weekly_fuel_quota_l": float(row["weekly_fuel_quota_l"]),
                "depot_code": row["depot"],
            }
            vehicle = session.get(Vehicle, row["vehicle_id"])
            if vehicle is None:
                session.add(Vehicle(vehicle_id=row["vehicle_id"], **values))
            elif is_demo:
                for key, value in values.items():
                    setattr(vehicle, key, value)
        session.flush()
        roles = {role.code: role.id for role in session.scalars(select(Role)).all()}
        settings: Settings = get_settings()
        seed_password = settings.dev_seed_password if settings.app_env.lower() == "development" else None
        outlet_ids = {row["outlet_id"] for row in outlets}
        default_outlet_id = "DEMO-OUT001" if is_demo else outlets[0]["outlet_id"]
        _ensure_development_users(session, roles, default_outlet_id, seed_password)
        for reference, official_outlet_id, demo_outlet_id, temperature, units, weight, volume in DEMO_ORDERS:
            outlet_id = demo_outlet_id if is_demo else official_outlet_id
            if outlet_id not in outlet_ids:
                continue
            existing_demo_order = session.scalar(select(Order).where(Order.reference == reference))
            if existing_demo_order is None:
                session.add(Order(reference=reference, outlet_id=outlet_id, requested_delivery_date=DEMO_FND03_ORDER_DATE if is_demo else DEMO_PLANNING_DATE, temperature_requirement=temperature, units=units, weight_kg=weight, volume_m3=volume, status="CONFIRMED", notes="Deterministic FND-03 development fixture"))
            elif is_demo and existing_demo_order.notes == "Deterministic FND-03 development fixture":
                # Keep the store-order smoke fixtures separate from the seven-order
                # Task 2B scenario so each planning run can account for all orders.
                existing_demo_order.requested_delivery_date = DEMO_FND03_ORDER_DATE
        if is_demo:
            planning_data = load_planning_reference_data(data_dir, "PEAK-DAY-01")
            for row in planning_data.orders:
                if row["outlet_id"] not in outlet_ids:
                    raise RuntimeError(f"Planning fixture refers to unknown outlet {row['outlet_id']}")
                if not session.scalar(select(Order).where(Order.reference == row["order_ref"])):
                    session.add(Order(
                        reference=row["order_ref"], outlet_id=row["outlet_id"],
                        requested_delivery_date=planning_data.planning_date,
                        temperature_requirement=row["temp_requirement"].upper(),
                        units=row["units"], weight_kg=row["weight_kg"], volume_m3=row["volume_m3"],
                        status="CONFIRMED", notes="Synthetic Task 2B peak-day planning fixture",
                    ))
        if not session.scalar(select(PlanningRun).where(PlanningRun.planning_date == DEMO_PLANNING_DATE, PlanningRun.snapshot_hash == "demo-2026-03-16")):
            session.add(PlanningRun(planning_date=DEMO_PLANNING_DATE, snapshot_hash="demo-2026-03-16", status="DRAFT", runtime_metadata={"fixture": "FND-03"}))
        session.commit()
    except Exception:
        session.rollback(); raise
    finally: session.close()


if __name__ == "__main__":
    import sys

    if sys.argv[1:] == ["--bootstrap-only"]:
        seed_development_accounts()
    elif sys.argv[1:] == ["--demo-only"]:
        seed(demo_only=True)
    elif not sys.argv[1:]:
        seed()
    else:
        raise SystemExit("Usage: python -m app.seed [--bootstrap-only]")
