import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse

from app.admin.routes import router as admin_router
from app.catalog import get_message
from app.config import settings
from app.db import get_session, init_db
from app.logging_utils import hash_phone, logger
from app.models import User
from app.onboarding import STEP_COMPLETE, handle_onboarding_reply, start_onboarding
from app.personal_features import handle_post_onboarding_message


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Louisville Jain Sangh Paryushan Agent", lifespan=_lifespan)
app.include_router(admin_router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


def _public_url(request: Request) -> str:
    """Reconstruct the externally-visible URL Twilio actually posted to.

    Railway (and most PaaS) terminate TLS at a proxy and forward to the app
    over plain HTTP, so `request.url` reports scheme=http even though
    Twilio's signature was computed against the https:// URL. Trust
    X-Forwarded-Proto when present.
    """
    forwarded_proto = request.headers.get("x-forwarded-proto")
    url = str(request.url)
    if forwarded_proto and url.startswith("http://"):
        url = forwarded_proto + url[len("http") :]
    return url


async def _validate_twilio_signature(request: Request, form: dict[str, str]) -> None:
    if settings.skip_twilio_signature_validation:
        return

    signature = request.headers.get("x-twilio-signature", "")
    validator = RequestValidator(settings.twilio_auth_token)
    if not validator.validate(_public_url(request), form, signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")


def _strip_whatsapp_prefix(address: str) -> str:
    return address.removeprefix("whatsapp:")


def _get_or_create_user(session: Session, phone: str) -> tuple[User, bool]:
    """Runs in a worker thread via asyncio.to_thread (see twilio_webhook) —
    plain SQLAlchemy sessions are synchronous, so this blocking DB I/O must
    be offloaded or it stalls the event loop for every other concurrent
    request. Returns (user, is_new_user)."""
    user = session.query(User).filter(User.phone == phone).one_or_none()
    if user is not None:
        return user, False

    user = User(phone=phone)
    session.add(user)
    try:
        session.flush()
    except IntegrityError:
        # Lost a race with a concurrent request for the same new phone
        # number (e.g. a duplicate Twilio webhook delivery) — the other
        # request's insert already went through. Use that row instead of
        # crashing with an unhandled 500 back to Twilio.
        session.rollback()
        user = session.query(User).filter(User.phone == phone).one()
        return user, False
    return user, True


@app.post("/webhook/twilio")
async def twilio_webhook(request: Request) -> Response:
    form_raw = await request.form()
    form = {k: str(v) for k, v in form_raw.items()}

    await _validate_twilio_signature(request, form)

    from_address = form.get("From", "")
    body = form.get("Body", "")
    phone = _strip_whatsapp_prefix(from_address)

    if not phone:
        raise HTTPException(status_code=400, detail="Missing From address")

    session = get_session()
    try:
        user, is_new_user = await asyncio.to_thread(_get_or_create_user, session, phone)

        logger.info(
            "inbound_message phone_hash=%s onboarding_step=%s is_new=%s",
            hash_phone(phone),
            user.onboarding_step,
            is_new_user,
        )

        if is_new_user:
            replies = start_onboarding(user)
        elif user.onboarding_step != STEP_COMPLETE:
            replies = handle_onboarding_reply(user, body)
        elif settings.anthropic_api_key:
            from app.agent_runtime import run_agent_turn

            try:
                replies = await run_agent_turn(user, body)
            except Exception:
                logger.exception("agent_turn_failed phone_hash=%s", hash_phone(phone))
                replies = [get_message("agent_error_fallback", user.language or "en")]
        else:
            replies = handle_post_onboarding_message(session, user, body)

        await asyncio.to_thread(session.commit)
    finally:
        session.close()

    twiml = MessagingResponse()
    for reply in replies:
        twiml.message(reply)

    return Response(content=str(twiml), media_type="application/xml")
