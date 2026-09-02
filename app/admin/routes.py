import datetime
import time

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.admin.auth import require_admin
from app.broadcast import _today, build_broadcast_text, send_daily_broadcast
from app.config import settings
from app.db import get_db
from app.logging_utils import hash_phone, logger
from app.models import FAQ, Broadcast, Escalation, User
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
    edit_date: str | None = None,
    edit_faq_id: int | None = None,
    db: Session = Depends(get_db),
):
    broadcasts = db.query(Broadcast).order_by(Broadcast.date.asc()).all()
    faqs = db.query(FAQ).order_by(FAQ.id.desc()).all()

    edit_broadcast = None
    if edit_date:
        edit_broadcast = (
            db.query(Broadcast).filter(Broadcast.date == datetime.date.fromisoformat(edit_date)).one_or_none()
        )
    edit_faq = db.get(FAQ, edit_faq_id) if edit_faq_id else None

    return templates.TemplateResponse(
        request,
        "admin/content.html",
        {
            "active_tab": "content",
            "broadcasts": broadcasts,
            "faqs": faqs,
            "edit_broadcast": edit_broadcast,
            "edit_faq": edit_faq,
        },
    )


@router.post("/content/broadcast")
def save_broadcast(
    date: str = Form(...),
    day_number: int = Form(...),
    theme_en: str = Form(...),
    theme_gu: str = Form(...),
    pratikraman_timing: str = Form(...),
    announcements_en: str = Form(""),
    announcements_gu: str = Form(""),
    db: Session = Depends(get_db),
):
    parsed_date = datetime.date.fromisoformat(date)
    broadcast = db.query(Broadcast).filter(Broadcast.date == parsed_date).one_or_none()
    if broadcast is None:
        broadcast = Broadcast(date=parsed_date)
        db.add(broadcast)

    broadcast.day_number = day_number
    broadcast.theme_en = theme_en
    broadcast.theme_gu = theme_gu
    broadcast.pratikraman_timing = pratikraman_timing
    broadcast.announcements_en = announcements_en
    broadcast.announcements_gu = announcements_gu
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


# --- Users -------------------------------------------------------------


@router.get("/users")
def users(request: Request, db: Session = Depends(get_db)):
    all_users = db.query(User).order_by(User.created_at.desc()).all()
    return templates.TemplateResponse(
        request, "admin/users.html", {"active_tab": "users", "users": all_users}
    )


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

    context = {
        "active_tab": "broadcast",
        "today": today,
        "broadcast": broadcast,
        "flash": flash,
        "flash_type": flash_type,
    }
    if broadcast is not None:
        opted_in_count = db.query(User).filter(User.broadcast_opt_in.is_(True)).count()
        context.update(
            {
                "preview_en": build_broadcast_text(db, broadcast, "en"),
                "preview_gu": build_broadcast_text(db, broadcast, "gu"),
                "opted_in_count": opted_in_count,
            }
        )
    return templates.TemplateResponse(request, "admin/broadcast.html", context)


@router.post("/broadcast/send")
def broadcast_send(db: Session = Depends(get_db)):
    result = send_daily_broadcast(db)
    return RedirectResponse(
        url=f"/admin/broadcast?sent={result['sent']}&failed={result['failed']}", status_code=303
    )
