import json
from pathlib import Path
from typing import Any

_CATALOG_PATH = Path(__file__).parent / "message_catalog.json"

with open(_CATALOG_PATH, encoding="utf-8") as f:
    _CATALOG: dict[str, dict[str, str]] = json.load(f)


def get_message(message_id: str, language: str, **kwargs: Any) -> str:
    """Look up a catalog entry by id and language, then fill in template values.

    `language` should be "en" or "gu". Falls back to "en" if the requested
    language is missing for that id (should not happen once the catalog is
    complete, but keeps onboarding from breaking on a partial entry).
    """
    entry = _CATALOG.get(message_id)
    if entry is None:
        raise KeyError(f"Unknown message catalog id: {message_id!r}")

    template = entry.get(language) or entry.get("en")
    if template is None:
        raise KeyError(f"No '{language}' or 'en' text for message id: {message_id!r}")

    return template.format(**kwargs)
