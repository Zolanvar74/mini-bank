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