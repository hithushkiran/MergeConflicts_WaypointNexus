from datetime import date
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.infrastructure.persistence import Base, Depot, Order, Outlet, PlanningRun, Vehicle
from app.modules.planning.snapshot import build_planning_snapshot, create_snapshot, persist_planning_snapshot


def sample_inputs():
    return {
        "orders": [
            {"id": "2", "reference": "ORD-2", "weight_kg": 4.0},
            {"id": "1", "reference": "ORD-1", "weight_kg": 2.0},
        ],
        "outlets": [{"outlet_id": "OUT001", "depot_code": "DEPOT-A"}],
        "vehicles": [{"vehicle_id": "VEH001", "weight_cap_kg": 20.0}],
        "depots": [{"code": "DEPOT-A", "name": "Depot A"}],
    }


def test_snapshot_digest_is_stable_across_input_order():
    first = sample_inputs()
    second = {key: list(reversed(value)) for key, value in first.items()}

    first_snapshot = create_snapshot(date(2026, 10, 4), **first)
    second_snapshot = create_snapshot(date(2026, 10, 4), **second)

    assert first_snapshot.digest == second_snapshot.digest
    assert first_snapshot.payload == second_snapshot.payload


def test_snapshot_digest_changes_when_a_planning_input_changes():
    first = sample_inputs()
    changed = sample_inputs()
    changed["vehicles"][0]["weight_cap_kg"] = 19.0

    assert create_snapshot(date(2026, 10, 4), **first).digest != create_snapshot(date(2026, 10, 4), **changed).digest


def test_snapshot_identifies_missing_availability_and_travel_inputs():
    snapshot = create_snapshot(date(2026, 10, 4), **sample_inputs())

    unavailable = {item["input"]: item["reason"] for item in snapshot.payload["unavailable_inputs"]}
    assert unavailable == {
        "vehicle_availability": "NO_AVAILABILITY_SCHEDULE",
        "operating_calendar": "NO_OPERATING_DAY_FLAG",
        "weekly_fuel_used": "NO_WEEKLY_FUEL_USAGE",
        "travel_service_data": "NO_DISTANCE_OR_SERVICE_TIME_DATA",
    }


def test_database_snapshot_persists_deterministically_and_reuses_same_run():
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            session.add(Depot(code="DEPOT-A", name="Depot A"))
            session.add(Outlet(
                outlet_id="OUT001", brand="FRESH", district="Colombo", depot_code="DEPOT-A",
                dock_type="STANDARD", parking_constraint="NONE",
            ))
            session.flush()
            session.add(Vehicle(
                vehicle_id="VEH001", type="VAN", temp="AMBIENT", weight_cap_kg=100,
                volume_cap_m3=4, fuel_type="DIESEL", km_per_l=8, weekly_fuel_quota_l=250,
                depot_code="DEPOT-A",
            ))
            session.add(Order(
                id=uuid4(), reference="ORD-1", outlet_id="OUT001",
                requested_delivery_date=date(2026, 10, 4), temperature_requirement="AMBIENT",
                units=4, weight_kg=20, volume_m3=1, status="CONFIRMED",
            ))
            session.commit()

            first_snapshot = build_planning_snapshot(session, date(2026, 10, 4))
            first_run = persist_planning_snapshot(session, first_snapshot)
            second_snapshot = build_planning_snapshot(session, date(2026, 10, 4))
            second_run = persist_planning_snapshot(session, second_snapshot)
            runs = session.scalars(select(PlanningRun)).all()

            assert first_run.id == second_run.id
            assert first_run.snapshot_hash == first_snapshot.digest
            assert first_snapshot.payload["orders"][0]["reference"] == "ORD-1"
            assert len(runs) == 1
            planning_context_snapshot = build_planning_snapshot(session, date(2026, 3, 16))
            context = planning_context_snapshot.payload["planning_context"]
            assert context[0]["scenario"] == "PEAK-DAY-01"
            assert context[0]["is_operating_day"] is True
            assert context[0]["vehicles"][0]["weekly_fuel_used_l"] == 238
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
