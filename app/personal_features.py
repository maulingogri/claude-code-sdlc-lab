from sqlalchemy.orm import Session

from app.catalog import get_message
from app.models import FastingLog, ForgivenessListEntry, Reflection, User
from app.timeutils import today_in_tz

FLOW_FAST_TYPE = "fast_type"
FLOW_FAST_NOTE = "fast_note"
FLOW_REFLECTION_TEXT = "reflection_text"
FLOW_FORGIVENESS_NAME = "forgiveness_name"
FLOW_FORGIVENESS_NOTE = "forgiveness_note"

_CANCEL_VALUES = {"cancel", "રદ"}
_SKIP_VALUES = {"skip", "no", "no note", "-"}

_MENU_CHOICES = {
    "1": FLOW_FAST_TYPE,
    "fast": FLOW_FAST_TYPE,
    "log a fast": FLOW_FAST_TYPE,
    "તપસ્યા": FLOW_FAST_TYPE,
    "2": FLOW_REFLECTION_TEXT,
    "reflect": FLOW_REFLECTION_TEXT,
    "reflection": FLOW_REFLECTION_TEXT,
    "ચિંતન": FLOW_REFLECTION_TEXT,
    "3": FLOW_FORGIVENESS_NAME,
    "forgive": FLOW_FORGIVENESS_NAME,
    "forgiveness": FLOW_FORGIVENESS_NAME,
    "ક્ષમાપના": FLOW_FORGIVENESS_NAME,
}

_MENU_KEYWORDS = {"menu", "help", "4", "મેનુ"}


def _is_cancel(body: str) -> bool:
    return body.strip().lower() in _CANCEL_VALUES


def _is_skip(body: str) -> bool:
    return body.strip().lower() in _SKIP_VALUES


def handle_post_onboarding_message(session: Session, user: User, body: str) -> list[str]:
    """Route a free-form message from an onboarded user: continue an
    in-progress flow (fast/reflection/forgiveness entry), start a new one
    from the menu, or show the menu. Mutates `user` and writes rows via
    `session`; caller commits."""
    lang = user.language or "en"

    if not user.personal_opt_in:
        return [get_message("personal_features_off_notice", lang)]

    if user.active_flow is None:
        return _handle_menu_selection(user, body, lang)

    if _is_cancel(body):
        user.active_flow = None
        return [get_message("flow_cancelled", lang)]

    return _continue_flow(session, user, body, lang)


def _handle_menu_selection(user: User, body: str, lang: str) -> list[str]:
    choice = body.strip().lower()
    if choice in _MENU_KEYWORDS:
        return [get_message("post_onboarding_menu", lang)]

    flow = _MENU_CHOICES.get(choice)
    if flow is None:
        return [
            get_message("invalid_menu_choice", lang),
            get_message("post_onboarding_menu", lang),
        ]

    user.active_flow = flow
    if flow == FLOW_FAST_TYPE:
        return [get_message("ask_fast_type", lang)]
    if flow == FLOW_REFLECTION_TEXT:
        return [get_message("ask_reflection_text", lang)]
    if flow == FLOW_FORGIVENESS_NAME:
        return [get_message("ask_forgiveness_name", lang)]
    raise AssertionError(f"unhandled flow {flow!r}")  # pragma: no cover


def _continue_flow(session: Session, user: User, body: str, lang: str) -> list[str]:
    step = user.active_flow

    if step == FLOW_FAST_TYPE:
        fast_type = body.strip()
        if not fast_type:
            return [get_message("ask_fast_type", lang)]
        session.add(
            FastingLog(
                user_id=user.id,
                date=today_in_tz(user.timezone),
                fast_type=fast_type,
            )
        )
        session.flush()
        user.active_flow = FLOW_FAST_NOTE
        return [get_message("ask_fast_note", lang)]

    if step == FLOW_FAST_NOTE:
        log = (
            session.query(FastingLog)
            .filter(FastingLog.user_id == user.id)
            .order_by(FastingLog.id.desc())
            .first()
        )
        if not _is_skip(body):
            log.note = body.strip()
        user.active_flow = None
        return [get_message("fast_logged_ack", lang, fast_type=log.fast_type)]

    if step == FLOW_REFLECTION_TEXT:
        text = body.strip()
        if not text:
            return [get_message("ask_reflection_text", lang)]
        session.add(Reflection(user_id=user.id, date=today_in_tz(user.timezone), text=text))
        user.active_flow = None
        return [get_message("reflection_saved_ack", lang)]

    if step == FLOW_FORGIVENESS_NAME:
        name = body.strip()
        if not name:
            return [get_message("ask_forgiveness_name", lang)]
        session.add(ForgivenessListEntry(user_id=user.id, name=name))
        session.flush()
        user.active_flow = FLOW_FORGIVENESS_NOTE
        return [get_message("ask_forgiveness_note", lang)]

    if step == FLOW_FORGIVENESS_NOTE:
        entry = (
            session.query(ForgivenessListEntry)
            .filter(ForgivenessListEntry.user_id == user.id)
            .order_by(ForgivenessListEntry.id.desc())
            .first()
        )
        if not _is_skip(body):
            entry.relationship_note = body.strip()
        user.active_flow = None
        return [get_message("forgiveness_saved_ack", lang, name=entry.name)]

    # Unknown/stale flow value — reset rather than get the user stuck.
    user.active_flow = None
    return [get_message("post_onboarding_menu", lang)]
