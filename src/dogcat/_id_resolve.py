"""Shared partial-ID resolution for issues and proposals.

Both :class:`dogcat.storage.JSONLStorage` and :class:`dogcat.inbox.InboxStorage`
need to map a partial id (e.g. ``"3hup"`` or ``"dogcat-inbox-4kzj"``) to a full
id from a known set. The algorithm is identical:

1. exact match wins,
2. then any id whose suffix or hash-segment matches the input,
3. >1 match raises with a unified ambiguity message.

Uses :py:meth:`str.rsplit` so multi-segment full ids like
``"dogcat-inbox-X"`` resolve correctly. (The inbox always had ``rsplit`` and
storage had ``split`` — they would diverge for any namespace containing a
hyphen. This helper picks the safe variant for both.)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable


def resolve_partial_id(
    partial_id: str,
    ids: Iterable[str],
    *,
    kind: str = "ids",
) -> str | None:
    """Resolve ``partial_id`` against ``ids``.

    Args:
        partial_id: Full or partial id (suffix or short hash).
        ids: All candidate full ids.
        kind: Plural noun used in the ambiguity error (e.g. ``"issues"``,
            ``"proposals"``).

    Returns:
        The full id, or ``None`` if no match.

    Raises:
        ValueError: If ``partial_id`` matches more than one id.
    """
    if not partial_id or not partial_id.strip():
        return None

    id_set = ids if isinstance(ids, set) else set(ids)

    if partial_id in id_set:
        return partial_id

    matches = [
        full_id
        for full_id in id_set
        if full_id.endswith(partial_id) or full_id.rsplit("-", 1)[-1] == partial_id
    ]

    if len(matches) == 1:
        return matches[0]

    if len(matches) > 1:
        sample = ", ".join(sorted(matches)[:5])
        suffix = f" and {len(matches) - 5} more" if len(matches) > 5 else ""
        msg = (
            f"Ambiguous partial ID '{partial_id}' "
            f"matches {len(matches)} {kind}: {sample}{suffix}"
        )
        raise ValueError(msg)

    return None
