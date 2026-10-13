import datetime
import random

from sqlalchemy.orm import Session

from app.catalog import get_message
from app.config import settings
from app.logging_utils import hash_phone, logger
from app.models import Broadcast, Dependent, FastingLog, User, Vow, VowAssignment
from app.timeutils import today_in_tz
from app.translation import translate_to_gujarati
from app.twilio_client import send_whatsapp_message


def _today(tz_name: str) -> datetime.date:
    return today_in_tz(tz_name)


def _day_number(today: datetime.date) -> int:
    start = datetime.date.fromisoformat(settings.paryushan_start_date)
    return (today - start).days + 1


def _recognition_names(session: Session, for_date: datetime.date) -> list[str]:
    self_names = (
        session.query(User.display_name)
        .join(FastingLog, FastingLog.user_id == User.id)
        .filter(
            FastingLog.date == for_date,
            FastingLog.dependent_id.is_(None),
            User.public_recognition_optin.is_(True),
        )
        .filter(User.display_name.is_not(None))
        .all()
    )
    # A dependent's name appears if their guardian opted into public
    # recognition — a dependent (young child, elder) can't consent for
    # themselves, so this follows the guardian's own choice on their behalf.
    dependent_names = (
        session.query(Dependent.name)
        .join(FastingLog, FastingLog.dependent_id == Dependent.id)
        .join(User, User.id == Dependent.guardian_id)
        .filter(FastingLog.date == for_date, User.public_recognition_optin.is_(True))
        .all()
    )
    return [name for (name,) in self_names] + [name for (name,) in dependent_names]


def _activity_lines_for_user(session: Session, user: User, for_date: datetime.date) -> list[str]:
    """Fasts logged for `for_date` by this user themselves or any of their
    family members — feeds the Individual broadcast's personal activity
    section. Not shared with anyone else (unlike _recognition_names, this
    doesn't require public_recognition_optin — it's the user's own data
    being shown back to them, not published)."""
    own_logs = (
        session.query(FastingLog)
        .filter(
            FastingLog.user_id == user.id,
            FastingLog.dependent_id.is_(None),
            FastingLog.date == for_date,
        )
        .all()
    )
    lines = [f"You: {log.fast_type}" for log in own_logs]

    dependent_logs = (
        session.query(FastingLog, Dependent.name)
        .join(Dependent, FastingLog.dependent_id == Dependent.id)
        .filter(Dependent.guardian_id == user.id, FastingLog.date == for_date)
        .all()
    )
    lines += [f"{dep_name}: {log.fast_type}" for log, dep_name in dependent_logs]

    return lines


def _individual_activity_section(
    session: Session, user: User, for_date: datetime.date, language: str
) -> str:
    lines = _activity_lines_for_user(session, user, for_date)
    if not lines:
        return ""
    return get_message("individual_activity_summary", language, entries="\n".join(lines))


def _group_relay_recipients(session: Session) -> list[User]:
    """Users flagged (Users tab) to receive the separate Group broadcast —
    a community-only update with no individual fasting/vow detail — so
    they can manually relay it into the real Sangh WhatsApp group. The
    WhatsApp Business API has no way to post into a group chat directly."""
    return session.query(User).filter(User.is_group_relay.is_(True)).all()


def build_individual_text(
    session: Session, broadcast: Broadcast, user: User, yesterday: datetime.date, today: datetime.date
) -> str:
    """The Individual broadcast: the admin's free-text draft
    (individual_message_en, translated at send time if the user's
    language is Gujarati) plus three sections that can't be pre-drafted
    because they depend on who's receiving it or change day to day —
    yesterday's public recognition list, this user's own/family fasting
    activity, and their vow if opted in."""
    language = user.language or "en"
    text = broadcast.individual_message_en or ""
    if language == "gu":
        text = translate_to_gujarati(text)

    names = _recognition_names(session, yesterday)
    if names:
        text += get_message("daily_broadcast_recognition", language, names=", ".join(names))

    text += _individual_activity_section(session, user, yesterday, language)
    text += _vow_section_for_user(session, user, today)
    return text


def build_group_text(session: Session, broadcast: Broadcast, yesterday: datetime.date) -> str:
    """The Group broadcast: the admin's free-text draft (group_message_en)
    plus yesterday's public recognition list, sent as one bilingual
    message (English + auto-drafted Gujarati) — there's only one send per
    relay recipient, not a per-language choice like Individual has."""
    text = broadcast.group_message_en or ""
    names = _recognition_names(session, yesterday)
    if names:
        text += get_message("daily_broadcast_recognition", "en", names=", ".join(names))
    return f"{text}\n\n---\n\n{translate_to_gujarati(text)}"


def _pick_vow_for_user(session: Session, user: User) -> Vow | None:
    """Picks a random approved vow this user hasn't received before. Falls
    back to allowing a repeat once the whole approved pool is exhausted,
    rather than sending nothing."""
    already_sent_ids = {
        vow_id for (vow_id,) in session.query(VowAssignment.vow_id).filter(VowAssignment.user_id == user.id)
    }
    approved = session.query(Vow).filter(Vow.approved.is_(True)).all()
    if not approved:
        return None

    unused = [v for v in approved if v.id not in already_sent_ids]
    return random.choice(unused or approved)


def _vow_section_for_user(session: Session, user: User, today: datetime.date) -> str:
    if not user.vow_opt_in:
        return ""
    vow = _pick_vow_for_user(session, user)
    if vow is None:
        return ""
    session.add(VowAssignment(user_id=user.id, vow_id=vow.id, date=today))
    vow_text = vow.text_gu if (user.language or "en") == "gu" else vow.text_en
    return get_message("daily_vow_section", user.language or "en", vow_text=vow_text)


def send_daily_broadcast(session: Session) -> dict[str, int]:
    """Send two kinds of message once a day (Railway cron job — see
    scripts/run_daily_broadcast.py):

    - Individual: to every broadcast-opted-in user, in their language —
      today's community content plus what they/their family logged
      yesterday, plus their vow if opted in.
    - Group: to whoever is flagged as the group relay (Users tab) —
      today's community content only, in English, with no individual
      detail, meant to be manually forwarded into the real Sangh
      WhatsApp group (the Business API can't post into one directly).
    """
    today = _today(settings.default_timezone)
    broadcast = session.query(Broadcast).filter(Broadcast.date == today).one_or_none()

    if broadcast is None:
        logger.warning("no_broadcast_content_for_date date=%s", today.isoformat())
        return {"sent": 0, "failed": 0, "skipped_no_content": 1}

    yesterday = today - datetime.timedelta(days=1)
    sent, failed = 0, 0

    users = session.query(User).filter(User.broadcast_opt_in.is_(True)).all()
    for user in users:
        text = build_individual_text(session, broadcast, user, yesterday, today)
        try:
            send_whatsapp_message(user.phone, text)
            sent += 1
        except Exception:
            logger.exception("broadcast_send_failed phone_hash=%s", hash_phone(user.phone))
            failed += 1

    group_text = build_group_text(session, broadcast, yesterday)
    for relay_user in _group_relay_recipients(session):
        try:
            send_whatsapp_message(relay_user.phone, group_text)
            sent += 1
        except Exception:
            logger.exception("broadcast_send_failed_group phone_hash=%s", hash_phone(relay_user.phone))
            failed += 1

    if sent > 0:
        broadcast.sent_at = datetime.datetime.utcnow()
        session.commit()
    else:
        logger.warning(
            "daily_broadcast_total_failure date=%s failed=%d — not marking as sent",
            today.isoformat(),
            failed,
        )

    logger.info("daily_broadcast_complete date=%s sent=%d failed=%d", today.isoformat(), sent, failed)
    return {"sent": sent, "failed": failed, "skipped_no_content": 0}
