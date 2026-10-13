"""English<->Gujarati translation via the Google Cloud Translation API
(v2, simple API-key auth — no GCP ADC/service account/gcloud CLI needed).

Replaces this project's earlier hand-curated bilingual message catalog:
callers now author English only, and app/catalog.py (or any other caller)
translates to Gujarati here at send/creation time. Results are cached in
the database (TranslationCache) so identical strings — most messages are
static or have only a few varying parameters — are only ever translated
once, keeping cost/latency down and wording consistent across repeats.
"""

import httpx

from app.config import settings
from app.logging_utils import logger

_TRANSLATE_URL = "https://translation.googleapis.com/language/translate/v2"


def translate(text: str, source: str = "en", target: str = "gu") -> str:
    """Translates `text` from `source` to `target`. Falls back to
    returning `text` unchanged if no API key is configured or the call
    fails — a bad/slow translation call must never break the webhook or
    admin dashboard."""
    if not text or not settings.google_translate_api_key:
        return text

    from app.db import get_session
    from app.models import TranslationCache

    session = get_session()
    try:
        cached = (
            session.query(TranslationCache).filter(TranslationCache.source_text == text).one_or_none()
        )
        if cached is not None:
            return cached.translated_text

        try:
            response = httpx.post(
                _TRANSLATE_URL,
                params={"key": settings.google_translate_api_key},
                json={"q": text, "source": source, "target": target, "format": "text"},
                timeout=10.0,
            )
            response.raise_for_status()
            translated = response.json()["data"]["translations"][0]["translatedText"]
        except Exception:
            logger.exception("translation_failed")
            return text

        session.add(TranslationCache(source_text=text, translated_text=translated))
        session.commit()
        return translated
    finally:
        session.close()


def translate_to_gujarati(text: str) -> str:
    return translate(text, source="en", target="gu")
