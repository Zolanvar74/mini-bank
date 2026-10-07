import pytest

from server.app.services.banking_service import (
    AccountNotFoundError,
    InvalidAmountError,
    MissingAmountError,
    deposit,
    get_balance,
)


def test_deposit_increases_balance(test_db):
    response = deposit(
        request_id="req-001",
        account_id="A1001",
        amount=200,
    )

    assert response["status"] == "success"
    assert response["balance"] == 1200
    assert get_balance("A1001") == 1200


def test_duplicate_deposit_is_not_applied_twice(test_db):
    first_response = deposit(
        request_id="req-duplicate",
        account_id="A1001",
        amount=200,
    )

    second_response = deposit(
        request_id="req-duplicate",
        account_id="A1001",
        amount=200,
    )

    assert first_response == second_response
    assert get_balance("A1001") == 1200


def test_negative_deposit(test_db):
    with pytest.raises(InvalidAmountError):
        deposit(
            request_id="req-negative",
            account_id="A1001",
            amount=-50,
        )


def test_zero_deposit(test_db):
    with pytest.raises(InvalidAmountError):
        deposit(
            request_id="req-zero",
            account_id="A1001",
            amount=0,
        )


def test_string_deposit(test_db):
    with pytest.raises(InvalidAmountError):
        deposit(
            request_id="req-string",
            account_id="A1001",
            amount="abc",
        )


def test_missing_deposit_amount(test_db):
    with pytest.raises(MissingAmountError):
        deposit(
            request_id="req-missing",
            account_id="A1001",
            amount=None,
        )


def test_deposit_unknown_account(test_db):
    with pytest.raises(AccountNotFoundError):
        deposit(
            request_id="req-unknown",
            account_id="Z9999",
            amount=200,
        )