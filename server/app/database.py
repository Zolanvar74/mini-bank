import sqlite3
from pathlib import Path

from server.app.core.config import settings


def get_connection() -> sqlite3.Connection:
    db_path = Path(settings.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(
        db_path,
        timeout=30,
        check_same_thread=False,
    )

    connection.row_factory = sqlite3.Row

    connection.execute("PRAGMA journal_mode=WAL;")
    connection.execute("PRAGMA synchronous=FULL;")
    connection.execute("PRAGMA foreign_keys=ON;")

    return connection


def initialize_database() -> None:
    connection = get_connection()

    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                account_id TEXT PRIMARY KEY,
                balance INTEGER NOT NULL CHECK(balance >= 0)
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS request_results (
                request_id TEXT PRIMARY KEY,
                action TEXT NOT NULL,
                account_id TEXT,
                amount INTEGER,
                status TEXT NOT NULL,
                response_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS replica_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                last_seq INTEGER NOT NULL DEFAULT 0
            )
            """
        )

        connection.execute(
    """
    INSERT OR IGNORE INTO replica_state (
        id,
        last_seq
    )
    VALUES (1, 0)
    """
)

        connection.commit()

    finally:
        connection.close()
        
def get_last_seq() -> int:
    connection = get_connection()

    try:
        row = connection.execute(
            """
            SELECT last_seq
            FROM replica_state
            WHERE id = 1
            """
        ).fetchone()

        return row["last_seq"]

    finally:
        connection.close()


def set_last_seq(
    connection: sqlite3.Connection,
    seq: int,
) -> None:
    connection.execute(
        """
        UPDATE replica_state
        SET last_seq =
            CASE
                WHEN last_seq < ? THEN ?
                ELSE last_seq
            END
        WHERE id = 1
        """,
        (seq, seq),
    )