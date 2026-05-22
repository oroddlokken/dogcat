"""Derive ASCII namespace slugs from directory names.

The slug must be safe to use as an issue ID prefix (``<slug>-abcd``),
in shell completion, and in URLs. That means lowercase ASCII letters,
digits, and hyphens only.

Norwegian and German digraphs are transliterated explicitly because
the standard NFKD strip would drop them (æ has no decomposition to
ASCII letters). Other accented Latin characters fall through to NFKD
strip, which preserves the base letter.
"""

from __future__ import annotations

import re
import unicodedata

_TRANSLIT: dict[str, str] = {
    "æ": "ae",
    "Æ": "Ae",
    "ø": "oe",
    "Ø": "Oe",
    "å": "aa",
    "Å": "Aa",
    "ä": "ae",
    "Ä": "Ae",
    "ö": "oe",
    "Ö": "Oe",
    "ü": "ue",
    "Ü": "Ue",
    "ß": "ss",
}

_NON_SLUG = re.compile(r"[^a-z0-9-]+")
_MULTI_DASH = re.compile(r"-+")


def slug_from_dir(name: str) -> str | None:
    """Return a slug suitable for use as a dogcat namespace, or None.

    Returns None when the input cannot be reduced to at least one
    ASCII alphanumeric character (empty string, only punctuation, only
    CJK or emoji, etc.). Callers should fall back to the next rule in
    their resolution order.
    """
    if not name:
        return None

    out = "".join(_TRANSLIT.get(ch, ch) for ch in name)

    out = unicodedata.normalize("NFKD", out)
    out = "".join(ch for ch in out if not unicodedata.combining(ch))

    out = out.lower()
    out = _NON_SLUG.sub("-", out)
    out = _MULTI_DASH.sub("-", out)
    out = out.strip("-")

    return out or None
