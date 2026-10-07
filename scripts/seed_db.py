from server.app.database import get_connection, initialize_database


INITIAL_ACCOUNTS = [
    ("A1001", 1000),
    ("A1002", 2000),
    ("A1003", 500),
]


def seed_database() -> None:
    initialize_database()

    with get_connection() as connection:
        connection.executemany(
            """
            INSERT OR IGNORE INTO accounts (account_id, balance)
            VALUES (?, ?)
            """,
            INITIAL_ACCOUNTS,
        )
        connection.commit()


if __name__ == "__main__":
    seed_database()
    print("Database initialized and seeded successfully.")