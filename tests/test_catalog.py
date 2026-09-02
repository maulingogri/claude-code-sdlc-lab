from unittest.mock import patch

import pytest

from app.catalog import get_message
from app.config import settings


def test_get_message_english():
    text = get_message("greeting", "en")
    assert "Jai Jinendra" in text


def test_get_message_gujarati_falls_back_to_english_without_a_translate_key():
    # Explicitly forced empty here rather than relying on the ambient .env
    # being blank — app.translation falls back to returning the English
    # text unchanged when there's no key, rather than calling the real
    # Google Translate API. See test_translation.py for coverage of the
    # actual translation/caching behavior with a key configured.
    with patch.object(settings, "google_translate_api_key", ""):
        text = get_message("greeting", "gu")
        assert text == get_message("greeting", "en")


def test_get_message_templating():
    text = get_message(
        "individual_activity_summary",
        "en",
        entries="You: Upvas\nGrandma Shah: Ekasana",
    )
    assert "You: Upvas" in text
    assert "Grandma Shah: Ekasana" in text


def test_unknown_message_id_raises():
    with pytest.raises(KeyError):
        get_message("not_a_real_id", "en")
