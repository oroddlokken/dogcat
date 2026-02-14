"""Tests for the reopen command and storage method."""

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


def _create_and_close(storage: JSONLStorage, issue_id: str = "test1") -> Issue:
    """Create an issue and close it, returning the closed issue."""
    issue = _make_issue(issue_id=issue_id)
    storage.create(issue)
    return storage.close(
        f"dc-{issue_id}", reason="Done", closed_by="closer@example.com"
    )


class TestStorageReopen:
    """Tests for storage.reopen()."""

    def test_reopen_sets_status_to_open(self, storage: JSONLStorage) -> None:
        """Test reopen sets status to open."""
        _create_and_close(storage)
        issue = storage.reopen("dc-test1")
        assert issue.status == Status.OPEN

    def test_reopen_clears_closed_fields(self, storage: JSONLStorage) -> None:
        """Test reopen clears closed_at, closed_by, and close_reason."""
        _create_and_close(storage)
        issue = storage.reopen("dc-test1")
        assert issue.closed_at is None
        assert issue.closed_by is None
        assert issue.close_reason is None

    def test_reopen_updates_timestamp(self, storage: JSONLStorage) -> None:
        """Test reopen updates the updated_at timestamp."""
        closed = _create_and_close(storage)
        issue = storage.reopen("dc-test1")
        assert issue.updated_at >= closed.updated_at

    def test_reopen_sets_updated_by(self, storage: JSONLStorage) -> None:
        """Test reopen sets updated_by to the reopener."""
        _create_and_close(storage)
        issue = storage.reopen("dc-test1", reopened_by="reopener@example.com")
        assert issue.updated_by == "reopener@example.com"

    def test_reopen_raises_if_not_found(self, storage: JSONLStorage) -> None:
        """Test reopen raises ValueError if issue not found."""
        with pytest.raises(ValueError, match="not found"):
            storage.reopen("dc-nonexistent")

    def test_reopen_raises_if_not_closed(self, storage: JSONLStorage) -> None:
        """Test reopen raises ValueError if issue is not closed."""
        issue = _make_issue()
        storage.create(issue)
        with pytest.raises(ValueError, match="not closed"):
            storage.reopen("dc-test1")

    def test_reopen_raises_if_in_progress(self, storage: JSONLStorage) -> None:
        """Test reopen raises ValueError if issue is in_progress."""
        issue = _make_issue(status=Status.IN_PROGRESS)
        storage.create(issue)
        with pytest.raises(ValueError, match="not closed"):
            storage.reopen("dc-test1")

    def test_reopen_persists_after_reload(self, temp_dogcats_dir: Path) -> None:
        """Test reopened status persists after reloading from disk."""
        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)
        _create_and_close(storage)
        storage.reopen("dc-test1")

        # Reload from disk
        storage2 = JSONLStorage(str(storage_path))
        issue = storage2.get("dc-test1")
        assert issue is not None
        assert issue.status == Status.OPEN
        assert issue.closed_at is None


class TestReopenEmitsEvent:
    """Tests for reopen event emission."""

    def test_reopen_emits_reopened_event(
        self,
        storage: JSONLStorage,
        event_log: EventLog,
    ) -> None:
        """Test reopen emits a reopened event with correct fields."""
        _create_and_close(storage)
        storage.reopen("dc-test1", reopened_by="reopener@example.com")

        events = event_log.read()
        # created, closed, reopened (newest first)
        assert events[0].event_type == "reopened"
        assert events[0].by == "reopener@example.com"
        assert events[0].changes["status"] == {"old": "closed", "new": "open"}

    def test_reopen_event_includes_reason(
        self,
        storage: JSONLStorage,
        event_log: EventLog,
    ) -> None:
        """Test reopen event includes reason when provided."""
        _create_and_close(storage)
        storage.reopen("dc-test1", reason="Bug returned")

        events = event_log.read()
        assert events[0].changes["reopen_reason"] == {
            "old": None,
            "new": "Bug returned",
        }

    def test_reopen_event_count(
        self,
        storage: JSONLStorage,
        event_log: EventLog,
    ) -> None:
        """Test total event count after create, close, and reopen."""
        _create_and_close(storage)
        storage.reopen("dc-test1")

        events = event_log.read()
        # created + closed + reopened = 3
        assert len(events) == 3
