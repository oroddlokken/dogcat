"""Tests for event emission from storage CRUD operations."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

import pytest

from dogcat.event_log import EventLog
from dogcat.models import Issue, IssueType, Status
from dogcat.storage import JSONLStorage

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def storage(temp_dogcats_dir: Path) -> JSONLStorage:
    """Provide storage fixture."""
    storage_path = temp_dogcats_dir / "issues.jsonl"
    return JSONLStorage(str(storage_path), create_dir=True)


@pytest.fixture
def event_log(storage: JSONLStorage) -> EventLog:
    """Provide event log fixture."""
    return EventLog(storage.dogcats_dir)


def _make_issue(
    issue_id: str = "test1",
    title: str = "Test issue",
    **kwargs: object,
) -> Issue:
    now = datetime.now().astimezone()
    defaults: dict[str, Any] = {
        "id": issue_id,
        "title": title,
        "namespace": "dc",
        "status": Status.OPEN,
        "priority": 2,
        "issue_type": IssueType.TASK,
        "created_at": now,
        "updated_at": now,
        "created_by": "test@example.com",
    }
    defaults.update(kwargs)
    return Issue(**defaults)  # type: ignore[arg-type]


class TestCreateEmitsEvent:
    """Tests for create emits event."""

    def test_create_emits_created_event(
        self,
        storage: JSONLStorage,
        event_log: EventLog,
    ) -> None:
        """Test create emits created event."""
        issue = _make_issue()
        storage.create(issue)

        events = event_log.read()
        assert len(events) == 1
        assert events[0].event_type == "created"
        assert events[0].issue_id == "dc-test1"
        assert events[0].by == "test@example.com"

    def test_create_event_has_initial_fields(
        self,
        storage: JSONLStorage,
        event_log: EventLog,
    ) -> None:
        """Test create event has initial fields."""
        issue = _make_issue(title="My task", priority=1, issue_type=IssueType.BUG)
        storage.create(issue)

        events = event_log.read()
        changes = events[0].changes
        assert changes["title"] == {"old": None, "new": "My task"}
        assert changes["priority"] == {"old": None, "new": 1}
        assert changes["issue_type"] == {"old": None, "new": "bug"}
        assert changes["status"] == {"old": None, "new": "open"}

    def test_create_event_stores_full_description(
        self,
        storage: JSONLStorage,
        event_log: EventLog,
    ) -> None:
        """Test create event stores full description for verbose display."""
        issue = _make_issue(description="A long detailed description")
        storage.create(issue)

        events = event_log.read()
        assert events[0].changes["description"] == {
            "old": None,
            "new": "A long detailed description",
        }


class TestUpdateEmitsEvent:
    """Tests for update emits event."""

    def test_update_emits_updated_event(
        self,
        storage: JSONLStorage,
        event_log: EventLog,
    ) -> None:
        """Test update emits updated event."""
        issue = _make_issue()
        storage.create(issue)

        storage.update("dc-test1", {"status": "in_progress"})

        events = event_log.read()
        assert len(events) == 2
        # Newest first
        assert events[0].event_type == "updated"
        assert events[0].changes["status"] == {"old": "open", "new": "in_progress"}

    def test_update_tracks_priority_change(
        self,
        storage: JSONLStorage,
        event_log: EventLog,
    ) -> None:
        """Test update tracks priority change."""
        issue = _make_issue(priority=2)
        storage.create(issue)

        storage.update("dc-test1", {"priority": 0})

        events = event_log.read()
        assert events[0].changes["priority"] == {"old": 2, "new": 0}

    def test_update_no_event_for_non_tracked_fields(
        self,
        storage: JSONLStorage,
        event_log: EventLog,
    ) -> None:
        """Test update no event for non tracked fields."""
        issue = _make_issue()
        storage.create(issue)

        # close_reason is not a tracked field
        storage.update("dc-test1", {"close_reason": "Done"})

        events = event_log.read()
        # Only the create event, no update event
        assert len(events) == 1
        assert events[0].event_type == "created"

    def test_update_stores_full_description_change(
        self,
        storage: JSONLStorage,
        event_log: EventLog,
    ) -> None:
        """Test update stores full description values for verbose display."""
        issue = _make_issue(description="Old text")
        storage.create(issue)

        storage.update("dc-test1", {"description": "New text"})

        events = event_log.read()
        assert events[0].changes["description"] == {
            "old": "Old text",
            "new": "New text",
        }

    def test_update_status_to_closed_emits_closed_event(
        self,
        storage: JSONLStorage,
        event_log: EventLog,
    ) -> None:
        """Test update status to closed emits closed event."""
        issue = _make_issue()
        storage.create(issue)

        storage.update("dc-test1", {"status": "closed"})

        events = event_log.read()
        assert events[0].event_type == "closed"


class TestCloseEmitsEvent:
    """Tests for close emits event."""

    def test_close_emits_closed_event(
        self,
        storage: JSONLStorage,
        event_log: EventLog,
    ) -> None:
        """Test close emits closed event."""
        issue = _make_issue()
        storage.create(issue)

        storage.close("dc-test1", reason="Fixed", closed_by="closer@example.com")

        events = event_log.read()
        assert len(events) == 2
        assert events[0].event_type == "closed"
        assert events[0].by == "closer@example.com"
        assert events[0].changes["status"] == {"old": "open", "new": "closed"}


class TestDeleteEmitsEvent:
    """Tests for delete emits event."""

    def test_delete_emits_deleted_event(
        self,
        storage: JSONLStorage,
        event_log: EventLog,
    ) -> None:
        """Test delete emits deleted event."""
        issue = _make_issue()
        storage.create(issue)

        storage.delete("dc-test1", reason="Duplicate", deleted_by="admin@example.com")

        events = event_log.read()
        assert len(events) == 2
        assert events[0].event_type == "deleted"
        assert events[0].by == "admin@example.com"
        assert events[0].changes["status"] == {"old": "open", "new": "tombstone"}


class TestEventsSurviveCompaction:
    """Tests for events survive compaction."""

    def test_events_persist_after_compaction(
        self,
        storage: JSONLStorage,
        event_log: EventLog,
    ) -> None:
        """Test events persist after compaction."""
        issue = _make_issue()
        storage.create(issue)

        # Force compaction
        storage._save()

        events = event_log.read()
        assert len(events) == 1
        assert events[0].event_type == "created"
