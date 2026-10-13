import json
from pathlib import Path
from typing import Any

from app.translation import translate_to_gujarati

_CATALOG_PATH = Path(__file__).parent / "message_catalog.json"

with open(_CATALOG_PATH, encoding="utf-8") as f:
    _CATALOG: dict[str, dict[str, str]] = json.load(f)


def get_message(message_id: str, language: str, **kwargs: Any) -> str:
    """Look up a catalog entry by id, fill in template values, then
    translate to Gujarati if needed (see app/translation.py).

    Formatting happens BEFORE translation, not after — translating a
    template like "Day {day_number} of 8" risks the API mangling the
    `{...}` placeholder syntax itself.
    """
    entry = _CATALOG.get(message_id)
    if entry is None:
        raise KeyError(f"Unknown message catalog id: {message_id!r}")

    template = entry.get("en")
    if template is None:
        raise KeyError(f"No 'en' text for message id: {message_id!r}")

    text = template.format(**kwargs)
    if language == "gu":
        return translate_to_gujarati(text)
    return text
