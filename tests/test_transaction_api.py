from fastapi.testclient import TestClient

from server.app.main import app


def test_balance_api(test_db):
    with TestClient(app) as client:
        response = client.post(
            "/api/transaction",
            json={
                "action": "balance",
                "account": "A1001",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "success",
        "account": "A1001",
        "balance": 1000,
    }


def test_unknown_account_api(test_db):
    with TestClient(app) as client:
        response = client.post(
            "/api/transaction",
            json={
                "action": "balance",
                "account": "Z9999",
            },
        )

    assert response.status_code == 404
    assert response.json()["code"] == "UNKNOWN_ACCOUNT"

def test_deposit_api(test_db):
    with TestClient(app) as client:
        response = client.post(
            "/api/transaction",
            json={
                "request_id": "api-deposit-001",
                "action": "deposit",
                "account": "A1001",
                "amount": 200,
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["balance"] == 1200


def test_invalid_amount_api(test_db):
    with TestClient(app) as client:
        response = client.post(
            "/api/transaction",
            json={
                "request_id": "api-invalid-001",
                "action": "deposit",
                "account": "A1001",
                "amount": -50,
            },
        )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_AMOUNT"


def test_unsupported_action_api(test_db):
    with TestClient(app) as client:
        response = client.post(
            "/api/transaction",
            json={
                "request_id": "api-transfer-001",
                "action": "transfer",
                "account": "A1001",
                "amount": 100,
            },
        )

    assert response.status_code == 400
    assert response.json()["code"] == "UNSUPPORTED_ACTION"
    
def test_withdraw_api(test_db):
    with TestClient(app) as client:
        response = client.post(
            "/api/transaction",
            json={
                "request_id": "api-withdraw-001",
                "action": "withdraw",
                "account": "A1001",
                "amount": 200,
            },
        )

    assert response.status_code == 200
    assert response.json()["balance"] == 800


def test_insufficient_funds_api(test_db):
    with TestClient(app) as client:
        response = client.post(
            "/api/transaction",
            json={
                "request_id": "api-withdraw-002",
                "action": "withdraw",
                "account": "A1001",
                "amount": 5000,
            },
        )

    assert response.status_code == 409
    assert response.json()["code"] == "INSUFFICIENT_FUNDS"