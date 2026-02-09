"""Tests for shell completion callbacks."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import pytest

from dogcat.cli._completions import (
    complete_issue_ids,
    complete_labels,
    complete_priorities,
    complete_statuses,
    complete_types,
)
from dogcat.models import Issue, IssueType, Status
from dogcat.storage import JSONLStorage

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def storage_with_issues(temp_dogcats_dir: Path) -> JSONLStorage:
    """Create a storage instance with sample issues."""
    storage = JSONLStorage(str(temp_dogcats_dir / "issues.jsonl"), create_dir=True)
    now = datetime.now().astimezone()

    storage.create(
        Issue(
            id="abc1",
            namespace="dc",
            title="First issue",
            status=Status.OPEN,
            priority=1,
            issue_type=IssueType.BUG,
            labels=["backend", "urgent"],
            created_by="test",
            created_at=now,
        ),
    )
    storage.create(
        Issue(
            id="abc2",
            namespace="dc",
            title="Second issue",
            status=Status.IN_PROGRESS,
            priority=2,
            issue_type=IssueType.FEATURE,
            labels=["frontend", "urgent"],
            created_by="test",
            created_at=now,
        ),
    )
    storage.create(
        Issue(
            id="xyz1",
            namespace="dc",
            title="Third issue",
            status=Status.OPEN,
            priority=3,
            issue_type=IssueType.TASK,
            labels=["backend"],
            created_by="test",
            created_at=now,
        ),
    )
    storage.create(
        Issue(
            id="closed1",
            namespace="dc",
            title="Closed issue",
            status=Status.CLOSED,
            priority=2,
            issue_type=IssueType.BUG,
            labels=["backend"],
            created_by="test",
            created_at=now,
        ),
    )
    return storage


def _values(results: list[tuple[str, str]]) -> list[str]:
    """Extract just the completion values from (value, help) tuples."""
    return [v for v, _ in results]


class TestCompleteStatuses:
    """Test complete_statuses completion callback."""

    def test_returns_all_statuses(self) -> None:
        """Should return all defined status values with descriptions."""
        result = complete_statuses("")
        values = _values(result)
        assert "open" in values
        assert "in_progress" in values
        assert "in_review" in values
        assert "blocked" in values
        assert "deferred" in values
        assert "closed" in values
        # Verify tuples have help text
        assert all(isinstance(item, tuple) and len(item) == 2 for item in result)

    def test_filters_by_prefix(self) -> None:
        """Should filter statuses by incomplete prefix."""
        result = complete_statuses("in_")
        assert _values(result) == ["in_progress", "in_review"]

    def test_no_match(self) -> None:
        """Should return empty list when no status matches."""
        assert complete_statuses("zzz") == []


class TestCompleteTypes:
    """Test complete_types completion callback."""

    def test_returns_all_types(self) -> None:
        """Should return all defined type values with descriptions."""
        result = complete_types("")
        values = _values(result)
        assert "task" in values
        assert "bug" in values
        assert "feature" in values
        assert "story" in values
        assert "epic" in values
        assert "question" in values
        # Verify tuples have help text
        assert all(isinstance(item, tuple) and len(item) == 2 for item in result)

    def test_filters_by_prefix(self) -> None:
        """Should filter types by incomplete prefix."""
        assert _values(complete_types("b")) == ["bug"]

    def test_no_match(self) -> None:
        """Should return empty list when no type matches."""
        assert complete_types("zzz") == []


class TestCompletePriorities:
    """Test complete_priorities completion callback."""

    def test_returns_all_priorities(self) -> None:
        """Should return numeric and named priority values with descriptions."""
        result = complete_priorities("")
        values = _values(result)
        assert "0" in values
        assert "4" in values
        assert "critical" in values
        assert "minimal" in values
        # Verify tuples have help text
        assert all(isinstance(item, tuple) and len(item) == 2 for item in result)

    def test_filters_numeric(self) -> None:
        """Should filter numeric priorities by prefix."""
        values = _values(complete_priorities("1"))
        assert "1" in values
        assert "0" not in values

    def test_filters_names(self) -> None:
        """Should filter named priorities by prefix."""
        assert _values(complete_priorities("c")) == ["critical"]


class TestCompleteIssueIds:
    """Test complete_issue_ids completion callback."""

    def test_returns_open_ids(
        self,
        storage_with_issues: JSONLStorage,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Should return open issue IDs and exclude closed ones."""
        monkeypatch.setattr(
            "dogcat.cli._completions.get_storage",
            lambda: storage_with_issues,
        )
        result = complete_issue_ids("")
        values = _values(result)
        assert "dc-abc1" in values
        assert "dc-abc2" in values
        assert "dc-xyz1" in values
        assert "dc-closed1" not in values
        # Verify help text contains issue titles
        helps = dict(result)
        assert helps["dc-abc1"] == "First issue"

    def test_filters_by_prefix(
        self,
        storage_with_issues: JSONLStorage,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Should filter issue IDs by incomplete prefix."""
        monkeypatch.setattr(
            "dogcat.cli._completions.get_storage",
            lambda: storage_with_issues,
        )
        result = complete_issue_ids("dc-abc")
        values = _values(result)
        assert "dc-abc1" in values
        assert "dc-abc2" in values
        assert "dc-xyz1" not in values

    def test_returns_empty_on_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return empty list when storage is unavailable."""

        def raise_error() -> JSONLStorage:
            msg = "no storage"
            raise FileNotFoundError(msg)

        monkeypatch.setattr("dogcat.cli._completions.get_storage", raise_error)
        assert complete_issue_ids("") == []


class TestCompleteLabels:
    """Test complete_labels completion callback."""

    def test_returns_labels(
        self,
        storage_with_issues: JSONLStorage,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Should return all unique labels from issues with descriptions."""
        monkeypatch.setattr(
            "dogcat.cli._completions.get_storage",
            lambda: storage_with_issues,
        )
        result = complete_labels("")
        values = _values(result)
        assert "backend" in values
        assert "frontend" in values
        assert "urgent" in values
        # Verify tuples have help text
        assert all(isinstance(item, tuple) and len(item) == 2 for item in result)

    def test_filters_by_prefix(
        self,
        storage_with_issues: JSONLStorage,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Should filter labels by incomplete prefix."""
        monkeypatch.setattr(
            "dogcat.cli._completions.get_storage",
            lambda: storage_with_issues,
        )
        assert _values(complete_labels("b")) == ["backend"]

    def test_returns_empty_on_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return empty list when storage is unavailable."""

        def raise_error() -> JSONLStorage:
            msg = "no storage"
            raise FileNotFoundError(msg)

        monkeypatch.setattr("dogcat.cli._completions.get_storage", raise_error)
        assert complete_labels("") == []
