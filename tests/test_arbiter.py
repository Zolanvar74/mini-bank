import time

from fastapi.testclient import TestClient

from arbiter.app.config import settings
from arbiter.app.database import get_connection
from arbiter.app.main import app


def test_arbiter_health(tmp_path, monkeypatch):
    db_path = tmp_path / "arbiter.db"

    monkeypatch.setattr(
        settings,
        "arbiter_db_path",
        str(db_path),
    )

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200

    body = response.json()

    assert body["status"] == "ok"
    assert body["service"] == "arbiter"
    assert body["node_id"] == "C"


def test_initial_cluster_status(tmp_path, monkeypatch):
    db_path = tmp_path / "arbiter.db"

    monkeypatch.setattr(
        settings,
        "arbiter_db_path",
        str(db_path),
    )

    with TestClient(app) as client:
        response = client.get("/cluster/status")

    assert response.status_code == 200

    body = response.json()

    assert body["leader_id"] is None
    assert body["epoch"] == 0
    assert body["lease_expires_at"] is None
    assert body["lease_valid"] is False


def test_node_a_can_acquire_leadership(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "arbiter.db"

    monkeypatch.setattr(
        settings,
        "arbiter_db_path",
        str(db_path),
    )

    with TestClient(app) as client:
        response = client.post(
            "/cluster/acquire",
            json={"node_id": "A"},
        )

        assert response.status_code == 200

        body = response.json()

        assert body["status"] == "success"
        assert body["leader_id"] == "A"
        assert body["epoch"] == 1

        status_response = client.get(
            "/cluster/status"
        )

        status = status_response.json()

        assert status["leader_id"] == "A"
        assert status["epoch"] == 1
        assert status["lease_valid"] is True


def test_second_node_cannot_acquire_valid_lease(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "arbiter.db"

    monkeypatch.setattr(
        settings,
        "arbiter_db_path",
        str(db_path),
    )

    with TestClient(app) as client:
        first = client.post(
            "/cluster/acquire",
            json={"node_id": "A"},
        )

        assert first.status_code == 200

        second = client.post(
            "/cluster/acquire",
            json={"node_id": "B"},
        )

        assert second.status_code == 409

        body = second.json()

        assert body["status"] == "error"
        assert body["code"] == "LEASE_HELD"
        assert body["leader_id"] == "A"
        assert body["epoch"] == 1


def test_new_leader_gets_new_epoch_after_expiry(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "arbiter.db"

    monkeypatch.setattr(
        settings,
        "arbiter_db_path",
        str(db_path),
    )

    with TestClient(app) as client:
        first = client.post(
            "/cluster/acquire",
            json={"node_id": "A"},
        )

        assert first.status_code == 200
        assert first.json()["epoch"] == 1

        connection = get_connection()

        try:
            connection.execute(
                """
                UPDATE cluster_state
                SET lease_expires_at = ?
                WHERE id = 1
                """,
                (time.time() - 1,),
            )
            connection.commit()

        finally:
            connection.close()

        second = client.post(
            "/cluster/acquire",
            json={"node_id": "B"},
        )

        assert second.status_code == 200

        body = second.json()

        assert body["leader_id"] == "B"
        assert body["epoch"] == 2
        
def test_leader_can_renew_valid_lease(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "arbiter.db"

    monkeypatch.setattr(
        settings,
        "arbiter_db_path",
        str(db_path),
    )

    with TestClient(app) as client:
        acquire = client.post(
            "/cluster/acquire",
            json={"node_id": "A"},
        )

        assert acquire.status_code == 200

        first_expiry = acquire.json()["lease_expires_at"]

        renew = client.post(
            "/cluster/renew",
            json={
                "node_id": "A",
                "epoch": 1,
            },
        )

        assert renew.status_code == 200

        body = renew.json()

        assert body["status"] == "success"
        assert body["leader_id"] == "A"
        assert body["epoch"] == 1
        assert body["lease_expires_at"] >= first_expiry


def test_wrong_node_cannot_renew_lease(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "arbiter.db"

    monkeypatch.setattr(
        settings,
        "arbiter_db_path",
        str(db_path),
    )

    with TestClient(app) as client:
        client.post(
            "/cluster/acquire",
            json={"node_id": "A"},
        )

        response = client.post(
            "/cluster/renew",
            json={
                "node_id": "B",
                "epoch": 1,
            },
        )

        assert response.status_code == 409
        assert response.json()["code"] == "NOT_LEADER"


def test_stale_epoch_cannot_renew_lease(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "arbiter.db"

    monkeypatch.setattr(
        settings,
        "arbiter_db_path",
        str(db_path),
    )

    with TestClient(app) as client:
        client.post(
            "/cluster/acquire",
            json={"node_id": "A"},
        )

        response = client.post(
            "/cluster/renew",
            json={
                "node_id": "A",
                "epoch": 999,
            },
        )

        assert response.status_code == 409
        assert response.json()["code"] == "STALE_EPOCH"
        
def test_expired_lease_cannot_be_renewed(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "arbiter.db"

    monkeypatch.setattr(
        settings,
        "arbiter_db_path",
        str(db_path),
    )

    with TestClient(app) as client:
        client.post(
            "/cluster/acquire",
            json={"node_id": "A"},
        )

        connection = get_connection()

        try:
            connection.execute(
                """
                UPDATE cluster_state
                SET lease_expires_at = ?
                WHERE id = 1
                """,
                (time.time() - 1,),
            )
            connection.commit()

        finally:
            connection.close()

        response = client.post(
            "/cluster/renew",
            json={
                "node_id": "A",
                "epoch": 1,
            },
        )

        assert response.status_code == 409
        assert response.json()["code"] == "LEASE_EXPIRED"