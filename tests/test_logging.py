import json

from fastapi.testclient import TestClient

from server.app.core.config import settings
from server.app.main import app


def test_successful_request_is_logged(
    test_db,
    tmp_path,
    monkeypatch,
):
    log_path = tmp_path / "server.jsonl"

    monkeypatch.setattr(
        settings,
        "log_path",
        str(log_path),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/transaction",
            json={
                "action": "balance",
                "account": "A1001",
            },
        )

    assert response.status_code == 200
    assert log_path.exists()

    lines = log_path.read_text(
        encoding="utf-8"
    ).splitlines()

    assert len(lines) == 1

    entry = json.loads(lines[0])

    assert entry["request_id"]
    assert entry["action"] == "balance"
    assert entry["account"] == "A1001"
    assert entry["result"] == "success"
    assert entry["status_code"] == 200
    assert entry["latency_ms"] >= 0
    assert entry["client_ip"]
    assert entry["timestamp"]


def test_failed_request_is_logged(
    test_db,
    tmp_path,
    monkeypatch,
):
    log_path = tmp_path / "server.jsonl"

    monkeypatch.setattr(
        settings,
        "log_path",
        str(log_path),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/transaction",
            json={
                "action": "balance",
                "account": "Z9999",
            },
        )

    assert response.status_code == 404

    lines = log_path.read_text(
        encoding="utf-8"
    ).splitlines()

    entry = json.loads(lines[0])

    assert entry["action"] == "balance"
    assert entry["account"] == "Z9999"
    assert entry["result"] == "UNKNOWN_ACCOUNT"
    assert entry["status_code"] == 404


def test_client_request_id_is_logged(
    test_db,
    tmp_path,
    monkeypatch,
):
    log_path = tmp_path / "server.jsonl"

    monkeypatch.setattr(
        settings,
        "log_path",
        str(log_path),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/transaction",
            json={
                "request_id": "logging-test-001",
                "action": "deposit",
                "account": "A1001",
                "amount": 100,
            },
        )

    assert response.status_code == 200

    entry = json.loads(
        log_path.read_text(
            encoding="utf-8"
        ).splitlines()[0]
    )

    assert (
        entry["request_id"]
        == "logging-test-001"
    )