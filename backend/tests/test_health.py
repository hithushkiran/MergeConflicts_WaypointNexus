from fastapi.testclient import TestClient

from app.main import app


def test_health_check_returns_ok() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_check_returns_ready_when_database_is_available(monkeypatch) -> None:
    monkeypatch.setattr("app.main.database_is_available", lambda: True)

    response = TestClient(app).get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}


def test_readiness_check_hides_database_connection_details_when_unavailable(monkeypatch) -> None:
    monkeypatch.setattr("app.main.database_is_available", lambda: False)

    response = TestClient(app).get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "database": "unavailable"}
    assert "postgresql" not in response.text.lower()
    assert "password" not in response.text.lower()
