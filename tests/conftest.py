import pytest

from server.app.core.config import settings
from server.app.database import get_connection, initialize_database


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    test_db_path = tmp_path / "test_bank.db"

    monkeypatch.setattr(
        settings,
        "db_path",
        str(test_db_path),
    )

    initialize_database()

    with get_connection() as connection:
        connection.executemany(
            """
            INSERT INTO accounts (account_id, balance)
            VALUES (?, ?)
            """,
            [
                ("A1001", 1000),
                ("A1002", 2000),
                ("A1003", 500),
            ],
        )
        connection.commit()

    return test_db_path