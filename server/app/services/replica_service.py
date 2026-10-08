import json

from server.app.core.wal_client import fetch_wal_since
from server.app.database import (
    get_connection,
    get_last_seq,
    set_last_seq,
)


class ReplicaGapError(Exception):
    pass


class ReplicaApplyError(Exception):
    pass


def apply_wal_entries(entries: list[dict]) -> dict:
    connection = get_connection()

    try:
        connection.execute("BEGIN IMMEDIATE")

        row = connection.execute(
            """
            SELECT last_seq
            FROM replica_state
            WHERE id = 1
            """
        ).fetchone()

        current_seq = row["last_seq"]
        applied = 0

        for entry in entries:
            seq = entry["seq"]

            # Safe if the same batch is accidentally replayed.
            if seq <= current_seq:
                continue

            expected_seq = current_seq + 1

            if seq != expected_seq:
                raise ReplicaGapError(
                    f"Expected WAL seq {expected_seq}, "
                    f"received {seq}."
                )

            if entry["status"] != "success":
                raise ReplicaApplyError(
                    f"Unsupported WAL status: "
                    f"{entry['status']}"
                )

            if entry["action"] not in {
                "deposit",
                "withdraw",
            }:
                raise ReplicaApplyError(
                    f"Unsupported WAL action: "
                    f"{entry['action']}"
                )

            cursor = connection.execute(
                """
                UPDATE accounts
                SET balance = ?
                WHERE account_id = ?
                """,
                (
                    entry["balance_after"],
                    entry["account_id"],
                ),
            )

            if cursor.rowcount != 1:
                raise ReplicaApplyError(
                    f"Unknown account "
                    f"{entry['account_id']}."
                )

            existing = connection.execute(
                """
                SELECT action, account_id, amount
                FROM request_results
                WHERE request_id = ?
                """,
                (entry["request_id"],),
            ).fetchone()

            if existing is not None:
                same_request = (
                    existing["action"]
                    == entry["action"]
                    and existing["account_id"]
                    == entry["account_id"]
                    and existing["amount"]
                    == entry["amount"]
                )

                if not same_request:
                    raise ReplicaApplyError(
                        "request_id conflict while "
                        "replaying WAL."
                    )

            else:
                connection.execute(
                    """
                    INSERT INTO request_results (
                        request_id,
                        action,
                        account_id,
                        amount,
                        status,
                        response_json,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry["request_id"],
                        entry["action"],
                        entry["account_id"],
                        entry["amount"],
                        entry["status"],
                        json.dumps(
                            entry["response_json"]
                        ),
                        entry["committed_at"],
                    ),
                )

            set_last_seq(
                connection,
                seq,
            )

            current_seq = seq
            applied += 1

        connection.commit()

        return {
            "applied": applied,
            "last_seq": current_seq,
        }

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def sync_from_arbiter() -> dict:
    before_seq = get_last_seq()

    entries = fetch_wal_since(before_seq)

    result = apply_wal_entries(entries)

    return {
        "from_seq": before_seq,
        "fetched": len(entries),
        "applied": result["applied"],
        "last_seq": result["last_seq"],
    }