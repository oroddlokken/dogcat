"""Tests for event log storage."""

from __future__ import annotations

from typing import TYPE_CHECKING

import orjson
import pytest

from dogcat.event_log import EventLog, EventRecord, _deserialize, _serialize

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def event_log(temp_dogcats_dir: Path) -> EventLog:
    """Provide event log fixture."""
    return EventLog(temp_dogcats_dir)


class TestEventRecord:
    """Tests for event record."""

    def test_create_record(self) -> None:
        """Test create record."""
        record = EventRecord(
            event_type="created",
            issue_id="dc-abcd",
            timestamp="2026-02-10T14:00:00+01:00",
            by="user@example.com",
            changes={"title": {"old": None, "new": "Test issue"}},
        )
        assert record.event_type == "created"
        assert record.issue_id == "dc-abcd"
        assert record.by == "user@example.com"
        assert record.changes["title"]["new"] == "Test issue"

    def test_default_changes(self) -> None:
        """Test default changes."""
        record = EventRecord(
            event_type="created",
            issue_id="dc-abcd",
            timestamp="2026-02-10T14:00:00+01:00",
        )
        assert record.changes == {}
        assert record.by is None


class TestSerialization:
    """Tests for serialization."""

    def test_round_trip(self) -> None:
        """Test round trip."""
        original = EventRecord(
            event_type="updated",
            issue_id="dc-1234",
            timestamp="2026-02-10T15:00:00+01:00",
            by="agent@test.com",
            changes={
                "status": {"old": "open", "new": "in_progress"},
                "priority": {"old": 2, "new": 1},
            },
        )
        data = _serialize(original)
        restored = _deserialize(data)
        assert restored.event_type == original.event_type
        assert restored.issue_id == original.issue_id
        assert restored.timestamp == original.timestamp
        assert restored.by == original.by
        assert restored.changes == original.changes

    def test_serialize_has_record_type(self) -> None:
        """Test serialize has record type."""
        record = EventRecord(
            event_type="created",
            issue_id="dc-abcd",
            timestamp="2026-02-10T14:00:00+01:00",
        )
        data = _serialize(record)
        assert data["record_type"] == "event"
        assert "dcat_version" in data

    def test_deserialize_missing_optional(self) -> None:
        """Test deserialize missing optional."""
        data = {
            "event_type": "created",
            "issue_id": "dc-abcd",
            "timestamp": "2026-02-10T14:00:00+01:00",
        }
        record = _deserialize(data)
        assert record.by is None
        assert record.changes == {}


class TestEventLogAppendAndRead:
    """Tests for event log append and read."""

    def test_append_creates_file(self, event_log: EventLog) -> None:
        """Test append creates file."""
        assert not event_log.path.exists()
        event_log.append(
            EventRecord(
                event_type="created",
                issue_id="dc-abcd",
                timestamp="2026-02-10T14:00:00+01:00",
            ),
        )
        assert event_log.path.exists()

    def test_append_writes_valid_jsonl(self, event_log: EventLog) -> None:
        """Test append writes valid jsonl."""
        event_log.append(
            EventRecord(
                event_type="created",
                issue_id="dc-abcd",
                timestamp="2026-02-10T14:00:00+01:00",
                changes={"title": {"old": None, "new": "Test"}},
            ),
        )
        line = event_log.path.read_bytes().strip()
        data = orjson.loads(line)
        assert data["record_type"] == "event"
        assert data["event_type"] == "created"
        assert data["issue_id"] == "dc-abcd"

    def test_read_empty(self, event_log: EventLog) -> None:
        """Test read empty."""
        assert event_log.read() == []

    def test_read_returns_reverse_chronological(self, event_log: EventLog) -> None:
        """Test read returns reverse chronological."""
        for i in range(3):
            event_log.append(
                EventRecord(
                    event_type="updated",
                    issue_id=f"dc-{i:04d}",
                    timestamp=f"2026-02-10T{14 + i}:00:00+01:00",
                ),
            )
        events = event_log.read()
        assert len(events) == 3
        # Newest first
        assert events[0].issue_id == "dc-0002"
        assert events[2].issue_id == "dc-0000"

    def test_read_filter_by_issue_id(self, event_log: EventLog) -> None:
        """Test read filter by issue id."""
        event_log.append(
            EventRecord(
                event_type="created",
                issue_id="dc-aaaa",
                timestamp="2026-02-10T14:00:00+01:00",
            ),
        )
        event_log.append(
            EventRecord(
                event_type="updated",
                issue_id="dc-bbbb",
                timestamp="2026-02-10T15:00:00+01:00",
            ),
        )
        event_log.append(
            EventRecord(
                event_type="closed",
                issue_id="dc-aaaa",
                timestamp="2026-02-10T16:00:00+01:00",
            ),
        )

        events = event_log.read(issue_id="dc-aaaa")
        assert len(events) == 2
        assert all(e.issue_id == "dc-aaaa" for e in events)
        assert events[0].event_type == "closed"
        assert events[1].event_type == "created"

    def test_read_with_limit(self, event_log: EventLog) -> None:
        """Test read with limit."""
        for i in range(10):
            event_log.append(
                EventRecord(
                    event_type="updated",
                    issue_id="dc-abcd",
                    timestamp=f"2026-02-10T{10 + i}:00:00+01:00",
                ),
            )
        events = event_log.read(limit=3)
        assert len(events) == 3

    def test_read_with_issue_id_and_limit(self, event_log: EventLog) -> None:
        """Test read with issue id and limit."""
        for i in range(5):
            event_log.append(
                EventRecord(
                    event_type="updated",
                    issue_id="dc-aaaa",
                    timestamp=f"2026-02-10T{10 + i}:00:00+01:00",
                ),
            )
        event_log.append(
            EventRecord(
                event_type="created",
                issue_id="dc-bbbb",
                timestamp="2026-02-10T20:00:00+01:00",
            ),
        )
        events = event_log.read(issue_id="dc-aaaa", limit=2)
        assert len(events) == 2
        assert all(e.issue_id == "dc-aaaa" for e in events)

    def test_multiple_appends(self, event_log: EventLog) -> None:
        """Test multiple appends."""
        for i in range(5):
            event_log.append(
                EventRecord(
                    event_type="updated",
                    issue_id="dc-abcd",
                    timestamp=f"2026-02-10T{10 + i}:00:00+01:00",
                ),
            )
        lines = event_log.path.read_bytes().strip().split(b"\n")
        assert len(lines) == 5
