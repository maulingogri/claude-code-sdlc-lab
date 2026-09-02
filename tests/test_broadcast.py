import datetime
from unittest.mock import patch

from app.broadcast import (
    _group_relay_recipients,
    _individual_activity_section,
    _pick_vow_for_user,
    _recognition_names,
    build_group_text,
    build_individual_text,
    send_daily_broadcast,
)
from app.db import get_session
from app.models import Broadcast, Dependent, FastingLog, User, Vow, VowAssignment


def test_build_individual_text_includes_recognition_names():
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

        today = datetime.date(2026, 9, 9)
        yesterday = today - datetime.timedelta(days=1)
        session.add(FastingLog(user_id=user.id, date=yesterday, fast_type="upvas"))

        broadcast = Broadcast(
            date=today,
            day_number=2,
            individual_message_en="Today's theme: Compassion.",
            group_message_en="",
        )
        session.add(broadcast)
        session.commit()

        text = build_individual_text(session, broadcast, user, yesterday, today)
        assert "Kavita Shah" in text
        assert "Today's theme: Compassion." in text
    finally:
        session.close()


def test_build_individual_text_includes_dependent_names_when_guardian_opted_in():
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

        today = datetime.date(2026, 9, 9)
        yesterday = today - datetime.timedelta(days=1)
        session.add(
            FastingLog(user_id=guardian.id, dependent_id=dependent.id, date=yesterday, fast_type="Upvas")
        )

        broadcast = Broadcast(date=today, day_number=2, individual_message_en="Compassion.", group_message_en="")
        session.add(broadcast)
        session.commit()

        text = build_individual_text(session, broadcast, guardian, yesterday, today)
        assert "Grandma Shah" in text
    finally:
        session.close()


def test_recognition_names_excludes_dependent_when_guardian_not_opted_in():
    """The PUBLIC recognition list excludes her — a separate assertion
    from the guardian's own personal activity section (tested below),
    which still shows her to the guardian regardless of the guardian's
    public-recognition choice, since that's the guardian's own data being
    shown back to them, not published to anyone else."""
    session = get_session()
    try:
        guardian = User(phone="+15550003333", language="en", public_recognition_optin=False)
        session.add(guardian)
        session.flush()
        dependent = Dependent(guardian_id=guardian.id, name="Little Priya")
        session.add(dependent)
        session.flush()

        yesterday = datetime.date(2026, 9, 8)
        session.add(
            FastingLog(user_id=guardian.id, dependent_id=dependent.id, date=yesterday, fast_type="Upvas")
        )
        session.commit()

        assert "Little Priya" not in _recognition_names(session, yesterday)
    finally:
        session.close()


def test_build_individual_text_still_shows_own_family_activity_when_not_publicly_opted_in():
    session = get_session()
    try:
        guardian = User(phone="+15550003334", language="en", public_recognition_optin=False)
        session.add(guardian)
        session.flush()
        dependent = Dependent(guardian_id=guardian.id, name="Little Priya")
        session.add(dependent)
        session.flush()

        today = datetime.date(2026, 9, 9)
        yesterday = today - datetime.timedelta(days=1)
        session.add(
            FastingLog(user_id=guardian.id, dependent_id=dependent.id, date=yesterday, fast_type="Upvas")
        )

        broadcast = Broadcast(date=today, day_number=2, individual_message_en="Compassion.", group_message_en="")
        session.add(broadcast)
        session.commit()

        text = build_individual_text(session, broadcast, guardian, yesterday, today)
        assert "Little Priya: Upvas" in text
    finally:
        session.close()


def test_build_individual_text_translates_to_gujarati():
    session = get_session()
    try:
        user = User(phone="+15550003344", language="gu")
        session.add(user)
        session.flush()

        today = datetime.date(2026, 9, 9)
        yesterday = today - datetime.timedelta(days=1)
        broadcast = Broadcast(
            date=today, day_number=2, individual_message_en="Hello there.", group_message_en=""
        )
        session.add(broadcast)
        session.commit()

        with patch("app.broadcast.translate_to_gujarati", return_value="ગુજ text") as mock_translate:
            text = build_individual_text(session, broadcast, user, yesterday, today)
        mock_translate.assert_called_once_with("Hello there.")
        assert "ગુજ text" in text
    finally:
        session.close()


def test_build_group_text_combines_english_and_gujarati():
    session = get_session()
    try:
        today = datetime.date(2026, 9, 9)
        yesterday = today - datetime.timedelta(days=1)
        broadcast = Broadcast(
            date=today, day_number=2, individual_message_en="", group_message_en="Group update."
        )
        session.add(broadcast)
        session.commit()

        with patch("app.broadcast.translate_to_gujarati", return_value="ગુજ સંદેશ") as mock_translate:
            text = build_group_text(session, broadcast, yesterday)
        mock_translate.assert_called_once_with("Group update.")
        assert "Group update." in text
        assert "ગુજ સંદેશ" in text
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
            Broadcast(date=today, day_number=3, individual_message_en="Compassion.", group_message_en="")
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


def test_individual_activity_section_lists_self_and_family_fasts():
    session = get_session()
    try:
        user = User(phone="+15550007777", language="en")
        session.add(user)
        session.flush()
        dependent = Dependent(guardian_id=user.id, name="Grandma Shah")
        session.add(dependent)
        session.flush()

        yesterday = datetime.date(2026, 9, 9)
        session.add(FastingLog(user_id=user.id, date=yesterday, fast_type="Upvas"))
        session.add(
            FastingLog(user_id=user.id, dependent_id=dependent.id, date=yesterday, fast_type="Ekasana")
        )
        session.commit()

        text = _individual_activity_section(session, user, yesterday, "en")
        assert "You: Upvas" in text
        assert "Grandma Shah: Ekasana" in text
    finally:
        session.close()


def test_individual_activity_section_empty_when_nothing_logged():
    session = get_session()
    try:
        user = User(phone="+15550008888", language="en")
        session.add(user)
        session.commit()

        text = _individual_activity_section(session, user, datetime.date(2026, 9, 9), "en")
        assert text == ""
    finally:
        session.close()


def test_group_relay_recipients_returns_only_flagged_users():
    session = get_session()
    try:
        relay = User(phone="+15550009999", is_group_relay=True)
        session.add(relay)
        session.add(User(phone="+15550001010", is_group_relay=False))
        session.commit()

        recipients = _group_relay_recipients(session)
        assert [u.id for u in recipients] == [relay.id]
    finally:
        session.close()


def test_send_daily_broadcast_sends_individual_and_group_messages():
    session = get_session()
    try:
        individual_user = User(
            phone="+15550002020", language="en", broadcast_opt_in=True, display_name="Bhavesh"
        )
        # Relay user is NOT broadcast_opt_in — the Group send must still
        # reach them, since being the relay is an assigned role, not a
        # personal content preference.
        relay_user = User(phone="+15550003030", broadcast_opt_in=False, is_group_relay=True)
        session.add_all([individual_user, relay_user])
        session.flush()

        today = datetime.date(2026, 9, 10)
        yesterday = today - datetime.timedelta(days=1)
        session.add(FastingLog(user_id=individual_user.id, date=yesterday, fast_type="Upvas"))
        session.add(
            Broadcast(
                date=today,
                day_number=3,
                individual_message_en="Individual intro.",
                group_message_en="Group intro.",
            )
        )
        session.commit()

        with patch("app.broadcast._today", return_value=today):
            with patch("app.broadcast.send_whatsapp_message") as mock_send:
                result = send_daily_broadcast(session)

        assert result == {"sent": 2, "failed": 0, "skipped_no_content": 0}
        calls = {call.args[0]: call.args[1] for call in mock_send.call_args_list}

        assert "You: Upvas" in calls[individual_user.phone]
        assert "Individual intro." in calls[individual_user.phone]
        assert "You: Upvas" not in calls[relay_user.phone]
        assert "Group intro." in calls[relay_user.phone]
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
