import datetime

from sqlalchemy.orm import Session

from app.catalog import get_message
from app.models import Dependent, FastingLog, Reflection, User
from app.timeutils import today_in_tz

FLOW_FAST_TYPE = "fast_type"
FLOW_FAST_FOR_WHOM = "fast_for_whom"
FLOW_FAST_NOTE = "fast_note"
FLOW_REFLECTION_TEXT = "reflection_text"
FLOW_REFLECTION_FOR_WHOM = "reflection_for_whom"

# An abandoned flow (user never sent a note, then went quiet) shouldn't
# silently swallow a much-later, unrelated message as if it were the
# answer. 30 minutes generously covers a real pause mid-conversation
# without leaving the state active for days.
_FLOW_EXPIRY = datetime.timedelta(minutes=30)

_CANCEL_VALUES = {"cancel", "રદ"}
_SKIP_VALUES = {"skip", "no", "no note", "-"}
_SELF_VALUES = {"you", "me", "myself", "self"}

_MENU_CHOICES = {
    "1": FLOW_FAST_TYPE,
    "fast": FLOW_FAST_TYPE,
    "log a fast": FLOW_FAST_TYPE,
    "તપસ્યા": FLOW_FAST_TYPE,
    "2": FLOW_REFLECTION_TEXT,
    "reflect": FLOW_REFLECTION_TEXT,
    "reflection": FLOW_REFLECTION_TEXT,
    "ચિંતન": FLOW_REFLECTION_TEXT,
}

_MENU_KEYWORDS = {"menu", "help", "4", "મેનુ"}
_VOW_TOGGLE_VALUES = {"3", "vow"}


def _is_cancel(body: str) -> bool:
    return body.strip().lower() in _CANCEL_VALUES


def _is_skip(body: str) -> bool:
    return body.strip().lower() in _SKIP_VALUES


def _clear_flow(user: User) -> None:
    user.active_flow = None
    user.active_flow_row_id = None
    user.active_flow_dependent_id = None
    user.active_flow_started_at = None


def _start_flow(user: User, flow: str, row_id: int | None = None, dependent_id: int | None = None) -> None:
    user.active_flow = flow
    user.active_flow_row_id = row_id
    user.active_flow_dependent_id = dependent_id
    user.active_flow_started_at = datetime.datetime.utcnow()


def _flow_expired(user: User) -> bool:
    if user.active_flow_started_at is None:
        return False  # pre-existing row from before this field existed
    return datetime.datetime.utcnow() - user.active_flow_started_at > _FLOW_EXPIRY


def _menu_text(user: User, lang: str) -> str:
    vow_status = "ON" if user.vow_opt_in else "OFF"
    return get_message("post_onboarding_menu", lang, vow_status=vow_status)


def handle_post_onboarding_message(session: Session, user: User, body: str) -> list[str]:
    """Route a free-form message from an onboarded user: continue an
    in-progress flow (fast/reflection entry), start a new one from the
    menu, toggle the daily vow, or show the menu. Mutates `user` and
    writes rows via `session`; caller commits."""
    lang = user.language or "en"

    if user.active_flow is not None and _flow_expired(user):
        # The user went quiet mid-flow; don't let a much-later, unrelated
        # message get silently swallowed as if it answered a question they
        # probably don't remember being asked.
        _clear_flow(user)

    if user.active_flow is None:
        return _handle_menu_selection(session, user, body, lang)

    if _is_cancel(body):
        _clear_flow(user)
        return [get_message("flow_cancelled", lang)]

    return _continue_flow(session, user, body, lang)


def _handle_menu_selection(session: Session, user: User, body: str, lang: str) -> list[str]:
    choice = body.strip().lower()
    if choice in _MENU_KEYWORDS:
        return [_menu_text(user, lang)]

    if choice in _VOW_TOGGLE_VALUES:
        user.vow_opt_in = not user.vow_opt_in
        ack_id = "vow_opt_in_on_ack" if user.vow_opt_in else "vow_opt_in_off_ack"
        return [get_message(ack_id, lang)]

    if not user.personal_opt_in:
        return [get_message("personal_features_off_notice", lang)]

    flow = _MENU_CHOICES.get(choice)
    if flow is None:
        return [
            get_message("invalid_menu_choice", lang),
            _menu_text(user, lang),
        ]

    _start_flow(user, flow)
    if flow == FLOW_FAST_TYPE:
        return [get_message("ask_fast_type", lang)]
    if flow == FLOW_REFLECTION_TEXT:
        return [get_message("ask_reflection_text", lang)]
    raise AssertionError(f"unhandled flow {flow!r}")  # pragma: no cover


def _get_or_create_dependent(session: Session, guardian: User, name: str) -> Dependent:
    existing = (
        session.query(Dependent)
        .filter(Dependent.guardian_id == guardian.id, Dependent.name == name)
        .one_or_none()
    )
    if existing is not None:
        return existing
    dependent = Dependent(guardian_id=guardian.id, name=name)
    session.add(dependent)
    session.flush()
    return dependent


def _continue_flow(session: Session, user: User, body: str, lang: str) -> list[str]:
    step = user.active_flow

    if step == FLOW_FAST_TYPE:
        fast_type = body.strip()
        if not fast_type:
            return [get_message("ask_fast_type", lang)]
        log = FastingLog(user_id=user.id, date=today_in_tz(user.timezone), fast_type=fast_type)
        session.add(log)
        session.flush()
        _start_flow(user, FLOW_FAST_FOR_WHOM, row_id=log.id)
        return [get_message("ask_for_whom", lang)]

    if step == FLOW_FAST_FOR_WHOM:
        log = (
            session.query(FastingLog)
            .filter(FastingLog.id == user.active_flow_row_id, FastingLog.user_id == user.id)
            .one_or_none()
        )
        if log is None:  # row was deleted out from under the flow — shouldn't happen, but don't crash
            _clear_flow(user)
            return [_menu_text(user, lang)]
        for_whom = body.strip()
        if not for_whom:
            return [get_message("ask_for_whom", lang)]
        if for_whom.lower() not in _SELF_VALUES:
            dependent = _get_or_create_dependent(session, user, for_whom)
            log.dependent_id = dependent.id
        _start_flow(user, FLOW_FAST_NOTE, row_id=log.id)
        return [get_message("ask_fast_note", lang)]

    if step == FLOW_FAST_NOTE:
        log = (
            session.query(FastingLog)
            .filter(FastingLog.id == user.active_flow_row_id, FastingLog.user_id == user.id)
            .one_or_none()
        )
        _clear_flow(user)
        if log is None:
            return [_menu_text(user, lang)]
        if not _is_skip(body):
            log.note = body.strip()
        if log.dependent_id is not None:
            dependent = session.get(Dependent, log.dependent_id)
            return [get_message("family_fast_logged_ack", lang, name=dependent.name, fast_type=log.fast_type)]
        return [get_message("fast_logged_ack", lang, fast_type=log.fast_type)]

    if step == FLOW_REFLECTION_TEXT:
        text = body.strip()
        if not text:
            return [get_message("ask_reflection_text", lang)]
        reflection = Reflection(user_id=user.id, date=today_in_tz(user.timezone), text=text)
        session.add(reflection)
        session.flush()
        _start_flow(user, FLOW_REFLECTION_FOR_WHOM, row_id=reflection.id)
        return [get_message("ask_for_whom", lang)]

    if step == FLOW_REFLECTION_FOR_WHOM:
        reflection = (
            session.query(Reflection)
            .filter(Reflection.id == user.active_flow_row_id, Reflection.user_id == user.id)
            .one_or_none()
        )
        if reflection is None:
            _clear_flow(user)
            return [_menu_text(user, lang)]
        for_whom = body.strip()
        if not for_whom:
            return [get_message("ask_for_whom", lang)]
        _clear_flow(user)
        if for_whom.lower() not in _SELF_VALUES:
            dependent = _get_or_create_dependent(session, user, for_whom)
            reflection.dependent_id = dependent.id
            return [get_message("family_reflection_saved_ack", lang, name=dependent.name)]
        return [get_message("reflection_saved_ack", lang)]

    # Unknown/stale flow value — reset rather than get the user stuck.
    _clear_flow(user)
    return [_menu_text(user, lang)]
