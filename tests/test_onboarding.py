from app.models import User
from app.onboarding import (
    STEP_BROADCAST_OPTIN,
    STEP_COMPLETE,
    STEP_DISPLAY_NAME,
    STEP_LANGUAGE,
    STEP_PERSONAL_OPTIN,
    STEP_PUBLIC_RECOGNITION_OPTIN,
    handle_onboarding_reply,
    start_onboarding,
)


def _new_user() -> User:
    return User(phone="+15551234567")


def test_start_onboarding_asks_language():
    user = _new_user()
    replies = start_onboarding(user)
    assert user.onboarding_step == STEP_LANGUAGE
    assert len(replies) == 2


def test_invalid_language_choice_stays_on_step():
    user = _new_user()
    start_onboarding(user)
    replies = handle_onboarding_reply(user, "banana")
    assert user.onboarding_step == STEP_LANGUAGE
    assert len(replies) == 1


def test_language_choice_advances_to_broadcast_optin():
    user = _new_user()
    start_onboarding(user)
    handle_onboarding_reply(user, "2")
    assert user.language == "gu"
    assert user.onboarding_step == STEP_BROADCAST_OPTIN


def test_full_flow_with_public_recognition_collects_name():
    user = _new_user()
    start_onboarding(user)
    handle_onboarding_reply(user, "1")  # English
    assert user.onboarding_step == STEP_BROADCAST_OPTIN

    handle_onboarding_reply(user, "yes")
    assert user.broadcast_opt_in is True
    assert user.onboarding_step == STEP_PERSONAL_OPTIN

    handle_onboarding_reply(user, "yes")
    assert user.personal_opt_in is True
    assert user.onboarding_step == STEP_PUBLIC_RECOGNITION_OPTIN

    handle_onboarding_reply(user, "yes")
    assert user.public_recognition_optin is True
    assert user.onboarding_step == STEP_DISPLAY_NAME

    replies = handle_onboarding_reply(user, "Bhavesh Shah")
    assert user.display_name == "Bhavesh Shah"
    assert user.onboarding_step == STEP_COMPLETE
    assert "Bhavesh Shah" in replies[0]


def test_full_flow_without_public_recognition_skips_name_step():
    user = _new_user()
    start_onboarding(user)
    handle_onboarding_reply(user, "1")
    handle_onboarding_reply(user, "no")
    handle_onboarding_reply(user, "no")
    handle_onboarding_reply(user, "no")

    assert user.public_recognition_optin is False
    assert user.display_name is None
    assert user.onboarding_step == STEP_COMPLETE


def test_invalid_yes_no_reply_stays_on_step():
    user = _new_user()
    start_onboarding(user)
    handle_onboarding_reply(user, "1")
    replies = handle_onboarding_reply(user, "maybe")
    assert user.onboarding_step == STEP_BROADCAST_OPTIN
    assert len(replies) == 1


def test_complete_step_is_a_no_op():
    user = _new_user()
    user.onboarding_step = STEP_COMPLETE
    replies = handle_onboarding_reply(user, "hello")
    assert replies == []
    assert user.onboarding_step == STEP_COMPLETE
