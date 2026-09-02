from dataclasses import dataclass

from app.catalog import get_message
from app.models import Dependent, User

# Onboarding state machine steps, in order. `complete` means onboarding is
# finished and free-form message handling takes over.
STEP_LANGUAGE = "language"
# Combines the broadcast opt-in with name collection in one message/reply —
# broadcast opt-in is a low-stakes preference (unlike personal_optin's
# admin-visibility disclosure or public_recognition_optin, which stay their
# own separate steps), and a name is needed either way, so asking both at
# once saves a round trip without blurring any consent.
STEP_BROADCAST_OPTIN = "broadcast_optin"
STEP_PERSONAL_OPTIN = "personal_optin"
STEP_PUBLIC_RECOGNITION_OPTIN = "public_recognition_optin"
STEP_FAMILY_MEMBERS = "family_members"
STEP_COMPLETE = "complete"

_YES_VALUES = {"yes", "y", "1", "હા"}
_NO_VALUES = {"no", "n", "0", "ના"}
_SKIP_FAMILY_MEMBERS_VALUES = {"none", "no", "n", "skip", "n/a", "na"}

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


def _parse_yes_no_and_name(body: str) -> tuple[bool, str] | None:
    """Parses a combined reply like "YES Bhavesh Shah" or "NO Bhavesh Shah"
    — the first word must be a yes/no value, everything after it is the
    name. Returns None if either half is missing/unrecognized."""
    parts = body.strip().split(maxsplit=1)
    if not parts:
        return None
    choice = _parse_yes_no(parts[0])
    if choice is None:
        return None
    name = parts[1].strip() if len(parts) > 1 else ""
    if not name:
        return None
    return choice, name


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
        parsed = _parse_yes_no_and_name(body)
        if parsed is None:
            return [get_message("invalid_broadcast_optin_and_name", lang)]
        choice, name = parsed
        user.broadcast_opt_in = choice
        user.display_name = name[:255]
        user.onboarding_step = STEP_PERSONAL_OPTIN
        ack_id = "broadcast_optin_yes_ack" if choice else "broadcast_optin_no_ack"
        return [
            get_message(ack_id, lang, name=user.display_name),
            get_message("ask_personal_optin", lang),
        ]

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
        ack = get_message(ack_id, lang)
        if user.personal_opt_in:
            user.onboarding_step = STEP_FAMILY_MEMBERS
            return [ack, get_message("ask_family_members", lang)]
        user.onboarding_step = STEP_COMPLETE
        return [ack, get_message("onboarding_complete", lang)]

    if step == STEP_FAMILY_MEMBERS:
        if body.strip().lower() in _SKIP_FAMILY_MEMBERS_VALUES:
            user.onboarding_step = STEP_COMPLETE
            return [get_message("onboarding_complete", lang)]
        names = [name.strip()[:255] for name in body.split(",") if name.strip()]
        if not names:
            return [get_message("ask_family_members", lang)]
        for name in names:
            user.dependents.append(Dependent(name=name))
        user.onboarding_step = STEP_COMPLETE
        return [
            get_message("family_members_added_ack", lang, names=", ".join(names)),
            get_message("onboarding_complete", lang),
        ]

    # Already complete — nothing for the state machine to do.
    return []
