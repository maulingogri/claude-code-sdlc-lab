import logging

from twilio.rest import Client

from app.config import settings

logger = logging.getLogger("paryushan_agent")

_client: Client | None = None


def _get_client() -> Client:
    global _client
    if _client is None:
        _client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    return _client


def _to_whatsapp_address(phone: str) -> str:
    return phone if phone.startswith("whatsapp:") else f"whatsapp:{phone}"


def send_whatsapp_message(to_phone: str, body: str) -> str:
    """Send a WhatsApp message via the Twilio REST API (used for proactive
    sends like the daily broadcast, outside the 24h webhook reply window).
    Returns the Twilio message SID."""
    message = _get_client().messages.create(
        from_=_to_whatsapp_address(settings.twilio_whatsapp_number),
        to=_to_whatsapp_address(to_phone),
        body=body,
    )
    logger.info("outbound_message_sent sid=%s", message.sid)
    return message.sid
