import datetime

from sqlalchemy.orm import Session

from app.catalog import get_message
from app.config import settings
from app.logging_utils import hash_phone, logger
from app.models import Broadcast, FastingLog, User
from app.timeutils import today_in_tz
from app.twilio_client import send_whatsapp_message


def _today(tz_name: str) -> datetime.date:
    return today_in_tz(tz_name)


def _day_number(today: datetime.date) -> int:
    start = datetime.date.fromisoformat(settings.paryushan_start_date)
    return (today - start).days + 1


def _recognition_names(session: Session, for_date: datetime.date) -> list[str]:
    rows = (
        session.query(User.display_name)
        .join(FastingLog, FastingLog.user_id == User.id)
        .filter(FastingLog.date == for_date, User.public_recognition_optin.is_(True))
        .filter(User.display_name.is_not(None))
        .all()
    )
    return [name for (name,) in rows]


def build_broadcast_text(session: Session, broadcast: Broadcast, language: str) -> str:
    text = get_message(
        "daily_broadcast_intro",
        language,
        day_number=broadcast.day_number,
        theme=broadcast.theme_gu if language == "gu" else broadcast.theme_en,
        pratikraman_timing=broadcast.pratikraman_timing,
        announcements=(broadcast.announcements_gu if language == "gu" else broadcast.announcements_en)
        or "",
    )

    yesterday = broadcast.date - datetime.timedelta(days=1)
    names = _recognition_names(session, yesterday)
    if names:
        text += get_message("daily_broadcast_recognition", language, names=", ".join(names))

    return text


def send_daily_broadcast(session: Session) -> dict[str, int]:
    """Send today's broadcast to every opted-in user, plus the Sangh group
    number, in each recipient's chosen language. Intended to be run once a
    day by a Railway cron job (see scripts/run_daily_broadcast.py)."""
    today = _today(settings.default_timezone)
    broadcast = session.query(Broadcast).filter(Broadcast.date == today).one_or_none()

    if broadcast is None:
        logger.warning("no_broadcast_content_for_date date=%s", today.isoformat())
        return {"sent": 0, "failed": 0, "skipped_no_content": 1}

    sent, failed = 0, 0
    users = session.query(User).filter(User.broadcast_opt_in.is_(True)).all()
    for user in users:
        language = user.language or "en"
        text = build_broadcast_text(session, broadcast, language)
        try:
            send_whatsapp_message(user.phone, text)
            sent += 1
        except Exception:
            logger.exception("broadcast_send_failed phone_hash=%s", hash_phone(user.phone))
            failed += 1

    if settings.sangh_group_whatsapp_number:
        try:
            send_whatsapp_message(
                settings.sangh_group_whatsapp_number, build_broadcast_text(session, broadcast, "en")
            )
            sent += 1
        except Exception:
            logger.exception("broadcast_send_failed_group")
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
