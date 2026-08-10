"""Tests for event streaming and change detection."""

import json
from datetime import timezone
from pathlib import Path
from typing import Any

import orjson
import pytest

from dogcat.inbox import InboxStorage
from dogcat.models import Issue, Proposal, Status, issue_to_dict
from dogcat.storage import JSONLStorage
from dogcat.stream import (
    FieldChange,
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
            changes={"title": FieldChange(old=None, new="Test")},
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
            changes={"status": FieldChange(old="open", new="in_progress")},
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
        assert events[0].changes["title"].old == "Original"
        assert events[0].changes["title"].new == "Updated"

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
        assert events[0].changes["status"].old == "open"
        assert events[0].changes["status"].new == "closed"

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

    def test_watcher_events_starts_empty(self, temp_dogcats_dir: Path) -> None:
        """Test watcher starts with no retained events."""
        storage_path = temp_dogcats_dir / "issues.jsonl"
        watcher = StreamWatcher(storage_path=str(storage_path))

        assert len(watcher.events) == 0

    def test_watcher_events_are_bounded(
        self,
        temp_dogcats_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Retention is capped so a days-long stream cannot grow forever.

        dogcat-44ry: the list had no reader and no trim, so every event
        payload stayed on the heap for the process lifetime.
        """
        from datetime import datetime

        from dogcat.stream import _RECENT_EVENTS_MAXLEN

        storage_path = temp_dogcats_dir / "issues.jsonl"
        watcher = StreamWatcher(storage_path=str(storage_path))

        overflow = _RECENT_EVENTS_MAXLEN + 50
        for n in range(overflow):
            watcher._handle_event(  # noqa: SLF001
                StreamEvent(
                    event_type="updated",
                    issue_id=f"issue-{n}",
                    timestamp=datetime.now(timezone.utc),
                ),
            )

        assert len(watcher.events) == _RECENT_EVENTS_MAXLEN
        assert watcher.events[-1].issue_id == f"issue-{overflow - 1}"
        assert watcher.events[0].issue_id == (
            f"issue-{overflow - _RECENT_EVENTS_MAXLEN}"
        )

        # Every event still reaches stdout; only retention is capped.
        printed = capsys.readouterr().out.strip().splitlines()
        assert len(printed) == overflow
        assert json.loads(printed[0])["issue_id"] == "issue-0"


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
            on_event=captured_events.append,
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
            on_event=captured_events.append,
        )

        assert emitter._file_position > 0
        assert len(emitter.current_state) == 3

        # Simulate compaction by rewriting the file in place with a
        # subset of records. Drives the shrink from real file input
        # rather than mutating storage._issues / _dependencies / _links
        # directly. (dogcat-308p)
        kept_lines = [
            line
            for line in storage_path.read_text().splitlines()
            if line.strip()
            and ('"id":"issue-1"' in line or '"issue_id":"dc-issue-1"' in line)
        ]
        storage_path.write_text("\n".join(kept_lines) + "\n")

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
            on_event=captured_events.append,
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
            on_event=captured_events.append,
        )

        # Update the issue (appends new line)
        storage.update("issue-1", {"title": "Updated"})

        emitter._handle_file_change()  # noqa: SLF001

        assert len(captured_events) == 1
        assert captured_events[0].event_type == "updated"
        assert "title" in captured_events[0].changes
        assert captured_events[0].changes["title"].old == "Original"
        assert captured_events[0].changes["title"].new == "Updated"

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
            on_event=captured_events.append,
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
            on_event=captured.append,
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
            on_event=captured.append,
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
            on_event=captured.append,
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
            on_event=captured.append,
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
            on_event=captured.append,
        )
        initial_pos = emitter._file_position

        # Add second proposal
        proposal2 = Proposal(id="test2", title="Second")
        inbox.create(proposal2)

        emitter._handle_file_change()  # noqa: SLF001

        assert emitter._file_position > initial_pos
        assert len(captured) == 1
        assert captured[0].event_type == "proposal_created"


class TestIncrementalDiffScope:
    """dogcat-3h90: the incremental path diffs only the touched records.

    The appended bytes already name which issues changed, so comparing
    every field of every issue in the store made per-event cost grow with
    store size. These tests pin the narrowing and the payloads it emits.
    """

    def _record_diff_sizes(
        self,
        emitter: StreamEmitter,
        sizes: list[tuple[int, int]],
    ) -> None:
        """Wrap _compute_diff so each call records its (old, new) sizes."""
        original = emitter._compute_diff  # noqa: SLF001

        def spy(
            old_state: dict[str, Any],
            new_state: dict[str, Any],
        ) -> list[StreamEvent]:
            sizes.append((len(old_state), len(new_state)))
            return original(old_state, new_state)

        emitter._compute_diff = spy  # type: ignore[method-assign]  # noqa: SLF001

    def test_diff_scope_is_changed_records_not_store_size(
        self,
        temp_dogcats_dir: Path,
    ) -> None:
        """One updated issue means a one-record diff, whatever the store holds."""
        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path))
        for n in range(6):
            storage.create(Issue(id=f"issue-{n}", title=f"Issue {n}"))

        captured: list[StreamEvent] = []
        emitter = StreamEmitter(str(storage_path), on_event=captured.append)
        assert len(emitter.current_state) == 6

        sizes: list[tuple[int, int]] = []
        self._record_diff_sizes(emitter, sizes)

        storage.update("issue-3", {"title": "Changed"})
        emitter._handle_file_change()  # noqa: SLF001

        assert sizes == [(1, 1)]
        assert len(captured) == 1
        assert captured[0].issue_id == "dc-issue-3"
        assert captured[0].changes["title"].new == "Changed"

        # Untouched issues stay in state and keep their values.
        assert len(emitter.current_state) == 6
        assert emitter.current_state["dc-issue-0"]["title"] == "Issue 0"

    def test_narrowed_diff_matches_full_diff_payload(
        self,
        temp_dogcats_dir: Path,
    ) -> None:
        """The narrowed path emits the same payload a full-state diff would."""
        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path))
        storage.create(Issue(id="issue-1", title="One"))
        storage.create(Issue(id="issue-2", title="Two"))

        captured: list[StreamEvent] = []
        emitter = StreamEmitter(str(storage_path), on_event=captured.append)
        before = {k: dict(v) for k, v in emitter.current_state.items()}

        storage.update("issue-2", {"title": "Two prime", "priority": 0})
        emitter._handle_file_change()  # noqa: SLF001

        after: dict[str, Any] = {}
        for issue in JSONLStorage(str(storage_path)).list():
            after[issue.full_id] = issue_to_dict(issue)

        reference = StreamEmitter(str(storage_path))._compute_diff(before, after)  # noqa: SLF001

        assert len(captured) == len(reference) == 1
        # Timestamps are wall-clock per diff call, so compare everything else.
        narrow_payload = captured[0].to_dict()
        full_payload = reference[0].to_dict()
        narrow_payload.pop("timestamp")
        full_payload.pop("timestamp")
        assert narrow_payload == full_payload

    def test_batch_of_two_records_emits_both_events(
        self,
        temp_dogcats_dir: Path,
    ) -> None:
        """A create and an update in one batch both surface."""
        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path))
        storage.create(Issue(id="issue-1", title="One"))
        storage.create(Issue(id="issue-2", title="Two"))

        captured: list[StreamEvent] = []
        emitter = StreamEmitter(str(storage_path), on_event=captured.append)

        storage.update("issue-1", {"title": "One prime"})
        storage.create(Issue(id="issue-3", title="Three"))
        emitter._handle_file_change()  # noqa: SLF001

        assert [(e.issue_id, e.event_type) for e in captured] == [
            ("dc-issue-1", "updated"),
            ("dc-issue-3", "created"),
        ]

    def test_inbox_diff_scope_is_changed_proposals(
        self,
        temp_dogcats_dir: Path,
    ) -> None:
        """The inbox emitter narrows the same way as the issue emitter."""
        inbox = InboxStorage(dogcats_dir=str(temp_dogcats_dir))
        for n in range(4):
            inbox.create(Proposal(id=f"test{n}", title=f"Proposal {n}"))

        inbox_path = temp_dogcats_dir / "inbox.jsonl"
        captured: list[StreamEvent] = []
        emitter = InboxStreamEmitter(str(inbox_path), on_event=captured.append)
        assert len(emitter.current_state) == 4

        sizes: list[tuple[int, int]] = []
        original = emitter._compute_diff  # noqa: SLF001

        def spy(
            old_state: dict[str, Any],
            new_state: dict[str, Any],
        ) -> list[StreamEvent]:
            sizes.append((len(old_state), len(new_state)))
            return original(old_state, new_state)

        emitter._compute_diff = spy  # type: ignore[method-assign]  # noqa: SLF001

        inbox.close("dc-inbox-test2", reason="Done")
        emitter._handle_file_change()  # noqa: SLF001

        assert sizes == [(1, 1)]
        assert len(captured) == 1
        assert captured[0].event_type == "proposal_closed"
        assert captured[0].issue_id == "dc-inbox-test2"
        assert len(emitter.current_state) == 4


class TestEmissionOrder:
    """dogcat-3h90: emission order survives the narrowed diff.

    The pre-change diff ran over the whole merged state, so events came out
    in the state's first-insertion order with this batch's new records last.
    Anything consuming `dcat stream` as a feed sees that order, so narrowing
    the diff must not reorder it. Each test below builds a batch whose file
    order differs from the state order, which is the only case that can tell
    the two apart.
    """

    def test_new_record_appended_first_still_emits_last(
        self,
        temp_dogcats_dir: Path,
    ) -> None:
        """A create written before an update still lands after it."""
        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path))
        storage.create(Issue(id="issue-1", title="One"))
        storage.create(Issue(id="issue-2", title="Two"))

        captured: list[StreamEvent] = []
        emitter = StreamEmitter(str(storage_path), on_event=captured.append)

        # File order: the new issue first, then the update.
        storage.create(Issue(id="issue-9", title="Nine"))
        storage.update("issue-2", {"title": "Two prime"})
        emitter._handle_file_change()  # noqa: SLF001

        assert [(e.issue_id, e.event_type) for e in captured] == [
            ("dc-issue-2", "updated"),
            ("dc-issue-9", "created"),
        ]

    def test_two_updates_follow_state_order_not_file_order(
        self,
        temp_dogcats_dir: Path,
    ) -> None:
        """Known issues emit in first-insertion order, not append order."""
        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path))
        storage.create(Issue(id="issue-1", title="One"))
        storage.create(Issue(id="issue-2", title="Two"))
        storage.create(Issue(id="issue-3", title="Three"))

        captured: list[StreamEvent] = []
        emitter = StreamEmitter(str(storage_path), on_event=captured.append)

        # File order is the reverse of the state order.
        storage.update("issue-3", {"title": "Three prime"})
        storage.update("issue-1", {"title": "One prime"})
        emitter._handle_file_change()  # noqa: SLF001

        assert [e.issue_id for e in captured] == ["dc-issue-1", "dc-issue-3"]

    def test_two_creates_keep_file_order(self, temp_dogcats_dir: Path) -> None:
        """Records new in the batch emit in the order they were appended."""
        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path))
        storage.create(Issue(id="issue-1", title="One"))

        captured: list[StreamEvent] = []
        emitter = StreamEmitter(str(storage_path), on_event=captured.append)

        storage.create(Issue(id="issue-b", title="B"))
        storage.create(Issue(id="issue-a", title="A"))
        emitter._handle_file_change()  # noqa: SLF001

        assert [e.issue_id for e in captured] == ["dc-issue-b", "dc-issue-a"]

    def test_order_of_a_created_record_persists_into_the_next_batch(
        self,
        temp_dogcats_dir: Path,
    ) -> None:
        """An issue created in one batch ranks after the older ones later."""
        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path))
        storage.create(Issue(id="issue-1", title="One"))
        storage.create(Issue(id="issue-2", title="Two"))

        captured: list[StreamEvent] = []
        emitter = StreamEmitter(str(storage_path), on_event=captured.append)

        storage.create(Issue(id="issue-9", title="Nine"))
        emitter._handle_file_change()  # noqa: SLF001
        captured.clear()

        # Second batch updates all three, youngest first in the file.
        storage.update("issue-9", {"title": "Nine prime"})
        storage.update("issue-2", {"title": "Two prime"})
        storage.update("issue-1", {"title": "One prime"})
        emitter._handle_file_change()  # noqa: SLF001

        assert [e.issue_id for e in captured] == [
            "dc-issue-1",
            "dc-issue-2",
            "dc-issue-9",
        ]

    def test_order_is_reanchored_after_compaction(
        self,
        temp_dogcats_dir: Path,
    ) -> None:
        """A full reload resets the ranking to the rewritten file's order."""
        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path))
        storage.create(Issue(id="issue-1", title="One"))
        storage.create(Issue(id="issue-2", title="Two"))

        captured: list[StreamEvent] = []
        emitter = StreamEmitter(str(storage_path), on_event=captured.append)

        # Compact to issue-2 then issue-1 — the reverse of the load order.
        kept: list[bytes] = []
        for raw in storage_path.read_bytes().splitlines():
            if not raw.strip():
                continue
            data = orjson.loads(raw)
            if data.get("record_type") == "issue":
                kept.append(orjson.dumps(data))
        storage_path.write_bytes(b"\n".join(reversed(kept)) + b"\n")

        emitter._handle_file_change()  # noqa: SLF001
        assert list(emitter.current_state) == ["dc-issue-2", "dc-issue-1"]
        captured.clear()

        storage = JSONLStorage(str(storage_path))
        storage.update("issue-1", {"title": "One prime"})
        storage.update("issue-2", {"title": "Two prime"})
        emitter._handle_file_change()  # noqa: SLF001

        assert [e.issue_id for e in captured] == ["dc-issue-2", "dc-issue-1"]

    def test_inbox_emission_order_matches_state_order(
        self,
        temp_dogcats_dir: Path,
    ) -> None:
        """The inbox emitter orders proposals the same way."""
        inbox = InboxStorage(dogcats_dir=str(temp_dogcats_dir))
        inbox.create(Proposal(id="test1", title="One"))
        inbox.create(Proposal(id="test2", title="Two"))

        inbox_path = temp_dogcats_dir / "inbox.jsonl"
        captured: list[StreamEvent] = []
        emitter = InboxStreamEmitter(str(inbox_path), on_event=captured.append)

        inbox.create(Proposal(id="test9", title="Nine"))
        inbox.close("dc-inbox-test1", reason="Done")
        emitter._handle_file_change()  # noqa: SLF001

        assert [(e.issue_id, e.event_type) for e in captured] == [
            ("dc-inbox-test1", "proposal_closed"),
            ("dc-inbox-test9", "proposal_created"),
        ]


class TestFullReloadAfterCompaction:
    """dogcat-3h90 guard: compaction still gets a whole-store diff.

    Narrowing the incremental path to the touched IDs is only safe because
    a rewritten file goes through _full_reload instead. If that path ever
    narrowed too, a compaction that drops or rewrites records the appended
    bytes never mention would emit nothing.
    """

    def _compact(self, storage_path: Path, keep: dict[str, str]) -> None:
        """Rewrite the file with only `keep` issues, applying new titles.

        Mirrors what JSONLStorage compaction produces: current issue state
        only, no event records, so the file also shrinks.
        """
        lines: list[bytes] = []
        for raw in storage_path.read_bytes().splitlines():
            if not raw.strip():
                continue
            data = orjson.loads(raw)
            if data.get("record_type") != "issue":
                continue
            if data["id"] not in keep:
                continue
            data["title"] = keep[data["id"]]
            lines.append(orjson.dumps(data))
        storage_path.write_bytes(b"\n".join(lines) + b"\n")

    def test_compaction_emits_events_for_untouched_records(
        self,
        temp_dogcats_dir: Path,
    ) -> None:
        """A compaction rewrite reports both the changed and the dropped issue."""
        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path))
        storage.create(Issue(id="issue-1", title="One"))
        storage.create(Issue(id="issue-2", title="Two"))
        storage.create(Issue(id="issue-3", title="Three"))

        captured: list[StreamEvent] = []
        emitter = StreamEmitter(str(storage_path), on_event=captured.append)
        position_before = emitter._file_position  # noqa: SLF001
        assert len(emitter.current_state) == 3

        self._compact(
            storage_path,
            {"issue-1": "One", "issue-2": "Two rewritten"},
        )
        assert storage_path.stat().st_size < position_before

        emitter._handle_file_change()  # noqa: SLF001

        by_id = {e.issue_id: e for e in captured}
        assert set(by_id) == {"dc-issue-2", "dc-issue-3"}
        assert by_id["dc-issue-2"].event_type == "updated"
        assert by_id["dc-issue-2"].changes["title"].old == "Two"
        assert by_id["dc-issue-2"].changes["title"].new == "Two rewritten"
        assert by_id["dc-issue-3"].event_type == "deleted"
        assert by_id["dc-issue-3"].changes["status"].new == "deleted"

        assert set(emitter.current_state) == {"dc-issue-1", "dc-issue-2"}

    def test_incremental_resumes_after_compaction(
        self,
        temp_dogcats_dir: Path,
    ) -> None:
        """The file position is re-anchored, so the next append still parses."""
        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path))
        storage.create(Issue(id="issue-1", title="One"))
        storage.create(Issue(id="issue-2", title="Two"))

        captured: list[StreamEvent] = []
        emitter = StreamEmitter(str(storage_path), on_event=captured.append)

        self._compact(storage_path, {"issue-1": "One"})
        emitter._handle_file_change()  # noqa: SLF001
        captured.clear()

        # Append past the compacted file with a fresh storage view.
        JSONLStorage(str(storage_path)).create(Issue(id="issue-9", title="Nine"))
        emitter._handle_file_change()  # noqa: SLF001

        assert [(e.issue_id, e.event_type) for e in captured] == [
            ("dc-issue-9", "created"),
        ]


class TestStreamEmitterPathFiltering:
    """Regression tests for dogcat-55zt: watchdog dispatch paths.

    StreamEmitter.on_modified, on_moved, and the InboxStreamEmitter
    counterparts were never directly exercised — tests called
    _handle_file_change instead, so the path-suffix check (e.g. a typo
    like endswith('issue.jsonl') instead of 'issues.jsonl') would not
    have been caught.
    """

    def test_on_modified_triggers_handler_for_issues_jsonl(
        self, temp_dogcats_dir: Path
    ) -> None:
        """on_modified handles a FileModifiedEvent ending in issues.jsonl."""
        from watchdog.events import FileModifiedEvent

        from dogcat.stream import StreamEmitter

        storage_path = temp_dogcats_dir / "issues.jsonl"
        emitter = StreamEmitter(str(storage_path))

        called: list[bool] = []

        def fake_handle() -> None:
            called.append(True)

        emitter._handle_file_change = fake_handle  # type: ignore[method-assign]
        emitter.on_modified(FileModifiedEvent(str(storage_path)))
        assert called == [True]

    def test_on_modified_ignores_unrelated_files(self, temp_dogcats_dir: Path) -> None:
        """on_modified ignores files that aren't issues.jsonl."""
        from watchdog.events import FileModifiedEvent

        from dogcat.stream import StreamEmitter

        storage_path = temp_dogcats_dir / "issues.jsonl"
        emitter = StreamEmitter(str(storage_path))

        called: list[bool] = []
        emitter._handle_file_change = lambda: called.append(True)  # type: ignore[method-assign]
        emitter.on_modified(FileModifiedEvent(str(temp_dogcats_dir / "other.txt")))
        assert called == []

    def test_on_moved_triggers_handler_for_atomic_replace(
        self, temp_dogcats_dir: Path
    ) -> None:
        """on_moved handles a FileMovedEvent landing on issues.jsonl.

        Atomic-rewrite renames a tempfile onto issues.jsonl, so the move
        event is the load-bearing notification on macOS/Linux.
        """
        from watchdog.events import FileMovedEvent

        from dogcat.stream import StreamEmitter

        storage_path = temp_dogcats_dir / "issues.jsonl"
        emitter = StreamEmitter(str(storage_path))
        called: list[bool] = []
        emitter._handle_file_change = lambda: called.append(True)  # type: ignore[method-assign]

        evt = FileMovedEvent(
            str(temp_dogcats_dir / "tmp.jsonl"),
            str(storage_path),
        )
        emitter.on_moved(evt)
        assert called == [True]

    def test_inbox_on_modified_triggers_for_inbox_jsonl(
        self, temp_dogcats_dir: Path
    ) -> None:
        """InboxStreamEmitter.on_modified responds to inbox.jsonl events."""
        from watchdog.events import FileModifiedEvent

        inbox_path = temp_dogcats_dir / "inbox.jsonl"
        emitter = InboxStreamEmitter(str(inbox_path))
        called: list[bool] = []
        emitter._handle_file_change = lambda: called.append(True)  # type: ignore[method-assign]
        emitter.on_modified(FileModifiedEvent(str(inbox_path)))
        assert called == [True]

    def test_inbox_on_modified_ignores_issues_jsonl(
        self, temp_dogcats_dir: Path
    ) -> None:
        """InboxStreamEmitter must NOT fire for issues.jsonl events.

        The two emitters are scheduled on the same directory; without the
        path filter they'd dispatch on each other's writes and double-fire.
        """
        from watchdog.events import FileModifiedEvent

        inbox_path = temp_dogcats_dir / "inbox.jsonl"
        emitter = InboxStreamEmitter(str(inbox_path))
        called: list[bool] = []
        emitter._handle_file_change = lambda: called.append(True)  # type: ignore[method-assign]
        emitter.on_modified(FileModifiedEvent(str(temp_dogcats_dir / "issues.jsonl")))
        assert called == []


class TestStreamWatcherObserverIntegration:
    """Real Observer start/stop integration test for StreamWatcher.

    Uses a real watchdog Observer against a temp file to make sure the
    schedule call wires the right handler types and doesn't choke on
    realistic FS events.
    """

    def test_start_then_stop_runs_cleanly(self, temp_dogcats_dir: Path) -> None:
        """StreamWatcher.start() then .stop() round-trips with no error."""
        import time

        from dogcat.stream import StreamWatcher

        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage_path.touch()
        watcher = StreamWatcher(storage_path=str(storage_path))
        watcher.start()
        try:
            deadline = time.monotonic() + 5.0
            while not watcher.observer.is_alive() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert watcher.observer.is_alive()
        finally:
            watcher.stop()
        deadline = time.monotonic() + 5.0
        while watcher.observer.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert not watcher.observer.is_alive()
