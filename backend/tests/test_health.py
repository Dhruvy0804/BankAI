from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.main import create_app


def client(probe):
    return TestClient(create_app(Settings(_env_file=None, app_env="test"), probe))


def test_health_does_not_depend_on_database():
    def unavailable():
        raise SQLAlchemyError("secret connection details")

    with client(unavailable) as api:
        response = api.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.headers["x-request-id"]


def test_readiness_succeeds_after_probe():
    probes = []
    with client(lambda: probes.append(True)) as api:
        assert api.get("/ready").json() == {"status": "ready", "database": "connected"}
    assert probes == [True]


def test_readiness_failure_is_sanitized_and_traceable():
    def unavailable():
        raise SQLAlchemyError("postgres://user:secret@host")

    with client(unavailable) as api:
        response = api.get("/ready")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
        assert response.json()["error"]["request_id"] == response.headers["x-request-id"]
        assert "secret" not in response.text


def test_cors_allows_only_configured_origin():
    with client(lambda: None) as api:
        allowed = api.get("/health", headers={"Origin": "http://localhost:5173"})
        denied = api.get("/health", headers={"Origin": "https://untrusted.example"})
        assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
        assert "access-control-allow-origin" not in denied.headers
