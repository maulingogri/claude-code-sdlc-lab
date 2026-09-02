"""Direct, LLM-free tests of the ADK agent's tool functions.

These call brain.agent's tool functions the same way the ADK Runner would
(a tool_context with a `.state` dict), but bypass the model entirely — so
they're deterministic and don't hit a real API, unlike an eval run. This
is the right layer to guard code-level behavior (like the opt-out check)
that must hold regardless of what the LLM decides to do.
"""

import datetime
from zoneinfo import ZoneInfo

from brain.agent import add_forgiveness_entry, escalate, log_fast, log_reflection
from brain.data import _today_in_tz

from app.catalog import get_message
from app.db import get_session
from app.models import FastingLog, ForgivenessListEntry, Reflection, User


class _FakeToolContext:
    def __init__(self, state: dict):
        self.state = state


def _make_user(**kwargs) -> User:
    session = get_session()
    defaults = {"phone": "+15559998888", "onboarding_step": "complete"}
    defaults.update(kwargs)
    user = User(**defaults)
    session.add(user)
    session.commit()
    session.refresh(user)
    session.close()
    return user


async def test_log_fast_blocked_when_personal_features_disabled():
    user = _make_user(personal_opt_in=False)
    ctx = _FakeToolContext({"user_id": user.id, "personal_features_enabled": False})

    result = await log_fast("Upvas", "trying anyway", ctx)

    assert result == {"status": "error", "reason": "personal_features_disabled"}
    session = get_session()
    assert session.query(FastingLog).filter(FastingLog.user_id == user.id).count() == 0
    session.close()


async def test_log_reflection_blocked_when_personal_features_disabled():
    user = _make_user(personal_opt_in=False)
    ctx = _FakeToolContext({"user_id": user.id, "personal_features_enabled": False})

    result = await log_reflection("trying anyway", ctx)

    assert result == {"status": "error", "reason": "personal_features_disabled"}
    session = get_session()
    assert session.query(Reflection).filter(Reflection.user_id == user.id).count() == 0
    session.close()


async def test_add_forgiveness_entry_blocked_when_personal_features_disabled():
    user = _make_user(personal_opt_in=False)
    ctx = _FakeToolContext({"user_id": user.id, "personal_features_enabled": False})

    result = await add_forgiveness_entry("Someone", "", ctx)

    assert result == {"status": "error", "reason": "personal_features_disabled"}
    session = get_session()
    assert session.query(ForgivenessListEntry).filter(ForgivenessListEntry.user_id == user.id).count() == 0
    session.close()


async def test_log_fast_allowed_when_personal_features_enabled():
    user = _make_user(personal_opt_in=True)
    ctx = _FakeToolContext({"user_id": user.id, "personal_features_enabled": True})

    result = await log_fast("Ekasana", "felt good", ctx)

    assert result == {"status": "success", "fast_type": "Ekasana"}
    session = get_session()
    log = session.query(FastingLog).filter(FastingLog.user_id == user.id).one()
    assert log.fast_type == "Ekasana"
    assert log.note == "felt good"
    session.close()


def test_today_in_tz_matches_manual_calculation():
    for tz_name in ["America/New_York", "Asia/Kolkata", "Pacific/Kiritimati", "UTC"]:
        assert _today_in_tz(tz_name) == datetime.datetime.now(ZoneInfo(tz_name)).date()


async def test_log_fast_uses_passed_timezone_not_server_clock():
    user = _make_user(personal_opt_in=True)
    # Pacific/Kiritimati is UTC+14 -- deliberately far from UTC so a
    # regression to datetime.date.today() (server-local/UTC) would very
    # often make this assertion fail.
    ctx = _FakeToolContext(
        {"user_id": user.id, "personal_features_enabled": True, "timezone": "Pacific/Kiritimati"}
    )

    await log_fast("Upvas", "", ctx)

    session = get_session()
    log = session.query(FastingLog).filter(FastingLog.user_id == user.id).one()
    assert log.date == _today_in_tz("Pacific/Kiritimati")
    session.close()


async def test_escalate_acknowledgment_matches_message_catalog():
    # brain/agent.py duplicates this string rather than importing
    # app.catalog (see the module's own comment on why) — this test is
    # the drift detector: it fails the moment the two copies disagree.
    user = _make_user()
    for lang in ["en", "gu"]:
        ctx = _FakeToolContext({"user_id": user.id, "language": lang})
        result = await escalate("test question", ctx)
        assert result["acknowledgment"] == get_message("escalation_ack", lang)
