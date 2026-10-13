"""Seed draft Individual + Group broadcast messages for all 8 days of
Paryushan (Sept 8-15, 2026), one of each per day, so the admin isn't
starting from a blank form for each of the 16 messages. Themes follow the
traditional 5 great vows (Ahimsa, Satya, Asteya, Brahmacharya, Aparigraha)
plus Tap and Kshama, closing on Samvatsari — a reasonable starting point,
NOT a final version.

Every field here is a draft: review and edit each one on the admin
dashboard's Content tab (click "Edit" next to a row) before it's sent —
Pratikraman timing in particular is a placeholder and should be corrected
to the Sangh's actual schedule. Safe to re-run: skips any date that
already has broadcast content, so it won't clobber edits already made.

Usage (run with -m from the repo root, not as a plain script path — see
README.md's "Run scripts with -m" note):
    uv run python -m scripts.seed_paryushan_broadcasts
"""

import datetime

from app.db import get_session, init_db
from app.models import Broadcast

_DRAFT_DAYS = [
    (1, "Ahimsa — Non-Violence & Compassion"),
    (2, "Satya — Truthfulness"),
    (3, "Asteya — Non-Stealing & Contentment"),
    (4, "Brahmacharya — Self-Restraint"),
    (5, "Aparigraha — Non-Attachment"),
    (6, "Tap — Austerity & Tapasya"),
    (7, "Kshama — Forgiveness"),
    (8, "Samvatsari — Universal Forgiveness (Micchami Dukkadam)"),
]

_START_DATE = datetime.date(2026, 9, 8)
_DRAFT_PRATIKRAMAN_TIMING = "7:00 PM (placeholder — confirm with the Sangh)"


def _individual_draft(day_number: int, theme: str) -> str:
    return (
        f"Jai Jinendra! Today is Day {day_number} of Paryushan — {theme}. "
        f"Pratikraman is at {_DRAFT_PRATIKRAMAN_TIMING}."
    )


def _group_draft(day_number: int, theme: str) -> str:
    return (
        f"📢 Sangh Update — Day {day_number} of Paryushan: {theme}. "
        f"Pratikraman timing: {_DRAFT_PRATIKRAMAN_TIMING}. "
        "Please share this with the group. Jai Jinendra!"
    )


def main() -> None:
    init_db()
    session = get_session()
    try:
        existing_dates = {b.date for b in session.query(Broadcast).all()}
        added = 0
        for day_number, theme in _DRAFT_DAYS:
            date = _START_DATE + datetime.timedelta(days=day_number - 1)
            if date in existing_dates:
                continue
            session.add(
                Broadcast(
                    date=date,
                    day_number=day_number,
                    individual_message_en=_individual_draft(day_number, theme),
                    group_message_en=_group_draft(day_number, theme),
                )
            )
            added += 1
        session.commit()
        print(
            f"Added {added} day(s) of draft broadcast content for admin review "
            f"(skipped {len(_DRAFT_DAYS) - added} already present)."
        )
    finally:
        session.close()


if __name__ == "__main__":
    main()
