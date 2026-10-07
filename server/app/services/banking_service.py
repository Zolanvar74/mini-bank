import json
from datetime import datetime, timezone

from server.app.database import get_connection


class AccountNotFoundError(Exception):
    pass


class InvalidAmountError(Exception):
    pass


class MissingAmountError(Exception):
    pass


def get_balance(account_id: str) -> int:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT balance
            FROM accounts
            WHERE account_id = ?
            """,
            (account_id,),
        ).fetchone()

    if row is None:
        raise AccountNotFoundError(account_id)

    return row["balance"]


def validate_amount(amount) -> int:
    if amount is None:
        raise MissingAmountError()

    if isinstance(amount, bool):
        raise InvalidAmountError()

    if not isinstance(amount, int):
        raise InvalidAmountError()

    if amount <= 0:
        raise InvalidAmountError()

    return amount


def deposit(
    request_id: str,
    account_id: str,
    amount,
) -> dict:
    amount = validate_amount(amount)

    connection = get_connection()

    try:
        connection.execute("BEGIN IMMEDIATE")

        previous_result = connection.execute(
            """
            SELECT response_json
            FROM request_results
            WHERE request_id = ?
            """,
            (request_id,),
        ).fetchone()

        if previous_result is not None:
            connection.rollback()
            return json.loads(previous_result["response_json"])

        account = connection.execute(
            """
            SELECT balance
            FROM accounts
            WHERE account_id = ?
            """,
            (account_id,),
        ).fetchone()

        if account is None:
            connection.rollback()
            raise AccountNotFoundError(account_id)

        new_balance = account["balance"] + amount

        connection.execute(
            """
            UPDATE accounts
            SET balance = ?
            WHERE account_id = ?
            """,
            (new_balance, account_id),
        )

        response = {
            "request_id": request_id,
            "status": "success",
            "account": account_id,
            "balance": new_balance,
        }

        connection.execute(
            """
            INSERT INTO request_results (
                request_id,
                action,
                account_id,
                status,
                response_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                request_id,
                "deposit",
                account_id,
                "success",
                json.dumps(response),
                datetime.now(timezone.utc).isoformat(),
            ),
        )

        connection.commit()

        return response

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()