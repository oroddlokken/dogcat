"""Tests for dogcat._queries — pure read queries over in-memory state.

These extract the logic-bearing query reads from ``JSONLStorage`` (dogcat-5qii)
so the filter ladder, child lookup, and dangling scan run against plain
dicts/lists without a constructed store.
"""

from __future__ import annotations

from datetime import datetime, timezone

from dogcat._queries import children_of, dangling_dependencies, filter_issues
from dogcat.models import (
    Dependency,
    DependencyType,
    FilterSpec,
    Issue,
    IssueType,
    Status,
)

_TS = datetime(2026, 7, 14, tzinfo=timezone.utc)


def _issue(issue_id: str, **kw: object) -> Issue:
    return Issue(id=issue_id, title=issue_id, created_at=_TS, updated_at=_TS, **kw)  # type: ignore[arg-type]


class TestFilterIssues:
    """The list() filter ladder."""

    def test_no_filters_returns_all(self) -> None:
        """An all-unset FilterSpec keeps every issue."""
        issues = [_issue("a"), _issue("b")]
        assert filter_issues(issues, FilterSpec()) == issues

    def test_status_priority_and_type_filters_combine(self) -> None:
        """Set fields are ANDed together."""
        a = _issue("a", status=Status.OPEN, priority=1, issue_type=IssueType.BUG)
        b = _issue("b", status=Status.CLOSED, priority=1, issue_type=IssueType.BUG)
        c = _issue("c", status=Status.OPEN, priority=3, issue_type=IssueType.BUG)
        out = filter_issues(
            [a, b, c], FilterSpec(status=Status.OPEN, priority=1, issue_type="bug")
        )
        assert out == [a]

    def test_label_single_is_membership(self) -> None:
        """A single label filters by membership."""
        a = _issue("a", labels=["cli", "ux"])
        b = _issue("b", labels=["api"])
        assert filter_issues([a, b], FilterSpec(label="cli")) == [a]

    def test_label_list_is_any_overlap(self) -> None:
        """A list label matches any overlap."""
        a = _issue("a", labels=["cli"])
        b = _issue("b", labels=["api"])
        c = _issue("c", labels=["ux"])
        out = filter_issues([a, b, c], FilterSpec(label=["cli", "api"]))
        assert out == [a, b]

    def test_status_accepts_string(self) -> None:
        """A string status is coerced to the Status enum."""
        a = _issue("a", status=Status.OPEN)
        b = _issue("b", status=Status.CLOSED)
        assert filter_issues([a, b], FilterSpec(status="open")) == [a]


class TestChildrenOf:
    """Child lookup skips ids no longer present."""

    def test_returns_existing_children_only(self) -> None:
        """A stale child id in the index is skipped."""
        a, c1 = _issue("a"), _issue("c1")
        issues = {a.full_id: a, c1.full_id: c1}
        index = {a.full_id: [c1.full_id, "dc-gone"]}
        assert children_of(index, issues, a.full_id) == [c1]

    def test_no_children_returns_empty(self) -> None:
        """A parent with no index entry yields an empty list."""
        a = _issue("a")
        assert children_of({}, {a.full_id: a}, a.full_id) == []


class TestDanglingDependencies:
    """Dangling scan flags edges whose endpoints are gone."""

    def test_flags_missing_endpoints(self) -> None:
        """A dependency to a removed issue is dangling; a valid one is not."""
        a, b = _issue("a"), _issue("b")
        issues = {a.full_id: a, b.full_id: b}
        good = Dependency(
            issue_id=a.full_id,
            depends_on_id=b.full_id,
            dep_type=DependencyType.BLOCKS,
            created_at=_TS,
        )
        bad = Dependency(
            issue_id=a.full_id,
            depends_on_id="dc-gone",
            dep_type=DependencyType.BLOCKS,
            created_at=_TS,
        )
        assert dangling_dependencies([good, bad], issues) == [bad]
