import sqlite3
from pathlib import Path

from server.app.core.config import settings


def get_connection() -> sqlite3.Connection:
    db_path = Path(settings.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(
        db_path,
        timeout=10,
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

        connection.commit()

    finally:
        connection.close()