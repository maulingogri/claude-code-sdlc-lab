"""Minimal, dependency-free data access for agent tools.

Deliberately does NOT import the root project's `app` package — this keeps
`paryushan-brain` independently installable/testable (agents-cli
playground/eval run it in its own venv, where the root `app` package isn't
importable). Instead it talks to the same SQLite file directly via the
DATABASE_URL env var, using the same schema `app/models.py` defines.
"""

import datetime
import os
import sqlite3
from contextlib import contextmanager
from zoneinfo import ZoneInfo


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


def log_fast(user_id: int, fast_type: str, note: str, timezone: str = "America/New_York") -> None:
    today = _today_in_tz(timezone).isoformat()
    with _connection() as conn:
        conn.execute(
            "INSERT INTO fasting_logs (user_id, date, fast_type, note) VALUES (?, ?, ?, ?)",
            (user_id, today, fast_type, note or None),
        )


def log_reflection(user_id: int, text: str, timezone: str = "America/New_York") -> None:
    today = _today_in_tz(timezone).isoformat()
    with _connection() as conn:
        conn.execute(
            "INSERT INTO reflections (user_id, date, text) VALUES (?, ?, ?)",
            (user_id, today, text),
        )


def add_forgiveness_entry(user_id: int, name: str, note: str) -> None:
    with _connection() as conn:
        conn.execute(
            "INSERT INTO forgiveness_list (user_id, name, relationship_note) VALUES (?, ?, ?)",
            (user_id, name, note or None),
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
