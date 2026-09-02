import datetime
import time

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.admin.auth import require_admin
from app.broadcast import (
    _day_number,
    _group_relay_recipients,
    _today,
    build_group_text,
    build_individual_text,
    send_daily_broadcast,
)
from app.config import settings
from app.db import get_db
from app.logging_utils import hash_phone, logger
from app.models import FAQ, Broadcast, Escalation, User, Vow
from app.translation import translate_to_gujarati
from app.twilio_client import send_whatsapp_message

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])
templates = Jinja2Templates(directory="app/templates")


@router.get("/")
def admin_root() -> RedirectResponse:
    return RedirectResponse(url="/admin/inbox")


# --- Inbox -------------------------------------------------------------


@router.get("/inbox")
def inbox(request: Request, db: Session = Depends(get_db)):
    pending = (
        db.query(Escalation)
        .filter(Escalation.status == "pending")
        .order_by(Escalation.timestamp.asc())
        .all()
    )
    answered = (
        db.query(Escalation)
        .filter(Escalation.status == "answered")
        .order_by(Escalation.timestamp.desc())
        .limit(50)
        .all()
    )
    return templates.TemplateResponse(
        request,
        "admin/inbox.html",
        {"active_tab": "inbox", "pending": pending, "answered": answered},
    )


def _commit_with_retry(db: Session, attempts: int = 3, delay_seconds: float = 0.15) -> None:
    """SQLite can raise 'database is locked' under contention with the ADK
    agent's independent raw sqlite3 connections (see brain/data.py). A
    short retry absorbs typical transient contention instead of losing
    track of a reply that has already been sent to the user."""
    for attempt in range(1, attempts + 1):
        try:
            db.commit()
            return
        except OperationalError:
            db.rollback()
            if attempt == attempts:
                raise
            time.sleep(delay_seconds)


@router.post("/inbox/{escalation_id}/reply")
def reply_to_escalation(
    escalation_id: int, answer_text: str = Form(...), db: Session = Depends(get_db)
):
    escalation = db.get(Escalation, escalation_id)
    if escalation is None:
        raise HTTPException(status_code=404, detail="Escalation not found")

    try:
        send_whatsapp_message(escalation.user.phone, answer_text)
    except Exception:
        logger.exception(
            "admin_reply_send_failed phone_hash=%s", hash_phone(escalation.user.phone)
        )
        raise HTTPException(status_code=502, detail="Failed to send WhatsApp reply") from None

    escalation.answer_text = answer_text
    escalation.status = "answered"
    try:
        _commit_with_retry(db)
    except Exception:
        # The WhatsApp message already went out — this only failed to
        # record that in the DB. Retrying the same request would send a
        # second, duplicate message, so make that explicit rather than
        # returning a generic 500 that invites a naive retry.
        logger.exception(
            "admin_reply_commit_failed_after_send phone_hash=%s escalation_id=%s",
            hash_phone(escalation.user.phone),
            escalation_id,
        )
        raise HTTPException(
            status_code=500,
            detail=(
                "The reply was already sent to the user via WhatsApp, but saving that to the "
                "database failed. Do NOT click Send again — that would deliver a duplicate "
                "message. Check the server logs and update this escalation manually."
            ),
        ) from None
    return RedirectResponse(url="/admin/inbox", status_code=303)


@router.get("/inbox/{escalation_id}/add-to-faq")
def add_to_faq_form(request: Request, escalation_id: int, db: Session = Depends(get_db)):
    escalation = db.get(Escalation, escalation_id)
    if escalation is None:
        raise HTTPException(status_code=404, detail="Escalation not found")

    is_gu = (escalation.user.language or "en") == "gu"
    return templates.TemplateResponse(
        request,
        "admin/add_to_faq.html",
        {
            "active_tab": "inbox",
            "escalation": escalation,
            "question_en": "" if is_gu else escalation.question_text,
            "question_gu": escalation.question_text if is_gu else "",
            "answer_en": "" if is_gu else (escalation.answer_text or ""),
            "answer_gu": (escalation.answer_text or "") if is_gu else "",
        },
    )


@router.post("/inbox/{escalation_id}/add-to-faq")
def add_to_faq_submit(
    escalation_id: int,
    question_en: str = Form(...),
    question_gu: str = Form(...),
    answer_en: str = Form(...),
    answer_gu: str = Form(...),
    db: Session = Depends(get_db),
):
    escalation = db.get(Escalation, escalation_id)
    if escalation is None:
        raise HTTPException(status_code=404, detail="Escalation not found")

    db.add(FAQ(question_en=question_en, question_gu=question_gu, answer_en=answer_en, answer_gu=answer_gu))
    escalation.added_to_faq = True
    db.commit()
    return RedirectResponse(url="/admin/inbox", status_code=303)


# --- Content -------------------------------------------------------------


@router.get("/content")
def content(
    request: Request,
    edit_individual_date: str | None = None,
    edit_group_date: str | None = None,
    edit_faq_id: int | None = None,
    db: Session = Depends(get_db),
):
    broadcasts = db.query(Broadcast).order_by(Broadcast.date.asc()).all()
    faqs = db.query(FAQ).order_by(FAQ.id.desc()).all()
    pending_vows = db.query(Vow).filter(Vow.approved.is_(False)).order_by(Vow.id.asc()).all()
    approved_vows = db.query(Vow).filter(Vow.approved.is_(True)).order_by(Vow.id.asc()).all()

    def _broadcast_for(date_str: str | None) -> Broadcast | None:
        if not date_str:
            return None
        return db.query(Broadcast).filter(Broadcast.date == datetime.date.fromisoformat(date_str)).one_or_none()

    edit_individual = _broadcast_for(edit_individual_date)
    edit_group = _broadcast_for(edit_group_date)
    edit_faq = db.get(FAQ, edit_faq_id) if edit_faq_id else None

    return templates.TemplateResponse(
        request,
        "admin/content.html",
        {
            "active_tab": "content",
            "broadcasts": broadcasts,
            "faqs": faqs,
            "pending_vows": pending_vows,
            "approved_vows": approved_vows,
            "edit_individual": edit_individual,
            "edit_group": edit_group,
            "edit_faq": edit_faq,
        },
    )


def _upsert_broadcast(db: Session, date: str) -> Broadcast:
    """day_number is always derived from the date (see broadcast._day_number)
    rather than entered by hand — the Individual and Group forms both edit
    the same underlying row for a date, so a manually-typed day number could
    silently drift between the two if entered differently on each."""
    parsed_date = datetime.date.fromisoformat(date)
    broadcast = db.query(Broadcast).filter(Broadcast.date == parsed_date).one_or_none()
    if broadcast is None:
        broadcast = Broadcast(date=parsed_date)
        db.add(broadcast)
    broadcast.day_number = _day_number(parsed_date)
    return broadcast


@router.post("/content/broadcast/individual")
def save_individual_broadcast(
    date: str = Form(...),
    message_en: str = Form(...),
    db: Session = Depends(get_db),
):
    """Admin writes English only; Gujarati is auto-drafted at send time
    (app/translation.py), same as vows and the group message."""
    broadcast = _upsert_broadcast(db, date)
    broadcast.individual_message_en = message_en
    db.commit()
    return RedirectResponse(url="/admin/content", status_code=303)


@router.post("/content/broadcast/group")
def save_group_broadcast(
    date: str = Form(...),
    message_en: str = Form(...),
    db: Session = Depends(get_db),
):
    broadcast = _upsert_broadcast(db, date)
    broadcast.group_message_en = message_en
    db.commit()
    return RedirectResponse(url="/admin/content", status_code=303)


@router.post("/content/faq")
def save_faq(
    question_en: str = Form(...),
    question_gu: str = Form(...),
    answer_en: str = Form(...),
    answer_gu: str = Form(...),
    faq_id: int | None = Form(None),
    db: Session = Depends(get_db),
):
    faq = db.get(FAQ, faq_id) if faq_id else None
    if faq is None:
        faq = FAQ()
        db.add(faq)

    faq.question_en = question_en
    faq.question_gu = question_gu
    faq.answer_en = answer_en
    faq.answer_gu = answer_gu
    db.commit()
    return RedirectResponse(url="/admin/content", status_code=303)


@router.post("/content/faq/{faq_id}/delete")
def delete_faq(faq_id: int, db: Session = Depends(get_db)):
    faq = db.get(FAQ, faq_id)
    if faq is not None:
        db.delete(faq)
        db.commit()
    return RedirectResponse(url="/admin/content", status_code=303)


@router.post("/content/vow")
def add_vow(text_en: str = Form(...), db: Session = Depends(get_db)):
    """Admin submits English only — Gujarati is auto-drafted via Google
    Translate. New vows always start unapproved (Vow.approved=False);
    nothing goes to users until an admin explicitly approves it below."""
    db.add(Vow(text_en=text_en, text_gu=translate_to_gujarati(text_en)))
    db.commit()
    return RedirectResponse(url="/admin/content", status_code=303)


@router.post("/content/vow/{vow_id}/approve")
def approve_vow(vow_id: int, db: Session = Depends(get_db)):
    vow = db.get(Vow, vow_id)
    if vow is not None:
        vow.approved = True
        db.commit()
    return RedirectResponse(url="/admin/content", status_code=303)


@router.post("/content/vow/{vow_id}/delete")
def delete_vow(vow_id: int, db: Session = Depends(get_db)):
    vow = db.get(Vow, vow_id)
    if vow is not None:
        db.delete(vow)
        db.commit()
    return RedirectResponse(url="/admin/content", status_code=303)


# --- Users -------------------------------------------------------------


@router.get("/users")
def users(request: Request, db: Session = Depends(get_db)):
    all_users = db.query(User).order_by(User.created_at.desc()).all()
    return templates.TemplateResponse(
        request, "admin/users.html", {"active_tab": "users", "users": all_users}
    )


@router.post("/users/{user_id}/toggle-group-relay")
def toggle_group_relay(user_id: int, db: Session = Depends(get_db)):
    """Flips whether this user receives the separate Group broadcast (see
    app/broadcast.py's _group_relay_recipients) for manual relaying into
    the real Sangh WhatsApp group."""
    user = db.get(User, user_id)
    if user is not None:
        user.is_group_relay = not user.is_group_relay
        db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)


@router.get("/users/{user_id}")
def user_detail(request: Request, user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return templates.TemplateResponse(
        request, "admin/user_detail.html", {"active_tab": "users", "user": user}
    )


# --- Broadcast -------------------------------------------------------------


@router.get("/broadcast")
def broadcast_tab(
    request: Request,
    sent: int | None = None,
    failed: int | None = None,
    group_sent: int | None = None,
    db: Session = Depends(get_db),
):
    today = _today(settings.default_timezone)
    broadcast = db.query(Broadcast).filter(Broadcast.date == today).one_or_none()

    flash, flash_type = None, None
    if sent is not None:
        if sent == 0 and failed:
            flash = (
                f"Send failed for all {failed} recipient(s) — nothing was marked as sent. "
                "Check Twilio credentials and server logs, then try again."
            )
            flash_type = "error"
        elif sent == 0:
            flash = "No one is opted in to daily broadcasts yet — nothing was sent."
        elif failed:
            flash = f"Sent to {sent} recipient(s), but failed for {failed}. Check server logs for details."
            flash_type = "error"
        else:
            flash = f"Sent successfully to {sent} recipient(s)."
    elif group_sent is not None:
        flash = (
            "Message sent to the Sangh WhatsApp group relay recipient(s)."
            if group_sent
            else "Failed to send — no one is flagged as the group relay yet. Set one on the Users tab."
        )
        flash_type = None if group_sent else "error"

    relay_users = _group_relay_recipients(db)
    context = {
        "active_tab": "broadcast",
        "today": today,
        "broadcast": broadcast,
        "flash": flash,
        "flash_type": flash_type,
        "group_configured": bool(relay_users),
        "relay_users": relay_users,
    }
    if broadcast is not None:
        yesterday = today - datetime.timedelta(days=1)
        opted_in_count = db.query(User).filter(User.broadcast_opt_in.is_(True)).count()
        # Unpersisted stand-in users just to drive text generation for a
        # generic preview — a real recipient's own activity/vow can't be
        # shown here since it depends on who's actually receiving it (see
        # build_individual_text); vow_opt_in stays False so this preview
        # doesn't claim a vow that may not apply to any given recipient.
        preview_user_en = User(language="en")
        preview_user_gu = User(language="gu")
        context.update(
            {
                "preview_individual_en": build_individual_text(
                    db, broadcast, preview_user_en, yesterday, today
                ),
                "preview_individual_gu": build_individual_text(
                    db, broadcast, preview_user_gu, yesterday, today
                ),
                "preview_group": build_group_text(db, broadcast, yesterday),
                "opted_in_count": opted_in_count,
            }
        )
    return templates.TemplateResponse(request, "admin/broadcast.html", context)


@router.post("/broadcast/group-message")
def send_group_message(message_en: str = Form(...), db: Session = Depends(get_db)):
    """Sends a one-off custom message to whoever is flagged as the group
    relay (Users tab), English plus an auto-drafted Gujarati translation —
    separate from the daily broadcast content."""
    relay_users = _group_relay_recipients(db)
    if not relay_users:
        return RedirectResponse(url="/admin/broadcast?group_sent=0", status_code=303)

    combined = f"{message_en}\n\n---\n\n{translate_to_gujarati(message_en)}"
    sent_any = False
    for relay_user in relay_users:
        try:
            send_whatsapp_message(relay_user.phone, combined)
            sent_any = True
        except Exception:
            logger.exception("admin_group_message_send_failed phone_hash=%s", hash_phone(relay_user.phone))
    return RedirectResponse(url=f"/admin/broadcast?group_sent={1 if sent_any else 0}", status_code=303)


@router.post("/broadcast/send")
def broadcast_send(db: Session = Depends(get_db)):
    result = send_daily_broadcast(db)
    return RedirectResponse(
        url=f"/admin/broadcast?sent={result['sent']}&failed={result['failed']}", status_code=303
    )
