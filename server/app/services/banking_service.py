from server.app.database import get_connection


class AccountNotFoundError(Exception):
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