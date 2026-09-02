import datetime
from unittest.mock import patch

from app.broadcast import _pick_vow_for_user, build_broadcast_text, send_daily_broadcast
from app.db import get_session
from app.models import Broadcast, Dependent, FastingLog, User, Vow, VowAssignment


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


def test_build_broadcast_text_includes_dependent_names_when_guardian_opted_in():
    session = get_session()
    try:
        guardian = User(
            phone="+15550002222",
            language="en",
            public_recognition_optin=True,
            display_name="Guardian Name",
        )
        session.add(guardian)
        session.flush()
        dependent = Dependent(guardian_id=guardian.id, name="Grandma Shah")
        session.add(dependent)
        session.flush()

        broadcast_date = datetime.date(2026, 9, 9)
        yesterday = broadcast_date - datetime.timedelta(days=1)
        session.add(
            FastingLog(user_id=guardian.id, dependent_id=dependent.id, date=yesterday, fast_type="Upvas")
        )

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
        assert "Grandma Shah" in text
    finally:
        session.close()


def test_build_broadcast_text_excludes_dependent_names_when_guardian_not_opted_in():
    session = get_session()
    try:
        guardian = User(phone="+15550003333", language="en", public_recognition_optin=False)
        session.add(guardian)
        session.flush()
        dependent = Dependent(guardian_id=guardian.id, name="Little Priya")
        session.add(dependent)
        session.flush()

        broadcast_date = datetime.date(2026, 9, 9)
        yesterday = broadcast_date - datetime.timedelta(days=1)
        session.add(
            FastingLog(user_id=guardian.id, dependent_id=dependent.id, date=yesterday, fast_type="Upvas")
        )

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
        assert "Little Priya" not in text
    finally:
        session.close()


def test_pick_vow_for_user_avoids_repeats_until_pool_exhausted():
    session = get_session()
    try:
        user = User(phone="+15550004444", language="en", vow_opt_in=True)
        session.add(user)
        session.flush()

        vow1 = Vow(text_en="Vow one", text_gu="", approved=True)
        vow2 = Vow(text_en="Vow two", text_gu="", approved=True)
        session.add_all([vow1, vow2])
        session.flush()

        session.add(VowAssignment(user_id=user.id, vow_id=vow1.id, date=datetime.date(2026, 9, 8)))
        session.commit()

        # Only vow2 is unused, so the pick must be deterministic even
        # though _pick_vow_for_user uses random.choice internally.
        for _ in range(5):
            picked = _pick_vow_for_user(session, user)
            assert picked.id == vow2.id
    finally:
        session.close()


def test_pick_vow_for_user_returns_none_when_no_approved_vows():
    session = get_session()
    try:
        user = User(phone="+15550005555", language="en", vow_opt_in=True)
        session.add(user)
        session.add(Vow(text_en="Unapproved", text_gu="", approved=False))
        session.commit()

        assert _pick_vow_for_user(session, user) is None
    finally:
        session.close()


def test_send_daily_broadcast_appends_vow_for_opted_in_user():
    session = get_session()
    try:
        user = User(phone="+15550006666", language="en", broadcast_opt_in=True, vow_opt_in=True)
        session.add(user)
        vow = Vow(text_en="Today, I will speak kindly.", text_gu="", approved=True)
        session.add(vow)

        today = datetime.date(2026, 9, 10)
        session.add(
            Broadcast(
                date=today,
                day_number=3,
                theme_en="Compassion",
                theme_gu="કરુણા",
                pratikraman_timing="7:00 PM",
            )
        )
        session.commit()

        with patch("app.broadcast._today", return_value=today):
            with patch("app.broadcast.send_whatsapp_message") as mock_send:
                result = send_daily_broadcast(session)

        assert result["sent"] == 1
        sent_text = mock_send.call_args_list[0][0][1]
        assert "Today, I will speak kindly." in sent_text

        assignment = session.query(VowAssignment).filter(VowAssignment.user_id == user.id).one()
        assert assignment.vow_id == vow.id
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
