from unittest.mock import MagicMock, patch

from app.config import settings
from app.db import get_session
from app.models import TranslationCache
from app.translation import translate_to_gujarati


def test_translate_returns_text_unchanged_without_a_key():
    assert settings.google_translate_api_key == ""
    assert translate_to_gujarati("Hello") == "Hello"


def test_translate_returns_text_unchanged_for_empty_string():
    with patch.object(settings, "google_translate_api_key", "fake-key"):
        assert translate_to_gujarati("") == ""


def test_translate_calls_api_and_caches_result():
    fake_response = MagicMock()
    fake_response.json.return_value = {"data": {"translations": [{"translatedText": "નમસ્તે"}]}}
    fake_response.raise_for_status.return_value = None

    with patch.object(settings, "google_translate_api_key", "fake-key"):
        with patch("app.translation.httpx.post", return_value=fake_response) as mock_post:
            result = translate_to_gujarati("Hello")
            assert result == "નમસ્તે"
            mock_post.assert_called_once()

            # Second call for the same text must hit the cache, not the API again.
            result_again = translate_to_gujarati("Hello")
            assert result_again == "નમસ્તે"
            mock_post.assert_called_once()

    session = get_session()
    cached = session.query(TranslationCache).filter(TranslationCache.source_text == "Hello").one()
    assert cached.translated_text == "નમસ્તે"
    session.close()


def test_translate_falls_back_to_english_on_api_failure():
    with patch.object(settings, "google_translate_api_key", "fake-key"):
        with patch("app.translation.httpx.post", side_effect=RuntimeError("network error")):
            assert translate_to_gujarati("Some text that fails") == "Some text that fails"

    session = get_session()
    cached = (
        session.query(TranslationCache)
        .filter(TranslationCache.source_text == "Some text that fails")
        .one_or_none()
    )
    assert cached is None
    session.close()
