import pytest

from app.catalog import get_message


def test_get_message_english():
    text = get_message("greeting", "en")
    assert "Jai Jinendra" in text


def test_get_message_gujarati_falls_back_to_english_without_a_translate_key():
    # No GOOGLE_TRANSLATE_API_KEY in the test environment, so app.translation
    # falls back to returning the English text unchanged rather than calling
    # the real Google Translate API. See test_translation.py for coverage of
    # the actual translation/caching behavior with a key configured.
    text = get_message("greeting", "gu")
    assert text == get_message("greeting", "en")


def test_get_message_templating():
    text = get_message(
        "daily_broadcast_intro",
        "en",
        day_number=1,
        theme="Compassion",
        pratikraman_timing="7:00 PM",
        announcements="Arrive early.",
    )
    assert "Day 1" in text
    assert "Compassion" in text
    assert "7:00 PM" in text
    assert "Arrive early." in text


def test_unknown_message_id_raises():
    with pytest.raises(KeyError):
        get_message("not_a_real_id", "en")
