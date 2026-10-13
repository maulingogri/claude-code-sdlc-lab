from app import rate_limit
from app.rate_limit import is_rate_limited, reset


def setup_function():
    reset()


def test_allows_up_to_the_limit():
    for _ in range(15):
        assert is_rate_limited("+15550001111") is False


def test_blocks_beyond_the_limit():
    for _ in range(15):
        is_rate_limited("+15550001111")
    assert is_rate_limited("+15550001111") is True


def test_different_phones_are_tracked_independently():
    for _ in range(15):
        is_rate_limited("+15550001111")
    assert is_rate_limited("+15550001111") is True
    assert is_rate_limited("+15550002222") is False


def test_reset_clears_state():
    for _ in range(15):
        is_rate_limited("+15550001111")
    assert is_rate_limited("+15550001111") is True

    reset()

    assert is_rate_limited("+15550001111") is False


def test_rejected_calls_are_not_recorded():
    """Under sustained abuse (far more than 15 calls), memory shouldn't
    grow unboundedly — only accepted calls get tracked."""
    for _ in range(15):
        is_rate_limited("+15550001111")
    for _ in range(500):
        assert is_rate_limited("+15550001111") is True

    assert len(rate_limit._recent_message_times["+15550001111"]) == 15
