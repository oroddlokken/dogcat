"""Tests for shell completion callbacks."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar

import pytest

from dogcat.cli._completions import (
    complete_closed_issue_ids,
    complete_comment_actions,
    complete_config_keys,
    complete_config_values,
    complete_dates,
    complete_dep_types,
    complete_durations,
    complete_export_formats,
    complete_issue_ids,
    complete_labels,
    complete_link_types,
    complete_namespaces,
    complete_owners,
    complete_priorities,
    complete_statuses,
    complete_subcommands,
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
        result = complete_issue_ids(None, [], "")
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
        result = complete_issue_ids(None, [], "dc-abc")
        values = _values(result)
        assert "dc-abc1" in values
        assert "dc-abc2" in values
        assert "dc-xyz1" not in values

    def test_matches_short_id(
        self,
        storage_with_issues: JSONLStorage,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Should match by short ID and return short ID as completion value."""
        monkeypatch.setattr(
            "dogcat.cli._completions.get_storage",
            lambda: storage_with_issues,
        )
        result = complete_issue_ids(None, [], "abc")
        values = _values(result)
        # Returns short IDs (not full IDs) so zsh prefix filtering works
        assert "abc1" in values
        assert "abc2" in values
        assert "xyz1" not in values

    def test_returns_empty_on_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return empty list when storage is unavailable."""

        def raise_error() -> JSONLStorage:
            msg = "no storage"
            raise FileNotFoundError(msg)

        monkeypatch.setattr("dogcat.cli._completions.get_storage", raise_error)
        assert complete_issue_ids(None, [], "") == []

    def test_all_namespaces_via_ctx_params(
        self,
        temp_dogcats_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Should show all namespaces when ctx.params has all_namespaces=True."""
        storage = JSONLStorage(str(temp_dogcats_dir / "issues.jsonl"), create_dir=True)
        now = datetime.now().astimezone()
        storage.create(
            Issue(
                id="aaa1",
                namespace="dc",
                title="DC issue",
                status=Status.OPEN,
                priority=2,
                issue_type=IssueType.TASK,
                created_by="test",
                created_at=now,
            ),
        )
        storage.create(
            Issue(
                id="bbb1",
                namespace="other",
                title="Other NS issue",
                status=Status.OPEN,
                priority=2,
                issue_type=IssueType.TASK,
                created_by="test",
                created_at=now,
            ),
        )
        monkeypatch.setattr(
            "dogcat.cli._completions.get_storage",
            lambda: storage,
        )

        # Simulate Click context with parsed all_namespaces param
        class FakeCtx:
            params: ClassVar[dict[str, Any]] = {"all_namespaces": True}

        result = complete_issue_ids(FakeCtx(), [], "")
        values = _values(result)
        assert "dc-aaa1" in values
        assert "other-bbb1" in values

    def test_explicit_namespace_via_ctx_params(
        self,
        temp_dogcats_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Should scope to namespace from ctx.params."""
        storage = JSONLStorage(str(temp_dogcats_dir / "issues.jsonl"), create_dir=True)
        now = datetime.now().astimezone()
        storage.create(
            Issue(
                id="aaa1",
                namespace="dc",
                title="DC issue",
                status=Status.OPEN,
                priority=2,
                issue_type=IssueType.TASK,
                created_by="test",
                created_at=now,
            ),
        )
        storage.create(
            Issue(
                id="bbb1",
                namespace="other",
                title="Other NS issue",
                status=Status.OPEN,
                priority=2,
                issue_type=IssueType.TASK,
                created_by="test",
                created_at=now,
            ),
        )
        monkeypatch.setattr(
            "dogcat.cli._completions.get_storage",
            lambda: storage,
        )

        class FakeCtx:
            params: ClassVar[dict[str, Any]] = {"namespace": "other"}

        result = complete_issue_ids(FakeCtx(), [], "")
        values = _values(result)
        assert "other-bbb1" in values
        assert "dc-aaa1" not in values


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
        result = complete_labels(None, [], "")
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
        assert _values(complete_labels(None, [], "b")) == ["backend"]

    def test_returns_empty_on_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return empty list when storage is unavailable."""

        def raise_error() -> JSONLStorage:
            msg = "no storage"
            raise FileNotFoundError(msg)

        monkeypatch.setattr("dogcat.cli._completions.get_storage", raise_error)
        assert complete_labels(None, [], "") == []

    def test_all_namespaces_via_ctx_params(
        self,
        temp_dogcats_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Should include labels from all namespaces when -A is in ctx.params."""
        storage = JSONLStorage(str(temp_dogcats_dir / "issues.jsonl"), create_dir=True)
        now = datetime.now().astimezone()
        storage.create(
            Issue(
                id="aaa1",
                namespace="dc",
                title="DC issue",
                status=Status.OPEN,
                priority=2,
                issue_type=IssueType.TASK,
                labels=["local-label"],
                created_by="test",
                created_at=now,
            ),
        )
        storage.create(
            Issue(
                id="bbb1",
                namespace="other",
                title="Other NS issue",
                status=Status.OPEN,
                priority=2,
                issue_type=IssueType.TASK,
                labels=["remote-label"],
                created_by="test",
                created_at=now,
            ),
        )
        monkeypatch.setattr(
            "dogcat.cli._completions.get_storage",
            lambda: storage,
        )

        class FakeCtx:
            params: ClassVar[dict[str, Any]] = {"all_namespaces": True}

        result = complete_labels(FakeCtx(), [], "")
        values = _values(result)
        assert "local-label" in values
        assert "remote-label" in values


class TestCompleteSubcommands:
    """Test complete_subcommands completion callback."""

    def test_returns_all_subcommands(self) -> None:
        """Should return add, remove, list with descriptions."""
        result = complete_subcommands("")
        values = _values(result)
        assert values == ["add", "remove", "list"]
        assert all(isinstance(item, tuple) and len(item) == 2 for item in result)

    def test_filters_by_prefix(self) -> None:
        """Should filter subcommands by incomplete prefix."""
        assert _values(complete_subcommands("a")) == ["add"]
        assert _values(complete_subcommands("r")) == ["remove"]
        assert _values(complete_subcommands("l")) == ["list"]

    def test_no_match(self) -> None:
        """Should return empty list when no subcommand matches."""
        assert complete_subcommands("zzz") == []


class TestCompleteCommentActions:
    """Test complete_comment_actions completion callback."""

    def test_returns_all_actions(self) -> None:
        """Should return add, list, delete with descriptions."""
        result = complete_comment_actions("")
        values = _values(result)
        assert values == ["add", "list", "delete"]
        assert all(isinstance(item, tuple) and len(item) == 2 for item in result)

    def test_filters_by_prefix(self) -> None:
        """Should filter actions by incomplete prefix."""
        assert _values(complete_comment_actions("a")) == ["add"]
        assert _values(complete_comment_actions("d")) == ["delete"]
        assert _values(complete_comment_actions("l")) == ["list"]

    def test_no_match(self) -> None:
        """Should return empty list when no action matches."""
        assert complete_comment_actions("zzz") == []


class TestCompleteClosedIssueIds:
    """Test complete_closed_issue_ids completion callback."""

    def test_returns_only_closed_ids(
        self,
        storage_with_issues: JSONLStorage,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Should return only closed issue IDs."""
        monkeypatch.setattr(
            "dogcat.cli._completions.get_storage",
            lambda: storage_with_issues,
        )
        result = complete_closed_issue_ids(None, [], "")
        values = _values(result)
        assert "dc-closed1" in values
        assert "dc-abc1" not in values
        assert "dc-abc2" not in values
        assert "dc-xyz1" not in values

    def test_filters_by_prefix(
        self,
        storage_with_issues: JSONLStorage,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Should filter closed IDs by incomplete prefix."""
        monkeypatch.setattr(
            "dogcat.cli._completions.get_storage",
            lambda: storage_with_issues,
        )
        result = complete_closed_issue_ids(None, [], "dc-closed")
        values = _values(result)
        assert "dc-closed1" in values

    def test_matches_short_id(
        self,
        storage_with_issues: JSONLStorage,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Should match by short ID and return short ID as completion value."""
        monkeypatch.setattr(
            "dogcat.cli._completions.get_storage",
            lambda: storage_with_issues,
        )
        result = complete_closed_issue_ids(None, [], "closed")
        values = _values(result)
        assert "closed1" in values

    def test_returns_empty_on_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return empty list when storage is unavailable."""

        def raise_error() -> JSONLStorage:
            msg = "no storage"
            raise FileNotFoundError(msg)

        monkeypatch.setattr("dogcat.cli._completions.get_storage", raise_error)
        assert complete_closed_issue_ids(None, [], "") == []


class TestCompleteNamespaces:
    """Test complete_namespaces completion callback."""

    def test_returns_namespaces(
        self,
        storage_with_issues: JSONLStorage,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Should return all namespaces with issue counts."""
        monkeypatch.setattr(
            "dogcat.cli._completions.get_storage",
            lambda: storage_with_issues,
        )
        result = complete_namespaces(None, [], "")
        values = _values(result)
        assert "dc" in values
        # Verify help text shows issue counts
        helps = dict(result)
        assert "issue(s)" in helps["dc"]

    def test_filters_by_prefix(
        self,
        temp_dogcats_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Should filter namespaces by incomplete prefix."""
        storage = JSONLStorage(str(temp_dogcats_dir / "issues.jsonl"), create_dir=True)
        now = datetime.now().astimezone()
        storage.create(
            Issue(
                id="aaa1",
                namespace="alpha",
                title="Alpha issue",
                status=Status.OPEN,
                priority=2,
                issue_type=IssueType.TASK,
                created_by="test",
                created_at=now,
            ),
        )
        storage.create(
            Issue(
                id="bbb1",
                namespace="beta",
                title="Beta issue",
                status=Status.OPEN,
                priority=2,
                issue_type=IssueType.TASK,
                created_by="test",
                created_at=now,
            ),
        )
        monkeypatch.setattr(
            "dogcat.cli._completions.get_storage",
            lambda: storage,
        )
        result = complete_namespaces(None, [], "a")
        values = _values(result)
        assert "alpha" in values
        assert "beta" not in values

    def test_returns_empty_on_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return empty list when storage is unavailable."""

        def raise_error() -> JSONLStorage:
            msg = "no storage"
            raise FileNotFoundError(msg)

        monkeypatch.setattr("dogcat.cli._completions.get_storage", raise_error)
        assert complete_namespaces(None, [], "") == []


class TestCompleteOwners:
    """Test complete_owners completion callback."""

    def test_returns_owners(
        self,
        temp_dogcats_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Should return all unique owners from issues."""
        storage = JSONLStorage(str(temp_dogcats_dir / "issues.jsonl"), create_dir=True)
        now = datetime.now().astimezone()
        storage.create(
            Issue(
                id="aaa1",
                namespace="dc",
                title="Issue 1",
                status=Status.OPEN,
                priority=2,
                issue_type=IssueType.TASK,
                owner="alice",
                created_by="test",
                created_at=now,
            ),
        )
        storage.create(
            Issue(
                id="bbb1",
                namespace="dc",
                title="Issue 2",
                status=Status.OPEN,
                priority=2,
                issue_type=IssueType.TASK,
                owner="bob",
                created_by="test",
                created_at=now,
            ),
        )
        storage.create(
            Issue(
                id="ccc1",
                namespace="dc",
                title="Issue 3 (no owner)",
                status=Status.OPEN,
                priority=2,
                issue_type=IssueType.TASK,
                created_by="test",
                created_at=now,
            ),
        )
        monkeypatch.setattr(
            "dogcat.cli._completions.get_storage",
            lambda: storage,
        )
        result = complete_owners(None, [], "")
        values = _values(result)
        assert "alice" in values
        assert "bob" in values
        assert len(values) == 2  # no empty owner

    def test_filters_by_prefix(
        self,
        temp_dogcats_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Should filter owners by incomplete prefix."""
        storage = JSONLStorage(str(temp_dogcats_dir / "issues.jsonl"), create_dir=True)
        now = datetime.now().astimezone()
        storage.create(
            Issue(
                id="aaa1",
                namespace="dc",
                title="Issue 1",
                status=Status.OPEN,
                priority=2,
                issue_type=IssueType.TASK,
                owner="alice",
                created_by="test",
                created_at=now,
            ),
        )
        storage.create(
            Issue(
                id="bbb1",
                namespace="dc",
                title="Issue 2",
                status=Status.OPEN,
                priority=2,
                issue_type=IssueType.TASK,
                owner="bob",
                created_by="test",
                created_at=now,
            ),
        )
        monkeypatch.setattr(
            "dogcat.cli._completions.get_storage",
            lambda: storage,
        )
        assert _values(complete_owners(None, [], "a")) == ["alice"]

    def test_returns_empty_on_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return empty list when storage is unavailable."""

        def raise_error() -> JSONLStorage:
            msg = "no storage"
            raise FileNotFoundError(msg)

        monkeypatch.setattr("dogcat.cli._completions.get_storage", raise_error)
        assert complete_owners(None, [], "") == []


class TestCompleteConfigKeys:
    """Test complete_config_keys completion callback."""

    def test_returns_all_keys(self) -> None:
        """Should return all known config keys with descriptions."""
        result = complete_config_keys("")
        values = _values(result)
        assert "namespace" in values
        assert "git_tracking" in values
        assert "visible_namespaces" in values
        assert "hidden_namespaces" in values
        assert "disable_legend_colors" in values
        assert all(isinstance(item, tuple) and len(item) == 2 for item in result)

    def test_filters_by_prefix(self) -> None:
        """Should filter config keys by incomplete prefix."""
        result = complete_config_keys("g")
        values = _values(result)
        assert "git_tracking" in values
        assert "namespace" not in values

    def test_no_match(self) -> None:
        """Should return empty list when no key matches."""
        assert complete_config_keys("zzz") == []


class TestCompleteExportFormats:
    """Test complete_export_formats completion callback."""

    def test_returns_all_formats(self) -> None:
        """Should return json and jsonl with descriptions."""
        result = complete_export_formats("")
        values = _values(result)
        assert "json" in values
        assert "jsonl" in values
        assert all(isinstance(item, tuple) and len(item) == 2 for item in result)

    def test_filters_by_prefix(self) -> None:
        """Should filter formats by incomplete prefix."""
        result = complete_export_formats("jsonl")
        assert _values(result) == ["jsonl"]

    def test_no_match(self) -> None:
        """Should return empty list when no format matches."""
        assert complete_export_formats("zzz") == []


class TestCompleteDepTypes:
    """Test complete_dep_types completion callback."""

    def test_returns_dep_types(self) -> None:
        """Should return blocks with description."""
        result = complete_dep_types("")
        values = _values(result)
        assert "blocks" in values
        assert all(isinstance(item, tuple) and len(item) == 2 for item in result)

    def test_filters_by_prefix(self) -> None:
        """Should filter dep types by incomplete prefix."""
        assert _values(complete_dep_types("b")) == ["blocks"]

    def test_no_match(self) -> None:
        """Should return empty list when no dep type matches."""
        assert complete_dep_types("zzz") == []


class TestCompleteLinkTypes:
    """Test complete_link_types completion callback."""

    def test_returns_link_types(self) -> None:
        """Should return relates_to and duplicates with descriptions."""
        result = complete_link_types("")
        values = _values(result)
        assert "relates_to" in values
        assert "duplicates" in values
        assert all(isinstance(item, tuple) and len(item) == 2 for item in result)

    def test_filters_by_prefix(self) -> None:
        """Should filter link types by incomplete prefix."""
        assert _values(complete_link_types("r")) == ["relates_to"]
        assert _values(complete_link_types("d")) == ["duplicates"]

    def test_no_match(self) -> None:
        """Should return empty list when no link type matches."""
        assert complete_link_types("zzz") == []


class TestCompleteDurations:
    """Test complete_durations completion callback."""

    def test_returns_all_durations(self) -> None:
        """Should return common duration values with descriptions."""
        result = complete_durations("")
        values = _values(result)
        assert values == ["7d", "14d", "30d", "60d", "90d"]
        assert all(isinstance(item, tuple) and len(item) == 2 for item in result)

    def test_filters_by_prefix(self) -> None:
        """Should filter durations by incomplete prefix."""
        assert _values(complete_durations("3")) == ["30d"]
        assert _values(complete_durations("1")) == ["14d"]
        assert _values(complete_durations("9")) == ["90d"]

    def test_no_match(self) -> None:
        """Should return empty list when no duration matches."""
        assert complete_durations("zzz") == []


class TestCompleteDates:
    """Test complete_dates completion callback."""

    def test_returns_date_suggestions(self) -> None:
        """Should return date strings with descriptions."""
        result = complete_dates("")
        values = _values(result)
        assert len(values) == 7
        # All values should be ISO date format YYYY-MM-DD
        for v in values:
            assert len(v) == 10
            assert v[4] == "-"
            assert v[7] == "-"
        # Verify tuples have help text
        helps = dict(result)
        assert "today" in list(helps.values())
        assert "1 week ago" in list(helps.values())

    def test_filters_by_prefix(self) -> None:
        """Should filter dates by year prefix."""
        result = complete_dates("2026")
        values = _values(result)
        assert all(v.startswith("2026") for v in values)

    def test_no_match(self) -> None:
        """Should return empty list when no date matches."""
        assert complete_dates("1999") == []


class TestCompleteConfigValues:
    """Test complete_config_values completion callback."""

    def test_bool_key_returns_true_false(self) -> None:
        """Should return true/false for boolean config keys."""

        class FakeCtx:
            params: ClassVar[dict[str, Any]] = {"key": "git_tracking"}

        result = complete_config_values(FakeCtx(), [], "")
        values = _values(result)
        assert "true" in values
        assert "false" in values

    def test_bool_key_filters_by_prefix(self) -> None:
        """Should filter boolean values by prefix."""

        class FakeCtx:
            params: ClassVar[dict[str, Any]] = {"key": "disable_legend_colors"}

        result = complete_config_values(FakeCtx(), [], "t")
        assert _values(result) == ["true"]

    def test_namespace_key_returns_namespaces(
        self,
        storage_with_issues: JSONLStorage,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Should return namespaces for visible_namespaces key."""
        monkeypatch.setattr(
            "dogcat.cli._completions.get_storage",
            lambda: storage_with_issues,
        )

        class FakeCtx:
            params: ClassVar[dict[str, Any]] = {"key": "visible_namespaces"}

        result = complete_config_values(FakeCtx(), [], "")
        values = _values(result)
        assert "dc" in values

    def test_unknown_key_returns_empty(self) -> None:
        """Should return empty list for unknown config keys."""

        class FakeCtx:
            params: ClassVar[dict[str, Any]] = {"key": "unknown_key"}

        assert complete_config_values(FakeCtx(), [], "") == []

    def test_no_key_in_params(self) -> None:
        """Should return empty list when key is not yet provided."""

        class FakeCtx:
            params: ClassVar[dict[str, Any]] = {}

        assert complete_config_values(FakeCtx(), [], "") == []
