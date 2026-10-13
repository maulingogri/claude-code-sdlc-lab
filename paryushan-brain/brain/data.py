"""Minimal, dependency-free data access for agent tools.

Deliberately does NOT import the root project's `app` package — this keeps
`paryushan-brain` independently installable/testable (agents-cli
playground/eval run it in its own venv, where the root `app` package isn't
importable). Instead it talks to the same SQLite file directly via the
DATABASE_URL env var, using the same schema `app/models.py` defines.
"""

import datetime
import json
import os
import sqlite3
import urllib.parse
import urllib.request
from contextlib import contextmanager
from zoneinfo import ZoneInfo

_TRANSLATE_URL = "https://translation.googleapis.com/language/translate/v2"


def _db_path() -> str:
    url = os.environ.get("DATABASE_URL", "sqlite:///./paryushan.db")
    if not url.startswith("sqlite:///"):
        raise RuntimeError(f"brain/data.py only supports sqlite DATABASE_URL, got: {url!r}")
    return url.removeprefix("sqlite:///")


def _today_in_tz(tz_name: str) -> datetime.date:
    # Mirrors app/timeutils.py's today_in_tz — duplicated rather than
    # imported (see module docstring on why this file avoids importing
    # `app`), but MUST stay behaviorally identical: a user's fast/
    # reflection date has to match regardless of which path (this ADK
    # agent vs. the deterministic menu in app/personal_features.py)
    # handled the message, or the same log can land under different
    # calendar dates near a timezone's day boundary.
    return datetime.datetime.now(ZoneInfo(tz_name)).date()


@contextmanager
def _connection():
    conn = sqlite3.connect(_db_path())
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def get_or_create_dependent(user_id: int, name: str) -> int:
    """Returns the id of the guardian's family member row for `name`,
    creating it if this is the first time it's been mentioned."""
    with _connection() as conn:
        row = conn.execute(
            "SELECT id FROM dependents WHERE guardian_id = ? AND name = ?", (user_id, name)
        ).fetchone()
        if row is not None:
            return row[0]
        now = datetime.datetime.utcnow().isoformat()
        cursor = conn.execute(
            "INSERT INTO dependents (guardian_id, name, created_at) VALUES (?, ?, ?)",
            (user_id, name, now),
        )
        return cursor.lastrowid


def log_fast(
    user_id: int,
    fast_type: str,
    note: str,
    timezone: str = "America/New_York",
    dependent_id: int | None = None,
) -> None:
    today = _today_in_tz(timezone).isoformat()
    with _connection() as conn:
        conn.execute(
            "INSERT INTO fasting_logs (user_id, dependent_id, date, fast_type, note) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, dependent_id, today, fast_type, note or None),
        )


def log_reflection(
    user_id: int, text: str, timezone: str = "America/New_York", dependent_id: int | None = None
) -> None:
    today = _today_in_tz(timezone).isoformat()
    with _connection() as conn:
        conn.execute(
            "INSERT INTO reflections (user_id, dependent_id, date, text) VALUES (?, ?, ?, ?)",
            (user_id, dependent_id, today, text),
        )


def list_faqs(language: str) -> list[dict]:
    question_col = "question_gu" if language == "gu" else "question_en"
    answer_col = "answer_gu" if language == "gu" else "answer_en"
    with _connection() as conn:
        rows = conn.execute(f"SELECT {question_col}, {answer_col} FROM faq").fetchall()
    return [{"question": q, "answer": a} for q, a in rows]


def create_escalation(user_id: int, question_text: str) -> None:
    # SQLAlchemy's `default=False` on the ORM column is Python-side only —
    # it isn't compiled into the SQLite DDL, so a raw INSERT must supply
    # added_to_faq explicitly or hit the NOT NULL constraint.
    now = datetime.datetime.utcnow().isoformat()
    with _connection() as conn:
        conn.execute(
            "INSERT INTO escalations (user_id, question_text, status, added_to_faq, timestamp) "
            "VALUES (?, ?, 'pending', 0, ?)",
            (user_id, question_text, now),
        )


def set_vow_opt_in(user_id: int, opted_in: bool) -> None:
    with _connection() as conn:
        conn.execute("UPDATE users SET vow_opt_in = ? WHERE id = ?", (1 if opted_in else 0, user_id))


def translate_to_gujarati(text: str) -> str:
    """Mirrors app/translation.py's translate_to_gujarati — duplicated
    (stdlib-only, no httpx dependency needed here) rather than imported,
    same reasoning as everything else in this file. Shares the SAME
    `translation_cache` table via raw SQL, so both halves of the app
    agree on a given string's translation and never re-pay for it twice."""
    api_key = os.environ.get("GOOGLE_TRANSLATE_API_KEY", "")
    if not api_key or not text:
        return text

    with _connection() as conn:
        row = conn.execute(
            "SELECT translated_text FROM translation_cache WHERE source_text = ?", (text,)
        ).fetchone()
        if row is not None:
            return row[0]

    try:
        url = f"{_TRANSLATE_URL}?{urllib.parse.urlencode({'key': api_key})}"
        payload = json.dumps({"q": text, "source": "en", "target": "gu", "format": "text"}).encode()
        request = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            body = json.loads(response.read())
        translated = body["data"]["translations"][0]["translatedText"]
    except Exception:
        return text

    with _connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO translation_cache (source_text, translated_text) VALUES (?, ?)",
            (text, translated),
        )
    return translated
