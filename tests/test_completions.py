"""Tests for shell completion callbacks."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

import pytest

from dogcat.cli._completions import (
    _ns_filter_from_ctx,
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
    from collections.abc import Callable


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
        assert set(_values(result)) == {"in_progress", "in_review"}

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
        assert set(values) == {"add", "remove", "list"}
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
        assert set(values) == {"add", "list", "delete"}
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
        assert "item(s)" in helps["dc"]

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


class _AllNamespacesCtx:
    """Click context stand-in that disables namespace filtering."""

    params: ClassVar[dict[str, Any]] = {"all_namespaces": True}


def _ref_issue_ids(
    storage: JSONLStorage,
    ctx: Any,
    incomplete: str,
    keep: Callable[[str], bool],
) -> list[tuple[str, str]]:
    """Complete issue ids the old way, over ``storage.list()``.

    Kept as the oracle: it materializes every Issue, so any field the raw
    branch of ``iter_completion_fields`` normalizes differently shows up as a
    diff here rather than as a wrong completion in a user's shell.
    """
    ns_filter = _ns_filter_from_ctx(ctx, str(storage.dogcats_dir))
    results: list[tuple[str, str]] = []
    for i in storage.list():
        if not keep(i.status.value):
            continue
        if ns_filter is not None and not ns_filter(i.namespace):
            continue
        fid = i.full_id
        short_id = i.id
        if fid.startswith(incomplete):
            results.append((fid, i.title))
        elif short_id.startswith(incomplete):
            results.append((short_id, i.title))
    return sorted(results)


def _ref_labels(
    storage: JSONLStorage,
    ctx: Any,
    incomplete: str,
) -> list[tuple[str, str]]:
    """Collect labels the old way, over ``storage.list()``."""
    ns_filter = _ns_filter_from_ctx(ctx, str(storage.dogcats_dir))
    labels: set[str] = set()
    for issue in storage.list():
        if ns_filter is None or ns_filter(issue.namespace):
            labels.update(issue.labels)
    return [(lbl, "label") for lbl in sorted(labels) if lbl.startswith(incomplete)]


def _ref_owners(storage: JSONLStorage, incomplete: str) -> list[tuple[str, str]]:
    """Collect owners the old way, over ``storage.list()``."""
    owners: set[str] = set()
    for issue in storage.list():
        if issue.owner:
            owners.add(issue.owner)
    return [
        (owner, "owner") for owner in sorted(owners) if owner.startswith(incomplete)
    ]


def _ref_fields(storage: JSONLStorage) -> list[tuple[Any, ...]]:
    """Completion fields read off fully materialized Issue objects."""
    return [
        (i.full_id, i.id, i.namespace, i.status.value, i.title, i.labels, i.owner)
        for i in storage.list()
    ]


# Records that exercise every normalization ``dict_to_issue`` applies to a
# completion field. Written as raw JSONL because ``issue_to_dict`` cannot
# produce a legacy id or an unknown enum value.
_SPARSE_RECORDS: list[dict[str, Any]] = [
    {
        "record_type": "issue",
        "namespace": "dc",
        "id": "plain",
        "title": "Fully populated",
        "status": "open",
        "issue_type": "bug",
        "labels": ["alpha", "beta"],
        "owner": "someone@example.com",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    },
    {
        # No namespace key: the id carries it (legacy format).
        "record_type": "issue",
        "id": "legacy-ns-lg01",
        "title": "Legacy embedded namespace",
        "status": "open",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    },
    {
        # No hyphen at all: namespace falls back to the default.
        "record_type": "issue",
        "id": "bare01",
        "title": "Bare id, no namespace",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    },
    {
        # Legacy issue_type=draft rewrites status to draft.
        "record_type": "issue",
        "namespace": "dc",
        "id": "draft1",
        "title": "Legacy draft type",
        "status": "open",
        "issue_type": "draft",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    },
    {
        # Legacy draft type on a closed record keeps the closed status.
        "record_type": "issue",
        "namespace": "dc",
        "id": "draft2",
        "title": "Legacy draft type, closed",
        "status": "closed",
        "issue_type": "draft",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    },
    {
        # Status from a newer dcat: coerced to the UNKNOWN sentinel.
        "record_type": "issue",
        "namespace": "dc",
        "id": "future",
        "title": "Unknown status value",
        "status": "quantum_superposition",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    },
    {
        # No status key: defaults to open.
        "record_type": "issue",
        "namespace": "dc",
        "id": "nostat",
        "title": "Missing status key",
        "labels": [],
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    },
    {
        "record_type": "issue",
        "namespace": "dc",
        "id": "tomb01",
        "title": "Tombstoned",
        "status": "tombstone",
        "owner": None,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    },
    {
        "record_type": "issue",
        "namespace": "other",
        "id": "clos01",
        "title": "Closed in another namespace",
        "status": "closed",
        "labels": ["alpha"],
        "owner": "someone@example.com",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    },
]


def _write_sparse_store(dogcats_dir: Path) -> Path:
    """Write ``_SPARSE_RECORDS`` as raw JSONL and return the store path."""
    path = dogcats_dir / "issues.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for record in _SPARSE_RECORDS:
            fh.write(json.dumps(record))
            fh.write("\n")
    return path


def _real_store_copy(tmp_path: Path) -> Path | None:
    """Copy this repo's own ``.dogcats/issues.jsonl`` into ``tmp_path``.

    Copied rather than opened in place so a test can never append to, lock or
    compact the project's real store.
    """
    source = Path(__file__).resolve().parent.parent / ".dogcats" / "issues.jsonl"
    if not source.is_file():
        return None
    dest_dir = tmp_path / "real" / ".dogcats"
    dest_dir.mkdir(parents=True)
    dest = dest_dir / "issues.jsonl"
    shutil.copyfile(source, dest)
    return dest


class TestRawFieldCompletionEquivalence:
    """Raw-dict completers must match the Issue-materializing loops exactly."""

    def test_sparse_records_yield_identical_fields(
        self,
        temp_dogcats_dir: Path,
    ) -> None:
        """Every normalization dict_to_issue applies is reproduced raw."""
        path = _write_sparse_store(temp_dogcats_dir)

        raw_side = JSONLStorage(str(path))
        raw_fields = list(raw_side._issues.iter_completion_fields())
        # Nothing was constructed to produce them.
        assert not any(isinstance(v, Issue) for v in raw_side._issues._entries.values())

        assert [tuple(f) for f in raw_fields] == _ref_fields(JSONLStorage(str(path)))

    def test_materialized_entries_yield_identical_fields(
        self,
        temp_dogcats_dir: Path,
    ) -> None:
        """The Issue branch of the iterator agrees with the raw branch."""
        path = _write_sparse_store(temp_dogcats_dir)

        raw_side = JSONLStorage(str(path))
        raw_fields = [tuple(f) for f in raw_side._issues.iter_completion_fields()]

        hot = JSONLStorage(str(path))
        hot.list()  # force every entry to materialize
        hot_fields = [tuple(f) for f in hot._issues.iter_completion_fields()]

        assert hot_fields == raw_fields

    def test_mixed_materialization_yields_identical_fields(
        self,
        temp_dogcats_dir: Path,
    ) -> None:
        """A map with some entries materialized takes both branches."""
        path = _write_sparse_store(temp_dogcats_dir)

        cold = JSONLStorage(str(path))
        expected = [tuple(f) for f in cold._issues.iter_completion_fields()]

        mixed = JSONLStorage(str(path))
        for key in list(mixed._issues)[::2]:
            _ = mixed._issues[key]
        assert [tuple(f) for f in mixed._issues.iter_completion_fields()] == expected

    def test_real_store_yields_identical_fields(self, tmp_path: Path) -> None:
        """The project's own store round-trips through both paths identically."""
        path = _real_store_copy(tmp_path)
        if path is None:
            pytest.skip("no .dogcats/issues.jsonl in this checkout")

        raw_fields = [
            tuple(f) for f in JSONLStorage(str(path))._issues.iter_completion_fields()
        ]
        assert raw_fields  # guard against a vacuous comparison
        assert raw_fields == _ref_fields(JSONLStorage(str(path)))

    @pytest.mark.parametrize(
        "incomplete",
        ["", "dc", "dc-", "dc-d", "legacy", "bare", "zzz"],
    )
    def test_issue_id_completers_match_reference(
        self,
        temp_dogcats_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        incomplete: str,
    ) -> None:
        """complete_issue_ids and complete_closed_issue_ids match the old loop."""
        path = _write_sparse_store(temp_dogcats_dir)
        ctx = _AllNamespacesCtx()

        def open_keep(status: str) -> bool:
            return status not in ("closed", "tombstone")

        def closed_keep(status: str) -> bool:
            return status == "closed"

        monkeypatch.setattr(
            "dogcat.cli._completions.get_storage",
            lambda: JSONLStorage(str(path)),
        )
        got_open = complete_issue_ids(ctx, [], incomplete)
        got_closed = complete_closed_issue_ids(ctx, [], incomplete)

        assert got_open == _ref_issue_ids(
            JSONLStorage(str(path)), ctx, incomplete, open_keep
        )
        assert got_closed == _ref_issue_ids(
            JSONLStorage(str(path)), ctx, incomplete, closed_keep
        )

    @pytest.mark.parametrize("incomplete", ["", "a", "al", "zzz"])
    def test_label_completer_matches_reference(
        self,
        temp_dogcats_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        incomplete: str,
    ) -> None:
        """complete_labels matches the old loop, including absent label keys."""
        path = _write_sparse_store(temp_dogcats_dir)
        ctx = _AllNamespacesCtx()

        monkeypatch.setattr(
            "dogcat.cli._completions.get_storage",
            lambda: JSONLStorage(str(path)),
        )
        got = complete_labels(ctx, [], incomplete)

        assert got == _ref_labels(JSONLStorage(str(path)), ctx, incomplete)

    @pytest.mark.parametrize("incomplete", ["", "some", "zzz"])
    def test_owner_completer_matches_reference(
        self,
        temp_dogcats_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        incomplete: str,
    ) -> None:
        """complete_owners matches the old loop, including null owners."""
        path = _write_sparse_store(temp_dogcats_dir)

        monkeypatch.setattr(
            "dogcat.cli._completions.get_storage",
            lambda: JSONLStorage(str(path)),
        )
        got = complete_owners(None, [], incomplete)

        assert got == _ref_owners(JSONLStorage(str(path)), incomplete)

    @pytest.mark.parametrize("incomplete", ["", "d", "o", "zzz"])
    def test_config_value_namespaces_match_reference(
        self,
        temp_dogcats_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        incomplete: str,
    ) -> None:
        """complete_config_values namespace branch matches the old loop."""
        path = _write_sparse_store(temp_dogcats_dir)

        class KeyCtx:
            params: ClassVar[dict[str, Any]] = {"key": "visible_namespaces"}

        monkeypatch.setattr(
            "dogcat.cli._completions.get_storage",
            lambda: JSONLStorage(str(path)),
        )
        got = complete_config_values(KeyCtx(), [], incomplete)

        expected_ns = sorted(
            {i.namespace for i in JSONLStorage(str(path)).list()},
        )
        assert got == [
            (ns, "namespace") for ns in expected_ns if ns.startswith(incomplete)
        ]

    def test_completers_do_not_materialize_issues(
        self,
        temp_dogcats_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The point of the change: no Issue is constructed for a Tab press."""
        path = _write_sparse_store(temp_dogcats_dir)
        storage = JSONLStorage(str(path))
        monkeypatch.setattr(
            "dogcat.cli._completions.get_storage",
            lambda: storage,
        )

        complete_issue_ids(_AllNamespacesCtx(), [], "")
        complete_closed_issue_ids(_AllNamespacesCtx(), [], "")
        complete_labels(_AllNamespacesCtx(), [], "")
        complete_owners(None, [], "")

        assert not any(isinstance(v, Issue) for v in storage._issues._entries.values())
