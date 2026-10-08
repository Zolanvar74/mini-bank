import pytest

from server.app.database import get_last_seq
from server.app.services.banking_service import (
    deposit,
    get_balance,
    withdraw,
)


def test_deposit_advances_replica_sequence(
    test_db,
):
    def fake_wal(response, balance_after):
        return {"seq": 7}

    response = deposit(
        request_id="rep-deposit-001",
        account_id="A1001",
        amount=100,
        wal_commit=fake_wal,
    )

    assert response["balance"] == 1100
    assert get_balance("A1001") == 1100
    assert get_last_seq() == 7


def test_wal_failure_rolls_back_deposit(
    test_db,
):
    def failing_wal(response, balance_after):
        raise RuntimeError("WAL failed")

    with pytest.raises(RuntimeError):
        deposit(
            request_id="rep-deposit-fail",
            account_id="A1001",
            amount=100,
            wal_commit=failing_wal,
        )

    assert get_balance("A1001") == 1000
    assert get_last_seq() == 0


def test_withdraw_advances_replica_sequence(
    test_db,
):
    def fake_wal(response, balance_after):
        return {"seq": 12}

    response = withdraw(
        request_id="rep-withdraw-001",
        account_id="A1001",
        amount=100,
        wal_commit=fake_wal,
    )

    assert response["balance"] == 900
    assert get_balance("A1001") == 900
    assert get_last_seq() == 12