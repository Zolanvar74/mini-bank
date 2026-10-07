import pytest

from server.app.services.banking_service import (
    AccountNotFoundError,
    get_balance,
)


def test_get_balance(test_db):
    assert get_balance("A1001") == 1000


def test_get_balance_second_account(test_db):
    assert get_balance("A1002") == 2000


def test_unknown_account(test_db):
    with pytest.raises(AccountNotFoundError):
        get_balance("Z9999")