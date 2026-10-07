import os
import sqlite3

from arbiter.app.config import settings


def get_connection() -> sqlite3.Connection:
    db_path = settings.arbiter_db_path

    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    connection = sqlite3.connect(
        db_path,
        timeout=30,
        check_same_thread=False,
    )

    connection.row_factory = sqlite3.Row

    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute("PRAGMA foreign_keys=ON")

    return connection


def initialize_database() -> None:
    connection = get_connection()

    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS cluster_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                leader_id TEXT,
                epoch INTEGER NOT NULL DEFAULT 0,
                lease_expires_at REAL
            )
            """
        )

        connection.execute(
            """
            INSERT OR IGNORE INTO cluster_state (
                id,
                leader_id,
                epoch,
                lease_expires_at
            )
            VALUES (1, NULL, 0, NULL)
            """
        )
        
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS wal (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                epoch INTEGER NOT NULL,
                request_id TEXT NOT NULL UNIQUE,
                action TEXT NOT NULL,
                account_id TEXT NOT NULL,
                amount INTEGER NOT NULL,
                status TEXT NOT NULL,
                balance_after INTEGER,
                response_json TEXT NOT NULL,
                committed_at TEXT NOT NULL
            )
            """
        )

        connection.commit()

    finally:
        connection.close()


def get_cluster_state() -> dict:
    connection = get_connection()

    try:
        row = connection.execute(
            """
            SELECT leader_id, epoch, lease_expires_at
            FROM cluster_state
            WHERE id = 1
            """
        ).fetchone()

        return {
            "leader_id": row["leader_id"],
            "epoch": row["epoch"],
            "lease_expires_at": row["lease_expires_at"],
        }

    finally:
        connection.close()