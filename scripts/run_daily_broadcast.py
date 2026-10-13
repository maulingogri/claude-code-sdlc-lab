"""Cron entrypoint for the daily Paryushan broadcast.

Run once a day (Railway cron) via:
    uv run python scripts/run_daily_broadcast.py
"""

from app.broadcast import send_daily_broadcast
from app.db import get_session, init_db


def main() -> None:
    init_db()
    session = get_session()
    try:
        result = send_daily_broadcast(session)
        print(result)
    finally:
        session.close()


if __name__ == "__main__":
    main()
