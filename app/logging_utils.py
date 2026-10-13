import hashlib
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

logger = logging.getLogger("paryushan_agent")


def hash_phone(phone: str) -> str:
    """One-way hash of a phone number for log lines. Never log raw phone
    numbers or message content (see CLAUDE.md Security & Logging Rules)."""
    return hashlib.sha256(phone.encode("utf-8")).hexdigest()[:16]
