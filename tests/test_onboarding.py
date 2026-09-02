from app.models import Dependent, User
from app.onboarding import (
    STEP_BROADCAST_OPTIN,
    STEP_COMPLETE,
    STEP_FAMILY_MEMBERS,
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


def test_broadcast_optin_and_name_combined_reply():
    """Broadcast opt-in and name are collected in one message/reply — a
    low-stakes preference paired with something needed either way, unlike
    personal_optin/public_recognition_optin which carry their own distinct
    consent disclosures and stay separate steps."""
    user = _new_user()
    start_onboarding(user)
    handle_onboarding_reply(user, "1")  # English

    replies = handle_onboarding_reply(user, "YES Bhavesh Shah")
    assert user.broadcast_opt_in is True
    assert user.display_name == "Bhavesh Shah"
    assert user.onboarding_step == STEP_PERSONAL_OPTIN
    assert "Bhavesh Shah" in replies[0]


def test_broadcast_optin_no_still_collects_name():
    user = _new_user()
    start_onboarding(user)
    handle_onboarding_reply(user, "1")

    handle_onboarding_reply(user, "NO Kavita Mehta")
    assert user.broadcast_opt_in is False
    assert user.display_name == "Kavita Mehta"
    assert user.onboarding_step == STEP_PERSONAL_OPTIN


def test_broadcast_optin_missing_name_reprompts():
    user = _new_user()
    start_onboarding(user)
    handle_onboarding_reply(user, "1")

    replies = handle_onboarding_reply(user, "yes")
    assert user.onboarding_step == STEP_BROADCAST_OPTIN
    assert user.display_name is None
    assert len(replies) == 1


def test_broadcast_optin_unrecognized_choice_reprompts():
    user = _new_user()
    start_onboarding(user)
    handle_onboarding_reply(user, "1")

    replies = handle_onboarding_reply(user, "Bhavesh Shah")  # no YES/NO first
    assert user.onboarding_step == STEP_BROADCAST_OPTIN
    assert len(replies) == 1


def test_public_recognition_always_advances_to_family_members_or_complete():
    for recognition_choice in ["yes", "no"]:
        user = _new_user()
        start_onboarding(user)
        handle_onboarding_reply(user, "1")
        handle_onboarding_reply(user, "YES Bhavesh Shah")
        handle_onboarding_reply(user, "yes")  # personal features
        handle_onboarding_reply(user, recognition_choice)
        assert user.onboarding_step == STEP_FAMILY_MEMBERS


def test_full_flow_with_personal_features_asks_for_family_members():
    user = _new_user()
    start_onboarding(user)
    handle_onboarding_reply(user, "1")  # English
    handle_onboarding_reply(user, "YES Bhavesh Shah")  # broadcast + name
    assert user.display_name == "Bhavesh Shah"
    handle_onboarding_reply(user, "yes")  # personal features

    replies = handle_onboarding_reply(user, "yes")  # public recognition
    assert user.onboarding_step == STEP_FAMILY_MEMBERS

    replies = handle_onboarding_reply(user, "Grandma Shah, Little Priya")
    assert user.onboarding_step == STEP_COMPLETE
    assert [d.name for d in user.dependents] == ["Grandma Shah", "Little Priya"]
    assert isinstance(user.dependents[0], Dependent)
    assert "Grandma Shah" in replies[0]
    assert "Little Priya" in replies[0]
    assert "onboarding complete" in replies[1].lower()


def test_family_members_step_skipped_with_none():
    user = _new_user()
    start_onboarding(user)
    handle_onboarding_reply(user, "1")
    handle_onboarding_reply(user, "YES Bhavesh Shah")
    handle_onboarding_reply(user, "yes")
    handle_onboarding_reply(user, "no")  # public recognition
    assert user.onboarding_step == STEP_FAMILY_MEMBERS

    replies = handle_onboarding_reply(user, "none")
    assert user.onboarding_step == STEP_COMPLETE
    assert user.dependents == []
    assert "onboarding complete" in replies[0].lower()


def test_family_members_step_reprompts_on_empty_reply():
    user = _new_user()
    start_onboarding(user)
    handle_onboarding_reply(user, "1")
    handle_onboarding_reply(user, "YES Bhavesh Shah")
    handle_onboarding_reply(user, "yes")
    handle_onboarding_reply(user, "no")

    replies = handle_onboarding_reply(user, "   ,  ,")
    assert user.onboarding_step == STEP_FAMILY_MEMBERS
    assert user.dependents == []
    assert len(replies) == 1


def test_full_flow_without_personal_features_skips_family_members_step():
    user = _new_user()
    start_onboarding(user)
    handle_onboarding_reply(user, "1")
    handle_onboarding_reply(user, "NO Bhavesh Shah")  # broadcast + name
    handle_onboarding_reply(user, "no")  # personal features

    replies = handle_onboarding_reply(user, "no")  # public recognition
    assert user.onboarding_step == STEP_COMPLETE
    assert "onboarding complete" in replies[1].lower()


def test_invalid_yes_no_reply_stays_on_step():
    user = _new_user()
    start_onboarding(user)
    handle_onboarding_reply(user, "1")
    handle_onboarding_reply(user, "YES Bhavesh Shah")
    replies = handle_onboarding_reply(user, "maybe")
    assert user.onboarding_step == STEP_PERSONAL_OPTIN
    assert len(replies) == 1


def test_complete_step_is_a_no_op():
    user = _new_user()
    user.onboarding_step = STEP_COMPLETE
    replies = handle_onboarding_reply(user, "hello")
    assert replies == []
    assert user.onboarding_step == STEP_COMPLETE
