import pytest

from server.app.services.banking_service import (
    InsufficientFundsError,
    InvalidAmountError,
    RequestIdConflictError,
    get_balance,
    withdraw,
)


def test_withdraw_decreases_balance(test_db):
    response = withdraw(
        request_id="withdraw-001",
        account_id="A1001",
        amount=200,
    )

    assert response["status"] == "success"
    assert response["balance"] == 800
    assert get_balance("A1001") == 800


def test_withdraw_exact_balance(test_db):
    response = withdraw(
        request_id="withdraw-exact",
        account_id="A1003",
        amount=500,
    )

    assert response["balance"] == 0
    assert get_balance("A1003") == 0


def test_insufficient_funds(test_db):
    with pytest.raises(InsufficientFundsError):
        withdraw(
            request_id="withdraw-too-much",
            account_id="A1001",
            amount=5000,
        )

    assert get_balance("A1001") == 1000


def test_negative_withdraw(test_db):
    with pytest.raises(InvalidAmountError):
        withdraw(
            request_id="withdraw-negative",
            account_id="A1001",
            amount=-50,
        )


def test_duplicate_withdraw_is_not_applied_twice(test_db):
    first = withdraw(
        request_id="withdraw-duplicate",
        account_id="A1001",
        amount=100,
    )

    second = withdraw(
        request_id="withdraw-duplicate",
        account_id="A1001",
        amount=100,
    )

    assert first == second
    assert get_balance("A1001") == 900


def test_request_id_conflict(test_db):
    withdraw(
        request_id="same-id",
        account_id="A1001",
        amount=100,
    )

    with pytest.raises(RequestIdConflictError):
        withdraw(
            request_id="same-id",
            account_id="A1001",
            amount=200,
        )

    assert get_balance("A1001") == 900