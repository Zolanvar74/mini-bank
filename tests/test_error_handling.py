from fastapi.testclient import TestClient

from server.app.main import app


def test_missing_action(test_db):
    with TestClient(app) as client:
        response = client.post(
            "/api/transaction",
            json={
                "account": "A1001",
            },
        )

    assert response.status_code == 400
    assert response.json()["code"] == "MISSING_FIELD"


def test_missing_account(test_db):
    with TestClient(app) as client:
        response = client.post(
            "/api/transaction",
            json={
                "action": "balance",
            },
        )

    assert response.status_code == 400
    assert response.json()["code"] == "MISSING_FIELD"


def test_missing_amount(test_db):
    with TestClient(app) as client:
        response = client.post(
            "/api/transaction",
            json={
                "request_id": "missing-amount-001",
                "action": "withdraw",
                "account": "A1001",
            },
        )

    assert response.status_code == 400
    assert response.json()["code"] == "MISSING_FIELD"


def test_missing_request_id(test_db):
    with TestClient(app) as client:
        response = client.post(
            "/api/transaction",
            json={
                "action": "deposit",
                "account": "A1001",
                "amount": 100,
            },
        )

    assert response.status_code == 400
    assert response.json()["code"] == "MISSING_FIELD"


def test_malformed_json(test_db):
    with TestClient(app) as client:
        response = client.post(
            "/api/transaction",
            content='{"action": "balance", "account": ',
            headers={
                "Content-Type": "application/json"
            },
        )

    assert response.status_code == 400
    assert response.json()["code"] == "MALFORMED_REQUEST"

def test_random_bytes_as_json(test_db):
    with TestClient(app) as client:
        response = client.post(
            "/api/transaction",
            content=b"\x00\x01\xffbroken-json",
            headers={
                "Content-Type": "application/json"
            },
        )

    assert response.status_code == 400
    assert response.json()["code"] == "MALFORMED_REQUEST"

def test_server_survives_malformed_request(test_db):
    with TestClient(app) as client:
        bad_response = client.post(
            "/api/transaction",
            content='{"broken": ',
            headers={
                "Content-Type": "application/json"
            },
        )

        assert bad_response.status_code == 400
        assert (
            bad_response.json()["code"]
            == "MALFORMED_REQUEST"
        )

        good_response = client.post(
            "/api/transaction",
            json={
                "action": "balance",
                "account": "A1001",
            },
        )

    assert good_response.status_code == 200
    assert good_response.json()["balance"] == 1000