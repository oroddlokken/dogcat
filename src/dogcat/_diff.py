"""Shared diffing primitives for event-log change tracking.

Storage and inbox both compute "what changed" between an old and new record
to emit event records. The same enum-normalization rule lives in three
places (storage, inbox, validate); centralising it here means any new
value-like type (or rule change) lands in one place.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable


def field_value(value: Any) -> Any:
    """Normalize a field value for diff comparison.

    Enums and other ``.value``-bearing wrappers are unwrapped to their
    underlying scalar so the diff compares like with like.
    """
    if hasattr(value, "value"):
        return value.value
    return value


def tracked_changes(
    old_values: dict[str, Any],
    new_values: dict[str, Any],
    tracked: Iterable[str],
) -> dict[str, dict[str, Any]]:
    """Compute the subset of changed fields restricted to ``tracked``.

    Returns a mapping ``{field: {"old": ..., "new": ...}}`` for each
    tracked field whose normalized value differs between ``old_values``
    and ``new_values``.
    """
    tracked_set = (
        tracked if isinstance(tracked, (set, frozenset)) else frozenset(tracked)
    )
    changes: dict[str, dict[str, Any]] = {}
    for field_name in tracked_set:
        old = field_value(old_values.get(field_name))
        new = field_value(new_values.get(field_name))
        if old != new:
            changes[field_name] = {"old": old, "new": new}
    return changes
