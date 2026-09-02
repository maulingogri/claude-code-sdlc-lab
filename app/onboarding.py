from dataclasses import dataclass

from app.catalog import get_message
from app.models import User

# Onboarding state machine steps, in order. `complete` means onboarding is
# finished and free-form message handling takes over.
STEP_LANGUAGE = "language"
STEP_BROADCAST_OPTIN = "broadcast_optin"
STEP_PERSONAL_OPTIN = "personal_optin"
STEP_PUBLIC_RECOGNITION_OPTIN = "public_recognition_optin"
STEP_DISPLAY_NAME = "display_name"
STEP_COMPLETE = "complete"

_YES_VALUES = {"yes", "y", "1", "હા"}
_NO_VALUES = {"no", "n", "0", "ના"}

_LANGUAGE_VALUES = {
    "1": "en",
    "english": "en",
    "en": "en",
    "2": "gu",
    "gujarati": "gu",
    "gu": "gu",
    "ગુજરાતી": "gu",
}


@dataclass
class OnboardingResult:
    replies: list[str]
    is_new_state: str


def _parse_yes_no(body: str) -> bool | None:
    normalized = body.strip().lower()
    if normalized in _YES_VALUES:
        return True
    if normalized in _NO_VALUES:
        return False
    return None


def _parse_language(body: str) -> str | None:
    return _LANGUAGE_VALUES.get(body.strip().lower())


def start_onboarding(user: User) -> list[str]:
    """First contact with a brand-new user: greet them (in English, since we
    don't know their language yet) and ask for a language choice."""
    user.onboarding_step = STEP_LANGUAGE
    return [get_message("greeting", "en"), get_message("ask_language", "en")]


def handle_onboarding_reply(user: User, body: str) -> list[str]:
    """Advance the onboarding state machine by one step based on the user's
    reply. Mutates `user` in place; caller is responsible for committing.
    Returns the list of WhatsApp messages to send back, in order."""
    lang = user.language or "en"
    step = user.onboarding_step

    if step == STEP_LANGUAGE:
        choice = _parse_language(body)
        if choice is None:
            return [get_message("invalid_language_choice", lang)]
        user.language = choice
        user.onboarding_step = STEP_BROADCAST_OPTIN
        return [
            get_message("language_confirmed", choice),
            get_message("ask_broadcast_optin", choice),
        ]

    if step == STEP_BROADCAST_OPTIN:
        choice = _parse_yes_no(body)
        if choice is None:
            return [get_message("invalid_yes_no_choice", lang)]
        user.broadcast_opt_in = choice
        user.onboarding_step = STEP_PERSONAL_OPTIN
        ack_id = "broadcast_optin_yes_ack" if choice else "broadcast_optin_no_ack"
        return [get_message(ack_id, lang), get_message("ask_personal_optin", lang)]

    if step == STEP_PERSONAL_OPTIN:
        choice = _parse_yes_no(body)
        if choice is None:
            return [get_message("invalid_yes_no_choice", lang)]
        user.personal_opt_in = choice
        user.onboarding_step = STEP_PUBLIC_RECOGNITION_OPTIN
        ack_id = "personal_optin_yes_ack" if choice else "personal_optin_no_ack"
        return [get_message(ack_id, lang), get_message("ask_public_recognition_optin", lang)]

    if step == STEP_PUBLIC_RECOGNITION_OPTIN:
        choice = _parse_yes_no(body)
        if choice is None:
            return [get_message("invalid_yes_no_choice", lang)]
        user.public_recognition_optin = choice
        ack_id = "public_recognition_yes_ack" if choice else "public_recognition_no_ack"
        if choice:
            user.onboarding_step = STEP_DISPLAY_NAME
            return [get_message(ack_id, lang), get_message("ask_display_name", lang)]
        user.onboarding_step = STEP_COMPLETE
        return [get_message(ack_id, lang), get_message("onboarding_complete", lang)]

    if step == STEP_DISPLAY_NAME:
        name = body.strip()
        if not name:
            return [get_message("ask_display_name", lang)]
        user.display_name = name[:255]
        user.onboarding_step = STEP_COMPLETE
        return [
            get_message("display_name_ack", lang, name=user.display_name),
            get_message("onboarding_complete", lang),
        ]

    # Already complete — nothing for the state machine to do.
    return []
