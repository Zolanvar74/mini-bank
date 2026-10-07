import pytest

from server.app.services.banking_service import (
    SimulatedFailureError,
    deposit,
    get_balance,
    withdraw,
)


def test_deposit_rolls_back_after_simulated_failure(test_db):
    assert get_balance("A1001") == 1000

    with pytest.raises(SimulatedFailureError):
        deposit(
            request_id="acid-deposit-failure",
            account_id="A1001",
            amount=200,
            fail_after_update=True,
        )

    assert get_balance("A1001") == 1000


def test_withdraw_rolls_back_after_simulated_failure(test_db):
    assert get_balance("A1001") == 1000

    with pytest.raises(SimulatedFailureError):
        withdraw(
            request_id="acid-withdraw-failure",
            account_id="A1001",
            amount=200,
            fail_after_update=True,
        )

    assert get_balance("A1001") == 1000


def test_failed_request_can_be_retried(test_db):
    with pytest.raises(SimulatedFailureError):
        deposit(
            request_id="acid-retry",
            account_id="A1001",
            amount=200,
            fail_after_update=True,
        )

    assert get_balance("A1001") == 1000

    response = deposit(
        request_id="acid-retry",
        account_id="A1001",
        amount=200,
    )

    assert response["balance"] == 1200
    assert get_balance("A1001") == 1200