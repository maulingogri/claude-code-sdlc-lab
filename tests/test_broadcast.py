import datetime

from app.broadcast import build_broadcast_text, send_daily_broadcast
from app.db import get_session
from app.models import Broadcast, FastingLog, User


def test_build_broadcast_text_includes_recognition_names():
    session = get_session()
    try:
        user = User(
            phone="+15550001111",
            language="en",
            public_recognition_optin=True,
            display_name="Kavita Shah",
        )
        session.add(user)
        session.flush()

        broadcast_date = datetime.date(2026, 9, 9)
        yesterday = broadcast_date - datetime.timedelta(days=1)
        session.add(FastingLog(user_id=user.id, date=yesterday, fast_type="upvas"))

        broadcast = Broadcast(
            date=broadcast_date,
            day_number=2,
            theme_en="Compassion",
            theme_gu="કરુણા",
            pratikraman_timing="7:00 PM",
            announcements_en="",
            announcements_gu="",
        )
        session.add(broadcast)
        session.commit()

        text = build_broadcast_text(session, broadcast, "en")
        assert "Kavita Shah" in text
        assert "Day 2" in text
    finally:
        session.close()


def test_send_daily_broadcast_skips_when_no_content(monkeypatch):
    monkeypatch.setattr("app.broadcast._today", lambda tz: datetime.date(2099, 1, 1))
    session = get_session()
    try:
        result = send_daily_broadcast(session)
        assert result == {"sent": 0, "failed": 0, "skipped_no_content": 1}
    finally:
        session.close()
