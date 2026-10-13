"""Create all database tables. Safe to run repeatedly (no-op if tables exist).

    uv run python scripts/init_db.py
"""

from app.db import init_db


def main() -> None:
    init_db()
    print("Database tables ready.")


if __name__ == "__main__":
    main()
