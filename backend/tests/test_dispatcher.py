from datetime import date
from importlib.util import find_spec
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import get_db_session
from app.infrastructure.persistence import AuditEvent, Base, Deferral, Depot, Order, Outlet, PlanVersion, Role, Trip, User, Vehicle
from app.main import app
from app.modules.identity.security import hash_password
from app.modules.planning.reference_data import load_planning_reference_data


DEMO_DATA = Path(__file__).parents[1] / "demo-data"
PLANNING_DATE = date(2026, 3, 16)


@pytest.fixture
def dispatcher_factory(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setenv("PLANNING_DATA_DIR", str(DEMO_DATA))
    monkeypatch.setenv("APP_ENV", "development")

    def override_db_session():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_db_session
    planner_backend = {"use_uvloop": True} if find_spec("uvloop") else {}
    with TestClient(app, backend_options=planner_backend) as client:
        with factory() as session:
            for code in {"Peliyagoda", "Kandy"}:
                session.add(Depot(code=code, name=code))
            data = load_planning_reference_data(DEMO_DATA, "PEAK-DAY-01")
            outlet_rows = {row["outlet_id"]: row for row in data.orders}
            for row in outlet_rows.values():
                session.add(Outlet(
                    outlet_id=row["outlet_id"], brand=row["brand"], district=row["district"],
                    depot_code=row["depot"], dock_type=row["dock_type"],
                    parking_constraint=row["parking_constraint"],
                    mall_window="City Mall" if row["parking_constraint"] == "van_only" else None,
                    window_open_time=row["window_open_time"], window_close_time=row["window_close_time"],
                ))
            for row in data.orders:
                session.add(Order(
                    reference=row["order_ref"], outlet_id=row["outlet_id"],
                    requested_delivery_date=PLANNING_DATE,
                    temperature_requirement=row["temp_requirement"].upper(), units=row["units"],
                    weight_kg=row["weight_kg"], volume_m3=row["volume_m3"], status="CONFIRMED",
                ))
            for row in data.vehicles:
                session.add(Vehicle(
                    vehicle_id=row["vehicle_id"], type=row["type"].upper(), temp=row["temp"].upper(),
                    weight_cap_kg=row["weight_cap_kg"], volume_cap_m3=row["volume_cap_m3"],
                    fuel_type=row["fuel_type"], km_per_l=row["km_per_l"],
                    weekly_fuel_quota_l=row["weekly_fuel_quota_l"], depot_code=row["depot_code"],
                ))
            role = Role(code="DISPATCHER", name="Dispatcher")
            store_role = Role(code="STORE_MANAGER", name="Store Manager")
            session.add_all([role, store_role])
            session.flush()
            session.add_all([
                User(email="dispatcher@test.local", display_name="Dispatcher", active=True,
                     role_id=role.id, password_hash=hash_password("test-password")),
                User(email="store@test.local", display_name="Store", active=True,
                     role_id=store_role.id, outlet_id=data.orders[0]["outlet_id"],
                     password_hash=hash_password("test-password")),
            ])
            session.commit()
        yield client, factory
    app.dependency_overrides.clear()
    engine.dispose()


def auth(client, email="dispatcher@test.local"):
    result = client.post("/api/v1/auth/login", json={"email": email, "password": "test-password"})
    assert result.status_code == 200
    return {"Authorization": f"Bearer {result.json()['access_token']}"}


def test_dispatcher_queue_is_role_guarded_and_filters_orders(dispatcher_factory):
    client, _factory = dispatcher_factory
    assert client.get("/api/v1/dispatcher/orders").status_code == 401
    store_headers = auth(client, "store@test.local")
    assert client.get("/api/v1/dispatcher/orders", headers=store_headers).status_code == 403

    headers = auth(client)
    response = client.get(
        "/api/v1/dispatcher/orders",
        params={"planning_date": PLANNING_DATE.isoformat(), "brand": "Fresh", "temperature": "CHILLED"},
        headers=headers,
    )
    assert response.status_code == 200
    assert len(response.json()["items"]) == 1
    assert response.json()["items"][0]["temperature_requirement"] == "CHILLED"
    windowed = client.get("/api/v1/dispatcher/orders", params={"delivery_window": "restricted"}, headers=headers)
    assert windowed.status_code == 200
    assert windowed.json()["items"]
    assert all(item["window_open_time"] and item["window_close_time"] for item in windowed.json()["items"])


def test_dispatcher_can_review_and_publish_a_candidate(dispatcher_factory):
    client, factory = dispatcher_factory
    headers = auth(client)
    candidate_key_headers = {**headers, "Idempotency-Key": "candidate-1"}
    candidate = client.post("/api/v1/dispatcher/plans", json={"planning_date": PLANNING_DATE.isoformat()}, headers=candidate_key_headers)
    assert candidate.status_code == 201, candidate.text
    plan = candidate.json()["plan"]
    assert plan["status"] == "DRAFT"
    assert len(plan["orders"]) == 7
    assert plan["trips"]
    assert all(trip["stops"] for trip in plan["trips"])
    assert all("metrics" in trip for trip in plan["trips"])
    replayed_candidate = client.post("/api/v1/dispatcher/plans", json={"planning_date": PLANNING_DATE.isoformat()}, headers=candidate_key_headers)
    assert replayed_candidate.status_code == 201
    assert replayed_candidate.json()["plan"]["id"] == plan["id"]
    reused_candidate_key = client.post("/api/v1/dispatcher/plans", json={"planning_date": "2026-03-17"}, headers=candidate_key_headers)
    assert reused_candidate_key.status_code == 409

    reviewed = client.get(f"/api/v1/dispatcher/plans/{plan['id']}", headers=headers)
    assert reviewed.status_code == 200
    assert reviewed.json()["plan"]["version_number"] == 1
    saved = client.get("/api/v1/dispatcher/plans", params={"planning_date": PLANNING_DATE.isoformat()}, headers=headers)
    assert saved.status_code == 200
    assert [item["id"] for item in saved.json()["items"]] == [plan["id"]]

    published = client.post(
        f"/api/v1/dispatcher/plans/{plan['id']}/publish",
        json={"reason": "Reviewed for dispatch"},
        headers={**headers, "Idempotency-Key": "publish-plan-1"},
    )
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "PUBLISHED"
    assert published.json()["served_orders"] + published.json()["deferred_orders"] == 7
    saved_after_publish = client.get("/api/v1/dispatcher/plans", params={"planning_date": PLANNING_DATE.isoformat()}, headers=headers)
    assert saved_after_publish.json()["items"][0]["status"] == "PUBLISHED"

    replay = client.post(
        f"/api/v1/dispatcher/plans/{plan['id']}/publish",
        json={"reason": "Reviewed for dispatch"},
        headers={**headers, "Idempotency-Key": "publish-plan-1"},
    )
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert client.post(
        f"/api/v1/dispatcher/plans/{plan['id']}/publish",
        json={}, headers={**headers, "Idempotency-Key": "publish-plan-again"},
    ).status_code == 409

    with factory() as session:
        version = session.get(PlanVersion, UUID(plan["id"]))
        assert version.status == "PUBLISHED"
        assert session.scalar(select(AuditEvent).where(AuditEvent.action == "PUBLISHED")) is not None
        assert session.scalar(select(Trip).where(Trip.plan_version_id == version.id, Trip.status != "PLANNED")) is None
        assert session.scalar(select(Order).where(Order.status == "CONFIRMED")) is None


def test_missing_planning_inputs_are_reported_without_persisting_a_candidate(dispatcher_factory, monkeypatch):
    client, factory = dispatcher_factory
    headers = auth(client)
    monkeypatch.setenv("PLANNING_DATA_DIR", str(Path("/definitely/missing")))
    monkeypatch.setenv("APP_ENV", "production")
    response = client.post("/api/v1/dispatcher/plans", json={"planning_date": PLANNING_DATE.isoformat()}, headers={**headers, "Idempotency-Key": "missing-inputs"})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "PLANNING_INPUTS_UNAVAILABLE"
    with factory() as session:
        assert session.scalar(select(PlanVersion)) is None


def test_candidate_refuses_to_omit_confirmed_orders_on_the_planning_date(dispatcher_factory):
    client, factory = dispatcher_factory
    with factory() as session:
        outlet = session.scalar(select(Outlet))
        session.add(Order(
            reference="UNMODELED-ORDER", outlet_id=outlet.outlet_id,
            requested_delivery_date=PLANNING_DATE, temperature_requirement="AMBIENT",
            units=1, weight_kg=1, volume_m3=0.1, status="CONFIRMED",
        ))
        session.commit()

    response = client.post(
        "/api/v1/dispatcher/plans", json={"planning_date": PLANNING_DATE.isoformat()},
        headers={**auth(client), "Idempotency-Key": "coverage-mismatch"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "SCENARIO_ORDER_COVERAGE_MISMATCH"
    with factory() as session:
        assert session.scalar(select(PlanVersion)) is None
