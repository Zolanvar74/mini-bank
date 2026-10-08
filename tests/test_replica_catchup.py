import pytest

from server.app.database import (
    get_last_seq,
)
from server.app.services.banking_service import (
    get_balance,
)
from server.app.services.replica_service import (
    ReplicaGapError,
    apply_wal_entries,
)


def make_entry(
    *,
    seq: int,
    request_id: str,
    action: str,
    amount: int,
    balance_after: int,
):
    return {
        "seq": seq,
        "epoch": 1,
        "request_id": request_id,
        "action": action,
        "account_id": "A1001",
        "amount": amount,
        "status": "success",
        "balance_after": balance_after,
        "response_json": {
            "request_id": request_id,
            "status": "success",
            "account": "A1001",
            "balance": balance_after,
        },
        "committed_at": (
            "2026-10-08T10:00:00+00:00"
        ),
    }


def test_replica_applies_wal_entries(test_db):
    entries = [
        make_entry(
            seq=1,
            request_id="replica-001",
            action="deposit",
            amount=200,
            balance_after=1200,
        ),
        make_entry(
            seq=2,
            request_id="replica-002",
            action="withdraw",
            amount=50,
            balance_after=1150,
        ),
    ]

    result = apply_wal_entries(entries)

    assert result["applied"] == 2
    assert result["last_seq"] == 2

    assert get_last_seq() == 2
    assert get_balance("A1001") == 1150


def test_replaying_same_entries_is_safe(test_db):
    entries = [
        make_entry(
            seq=1,
            request_id="replica-duplicate",
            action="deposit",
            amount=100,
            balance_after=1100,
        ),
    ]

    first = apply_wal_entries(entries)
    second = apply_wal_entries(entries)

    assert first["applied"] == 1
    assert second["applied"] == 0

    assert get_last_seq() == 1
    assert get_balance("A1001") == 1100


def test_wal_gap_rolls_back_batch(test_db):
    entries = [
        make_entry(
            seq=2,
            request_id="gap-002",
            action="deposit",
            amount=100,
            balance_after=1100,
        ),
    ]

    with pytest.raises(ReplicaGapError):
        apply_wal_entries(entries)

    assert get_last_seq() == 0
    assert get_balance("A1001") == 1000