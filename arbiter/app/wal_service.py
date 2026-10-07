import json
import time
from datetime import datetime, timezone

from arbiter.app.database import get_connection


class WalCommitRejected(Exception):
    def __init__(
        self,
        code: str,
        leader_id: str | None = None,
        epoch: int | None = None,
    ):
        self.code = code
        self.leader_id = leader_id
        self.epoch = epoch
        super().__init__(code)


class WalRequestConflict(Exception):
    pass


def _row_to_dict(row) -> dict:
    return {
        "seq": row["seq"],
        "epoch": row["epoch"],
        "request_id": row["request_id"],
        "action": row["action"],
        "account_id": row["account_id"],
        "amount": row["amount"],
        "status": row["status"],
        "balance_after": row["balance_after"],
        "response_json": json.loads(row["response_json"]),
        "committed_at": row["committed_at"],
    }


def commit_wal_entry(
    *,
    node_id: str,
    epoch: int,
    request_id: str,
    action: str,
    account_id: str,
    amount: int,
    status: str,
    balance_after: int | None,
    response_json: dict,
) -> dict:
    connection = get_connection()

    try:
        connection.execute("BEGIN IMMEDIATE")

        state = connection.execute(
            """
            SELECT leader_id, epoch, lease_expires_at
            FROM cluster_state
            WHERE id = 1
            """
        ).fetchone()

        now = time.time()

        if state["leader_id"] != node_id:
            connection.rollback()
            raise WalCommitRejected(
                code="NOT_LEADER",
                leader_id=state["leader_id"],
                epoch=state["epoch"],
            )

        if state["epoch"] != epoch:
            connection.rollback()
            raise WalCommitRejected(
                code="STALE_EPOCH",
                leader_id=state["leader_id"],
                epoch=state["epoch"],
            )

        if (
            state["lease_expires_at"] is None
            or state["lease_expires_at"] <= now
        ):
            connection.rollback()
            raise WalCommitRejected(
                code="LEASE_EXPIRED",
                leader_id=state["leader_id"],
                epoch=state["epoch"],
            )

        existing = connection.execute(
            """
            SELECT *
            FROM wal
            WHERE request_id = ?
            """,
            (request_id,),
        ).fetchone()

        if existing is not None:
            same_request = (
                existing["action"] == action
                and existing["account_id"] == account_id
                and existing["amount"] == amount
            )

            if not same_request:
                connection.rollback()
                raise WalRequestConflict()

            connection.commit()

            result = _row_to_dict(existing)
            result["duplicate"] = True
            return result

        committed_at = datetime.now(
            timezone.utc
        ).isoformat()

        cursor = connection.execute(
            """
            INSERT INTO wal (
                epoch,
                request_id,
                action,
                account_id,
                amount,
                status,
                balance_after,
                response_json,
                committed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                epoch,
                request_id,
                action,
                account_id,
                amount,
                status,
                balance_after,
                json.dumps(
                    response_json,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                committed_at,
            ),
        )

        seq = cursor.lastrowid

        connection.commit()

        return {
            "seq": seq,
            "epoch": epoch,
            "request_id": request_id,
            "action": action,
            "account_id": account_id,
            "amount": amount,
            "status": status,
            "balance_after": balance_after,
            "response_json": response_json,
            "committed_at": committed_at,
            "duplicate": False,
        }

    except (WalCommitRejected, WalRequestConflict):
        raise

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def get_wal_since(seq: int) -> list[dict]:
    connection = get_connection()

    try:
        rows = connection.execute(
            """
            SELECT *
            FROM wal
            WHERE seq > ?
            ORDER BY seq ASC
            """,
            (seq,),
        ).fetchall()

        return [_row_to_dict(row) for row in rows]

    finally:
        connection.close()


def get_wal_status() -> dict:
    connection = get_connection()

    try:
        row = connection.execute(
            """
            SELECT
                COUNT(*) AS entry_count,
                COALESCE(MAX(seq), 0) AS last_seq
            FROM wal
            """
        ).fetchone()

        return {
            "entry_count": row["entry_count"],
            "last_seq": row["last_seq"],
        }

    finally:
        connection.close()