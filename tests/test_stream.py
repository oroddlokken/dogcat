"""Tests for event streaming and change detection."""

import json
from datetime import timezone
from pathlib import Path
from typing import Any

from dogcat.inbox import InboxStorage
from dogcat.models import Issue, Proposal, Status, issue_to_dict
from dogcat.storage import JSONLStorage
from dogcat.stream import (
    InboxStreamEmitter,
    StreamEmitter,
    StreamEvent,
    StreamWatcher,
)


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
            # Should round-trip through JSON serialization
            json_str = json.dumps(event.to_dict())
            assert len(json_str) > 2  # More than just "{}"
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


class TestStreamEmitterIncrementalParsing:
    """Test incremental parsing in StreamEmitter._handle_file_change()."""

    def test_incremental_parse_on_append(self, temp_dogcats_dir: Path) -> None:
        """Test that appending to the file triggers incremental parse."""
        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path))
        storage.create(Issue(id="issue-1", title="First"))

        # Create emitter (loads initial state and records file position)
        captured_events: list[StreamEvent] = []
        emitter = StreamEmitter(
            str(storage_path),
            on_event=lambda e: captured_events.append(e),
        )
        initial_position = emitter._file_position

        # Append a new issue to the file
        storage.create(Issue(id="issue-2", title="Second"))

        # Trigger file change handling
        emitter._handle_file_change()  # noqa: SLF001

        # Position should have advanced (incremental parse)
        assert emitter._file_position > initial_position

        # Should detect the new issue
        assert len(captured_events) == 1
        assert captured_events[0].event_type == "created"
        assert captured_events[0].issue_id == "dc-issue-2"

    def test_full_reload_on_file_shrink(self, temp_dogcats_dir: Path) -> None:
        """Test that file shrinking triggers full reload instead of incremental."""
        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path))

        # Create several issues to build up file size
        storage.create(Issue(id="issue-1", title="First"))
        storage.create(Issue(id="issue-2", title="Second"))
        storage.create(Issue(id="issue-3", title="Third"))

        # Create emitter with state for all three issues
        captured_events: list[StreamEvent] = []
        emitter = StreamEmitter(
            str(storage_path),
            on_event=lambda e: captured_events.append(e),
        )

        assert emitter._file_position > 0
        assert len(emitter.current_state) == 3

        # Simulate compaction by rewriting file with fewer lines
        # (keeping only dc-issue-1, removing dc-issue-2 and dc-issue-3)
        storage._issues = {
            "dc-issue-1": storage._issues["dc-issue-1"],
        }
        storage._dependencies = []
        storage._links = []
        storage._save(_reload=False)

        # Now file is smaller than file_position — should trigger full reload
        emitter._handle_file_change()  # noqa: SLF001

        # After full reload, state should have only dc-issue-1
        assert len(emitter.current_state) == 1
        assert "dc-issue-1" in emitter.current_state

        # Should have emitted delete events for dc-issue-2 and dc-issue-3
        delete_events = [e for e in captured_events if e.event_type == "deleted"]
        assert len(delete_events) == 2

    def test_no_change_when_file_unchanged(self, temp_dogcats_dir: Path) -> None:
        """Test that no events are emitted when file size hasn't changed."""
        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path))
        storage.create(Issue(id="issue-1", title="First"))

        captured_events: list[StreamEvent] = []
        emitter = StreamEmitter(
            str(storage_path),
            on_event=lambda e: captured_events.append(e),
        )

        # Call handle_file_change without any actual file changes
        emitter._handle_file_change()  # noqa: SLF001

        assert len(captured_events) == 0

    def test_incremental_parse_detects_update(self, temp_dogcats_dir: Path) -> None:
        """Test that incremental parse detects issue updates."""
        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path))
        storage.create(Issue(id="issue-1", title="Original"))

        captured_events: list[StreamEvent] = []
        emitter = StreamEmitter(
            str(storage_path),
            on_event=lambda e: captured_events.append(e),
        )

        # Update the issue (appends new line)
        storage.update("issue-1", {"title": "Updated"})

        emitter._handle_file_change()  # noqa: SLF001

        assert len(captured_events) == 1
        assert captured_events[0].event_type == "updated"
        assert "title" in captured_events[0].changes
        assert captured_events[0].changes["title"]["old"] == "Original"
        assert captured_events[0].changes["title"]["new"] == "Updated"

    def test_handle_file_change_survives_missing_file(
        self,
        temp_dogcats_dir: Path,
    ) -> None:
        """Test that handle_file_change doesn't crash if file disappears."""
        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path))
        storage.create(Issue(id="issue-1", title="First"))

        emitter = StreamEmitter(str(storage_path))

        # Delete the file
        storage_path.unlink()

        # Should not raise
        emitter._handle_file_change()  # noqa: SLF001

    def test_callback_called_for_each_event(self, temp_dogcats_dir: Path) -> None:
        """Test that on_event callback is called for each detected event."""
        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path))

        captured_events: list[StreamEvent] = []
        emitter = StreamEmitter(
            str(storage_path),
            on_event=lambda e: captured_events.append(e),
        )

        # Create two issues
        storage.create(Issue(id="issue-1", title="First"))
        storage.create(Issue(id="issue-2", title="Second"))

        emitter._handle_file_change()  # noqa: SLF001

        assert len(captured_events) == 2
        event_types = {e.event_type for e in captured_events}
        assert event_types == {"created"}


class TestInboxStreamEmitter:
    """Test InboxStreamEmitter change detection for proposals."""

    def test_emitter_initialization(self, temp_dogcats_dir: Path) -> None:
        """Test initializing inbox emitter."""
        inbox_path = temp_dogcats_dir / "inbox.jsonl"
        emitter = InboxStreamEmitter(str(inbox_path))
        assert emitter.inbox_path == inbox_path

    def test_detect_proposal_create(self, temp_dogcats_dir: Path) -> None:
        """Test detecting proposal creation."""
        inbox = InboxStorage(dogcats_dir=str(temp_dogcats_dir))

        inbox_path = temp_dogcats_dir / "inbox.jsonl"
        captured: list[StreamEvent] = []
        emitter = InboxStreamEmitter(
            str(inbox_path),
            on_event=lambda e: captured.append(e),
        )

        # Create a proposal
        proposal = Proposal(id="test1", title="Test proposal")
        inbox.create(proposal)

        emitter._handle_file_change()  # noqa: SLF001

        assert len(captured) == 1
        assert captured[0].event_type == "proposal_created"
        assert "dc-inbox-test1" in captured[0].issue_id

    def test_detect_proposal_close(self, temp_dogcats_dir: Path) -> None:
        """Test detecting proposal close."""
        inbox = InboxStorage(dogcats_dir=str(temp_dogcats_dir))

        proposal = Proposal(id="test1", title="Close me")
        inbox.create(proposal)

        inbox_path = temp_dogcats_dir / "inbox.jsonl"
        captured: list[StreamEvent] = []
        emitter = InboxStreamEmitter(
            str(inbox_path),
            on_event=lambda e: captured.append(e),
        )

        # Close the proposal
        inbox.close("dc-inbox-test1", reason="Done")

        emitter._handle_file_change()  # noqa: SLF001

        assert len(captured) == 1
        assert captured[0].event_type == "proposal_closed"
        assert "status" in captured[0].changes

    def test_detect_proposal_delete(self, temp_dogcats_dir: Path) -> None:
        """Test detecting proposal deletion (tombstone)."""
        inbox = InboxStorage(dogcats_dir=str(temp_dogcats_dir))

        proposal = Proposal(id="test1", title="Delete me")
        inbox.create(proposal)

        inbox_path = temp_dogcats_dir / "inbox.jsonl"
        captured: list[StreamEvent] = []
        emitter = InboxStreamEmitter(
            str(inbox_path),
            on_event=lambda e: captured.append(e),
        )

        inbox.delete("dc-inbox-test1")

        emitter._handle_file_change()  # noqa: SLF001

        assert len(captured) == 1
        assert captured[0].event_type == "proposal_deleted"

    def test_no_events_when_unchanged(self, temp_dogcats_dir: Path) -> None:
        """Test no events emitted when inbox hasn't changed."""
        inbox = InboxStorage(dogcats_dir=str(temp_dogcats_dir))
        proposal = Proposal(id="test1", title="Static")
        inbox.create(proposal)

        inbox_path = temp_dogcats_dir / "inbox.jsonl"
        captured: list[StreamEvent] = []
        emitter = InboxStreamEmitter(
            str(inbox_path),
            on_event=lambda e: captured.append(e),
        )

        emitter._handle_file_change()  # noqa: SLF001

        assert len(captured) == 0

    def test_incremental_parse_on_append(self, temp_dogcats_dir: Path) -> None:
        """Test that appending to inbox triggers incremental parse."""
        inbox = InboxStorage(dogcats_dir=str(temp_dogcats_dir))
        proposal = Proposal(id="test1", title="First")
        inbox.create(proposal)

        inbox_path = temp_dogcats_dir / "inbox.jsonl"
        captured: list[StreamEvent] = []
        emitter = InboxStreamEmitter(
            str(inbox_path),
            on_event=lambda e: captured.append(e),
        )
        initial_pos = emitter._file_position

        # Add second proposal
        proposal2 = Proposal(id="test2", title="Second")
        inbox.create(proposal2)

        emitter._handle_file_change()  # noqa: SLF001

        assert emitter._file_position > initial_pos
        assert len(captured) == 1
        assert captured[0].event_type == "proposal_created"
