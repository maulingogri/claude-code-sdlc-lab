"""Create or update a day's broadcast content.

Stand-in for the admin dashboard's Content tab (Build Order step 6, not yet
built). Lets us test the daily broadcast cron end-to-end in Stage 1.

Usage:
    uv run python scripts/seed_broadcast.py \\
        --date 2026-09-08 --day-number 1 \\
        --theme-en "Compassion" --theme-gu "કરુણા" \\
        --pratikraman-timing "7:00 PM" \\
        --announcements-en "Please arrive 15 min early." \\
        --announcements-gu "કૃપા કરી 15 મિનિટ વહેલા આવો."
"""

import argparse
import datetime

from app.db import get_session, init_db
from app.models import Broadcast


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--day-number", required=True, type=int)
    parser.add_argument("--theme-en", required=True)
    parser.add_argument("--theme-gu", required=True)
    parser.add_argument("--pratikraman-timing", required=True)
    parser.add_argument("--announcements-en", default="")
    parser.add_argument("--announcements-gu", default="")
    args = parser.parse_args()

    init_db()
    session = get_session()
    try:
        date = datetime.date.fromisoformat(args.date)
        broadcast = session.query(Broadcast).filter(Broadcast.date == date).one_or_none()
        if broadcast is None:
            broadcast = Broadcast(date=date)
            session.add(broadcast)

        broadcast.day_number = args.day_number
        broadcast.theme_en = args.theme_en
        broadcast.theme_gu = args.theme_gu
        broadcast.pratikraman_timing = args.pratikraman_timing
        broadcast.announcements_en = args.announcements_en
        broadcast.announcements_gu = args.announcements_gu

        session.commit()
        print(f"Broadcast content saved for {date.isoformat()} (day {args.day_number}).")
    finally:
        session.close()


if __name__ == "__main__":
    main()
