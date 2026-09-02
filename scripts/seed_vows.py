"""Seed a starter set of candidate daily vows for admin review.

These are drafted starting points grounded in well-known Jain ethical
principles (Ahimsa, Satya, Asteya, Brahmacharya, Aparigraha) and Paryushan
themes (forgiveness, reflection) — NOT a finished, authoritative list.
Every vow is inserted with approved=False; an admin must review and
approve each one in the dashboard (Content tab) before it can ever be
sent to a user. Safe to re-run — skips vows already present by exact
English text.

Usage:
    uv run python scripts/seed_vows.py
"""

from app.db import get_session, init_db
from app.models import Vow
from app.translation import translate_to_gujarati

_STARTER_VOWS = [
    "Today, I will not raise my voice in anger toward anyone.",
    "Today, I will speak only what is true and kind — even when it's difficult.",
    "Today, I will not take anything that isn't freely given to me, not even a small thing.",
    "Today, I will practice contentment and not covet what belongs to others.",
    "Today, I will let go of one grudge I've been holding.",
    "Today, I will avoid wasting food, water, or any resource.",
    "Today, I will be mindful of the smallest creatures around me and avoid harming them, even unintentionally.",
    "Today, I will spend at least ten quiet minutes in reflection or prayer.",
    "Today, I will forgive someone who has hurt me, even if only in my own heart.",
    "Today, I will ask forgiveness from someone I may have wronged.",
    "Today, I will practice restraint in what I eat and drink, mindful of Ahimsa.",
    "Today, I will not gossip or speak ill of anyone, present or absent.",
    "Today, I will offer help to someone without expecting anything in return.",
    "Today, I will limit my possessions' hold on me — I will not buy anything I don't need.",
    "Today, I will practice patience with someone who tests it.",
    "Today, I will express gratitude to at least three people in my life.",
    "Today, I will avoid unnecessary waste — I will use only what I truly need.",
    "Today, I will listen more than I speak.",
    "Today, I will treat every living being I encounter with compassion.",
    "Today, I will reflect on one mistake I made recently and how I can do better.",
    "Today, I will avoid harsh or hurtful words, even when frustrated.",
    "Today, I will practice honesty in even the smallest matters.",
    "Today, I will spend time with family or community rather than alone with distractions.",
    "Today, I will control one habit that doesn't serve my well-being.",
    "Today, I will remember that every soul I meet is on its own journey, and treat them with respect.",
]


def main() -> None:
    init_db()
    session = get_session()
    try:
        existing = {v.text_en for v in session.query(Vow).all()}
        added = 0
        for text_en in _STARTER_VOWS:
            if text_en in existing:
                continue
            session.add(Vow(text_en=text_en, text_gu=translate_to_gujarati(text_en), approved=False))
            added += 1
        session.commit()
        print(f"Added {added} new vow candidate(s) for admin review (skipped {len(_STARTER_VOWS) - added} already present).")
    finally:
        session.close()


if __name__ == "__main__":
    main()
