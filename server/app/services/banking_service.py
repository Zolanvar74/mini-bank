import json
from datetime import datetime, timezone

from server.app.database import get_connection


class AccountNotFoundError(Exception):
    pass


class InvalidAmountError(Exception):
    pass


class MissingAmountError(Exception):
    pass


class InsufficientFundsError(Exception):
    pass


class RequestIdConflictError(Exception):
    pass


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


def get_balance(account_id: str) -> int:
    connection = get_connection()

    try:
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

    finally:
        connection.close()


def get_previous_result(
    connection,
    request_id: str,
    action: str,
    account_id: str,
    amount: int,
):
    row = connection.execute(
        """
        SELECT action, account_id, amount, response_json
        FROM request_results
        WHERE request_id = ?
        """,
        (request_id,),
    ).fetchone()

    if row is None:
        return None

    if (
        row["action"] != action
        or row["account_id"] != account_id
        or row["amount"] != amount
    ):
        raise RequestIdConflictError(request_id)

    return json.loads(row["response_json"])


def store_result(
    connection,
    request_id: str,
    action: str,
    account_id: str,
    amount: int,
    response: dict,
) -> None:
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
            request_id,
            action,
            account_id,
            amount,
            "success",
            json.dumps(response),
            datetime.now(timezone.utc).isoformat(),
        ),
    )


def deposit(
    request_id: str,
    account_id: str,
    amount,
) -> dict:
    amount = validate_amount(amount)

    connection = get_connection()

    try:
        connection.execute("BEGIN IMMEDIATE")

        previous_result = get_previous_result(
            connection,
            request_id,
            "deposit",
            account_id,
            amount,
        )

        if previous_result is not None:
            connection.rollback()
            return previous_result

        account = connection.execute(
            """
            SELECT balance
            FROM accounts
            WHERE account_id = ?
            """,
            (account_id,),
        ).fetchone()

        if account is None:
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

        store_result(
            connection,
            request_id,
            "deposit",
            account_id,
            amount,
            response,
        )

        connection.commit()
        return response

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def withdraw(
    request_id: str,
    account_id: str,
    amount,
) -> dict:
    amount = validate_amount(amount)

    connection = get_connection()

    try:
        connection.execute("BEGIN IMMEDIATE")

        previous_result = get_previous_result(
            connection,
            request_id,
            "withdraw",
            account_id,
            amount,
        )

        if previous_result is not None:
            connection.rollback()
            return previous_result

        account = connection.execute(
            """
            SELECT balance
            FROM accounts
            WHERE account_id = ?
            """,
            (account_id,),
        ).fetchone()

        if account is None:
            raise AccountNotFoundError(account_id)

        if account["balance"] < amount:
            raise InsufficientFundsError()

        new_balance = account["balance"] - amount

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

        store_result(
            connection,
            request_id,
            "withdraw",
            account_id,
            amount,
            response,
        )

        connection.commit()
        return response

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()