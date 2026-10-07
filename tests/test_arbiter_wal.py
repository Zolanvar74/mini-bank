from fastapi.testclient import TestClient

from arbiter.app.config import settings
from arbiter.app.main import app


def acquire_a(client):
    response = client.post(
        "/cluster/acquire",
        json={"node_id": "A"},
    )

    assert response.status_code == 200

    return response.json()["epoch"]


def test_primary_can_commit_wal_entry(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "arbiter_db_path",
        str(tmp_path / "arbiter.db"),
    )

    with TestClient(app) as client:
        epoch = acquire_a(client)

        response = client.post(
            "/wal/commit",
            json={
                "node_id": "A",
                "epoch": epoch,
                "request_id": "req-001",
                "action": "deposit",
                "account_id": "A1001",
                "amount": 100,
                "status": "success",
                "balance_after": 1100,
                "response_json": {
                    "status": "success",
                    "account": "A1001",
                    "balance": 1100,
                },
            },
        )

        assert response.status_code == 200

        body = response.json()

        assert body["seq"] == 1
        assert body["epoch"] == epoch
        assert body["request_id"] == "req-001"
        assert body["duplicate"] is False


def test_non_leader_cannot_commit_wal(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "arbiter_db_path",
        str(tmp_path / "arbiter.db"),
    )

    with TestClient(app) as client:
        epoch = acquire_a(client)

        response = client.post(
            "/wal/commit",
            json={
                "node_id": "B",
                "epoch": epoch,
                "request_id": "req-002",
                "action": "deposit",
                "account_id": "A1001",
                "amount": 100,
                "status": "success",
                "balance_after": 1100,
                "response_json": {
                    "status": "success"
                },
            },
        )

        assert response.status_code == 409
        assert response.json()["code"] == "NOT_LEADER"


def test_stale_epoch_cannot_commit_wal(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "arbiter_db_path",
        str(tmp_path / "arbiter.db"),
    )

    with TestClient(app) as client:
        acquire_a(client)

        response = client.post(
            "/wal/commit",
            json={
                "node_id": "A",
                "epoch": 999,
                "request_id": "req-003",
                "action": "deposit",
                "account_id": "A1001",
                "amount": 100,
                "status": "success",
                "balance_after": 1100,
                "response_json": {
                    "status": "success"
                },
            },
        )

        assert response.status_code == 409
        assert response.json()["code"] == "STALE_EPOCH"


def test_same_request_id_is_idempotent(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "arbiter_db_path",
        str(tmp_path / "arbiter.db"),
    )

    payload = {
        "node_id": "A",
        "epoch": 1,
        "request_id": "req-004",
        "action": "withdraw",
        "account_id": "A1001",
        "amount": 50,
        "status": "success",
        "balance_after": 950,
        "response_json": {
            "status": "success",
            "balance": 950,
        },
    }

    with TestClient(app) as client:
        acquire_a(client)

        first = client.post(
            "/wal/commit",
            json=payload,
        )

        second = client.post(
            "/wal/commit",
            json=payload,
        )

        assert first.status_code == 200
        assert second.status_code == 200

        assert first.json()["seq"] == 1
        assert second.json()["seq"] == 1

        assert first.json()["duplicate"] is False
        assert second.json()["duplicate"] is True


def test_wal_sequence_and_since_endpoint(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "arbiter_db_path",
        str(tmp_path / "arbiter.db"),
    )

    with TestClient(app) as client:
        epoch = acquire_a(client)

        for index in range(3):
            response = client.post(
                "/wal/commit",
                json={
                    "node_id": "A",
                    "epoch": epoch,
                    "request_id": f"req-{index}",
                    "action": "deposit",
                    "account_id": "A1001",
                    "amount": 10,
                    "status": "success",
                    "balance_after": 1010 + index * 10,
                    "response_json": {
                        "status": "success",
                    },
                },
            )

            assert response.status_code == 200

        response = client.get("/wal/since/1")

        assert response.status_code == 200

        entries = response.json()["entries"]

        assert len(entries) == 2
        assert entries[0]["seq"] == 2
        assert entries[1]["seq"] == 3

        status = client.get("/wal/status").json()

        assert status["entry_count"] == 3
        assert status["last_seq"] == 3