from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.infrastructure.persistence import Base, Deferral, Depot, Order, Outlet, PlanVersion, PlanningRun, Trip, TripStop, Vehicle
from app.modules.planning.allocation import allocate_scenario, persist_scenario_allocation
from app.modules.planning.reference_data import load_planning_reference_data


DEMO_DATA = Path(__file__).parents[1] / "demo-data"


def test_scenario_allocation_enforces_two_trips_and_emits_checker_rows():
    reference_data = load_planning_reference_data(DEMO_DATA, "PEAK-DAY-01")
    result = allocate_scenario(reference_data)

    assert result.status == "OPTIMAL"
    assert result.diagnostics == ()
    assert len(result.rows) == len(reference_data.orders)
    assert {row["decision"] for row in result.rows} == {"served", "deferred"}
    served = [row for row in result.rows if row["decision"] == "served"]
    assert all(row["vehicle_id"] and row["trip_id"] in {1, 2} for row in served)
    assert any(row["vehicle_id"] == "DEMO-VEH001" and row["trip_id"] == 2 for row in served)

    by_trip = {}
    orders = {row["order_ref"]: row for row in reference_data.orders}
    for row in served:
        by_trip.setdefault((row["vehicle_id"], row["trip_id"]), []).append(orders[row["order_ref"]])
    for trip_orders in by_trip.values():
        assert len({row["depot"] for row in trip_orders}) == 1
        assert len({row["brand"] for row in trip_orders}) == 1
        assert len({row["district"] for row in trip_orders}) == 1


def test_non_operating_calendar_date_defers_every_order():
    reference_data = load_planning_reference_data(DEMO_DATA, "PEAK-DAY-01")
    result = allocate_scenario(replace(reference_data, is_operating_day=False))
    assert result.status == "NOT_OPERATING_DAY"
    assert all(row["reasons"] == ["NON_OPERATING_DAY"] for row in result.rows)


def test_weekly_fuel_already_consumed_can_make_candidate_ineligible():
    reference_data = load_planning_reference_data(DEMO_DATA, "PEAK-DAY-01")
    vehicles = tuple(
        {**vehicle, "weekly_fuel_used_l": 299}
        if vehicle["vehicle_id"] == "DEMO-VEH003" else vehicle
        for vehicle in reference_data.vehicles
    )
    result = allocate_scenario(replace(reference_data, vehicles=vehicles))
    chilled = next(row for row in result.rows if row["order_ref"] == "PEAK-ORD-001")
    assert chilled["decision"] == "deferred"
    assert "FUEL_QUOTA_EXCEEDED" in chilled["reasons"]


def test_scenario_candidate_persists_plan_trips_stops_and_deferrals_atomically():
    reference_data = load_planning_reference_data(DEMO_DATA, "PEAK-DAY-01")
    result = allocate_scenario(reference_data)
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            session.add_all([Depot(code="Peliyagoda", name="Peliyagoda"),
                             Depot(code="Kandy", name="Kandy")])
            session.flush()
            outlet_rows = {row["outlet_id"]: row for row in reference_data.orders}
            for outlet_id, row in outlet_rows.items():
                session.add(Outlet(
                    outlet_id=outlet_id, brand=row["brand"].upper(), district=row["district"],
                    depot_code=row["depot"], dock_type=row["dock_type"],
                    parking_constraint=row["parking_constraint"],
                    window_open_time=row["window_open_time"] or None,
                    window_close_time=row["window_close_time"] or None,
                ))
            for row in reference_data.vehicles:
                session.add(Vehicle(
                    vehicle_id=row["vehicle_id"], type=row["type"].upper(),
                    temp=row["temp"].upper(), weight_cap_kg=row["weight_cap_kg"],
                    volume_cap_m3=row["volume_cap_m3"], fuel_type=row["fuel_type"],
                    km_per_l=row["km_per_l"], weekly_fuel_quota_l=row["weekly_fuel_quota_l"],
                    depot_code=row["depot_code"],
                ))
            for row in reference_data.orders:
                session.add(Order(
                    id=uuid4(), reference=row["order_ref"], outlet_id=row["outlet_id"],
                    requested_delivery_date=reference_data.planning_date,
                    temperature_requirement=row["temp_requirement"].upper(), units=row["units"],
                    weight_kg=row["weight_kg"], volume_m3=row["volume_m3"], status="CONFIRMED",
                ))
            planning_run = PlanningRun(
                planning_date=reference_data.planning_date,
                snapshot_hash="synthetic-peak-day-test", status="SNAPSHOT", runtime_metadata={},
            )
            session.add(planning_run)
            session.commit()

            version = persist_scenario_allocation(session, planning_run, result)

            assert version.status == "DRAFT"
            assert version.input_digest == planning_run.snapshot_hash
            assert len(session.scalars(select(Trip)).all()) == len(result.trips)
            assert len(session.scalars(select(TripStop)).all()) == sum(len(t["stops"]) for t in result.trips)
            assert len(session.scalars(select(Deferral)).all()) == 1
            assert len(session.scalars(select(PlanVersion)).all()) == 1
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
