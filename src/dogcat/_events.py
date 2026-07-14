"""Shared event-emission behavior for the JSONL stores.

Both :class:`~dogcat.storage.JSONLStorage` and
:class:`~dogcat.inbox.InboxStorage` record change events to a
:class:`~dogcat.event_log._BaseEventLog` and coalesce the data record + event
record into a single locked append. That logic was duplicated verbatim in both
classes; :class:`EventEmitterMixin` provides the one implementation. Each store
supplies ``_event_log`` (its ``EventLog`` / ``InboxEventLog``) and ``_append``
(its buffered writer). The per-store field selection for tracked-change diffs
stays in each class — it is configuration, not shared logic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from datetime import datetime

    from dogcat.event_log import _BaseEventLog


class EventSubject(Protocol):
    """The attributes an event needs from an issue or proposal.

    Declared as read-only properties so a class exposing ``full_id`` as a
    computed ``@property`` (as both :class:`~dogcat.models.Issue` and
    :class:`~dogcat.models.Proposal` do) satisfies the protocol — a plain
    ``full_id: str`` attribute would require a read-write field.
    """

    @property
    def full_id(self) -> str: ...
    @property
    def title(self) -> str: ...
    @property
    def updated_at(self) -> datetime: ...


class EventEmitterMixin:
    """Best-effort event emission shared by ``JSONLStorage`` / ``InboxStorage``.

    The subclass provides ``_event_log`` and ``_append``; both are declared here
    (type-check only) so the mixin can be type-checked in isolation without
    owning those members at runtime.
    """

    if TYPE_CHECKING:
        _event_log: _BaseEventLog

        def _append(self, records: list[dict[str, Any]]) -> None: ...

    def _emit_event(
        self,
        event_type: str,
        subject: EventSubject,
        changes: dict[str, dict[str, Any]],
        by: str | None = None,
    ) -> None:
        """Emit an event to the event log (best-effort)."""
        self._event_log.try_emit(
            event_type,
            subject.full_id,
            subject.updated_at.isoformat(),
            subject.title,
            changes,
            by=by,
        )

    def _build_event_record(
        self,
        event_type: str,
        subject: EventSubject,
        changes: dict[str, dict[str, Any]],
        by: str | None = None,
    ) -> dict[str, Any] | None:
        """Build the event JSONL dict for a mutation without writing it.

        Returns ``None`` when there are no changes to record, so callers can
        coalesce the data record + event record into one locked append, halving
        file-lock + fsync churn per mutation.
        """
        return self._event_log.build_record(
            event_type,
            subject.full_id,
            subject.updated_at.isoformat(),
            subject.title,
            changes,
            by=by,
        )

    def _append_with_event(
        self,
        records: list[dict[str, Any]],
        event_record: dict[str, Any] | None,
    ) -> None:
        """Append data records and an optional event record in one locked call.

        Single-lock, single-fsync equivalent of ``_append(records)`` followed by
        emitting the event — eliminates the write amplification a batched
        multi-id mutation (e.g. ``dcat close A B C``) would otherwise pay.
        """
        if event_record is None:
            self._append(records)
            return
        self._append([*records, event_record])
