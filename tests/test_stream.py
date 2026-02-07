"""Tests for event streaming and change detection."""

import json
from datetime import timezone
from pathlib import Path
from typing import Any

from dogcat.models import Issue, Status, issue_to_dict
from dogcat.storage import JSONLStorage
from dogcat.stream import StreamEmitter, StreamEvent, StreamWatcher


class TestStreamEvent:
    """Test StreamEvent dataclass."""

    def test_stream_event_creation(self) -> None:
        """Test creating a stream event."""
        from datetime import datetime

        event = StreamEvent(
            event_type="created",
            issue_id="issue-1",
            timestamp=datetime.now(timezone.utc),
            by="user@example.com",
            changes={"title": {"old": None, "new": "Test"}},
        )

        assert event.event_type == "created"
        assert event.issue_id == "issue-1"
        assert event.by == "user@example.com"

    def test_stream_event_to_dict(self) -> None:
        """Test converting event to dict."""
        from datetime import datetime

        now = datetime.now(timezone.utc)
        event = StreamEvent(
            event_type="updated",
            issue_id="issue-1",
            timestamp=now,
            by="user@example.com",
            changes={"status": {"old": "open", "new": "in_progress"}},
        )

        data = event.to_dict()
        assert data["event_type"] == "updated"
        assert data["issue_id"] == "issue-1"
        assert isinstance(data["timestamp"], str)
        assert data["by"] == "user@example.com"


class TestStreamEmitter:
    """Test StreamEmitter change detection."""

    def test_emitter_initialization(self, temp_dogcats_dir: Path) -> None:
        """Test initializing emitter."""
        storage_path = temp_dogcats_dir / "issues.jsonl"
        emitter = StreamEmitter(str(storage_path))

        assert emitter.storage_path == storage_path

    def test_detect_create(self, temp_dogcats_dir: Path) -> None:
        """Test detecting issue creation."""
        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path))

        # Create initial state
        emitter = StreamEmitter(str(storage_path))
        old_state = emitter.current_state.copy()

        # Create an issue
        issue = Issue(id="issue-1", title="Test issue")
        storage.create(issue)

        # Get new state
        storage = JSONLStorage(str(storage_path))
        new_state: dict[str, Any] = {}
        for issue in storage.list():
            new_state[issue.id] = issue_to_dict(issue)

        # Compute diff
        events = emitter._compute_diff(old_state, new_state)  # noqa: SLF001

        assert len(events) == 1
        assert events[0].event_type == "created"
        assert events[0].issue_id == "issue-1"
        assert "title" in events[0].changes

    def test_detect_update(self, temp_dogcats_dir: Path) -> None:
        """Test detecting issue update."""
        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path))

        # Create an issue
        issue = Issue(id="issue-1", title="Original", status=Status.OPEN)
        storage.create(issue)

        # Get initial state
        storage = JSONLStorage(str(storage_path))
        old_state: dict[str, Any] = {}
        for issue in storage.list():
            old_state[issue.id] = issue_to_dict(issue)

        # Update the issue
        storage.update("issue-1", {"title": "Updated"})

        # Get new state
        storage = JSONLStorage(str(storage_path))
        new_state: dict[str, Any] = {}
        for issue in storage.list():
            new_state[issue.id] = issue_to_dict(issue)

        # Compute diff
        emitter = StreamEmitter(str(storage_path))
        events = emitter._compute_diff(old_state, new_state)  # noqa: SLF001

        assert len(events) == 1
        assert events[0].event_type == "updated"
        assert "title" in events[0].changes
        assert events[0].changes["title"]["old"] == "Original"
        assert events[0].changes["title"]["new"] == "Updated"

    def test_detect_close(self, temp_dogcats_dir: Path) -> None:
        """Test detecting issue close (status change)."""
        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path))

        # Create an issue
        issue = Issue(id="issue-1", title="Test", status=Status.OPEN)
        storage.create(issue)

        # Get initial state
        storage = JSONLStorage(str(storage_path))
        old_state: dict[str, Any] = {}
        for issue in storage.list():
            old_state[issue.id] = issue_to_dict(issue)

        # Close the issue
        storage.close("issue-1")

        # Get new state
        storage = JSONLStorage(str(storage_path))
        new_state: dict[str, Any] = {}
        for issue in storage.list():
            new_state[issue.id] = issue_to_dict(issue)

        # Compute diff
        emitter = StreamEmitter(str(storage_path))
        events = emitter._compute_diff(old_state, new_state)  # noqa: SLF001

        assert len(events) == 1
        assert events[0].event_type == "closed"
        assert "status" in events[0].changes
        assert events[0].changes["status"]["old"] == "open"
        assert events[0].changes["status"]["new"] == "closed"

    def test_multiple_changes(self, temp_dogcats_dir: Path) -> None:
        """Test detecting multiple changes at once."""
        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path))

        # Create two issues
        storage.create(Issue(id="issue-1", title="Test 1"))
        storage.create(Issue(id="issue-2", title="Test 2"))

        # Get initial state
        storage = JSONLStorage(str(storage_path))
        old_state: dict[str, Any] = {}
        for issue in storage.list():
            old_state[issue.id] = issue_to_dict(issue)

        # Create a new issue and update an existing one
        storage.create(Issue(id="issue-3", title="Test 3"))
        storage.update("issue-1", {"title": "Updated"})

        # Get new state
        storage = JSONLStorage(str(storage_path))
        new_state: dict[str, Any] = {}
        for issue in storage.list():
            new_state[issue.id] = issue_to_dict(issue)

        # Compute diff
        emitter = StreamEmitter(str(storage_path))
        events = emitter._compute_diff(old_state, new_state)  # noqa: SLF001

        assert len(events) == 2
        event_types = {e.event_type for e in events}
        assert "created" in event_types
        assert "updated" in event_types

    def test_no_changes(self, temp_dogcats_dir: Path) -> None:
        """Test when there are no changes."""
        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path))

        # Create an issue
        storage.create(Issue(id="issue-1", title="Test"))

        # Get state
        storage = JSONLStorage(str(storage_path))
        state: dict[str, Any] = {}
        for issue in storage.list():
            state[issue.id] = issue_to_dict(issue)

        # Compute diff with same state
        emitter = StreamEmitter(str(storage_path))
        events = emitter._compute_diff(state, state)  # noqa: SLF001

        assert len(events) == 0


class TestStreamWatcher:
    """Test StreamWatcher."""

    def test_watcher_initialization(self, temp_dogcats_dir: Path) -> None:
        """Test initializing watcher."""
        storage_path = temp_dogcats_dir / "issues.jsonl"
        watcher = StreamWatcher(storage_path=str(storage_path))

        assert watcher.storage_path == Path(storage_path)

    def test_watcher_events_list(self, temp_dogcats_dir: Path) -> None:
        """Test watcher events list."""
        storage_path = temp_dogcats_dir / "issues.jsonl"
        watcher = StreamWatcher(storage_path=str(storage_path))

        assert isinstance(watcher.events, list)
        assert len(watcher.events) == 0


class TestStreamIntegration:
    """Integration tests for streaming."""

    def test_event_json_serialization(self, temp_dogcats_dir: Path) -> None:
        """Test that events can be serialized as JSON."""
        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path))

        # Create an issue
        storage.create(Issue(id="issue-1", title="Test"))

        # Get state
        storage = JSONLStorage(str(storage_path))
        state: dict[str, Any] = {}
        for issue in storage.list():
            state[issue.id] = issue_to_dict(issue)

        # Create event and serialize
        emitter = StreamEmitter(str(storage_path))
        empty_state: dict[str, Any] = {}
        events = emitter._compute_diff(empty_state, state)  # noqa: SLF001

        assert len(events) > 0
        for event in events:
            # Should be serializable as JSON
            json_str = json.dumps(event.to_dict())
            assert json_str is not None
            # Should be deserializable
            data = json.loads(json_str)
            assert data["event_type"] in ["created", "updated", "closed", "deleted"]

    def test_by_tracking_in_events(self, temp_dogcats_dir: Path) -> None:
        """Test that by attribution is tracked in events."""
        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path))

        storage.create(Issue(id="issue-1", title="Test"))

        storage = JSONLStorage(str(storage_path))
        state: dict[str, Any] = {}
        for issue in storage.list():
            state[issue.id] = issue_to_dict(issue)

        emitter = StreamEmitter(str(storage_path), by="user@example.com")
        empty_state: dict[str, Any] = {}
        events = emitter._compute_diff(empty_state, state)  # noqa: SLF001

        assert len(events) > 0
        assert events[0].by == "user@example.com"
