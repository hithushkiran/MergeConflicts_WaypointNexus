from importlib.util import find_spec

from fastapi.testclient import TestClient

from app.main import app


def make_test_client() -> TestClient:
    # The local Python runtime's default asyncio selector can leave Starlette's
    # cross-thread TestClient portal asleep. Use uvloop when installed (it is
    # already part of uvicorn[standard]); retain the default on platforms
    # where uvloop is unavailable, such as Windows.
    backend_options = {"use_uvloop": True} if find_spec("uvloop") else {}
    return TestClient(app, backend_options=backend_options)


def test_health_check_returns_ok() -> None:
    response = make_test_client().get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_check_returns_ready_when_database_is_available(monkeypatch) -> None:
    monkeypatch.setattr("app.main.database_is_available", lambda: True)

    response = make_test_client().get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}


def test_readiness_check_hides_database_connection_details_when_unavailable(monkeypatch) -> None:
    monkeypatch.setattr("app.main.database_is_available", lambda: False)

    response = make_test_client().get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "database": "unavailable"}
    assert "postgresql" not in response.text.lower()
    assert "password" not in response.text.lower()
