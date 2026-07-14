"""Lazy issue map: raw JSONL records materialized to Issue objects on access.

``dict_to_issue`` is the dominant cost of loading a store — constructing
every Issue dataclass (plus comments, enums, datetimes) accounts for ~40%
of ``JSONLStorage._load`` wall time at scale, yet most CLI invocations touch
a handful of issues. This map lets ``_load`` store the raw parsed dicts and
defer construction to first access (dogcat-4g8d).

Entries live in a single dict whose values are either a raw record dict or
a materialized :class:`~dogcat.models.Issue`. ``__getitem__`` replaces the
raw dict with the Issue in place, which is safe during iteration (replacing
a dict value never resizes the dict) and guarantees identity: repeated
access returns the same object, so in-place mutations by storage code stay
visible through the map.

Raw records MUST be validated with
:func:`dogcat.models_serde.precheck_issue_record` before insertion via
:meth:`LazyIssueMap.set_raw` — materialization assumes ``dict_to_issue``
cannot raise, so malformed records are rejected at load time (where
``_load`` records them in ``_bad_lines``) rather than exploding at some
arbitrary later access.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import TYPE_CHECKING, Any

from dogcat.models import Issue
from dogcat.models_serde import dict_to_issue

if TYPE_CHECKING:
    from collections.abc import Iterator


class LazyIssueMap(MutableMapping[str, Issue]):
    """Mapping of ``full_id -> Issue`` that materializes records lazily."""

    __slots__ = ("_entries",)

    def __init__(self) -> None:
        self._entries: dict[str, Issue | dict[str, Any]] = {}

    def set_raw(self, full_id: str, data: dict[str, Any]) -> None:
        """Store a validated raw record (last-write-wins during replay)."""
        self._entries[full_id] = data

    def iter_id_parent(self) -> Iterator[tuple[str, str | None]]:
        """Yield ``(full_id, parent)`` pairs without materializing.

        Index rebuilds only need these two fields, and they run after every
        mutation — reading them off the raw dicts keeps ``dcat show <id>``
        from paying for 100k Issue constructions.
        """
        for full_id, value in self._entries.items():
            if isinstance(value, Issue):
                yield full_id, value.parent
            else:
                yield full_id, value.get("parent")

    def __getitem__(self, key: str) -> Issue:
        value = self._entries[key]
        if not isinstance(value, Issue):
            value = dict_to_issue(value)
            self._entries[key] = value
        return value

    def __setitem__(self, key: str, value: Issue) -> None:
        self._entries[key] = value

    def __delitem__(self, key: str) -> None:
        del self._entries[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    # Mapping's default __contains__ goes through __getitem__, which would
    # materialize on every membership test — override to stay key-only.
    def __contains__(self, key: object) -> bool:
        return key in self._entries

    # MutableMapping's default clear() pops entries one by one through
    # __getitem__, materializing each — override to drop them wholesale.
    def clear(self) -> None:
        self._entries.clear()
