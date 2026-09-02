"""Basic per-user in-memory rate limiting for the Twilio webhook (CLAUDE.md
Security & Logging Rules: "Basic per-user rate limiting on the webhook").

In-memory only — resets on restart and doesn't share state across
multiple worker processes, consistent with this project's other Stage 1
single-process assumptions (see app/agent_runtime.py's session service).
"""

import time
from collections import defaultdict, deque

_WINDOW_SECONDS = 60
_MAX_MESSAGES_PER_WINDOW = 15

_recent_message_times: dict[str, deque[float]] = defaultdict(deque)


def is_rate_limited(phone: str) -> bool:
    """Records this message and returns True if `phone` has already sent
    _MAX_MESSAGES_PER_WINDOW messages in the last _WINDOW_SECONDS. A
    rejected message isn't recorded — the window is a sliding count of
    accepted messages, so a limited user recovers as soon as their oldest
    accepted message ages out."""
    now = time.monotonic()
    window_start = now - _WINDOW_SECONDS
    times = _recent_message_times[phone]

    while times and times[0] < window_start:
        times.popleft()

    if len(times) >= _MAX_MESSAGES_PER_WINDOW:
        return True

    times.append(now)
    return False


def reset() -> None:
    """Test-only: clear all tracked state."""
    _recent_message_times.clear()
