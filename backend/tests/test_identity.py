from datetime import UTC, datetime, timedelta
from importlib.util import find_spec
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import get_db_session
from app.infrastructure.persistence import AuthSession, Base, Role, User
from app.modules.identity.routes import Principal, get_current_principal, require_roles
from app.modules.identity.security import hash_bearer_token, hash_password, verify_password
from app.main import app


@pytest.fixture
def identity_session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False, autocommit=False)
    engine.dispose()


@pytest.fixture
def client(identity_session_factory):
    def override_db_session():
        session = identity_session_factory()
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
def store_user(identity_session_factory):
    with identity_session_factory() as session:
        role = Role(code="STORE_MANAGER", name="Store Manager")
        session.add(role)
        session.flush()
        user = User(
            id=uuid4(),
            email="store.manager@example.test",
            display_name="Store Manager",
            active=True,
            role_id=role.id,
            outlet_id="OUT001",
            password_hash=hash_password("correct-horse-battery-staple"),
        )
        session.add(user)
        session.commit()
        return user.id


def test_password_hash_is_salted_and_verifies() -> None:
    first = hash_password("secure-password")
    second = hash_password("secure-password")

    assert first != second
    assert verify_password("secure-password", first)
    assert not verify_password("wrong-password", first)
    assert not verify_password("secure-password", None)


def test_login_returns_public_profile_and_opaque_bearer_token(client, store_user) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "STORE.MANAGER@example.test", "password": "correct-horse-battery-staple"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["user"] == {
        "id": str(store_user),
        "email": "store.manager@example.test",
        "display_name": "Store Manager",
        "role": "STORE",
        "outlet_id": "OUT001",
        "depot_code": None,
    }
    assert "password" not in response.text


def test_login_rejects_client_supplied_role(client, store_user) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "store.manager@example.test",
            "password": "correct-horse-battery-staple",
            "role": "DISPATCHER",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_invalid_login_does_not_disclose_unknown_email(client, store_user) -> None:
    known_user = client.post(
        "/api/v1/auth/login",
        json={"email": "store.manager@example.test", "password": "wrong-password"},
    )
    unknown_user = client.post(
        "/api/v1/auth/login",
        json={"email": "missing@example.test", "password": "wrong-password"},
    )

    assert known_user.status_code == unknown_user.status_code == 401
    assert known_user.json() == unknown_user.json()


def test_me_requires_authentication_and_errors_follow_api_contract(client) -> None:
    unauthenticated = client.get("/api/v1/auth/me")
    invalid_body = client.post("/api/v1/auth/login", json={"email": "bad", "password": ""})

    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["detail"]["code"] == "AUTHENTICATION_REQUIRED"
    assert invalid_body.status_code == 422
    assert invalid_body.json()["detail"]["code"] == "VALIDATION_ERROR"
    assert invalid_body.json()["detail"]["fields"]


def test_session_me_and_logout_revoke_bearer_token(client, store_user):
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "store.manager@example.test", "password": "correct-horse-battery-staple"},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/api/v1/auth/me", headers=headers).json()["id"] == str(store_user)
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    rejected = client.get("/api/v1/auth/me", headers=headers)
    assert rejected.status_code == 401
    assert rejected.json()["detail"]["code"] == "INVALID_TOKEN"


def test_expired_session_is_rejected(client, identity_session_factory, store_user):
    token = "expired-test-token"
    with identity_session_factory() as session:
        session.add(
            AuthSession(
                user_id=store_user,
                token_hash=hash_bearer_token(token),
                expires_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
        session.commit()

    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "INVALID_TOKEN"


@pytest.mark.parametrize(
    ("role", "allowed_roles", "expected_status"),
    [
        ("STORE", ("DISPATCHER",), 403),
        ("DISPATCHER", ("DISPATCHER",), 200),
        ("LOADER", ("LOADER",), 200),
        ("DRIVER", ("DRIVER",), 200),
        ("DISPATCHER", ("DRIVER",), 403),
    ],
)
def test_role_guards_enforce_operation_permissions(identity_session_factory, store_user, role, allowed_roles, expected_status):
    with identity_session_factory() as session:
        user = session.get(User, store_user)
        auth_session = AuthSession(user_id=user.id, token_hash="x" * 64, expires_at=datetime.now(UTC))
        principal = Principal(user=user, role=role, session=auth_session)

    protected = FastAPI()
    protected.dependency_overrides[get_current_principal] = lambda: principal

    @protected.get("/protected")
    def protected_route(_=Depends(require_roles(*allowed_roles))):
        return {"ok": True}

    backend_options = {"use_uvloop": True} if find_spec("uvloop") else {}
    response = TestClient(protected, backend_options=backend_options).get("/protected")

    assert response.status_code == expected_status
    if expected_status == 403:
        assert response.json()["detail"]["code"] == "FORBIDDEN"
