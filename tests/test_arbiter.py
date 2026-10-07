from fastapi.testclient import TestClient

from arbiter.app.config import settings
from arbiter.app.main import app


def test_arbiter_health(tmp_path, monkeypatch):
    db_path = tmp_path / "arbiter.db"
    monkeypatch.setattr(settings, "arbiter_db_path", str(db_path))

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200

    body = response.json()

    assert body["status"] == "ok"
    assert body["service"] == "arbiter"
    assert body["node_id"] == "C"


def test_initial_cluster_status(tmp_path, monkeypatch):
    db_path = tmp_path / "arbiter.db"
    monkeypatch.setattr(settings, "arbiter_db_path", str(db_path))

    with TestClient(app) as client:
        response = client.get("/cluster/status")

    assert response.status_code == 200

    body = response.json()

    assert body["leader_id"] is None
    assert body["epoch"] == 0
    assert body["lease_expires_at"] is None
    assert body["lease_valid"] is False