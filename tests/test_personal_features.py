import datetime

from app.db import get_session
from app.models import Dependent, FastingLog, Reflection, User
from app.personal_features import _FLOW_EXPIRY, handle_post_onboarding_message


def _onboarded_user(session, personal_opt_in: bool = True) -> User:
    user = User(
        phone="+15550009999",
        language="en",
        onboarding_step="complete",
        personal_opt_in=personal_opt_in,
    )
    session.add(user)
    session.flush()
    return user


def test_personal_features_off_notice_when_opted_out():
    session = get_session()
    try:
        user = _onboarded_user(session, personal_opt_in=False)
        replies = handle_post_onboarding_message(session, user, "1")
        assert "opted out" in replies[0].lower()
    finally:
        session.close()


def test_menu_and_vow_toggle_work_even_when_opted_out():
    """Personal features (fast/reflection/family logging) require opt-in,
    but seeing the menu and toggling the vow don't — the vow isn't the
    same kind of personal data."""
    session = get_session()
    try:
        user = _onboarded_user(session, personal_opt_in=False)

        menu_replies = handle_post_onboarding_message(session, user, "menu")
        assert "log a fast" in menu_replies[0].lower()

        vow_replies = handle_post_onboarding_message(session, user, "4")
        assert user.vow_opt_in is True
        assert "vow" in vow_replies[0].lower()
    finally:
        session.close()


def test_unrecognized_message_shows_fallback_and_menu():
    session = get_session()
    try:
        user = _onboarded_user(session)
        replies = handle_post_onboarding_message(session, user, "random question")
        assert len(replies) == 2
        assert "didn't understand" in replies[0].lower()
        assert "log a fast" in replies[1].lower()
    finally:
        session.close()


def test_menu_keyword_shows_menu():
    session = get_session()
    try:
        user = _onboarded_user(session)
        replies = handle_post_onboarding_message(session, user, "menu")
        assert "log a fast" in replies[0].lower()
    finally:
        session.close()


def test_log_fast_flow_with_note():
    session = get_session()
    try:
        user = _onboarded_user(session)
        handle_post_onboarding_message(session, user, "1")
        assert user.active_flow == "fast_type"

        handle_post_onboarding_message(session, user, "Upvas")
        assert user.active_flow == "fast_note"

        replies = handle_post_onboarding_message(session, user, "Felt peaceful today")
        session.commit()

        assert user.active_flow is None
        assert "Upvas" in replies[0]

        log = session.query(FastingLog).filter(FastingLog.user_id == user.id).one()
        assert log.fast_type == "Upvas"
        assert log.note == "Felt peaceful today"
        assert log.dependent_id is None
    finally:
        session.close()


def test_log_fast_flow_skip_note():
    session = get_session()
    try:
        user = _onboarded_user(session)
        handle_post_onboarding_message(session, user, "fast")
        handle_post_onboarding_message(session, user, "Ekasana")
        handle_post_onboarding_message(session, user, "skip")
        session.commit()

        log = session.query(FastingLog).filter(FastingLog.user_id == user.id).one()
        assert log.fast_type == "Ekasana"
        assert log.note is None
    finally:
        session.close()


def test_log_reflection_flow():
    session = get_session()
    try:
        user = _onboarded_user(session)
        handle_post_onboarding_message(session, user, "2")
        assert user.active_flow == "reflection_text"

        replies = handle_post_onboarding_message(session, user, "Grateful for community today.")
        session.commit()

        assert user.active_flow is None
        assert "saved" in replies[0].lower()
        reflection = session.query(Reflection).filter(Reflection.user_id == user.id).one()
        assert reflection.text == "Grateful for community today."
    finally:
        session.close()


def test_family_member_fast_flow_with_note():
    session = get_session()
    try:
        user = _onboarded_user(session)
        handle_post_onboarding_message(session, user, "3")
        assert user.active_flow == "family_name"

        handle_post_onboarding_message(session, user, "Grandma Shah")
        assert user.active_flow == "family_action"

        handle_post_onboarding_message(session, user, "1")  # fast
        assert user.active_flow == "family_fast_type"

        handle_post_onboarding_message(session, user, "Upvas")
        assert user.active_flow == "family_fast_note"

        replies = handle_post_onboarding_message(session, user, "Felt strong")
        session.commit()

        assert user.active_flow is None
        assert "Grandma Shah" in replies[0]
        assert "Upvas" in replies[0]

        dependent = session.query(Dependent).filter(Dependent.guardian_id == user.id).one()
        assert dependent.name == "Grandma Shah"
        log = session.query(FastingLog).filter(FastingLog.dependent_id == dependent.id).one()
        assert log.user_id == user.id
        assert log.fast_type == "Upvas"
        assert log.note == "Felt strong"
    finally:
        session.close()


def test_family_member_reflection_flow():
    session = get_session()
    try:
        user = _onboarded_user(session)
        handle_post_onboarding_message(session, user, "3")
        handle_post_onboarding_message(session, user, "Little Priya")
        handle_post_onboarding_message(session, user, "2")  # reflection
        assert user.active_flow == "family_reflection_text"

        replies = handle_post_onboarding_message(session, user, "Priya enjoyed the story today.")
        session.commit()

        assert "Little Priya" in replies[0]
        dependent = session.query(Dependent).filter(Dependent.guardian_id == user.id).one()
        reflection = session.query(Reflection).filter(Reflection.dependent_id == dependent.id).one()
        assert reflection.text == "Priya enjoyed the story today."
    finally:
        session.close()


def test_family_member_reuses_existing_dependent_by_name():
    session = get_session()
    try:
        user = _onboarded_user(session)
        handle_post_onboarding_message(session, user, "3")
        handle_post_onboarding_message(session, user, "Grandma Shah")
        handle_post_onboarding_message(session, user, "1")
        handle_post_onboarding_message(session, user, "Upvas")
        handle_post_onboarding_message(session, user, "skip")
        session.commit()

        # Log a second entry for the same family member — should reuse
        # the same Dependent row, not create a second one.
        handle_post_onboarding_message(session, user, "3")
        handle_post_onboarding_message(session, user, "Grandma Shah")
        handle_post_onboarding_message(session, user, "2")
        handle_post_onboarding_message(session, user, "A quiet, peaceful day.")
        session.commit()

        dependents = session.query(Dependent).filter(Dependent.guardian_id == user.id).all()
        assert len(dependents) == 1
    finally:
        session.close()


def test_cancel_mid_flow():
    session = get_session()
    try:
        user = _onboarded_user(session)
        handle_post_onboarding_message(session, user, "1")
        assert user.active_flow == "fast_type"

        replies = handle_post_onboarding_message(session, user, "cancel")
        assert user.active_flow is None
        assert "cancelled" in replies[0].lower()
    finally:
        session.close()


def test_invalid_menu_choice_reprompts():
    session = get_session()
    try:
        user = _onboarded_user(session)
        replies = handle_post_onboarding_message(session, user, "xyz")
        assert user.active_flow is None
        assert "didn't understand" in replies[0].lower()
    finally:
        session.close()


def test_fast_note_attaches_to_the_row_that_started_the_flow():
    """Regression test: the note step used to look up "the user's most
    recent FastingLog," so a second, unrelated fast created while the
    first was still mid-flow would silently steal the note."""
    session = get_session()
    try:
        user = _onboarded_user(session)
        handle_post_onboarding_message(session, user, "1")
        handle_post_onboarding_message(session, user, "Upvas")
        first_log_id = user.active_flow_row_id
        session.commit()

        # A second, unrelated fast log appears for this user before they
        # answer the note prompt (e.g. logged some other way).
        session.add(FastingLog(user_id=user.id, date=datetime.date.today(), fast_type="Ekasana"))
        session.commit()

        replies = handle_post_onboarding_message(session, user, "Felt peaceful")
        session.commit()

        assert "Upvas" in replies[0]
        first_log = session.get(FastingLog, first_log_id)
        assert first_log.note == "Felt peaceful"

        unrelated_log = (
            session.query(FastingLog)
            .filter(FastingLog.user_id == user.id, FastingLog.fast_type == "Ekasana")
            .one()
        )
        assert unrelated_log.note is None
    finally:
        session.close()


def test_abandoned_flow_expires_instead_of_swallowing_a_later_message():
    session = get_session()
    try:
        user = _onboarded_user(session)
        handle_post_onboarding_message(session, user, "1")
        handle_post_onboarding_message(session, user, "Upvas")
        assert user.active_flow == "fast_note"
        session.commit()

        # Simulate the user going quiet well past the expiry window, then
        # sending an unrelated message later.
        user.active_flow_started_at = datetime.datetime.utcnow() - _FLOW_EXPIRY - datetime.timedelta(minutes=1)
        session.commit()

        replies = handle_post_onboarding_message(session, user, "2")
        session.commit()

        # Treated as a fresh menu selection (reflection), not a note on
        # the abandoned fast log.
        assert user.active_flow == "reflection_text"
        assert "reflection" in replies[0].lower()

        log = session.query(FastingLog).filter(FastingLog.user_id == user.id).one()
        assert log.note is None
    finally:
        session.close()
