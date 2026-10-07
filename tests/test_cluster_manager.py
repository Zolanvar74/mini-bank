from fastapi.testclient import TestClient

from server.app.core.config import settings
from server.app.main import app


def test_cluster_status_when_cluster_disabled(
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "cluster_enabled",
        False,
    )

    monkeypatch.setattr(
        settings,
        "auto_acquire_enabled",
        False,
    )

    with TestClient(app) as client:
        response = client.get(
            "/cluster/local-status"
        )

    assert response.status_code == 200

    body = response.json()

    assert body["role"] == "DISABLED"
    assert body["epoch"] is None
    assert body["lease_valid"] is False