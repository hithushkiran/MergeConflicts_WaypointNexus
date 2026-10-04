from datetime import UTC, date, datetime, timedelta
from importlib.util import find_spec
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import get_db_session
from app.infrastructure.persistence import Base, Depot, IdempotencyRecord, Order, Outlet, Role, User
from app.main import app
from app.modules.identity.security import hash_password
from app.modules.orders.service import calculate_order_timing


@pytest.fixture
def order_session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False, autocommit=False)
    engine.dispose()


@pytest.fixture
def order_client(order_session_factory):
    def override_db_session():
        session = order_session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_db_session
    backend_options = {"use_uvloop": True} if find_spec("uvloop") else {}
    with TestClient(app, backend_options=backend_options) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def order_accounts(order_session_factory):
    with order_session_factory() as session:
        session.add(Depot(code="Peliyagoda", name="Peliyagoda"))
        session.add_all([
            Outlet(outlet_id="OUT001", brand="FRESH", district="Colombo", depot_code="Peliyagoda", dock_type="STANDARD", parking_constraint="NONE"),
            Outlet(outlet_id="OUT002", brand="STYLE", district="Colombo", depot_code="Peliyagoda", dock_type="STANDARD", parking_constraint="NONE"),
        ])
        store_role = Role(code="STORE_MANAGER", name="Store Manager")
        dispatcher_role = Role(code="DISPATCHER", name="Dispatcher")
        session.add_all([store_role, dispatcher_role])
        session.flush()
        store = User(
            id=uuid4(), email="store@example.test", display_name="Store", active=True,
            role_id=store_role.id, outlet_id="OUT001", password_hash=hash_password("store-password"),
        )
        out_of_scope_store = User(
            id=uuid4(), email="other-store@example.test", display_name="Other Store", active=True,
            role_id=store_role.id, outlet_id="OUT002", password_hash=hash_password("store-password"),
        )
        unscoped_store = User(
            id=uuid4(), email="unscoped@example.test", display_name="Unscoped Store", active=True,
            role_id=store_role.id, outlet_id=None, password_hash=hash_password("store-password"),
        )
        dispatcher = User(
            id=uuid4(), email="dispatcher@example.test", display_name="Dispatcher", active=True,
            role_id=dispatcher_role.id, password_hash=hash_password("store-password"),
        )
        session.add_all([store, out_of_scope_store, unscoped_store, dispatcher])
        session.commit()
        return {"store": store.id, "other_store": out_of_scope_store.id, "unscoped": unscoped_store.id}


def login(client: TestClient, email: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": "store-password"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def valid_order_body(client: TestClient, headers: dict[str, str]) -> dict:
    eligibility = client.get("/api/v1/store/orders/eligibility", headers=headers)
    assert eligibility.status_code == 200
    return {
        "requested_delivery_date": eligibility.json()["next_eligible_delivery_date"],
        "temperature_requirement": "AMBIENT",
        "units": 12,
        "weight_kg": 25.5,
        "volume_m3": 0.8,
        "notes": "Call on arrival",
    }


def test_store_can_create_and_list_its_persisted_orders(order_client, order_accounts):
    headers = login(order_client, "store@example.test")
    body = valid_order_body(order_client, headers)

    created = order_client.post(
        "/api/v1/store/orders", json=body, headers={**headers, "Idempotency-Key": "create-order-1"}
    )
    listed = order_client.get("/api/v1/store/orders", headers=headers)

    assert created.status_code == 201
    assert created.json()["status"] == "CONFIRMED"
    assert created.json()["outlet_id"] == "OUT001"
    assert created.json()["requested_delivery_date"] == body["requested_delivery_date"]
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [created.json()["id"]]


def test_order_create_idempotency_replays_the_original_order(order_client, order_accounts, order_session_factory):
    headers = login(order_client, "store@example.test")
    body = valid_order_body(order_client, headers)
    headers_with_key = {**headers, "Idempotency-Key": "retry-order-1"}

    first = order_client.post("/api/v1/store/orders", json=body, headers=headers_with_key)
    replay = order_client.post("/api/v1/store/orders", json=body, headers=headers_with_key)
    with order_session_factory() as session:
        orders = session.scalars(select(Order)).all()
        records = session.scalars(select(IdempotencyRecord)).all()

    assert first.status_code == replay.status_code == 201
    assert first.json() == replay.json()
    assert len(orders) == len(records) == 1


def test_reusing_order_idempotency_key_with_different_body_conflicts(order_client, order_accounts):
    headers = login(order_client, "store@example.test")
    body = valid_order_body(order_client, headers)
    key_headers = {**headers, "Idempotency-Key": "same-key"}
    first = order_client.post("/api/v1/store/orders", json=body, headers=key_headers)
    changed = {**body, "units": 13}

    conflict = order_client.post("/api/v1/store/orders", json=changed, headers=key_headers)

    assert first.status_code == 201
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_store_orders_are_outlet_scoped_and_non_store_roles_are_denied(order_client, order_accounts, order_session_factory):
    with order_session_factory() as session:
        session.add(Order(
            reference="WN-OTHER-ORDER", outlet_id="OUT002", requested_delivery_date=date(2026, 10, 10),
            temperature_requirement="AMBIENT", units=1, weight_kg=1, volume_m3=1, status="CONFIRMED",
        ))
        session.commit()

    own_store = login(order_client, "store@example.test")
    other_store = login(order_client, "other-store@example.test")
    dispatcher = login(order_client, "dispatcher@example.test")
    own_list = order_client.get("/api/v1/store/orders", headers=own_store)
    other_list = order_client.get("/api/v1/store/orders", headers=other_store)
    denied = order_client.get("/api/v1/store/orders", headers=dispatcher)

    assert own_list.json()["items"] == []
    assert [item["reference"] for item in other_list.json()["items"]] == ["WN-OTHER-ORDER"]
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "FORBIDDEN"


def test_store_without_outlet_scope_cannot_read_or_create_orders(order_client, order_accounts):
    headers = login(order_client, "unscoped@example.test")

    response = order_client.get("/api/v1/store/orders", headers=headers)
    create_response = order_client.post(
        "/api/v1/store/orders",
        json={
            "requested_delivery_date": "2026-10-10",
            "temperature_requirement": "AMBIENT",
            "units": 1,
            "weight_kg": 1,
            "volume_m3": 1,
        },
        headers={**headers, "Idempotency-Key": "unscoped-order"},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "STORE_SCOPE_REQUIRED"
    assert create_response.status_code == 403
    assert create_response.json()["detail"]["code"] == "STORE_SCOPE_REQUIRED"


def test_order_validation_rejects_invalid_quantities(order_client, order_accounts):
    headers = login(order_client, "store@example.test")
    body = {**valid_order_body(order_client, headers), "units": 0}

    response = order_client.post(
        "/api/v1/store/orders", json=body, headers={**headers, "Idempotency-Key": "invalid-order"}
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_store_cannot_choose_another_outlet_or_submit_an_ineligible_date(order_client, order_accounts):
    headers = login(order_client, "store@example.test")
    body = valid_order_body(order_client, headers)
    payload_with_outlet = {**body, "outlet_id": "OUT002"}
    invalid_contract = order_client.post(
        "/api/v1/store/orders",
        json=payload_with_outlet,
        headers={**headers, "Idempotency-Key": "outlet-override"},
    )
    too_early = order_client.post(
        "/api/v1/store/orders",
        json={**body, "requested_delivery_date": (date.today() - timedelta(days=1)).isoformat()},
        headers={**headers, "Idempotency-Key": "date-too-early"},
    )

    assert invalid_contract.status_code == 422
    assert invalid_contract.json()["detail"]["code"] == "VALIDATION_ERROR"
    assert too_early.status_code == 422
    assert too_early.json()["detail"]["code"] == "ORDER_DATE_TOO_SOON"


def test_order_timing_uses_colombo_cutoff_and_next_calendar_date():
    before_cutoff = datetime(2026, 10, 4, 9, 59, tzinfo=UTC)  # 15:29 Colombo
    after_cutoff = datetime(2026, 10, 4, 10, 1, tzinfo=UTC)  # 15:31 Colombo

    early = calculate_order_timing(datetime.strptime("16:00", "%H:%M").time(), before_cutoff)
    late = calculate_order_timing(datetime.strptime("15:00", "%H:%M").time(), after_cutoff)

    assert early.next_eligible_delivery_date.isoformat() == "2026-10-04"
    assert not early.late_order
    assert late.next_eligible_delivery_date.isoformat() == "2026-10-05"
    assert late.late_order
