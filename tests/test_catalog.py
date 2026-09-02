import pytest

from app.catalog import get_message


def test_get_message_english():
    text = get_message("greeting", "en")
    assert "Jai Jinendra" in text


def test_get_message_gujarati():
    text = get_message("greeting", "gu")
    assert "જય જિનેન્દ્ર" in text


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
