"""Tests for event log storage."""

from __future__ import annotations

from typing import TYPE_CHECKING

import orjson
import pytest

from dogcat.event_log import (
    EventLog,
    EventRecord,
    _deserialize,
    _serialize,
    diff_metadata,
)

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

    def test_read_limit_zero_returns_empty(self, event_log: EventLog) -> None:
        """``limit=0`` is a valid input that returns an empty list."""
        for i in range(3):
            event_log.append(
                EventRecord(
                    event_type="updated",
                    issue_id="dc-abcd",
                    timestamp=f"2026-02-10T{10 + i}:00:00+01:00",
                ),
            )
        assert event_log.read(limit=0) == []

    def test_read_limit_negative_rejected(self, event_log: EventLog) -> None:
        """Negative limits are rejected with ``ValueError``.

        Prior to dogcat-3r0s the API silently accepted ``limit=-1`` and
        sliced off the last event (``events[:-1]``), an off-by-one bug
        observable to any caller passing through user input.
        """
        with pytest.raises(ValueError, match="limit must be"):
            event_log.read(limit=-1)

    def test_read_limit_giant_returns_all(self, event_log: EventLog) -> None:
        """A limit larger than the total event count returns every event."""
        for i in range(3):
            event_log.append(
                EventRecord(
                    event_type="updated",
                    issue_id="dc-abcd",
                    timestamp=f"2026-02-10T{10 + i}:00:00+01:00",
                ),
            )
        assert len(event_log.read(limit=10_000)) == 3

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

    def test_read_skips_invalid_json_line(self, event_log: EventLog) -> None:
        """An invalid-JSON line in the middle is logged and skipped, not raised.

        Regression for dogcat-4s8b: read() used to bubble JSONDecodeError
        out to ``dcat history`` etc.
        """
        valid_record = EventRecord(
            event_type="created",
            issue_id="dc-aaa1",
            timestamp="2026-02-10T10:00:00+01:00",
        )
        event_log.append(valid_record)
        with event_log.path.open("ab") as f:
            f.write(b"not json\n")
        event_log.append(
            EventRecord(
                event_type="updated",
                issue_id="dc-bbb2",
                timestamp="2026-02-10T11:00:00+01:00",
            )
        )

        events = event_log.read()
        ids = {ev.issue_id for ev in events}
        assert ids == {"dc-aaa1", "dc-bbb2"}

    def test_read_skips_non_dict_line(self, event_log: EventLog) -> None:
        """A line that decodes to a scalar / null is skipped, not raised."""
        event_log.append(
            EventRecord(
                event_type="created",
                issue_id="dc-aaa1",
                timestamp="2026-02-10T10:00:00+01:00",
            )
        )
        with event_log.path.open("ab") as f:
            f.write(b"42\n")
            f.write(b"null\n")
            f.write(b'"string"\n')

        events = event_log.read()
        assert {ev.issue_id for ev in events} == {"dc-aaa1"}

    def test_file_lock_open_failure_raises_runtimeerror(
        self, event_log: EventLog
    ) -> None:
        """OSError opening the event log lock file is wrapped in RuntimeError."""
        event_log._lock_path = (
            event_log.dogcats_dir / "missing-dir" / "subdir" / ".issues.lock"
        )

        with pytest.raises(RuntimeError, match="Failed to open lock file"):
            event_log.append(
                EventRecord(
                    event_type="created",
                    issue_id="dc-zzzz",
                    timestamp="2026-02-10T10:00:00+01:00",
                ),
            )


class TestDiffMetadata:
    """Tests for the ``diff_metadata`` helper."""

    def test_returns_empty_for_identical_inputs(self) -> None:
        """Returns empty for identical inputs."""
        assert diff_metadata({"manual": True}, {"manual": True}) == {}

    def test_returns_empty_for_two_empty_dicts(self) -> None:
        """Returns empty for two empty dicts."""
        assert diff_metadata({}, {}) == {}

    def test_returns_empty_for_two_none_inputs(self) -> None:
        """Returns empty for two none inputs."""
        assert diff_metadata(None, None) == {}

    def test_added_key_yields_old_none(self) -> None:
        """Added key yields old none."""
        result = diff_metadata({}, {"manual": True})
        assert result == {"metadata.manual": {"old": None, "new": True}}

    def test_removed_key_yields_new_none(self) -> None:
        """Removed key yields new none."""
        result = diff_metadata({"manual": True}, {})
        assert result == {"metadata.manual": {"old": True, "new": None}}

    def test_changed_value(self) -> None:
        """Changed value."""
        result = diff_metadata({"prio": 1}, {"prio": 2})
        assert result == {"metadata.prio": {"old": 1, "new": 2}}

    def test_none_old_treated_as_empty(self) -> None:
        """None old treated as empty."""
        result = diff_metadata(None, {"manual": True})
        assert result == {"metadata.manual": {"old": None, "new": True}}

    def test_none_new_treated_as_empty(self) -> None:
        """None new treated as empty."""
        result = diff_metadata({"manual": True}, None)
        assert result == {"metadata.manual": {"old": True, "new": None}}

    def test_keys_emitted_with_metadata_prefix(self) -> None:
        """Keys emitted with metadata prefix."""
        result = diff_metadata({}, {"a": 1, "b": 2})
        assert set(result) == {"metadata.a", "metadata.b"}


class TestBuildRecord:
    """Tests for the static ``EventLog.build_record`` helper."""

    def test_returns_none_when_no_changes(self) -> None:
        """Returns none when no changes."""
        assert (
            EventLog.build_record(
                event_type="updated",
                full_id="dc-abcd",
                timestamp="2026-02-10T10:00:00+01:00",
                title=None,
                changes={},
            )
            is None
        )

    def test_returns_serialized_dict_with_record_type(self) -> None:
        """Returns serialized dict with record type."""
        record = EventLog.build_record(
            event_type="updated",
            full_id="dc-abcd",
            timestamp="2026-02-10T10:00:00+01:00",
            title="Test issue",
            changes={"status": {"old": "open", "new": "closed"}},
            by="user@example.com",
        )
        assert record is not None
        assert record["record_type"] == "event"
        assert record["event_type"] == "updated"
        assert record["issue_id"] == "dc-abcd"
        assert record["title"] == "Test issue"
        assert record["by"] == "user@example.com"
        assert record["changes"] == {"status": {"old": "open", "new": "closed"}}

    def test_no_event_written_to_disk(self, event_log: EventLog) -> None:
        """build_record never touches the file — only ``append`` does."""
        EventLog.build_record(
            event_type="updated",
            full_id="dc-abcd",
            timestamp="2026-02-10T10:00:00+01:00",
            title=None,
            changes={"status": {"old": "open", "new": "closed"}},
        )
        assert not event_log.path.exists()
