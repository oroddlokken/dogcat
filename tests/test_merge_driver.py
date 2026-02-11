"""Tests for the custom JSONL merge driver.

Unit tests for the merge logic and integration tests verifying that
previously-conflicting git merge scenarios now resolve cleanly when
the merge driver is installed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import orjson

from dogcat.constants import MERGE_DRIVER_CMD
from dogcat.merge_driver import merge_jsonl
from dogcat.models import DependencyType, Issue
from dogcat.storage import JSONLStorage

if TYPE_CHECKING:
    from conftest import GitRepo


def _issue_record(**kwargs: Any) -> dict[str, Any]:
    """Build a minimal issue record dict."""
    defaults: dict[str, Any] = {
        "record_type": "issue",
        "namespace": "test",
        "id": "x",
        "title": "Test",
        "status": "open",
        "priority": 2,
        "issue_type": "task",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    defaults.update(kwargs)
    return defaults


def _event_record(**kwargs: Any) -> dict[str, Any]:
    """Build a minimal event record dict."""
    defaults: dict[str, Any] = {
        "record_type": "event",
        "event_type": "created",
        "issue_id": "test-x",
        "timestamp": "2026-01-01T00:00:00+00:00",
    }
    defaults.update(kwargs)
    return defaults


def _dep_record(**kwargs: Any) -> dict[str, Any]:
    """Build a minimal dependency record dict."""
    defaults: dict[str, Any] = {
        "record_type": "dependency",
        "issue_id": "test-a",
        "depends_on_id": "test-b",
        "type": "blocks",
    }
    defaults.update(kwargs)
    return defaults


# ---------------------------------------------------------------------------
# Unit tests for merge_jsonl()
# ---------------------------------------------------------------------------


class TestMergeJSONL:
    """Unit tests for the JSONL merge logic."""

    def test_non_overlapping_issues(self) -> None:
        """Different issues from each side are both kept."""
        base: list[dict[str, Any]] = []
        ours = [_issue_record(id="a1", title="Issue A")]
        theirs = [_issue_record(id="b1", title="Issue B")]

        result = merge_jsonl(base, ours, theirs)
        issue_ids = {
            f"{r['namespace']}-{r['id']}"
            for r in result
            if r.get("record_type") == "issue"
        }
        assert issue_ids == {"test-a1", "test-b1"}

    def test_same_issue_latest_wins(self) -> None:
        """Same issue edited on both sides: later updated_at wins."""
        base = [_issue_record(id="s1", title="Original")]
        ours = [
            _issue_record(
                id="s1",
                title="Title from ours",
                updated_at="2026-01-02T00:00:00+00:00",
            ),
        ]
        theirs = [
            _issue_record(
                id="s1",
                title="Title from theirs",
                updated_at="2026-01-03T00:00:00+00:00",
            ),
        ]

        result = merge_jsonl(base, ours, theirs)
        issues = [r for r in result if r.get("record_type") == "issue"]
        assert len(issues) == 1
        assert issues[0]["title"] == "Title from theirs"

    def test_events_deduplicated(self) -> None:
        """Same event from both sides is kept only once."""
        event = _event_record(issue_id="test-x", timestamp="2026-01-01T00:00:00+00:00")
        base: list[dict[str, Any]] = []
        ours = [event.copy()]
        theirs = [event.copy()]

        result = merge_jsonl(base, ours, theirs)
        events = [r for r in result if r.get("record_type") == "event"]
        assert len(events) == 1

    def test_events_union(self) -> None:
        """Different events from each side are both kept."""
        base: list[dict[str, Any]] = []
        ours = [_event_record(issue_id="test-a", timestamp="2026-01-01T00:00:00+00:00")]
        theirs = [
            _event_record(issue_id="test-b", timestamp="2026-01-02T00:00:00+00:00"),
        ]

        result = merge_jsonl(base, ours, theirs)
        events = [r for r in result if r.get("record_type") == "event"]
        assert len(events) == 2

    def test_deps_union(self) -> None:
        """Different dependencies from each side are both kept."""
        base: list[dict[str, Any]] = []
        ours = [_dep_record(issue_id="test-a", depends_on_id="test-b")]
        theirs = [_dep_record(issue_id="test-c", depends_on_id="test-d")]

        result = merge_jsonl(base, ours, theirs)
        deps = [r for r in result if r.get("record_type") == "dependency"]
        assert len(deps) == 2

    def test_deps_deduplicated(self) -> None:
        """Same dependency from both sides is kept only once."""
        dep = _dep_record()
        base: list[dict[str, Any]] = []
        ours = [dep.copy()]
        theirs = [dep.copy()]

        result = merge_jsonl(base, ours, theirs)
        deps = [r for r in result if r.get("record_type") == "dependency"]
        assert len(deps) == 1

    def test_mixed_records(self) -> None:
        """Issues, events, deps, and links all merge correctly."""
        base: list[dict[str, Any]] = []
        ours = [
            _issue_record(id="a1", title="Issue A"),
            _event_record(issue_id="test-a1", timestamp="2026-01-01T00:00:00+00:00"),
            _dep_record(issue_id="test-a1", depends_on_id="test-a2"),
        ]
        theirs = [
            _issue_record(id="b1", title="Issue B"),
            _event_record(issue_id="test-b1", timestamp="2026-01-02T00:00:00+00:00"),
        ]

        result = merge_jsonl(base, ours, theirs)
        issues = [r for r in result if r.get("record_type") == "issue"]
        events = [r for r in result if r.get("record_type") == "event"]
        deps = [r for r in result if r.get("record_type") == "dependency"]
        assert len(issues) == 2
        assert len(events) == 2
        assert len(deps) == 1

    def test_empty_inputs(self) -> None:
        """All empty inputs produce empty output."""
        result = merge_jsonl([], [], [])
        assert result == []


# ---------------------------------------------------------------------------
# Integration tests: merge driver with real git repos
# ---------------------------------------------------------------------------


def _install_merge_driver(repo: GitRepo) -> None:
    """Configure the dcat-jsonl merge driver in a git repo."""
    repo.git("config", "merge.dcat-jsonl.driver", MERGE_DRIVER_CMD)
    # Write .gitattributes
    attrs = repo.path / ".gitattributes"
    attrs.write_text(".dogcats/*.jsonl merge=dcat-jsonl\n")
    repo.commit_all("Add merge driver config")


def _all_valid_json(repo: GitRepo) -> bool:
    """Return True if every non-empty line in issues.jsonl is valid JSON."""
    lines = repo.read_jsonl_lines()
    try:
        for line in lines:
            orjson.loads(line)
    except orjson.JSONDecodeError:
        return False
    return True


class TestMergeDriverIntegration:
    """Integration tests verifying the merge driver resolves conflicts."""

    def test_non_overlapping_adds_resolve(self, git_repo: GitRepo) -> None:
        """With merge driver, non-overlapping adds merge cleanly."""
        repo = git_repo
        _install_merge_driver(repo)

        # Branch A
        repo.create_branch("branch-a")
        s = repo.storage()
        s.create(Issue(id="a1", namespace="test", title="Issue A1"))
        s.create(Issue(id="a2", namespace="test", title="Issue A2"))
        repo.commit_all("Add issues on branch-a")

        # Branch B
        repo.switch_branch("main")
        repo.create_branch("branch-b")
        s = repo.storage()
        s.create(Issue(id="b1", namespace="test", title="Issue B1"))
        s.create(Issue(id="b2", namespace="test", title="Issue B2"))
        repo.commit_all("Add issues on branch-b")

        # Merge
        repo.switch_branch("main")
        result_a = repo.merge("branch-a")
        assert result_a.returncode == 0

        result_b = repo.merge("branch-b")
        assert result_b.returncode == 0, f"Merge failed: {result_b.stdout}"

        assert _all_valid_json(repo)
        storage = JSONLStorage(str(repo.storage_path))
        assert len(storage.list()) == 4

    def test_same_issue_edits_resolve(self, git_repo: GitRepo) -> None:
        """With merge driver, same-issue edits resolve via latest timestamp."""
        repo = git_repo
        _install_merge_driver(repo)

        # Seed
        s = repo.storage()
        s.create(Issue(id="shared1", namespace="test", title="Original"))
        repo.commit_all("Seed shared issue")

        # Branch A: update title
        repo.create_branch("branch-a")
        s = repo.storage()
        s.update("test-shared1", {"title": "Title from A"})
        repo.commit_all("Update on branch-a")

        # Branch B: update title
        repo.switch_branch("main")
        repo.create_branch("branch-b")
        s = repo.storage()
        s.update("test-shared1", {"title": "Title from B"})
        repo.commit_all("Update on branch-b")

        # Merge
        repo.switch_branch("main")
        repo.merge("branch-a")
        result_b = repo.merge("branch-b")
        assert result_b.returncode == 0, f"Merge failed: {result_b.stdout}"

        assert _all_valid_json(repo)
        storage = JSONLStorage(str(repo.storage_path))
        issue = storage.get("test-shared1")
        assert issue is not None
        # The one with later updated_at wins (branch-b was created after A)
        assert issue.title == "Title from B"

    def test_concurrent_creates_resolve(self, git_repo: GitRepo) -> None:
        """With merge driver, concurrent creates merge cleanly."""
        repo = git_repo
        _install_merge_driver(repo)

        repo.create_branch("branch-a")
        s = repo.storage()
        for i in range(3):
            s.create(Issue(id=f"ca{i}", namespace="test", title=f"A issue {i}"))
        repo.commit_all("Creates on branch-a")

        repo.switch_branch("main")
        repo.create_branch("branch-b")
        s = repo.storage()
        for i in range(3):
            s.create(Issue(id=f"cb{i}", namespace="test", title=f"B issue {i}"))
        repo.commit_all("Creates on branch-b")

        repo.switch_branch("main")
        repo.merge("branch-a")
        result_b = repo.merge("branch-b")
        assert result_b.returncode == 0, f"Merge failed: {result_b.stdout}"

        assert _all_valid_json(repo)
        storage = JSONLStorage(str(repo.storage_path))
        assert len(storage.list()) == 6

    def test_mixed_record_types_resolve(self, git_repo: GitRepo) -> None:
        """With merge driver, deps and links on separate branches merge cleanly."""
        repo = git_repo
        _install_merge_driver(repo)

        s = repo.storage()
        s.create(Issue(id="d1", namespace="test", title="Issue D1"))
        s.create(Issue(id="d2", namespace="test", title="Issue D2"))
        repo.commit_all("Seed issues")

        # Branch A: add dependency
        repo.create_branch("branch-a")
        s = repo.storage()
        s.add_dependency("test-d1", "test-d2", DependencyType.BLOCKS)
        repo.commit_all("Add dep on branch-a")

        # Branch B: add link
        repo.switch_branch("main")
        repo.create_branch("branch-b")
        s = repo.storage()
        s.add_link("test-d1", "test-d2", "relates_to")
        repo.commit_all("Add link on branch-b")

        repo.switch_branch("main")
        repo.merge("branch-a")
        result_b = repo.merge("branch-b")
        assert result_b.returncode == 0, f"Merge failed: {result_b.stdout}"

        assert _all_valid_json(repo)
        storage = JSONLStorage(str(repo.storage_path))
        assert len(storage.all_dependencies) >= 1
        assert len(storage.all_links) >= 1
