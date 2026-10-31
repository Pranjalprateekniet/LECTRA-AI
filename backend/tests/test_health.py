"""Tests for backend API and health endpoints."""

from fastapi.testclient import TestClient
from lectra_backend.main import create_app
from lectra_core.config import Settings
from lectra_core.db.session import init_db


def test_root_endpoint(tmp_path):
    """Verify root / endpoint returns metadata."""
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/test_api.db",
        data_dir=tmp_path,
    )
    init_db(settings=settings)
    app = create_app(settings=settings)
    client = TestClient(app)

    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Revision RAG API"
    assert "health" in data


def test_health_endpoint(tmp_path):
    """Verify /api/v1/health returns healthy status."""
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/test_health.db",
        data_dir=tmp_path,
        environment="testing",
    )
    init_db(settings=settings)
    app = create_app(settings=settings)
    client = TestClient(app)

    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["environment"] == "testing"
    assert data["database"] == "connected"
    assert data["execution_device"] == "cpu"
    assert "components" in data
