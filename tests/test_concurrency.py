from concurrent.futures import ThreadPoolExecutor

from server.app.services.banking_service import (
    InsufficientFundsError,
    deposit,
    get_balance,
    withdraw,
)


def test_concurrent_deposits_no_lost_updates(test_db):
    def make_deposit(index):
        return deposit(
            request_id=f"concurrent-deposit-{index}",
            account_id="A1001",
            amount=10,
        )

    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(
            executor.map(
                make_deposit,
                range(100),
            )
        )

    assert len(results) == 100

    # Initial balance = 1000
    # 100 deposits * 10 = 1000
    assert get_balance("A1001") == 2000


def test_concurrent_withdrawals_never_go_negative(test_db):
    def make_withdraw(index):
        try:
            withdraw(
                request_id=f"concurrent-withdraw-{index}",
                account_id="A1001",
                amount=10,
            )
            return "success"

        except InsufficientFundsError:
            return "insufficient"

    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(
            executor.map(
                make_withdraw,
                range(120),
            )
        )

    success_count = results.count("success")
    insufficient_count = results.count("insufficient")

    assert success_count == 100
    assert insufficient_count == 20
    assert get_balance("A1001") == 0


def test_concurrent_duplicate_request_is_applied_once(test_db):
    def send_same_request(_):
        return deposit(
            request_id="same-concurrent-request",
            account_id="A1001",
            amount=100,
        )

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(
            executor.map(
                send_same_request,
                range(10),
            )
        )

    assert len(results) == 10

    for result in results:
        assert result["balance"] == 1100

    assert get_balance("A1001") == 1100