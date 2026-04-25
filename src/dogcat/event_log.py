"""Persistent event log for tracking issue changes."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import orjson

from dogcat._version import version as _dcat_version
from dogcat.locking import advisory_file_lock

if TYPE_CHECKING:
    from contextlib import AbstractContextManager


@dataclass
class EventRecord:
    """A single event recording a change to an issue."""

    event_type: str  # "created", "updated", "closed", "reopened", "deleted"
    issue_id: str  # full_id, e.g. "dc-4kzj"
    timestamp: str  # ISO-8601
    by: str | None = None
    title: str | None = None
    changes: dict[str, dict[str, Any]] = field(
        default_factory=dict[str, dict[str, Any]],
    )


def _serialize(event: EventRecord) -> dict[str, Any]:
    """Serialize an EventRecord to a dict for JSONL storage."""
    data: dict[str, Any] = {
        "record_type": "event",
        "dcat_version": _dcat_version,
        "event_type": event.event_type,
        "issue_id": event.issue_id,
        "timestamp": event.timestamp,
        "by": event.by,
        "changes": event.changes,
    }
    if event.title is not None:
        data["title"] = event.title
    return data


def _deserialize(data: dict[str, Any]) -> EventRecord:
    """Deserialize a dict from JSONL into an EventRecord."""
    return EventRecord(
        event_type=data["event_type"],
        issue_id=data["issue_id"],
        timestamp=data["timestamp"],
        by=data.get("by"),
        title=data.get("title"),
        changes=data.get("changes", {}),
    )


def diff_metadata(
    old: dict[str, Any] | None,
    new: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Diff two metadata dicts into per-key change entries.

    Keys are emitted as ``metadata.<key>`` so they slot alongside top-level
    field changes in event records and dcat diff output. A missing key is
    treated as ``None`` — e.g. setting ``manual=True`` on an issue without
    prior metadata yields ``{"metadata.manual": {"old": None, "new": True}}``.
    """
    old = old or {}
    new = new or {}
    changes: dict[str, dict[str, Any]] = {}
    for key in set(old) | set(new):
        old_v = old.get(key)
        new_v = new.get(key)
        if old_v != new_v:
            changes[f"metadata.{key}"] = {"old": old_v, "new": new_v}
    return changes


class EventLog:
    """Append-only event log stored alongside issues in .dogcats/issues.jsonl."""

    def __init__(self, dogcats_dir: str | Path) -> None:
        self.dogcats_dir = Path(dogcats_dir)
        self.path = self.dogcats_dir / "issues.jsonl"
        self._lock_path = self.dogcats_dir / ".issues.lock"

    def append(self, event: EventRecord) -> None:
        """Append a single event record to issues.jsonl."""
        data = _serialize(event)
        with self._file_lock(), self.path.open("ab") as f:
            f.write(orjson.dumps(data))
            f.write(b"\n")
            f.flush()

    def read(
        self,
        *,
        issue_id: str | None = None,
        limit: int | None = None,
    ) -> list[EventRecord]:
        """Read events in reverse chronological order (newest first).

        Args:
            issue_id: Filter to events for this issue ID.
            limit: Maximum number of events to return.

        Returns:
            List of EventRecord, newest first.
        """
        if not self.path.exists():
            return []

        events: list[EventRecord] = []
        with self.path.open("rb") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = orjson.loads(line)
                if data.get("record_type") != "event":
                    continue
                record = _deserialize(data)
                if issue_id is not None and record.issue_id != issue_id:
                    continue
                events.append(record)

        # Reverse for newest-first
        events.reverse()

        if limit is not None:
            events = events[:limit]

        return events

    def _file_lock(self) -> AbstractContextManager[None]:
        """Create an advisory file lock context manager."""
        return advisory_file_lock(self._lock_path)


class InboxEventLog:
    """Append-only event log stored alongside proposals in .dogcats/inbox.jsonl."""

    def __init__(self, dogcats_dir: str | Path) -> None:
        self.dogcats_dir = Path(dogcats_dir)
        self.path = self.dogcats_dir / "inbox.jsonl"
        self._lock_path = self.dogcats_dir / ".issues.lock"

    def append(self, event: EventRecord) -> None:
        """Append a single event record to inbox.jsonl."""
        data = _serialize(event)
        with self._file_lock(), self.path.open("ab") as f:
            f.write(orjson.dumps(data))
            f.write(b"\n")
            f.flush()

    def read(
        self,
        *,
        issue_id: str | None = None,
        limit: int | None = None,
    ) -> list[EventRecord]:
        """Read inbox events in reverse chronological order (newest first).

        Args:
            issue_id: Filter to events for this proposal ID.
            limit: Maximum number of events to return.

        Returns:
            List of EventRecord, newest first.
        """
        if not self.path.exists():
            return []

        events: list[EventRecord] = []
        with self.path.open("rb") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = orjson.loads(line)
                if data.get("record_type") != "event":
                    continue
                record = _deserialize(data)
                if issue_id is not None and record.issue_id != issue_id:
                    continue
                events.append(record)

        # Reverse for newest-first
        events.reverse()

        if limit is not None:
            events = events[:limit]

        return events

    def _file_lock(self) -> AbstractContextManager[None]:
        """Create an advisory file lock context manager."""
        return advisory_file_lock(self._lock_path)
