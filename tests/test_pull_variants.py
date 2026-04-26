"""Tests for pull and rebase variants with JSONL issue storage.

Validates that the merge driver works correctly with different ways
users invoke the merge machinery: git pull, git pull --rebase,
git fetch && merge, and git rebase --interactive.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import orjson

from dogcat.constants import MERGE_DRIVER_CMD
from dogcat.models import Issue
from dogcat.storage import JSONLStorage

if TYPE_CHECKING:
    from conftest import GitRepo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _install_merge_driver(repo: GitRepo) -> None:
    """Configure the dcat-jsonl merge driver in a git repo."""
    repo.git("config", "merge.dcat-jsonl.driver", MERGE_DRIVER_CMD)
    # Write .gitattributes
    attrs = repo.path / ".gitattributes"
    attrs.write_text(".dogcats/*.jsonl merge=dcat-jsonl\n")
    repo.commit_all("Add merge driver config")


def _create_issue_on_branch(
    repo: GitRepo,
    branch: str,
    issue_id: str,
    title: str,
    *,
    namespace: str = "test",
    **extra_fields: Any,
) -> None:
    """Switch to *branch*, create an issue via storage, and commit."""
    repo.switch_branch(branch)
    s = repo.storage()
    issue = Issue(id=issue_id, namespace=namespace, title=title, **extra_fields)
    s.create(issue)
    repo.commit_all(f"Create {namespace}-{issue_id}")


def _update_issue_on_branch(
    repo: GitRepo,
    branch: str,
    full_id: str,
    updates: dict[str, Any],
    commit_msg: str = "",
) -> None:
    """Switch to *branch*, update an issue via storage, and commit."""
    repo.switch_branch(branch)
    s = repo.storage()
    s.update(full_id, updates)
    repo.commit_all(commit_msg or f"Update {full_id}")


def _has_conflict_markers(repo: GitRepo) -> bool:
    """Return True if the JSONL file contains git conflict markers."""
    raw = repo.storage_path.read_text()
    return "<<<<<<<" in raw or "=======" in raw


def _all_valid_json(repo: GitRepo) -> bool:
    """Return True if every non-empty line in issues.jsonl is valid JSON."""
    lines = [
        line for line in repo.storage_path.read_text().splitlines() if line.strip()
    ]
    try:
        for line in lines:
            orjson.loads(line)
    except orjson.JSONDecodeError:
        return False
    return True


def _verify_jsonl_integrity(repo: GitRepo) -> JSONLStorage:
    """Verify JSONL loads cleanly and has no conflict markers."""
    assert not _has_conflict_markers(repo), "JSONL contains conflict markers"
    assert _all_valid_json(repo), "JSONL contains invalid JSON"
    return JSONLStorage(str(repo.storage_path))


def _record_on_branch(repo: GitRepo, branch: str, full_id: str) -> Issue:
    """Read an issue's record while ``branch`` is checked out.

    Used by LWW assertions: captures a branch's view of a contested
    record (specifically its ``updated_at``) before a merge so the test
    can prove the merge result equals the side with the later
    timestamp. (dogcat-2bt3)
    """
    repo.switch_branch(branch)
    issue = JSONLStorage(str(repo.storage_path)).get(full_id)
    assert issue is not None, f"{full_id} missing on {branch}"
    return issue


def _assert_lww_winner(
    merged: Issue,
    side_a: Issue,
    side_b: Issue,
    *,
    fields: tuple[str, ...] = ("status", "priority", "title"),
) -> None:
    """Assert the merged record equals the side with the later ``updated_at``.

    A merge driver that quietly mixes fields, drops one side, or returns
    the wrong record entirely will fail this — ``is not None`` will not.
    (dogcat-2bt3)
    """
    assert side_a.updated_at != side_b.updated_at, (
        "test setup must produce distinct updated_at timestamps so LWW has"
        " a definite winner"
    )
    winner = side_a if side_a.updated_at > side_b.updated_at else side_b
    for field_name in fields:
        assert getattr(merged, field_name) == getattr(winner, field_name), (
            f"LWW lost {field_name}: merged={getattr(merged, field_name)!r}"
            f" winner={getattr(winner, field_name)!r}"
        )


# ---------------------------------------------------------------------------
# Test scenarios
# ---------------------------------------------------------------------------


class TestGitPullMerge:
    """git pull (default merge strategy)."""

    def test_pull_merge_with_concurrent_edits(self, git_repo: GitRepo) -> None:
        """Both main and remote have unique issues and edit the same issue.

        Simulates pull with merge by testing merge directly.
        LWW semantics: latest updated_at wins for contested edits.
        """
        repo = git_repo
        _install_merge_driver(repo)

        # Create base issue
        s = repo.storage()
        s.create(Issue(id="shared", namespace="test", title="Shared Issue"))
        repo.commit_all("Create shared issue")

        # Feature branch: create unique issue and edit shared
        repo.create_branch("feature")
        _create_issue_on_branch(repo, "feature", "feature1", "Feature Issue")
        _update_issue_on_branch(
            repo, "feature", "test-shared", {"status": "in_progress"}, "Feature edit"
        )

        # Main branch: create unique issue and edit shared
        repo.switch_branch("main")
        _create_issue_on_branch(repo, "main", "main1", "Main Issue")
        _update_issue_on_branch(
            repo, "main", "test-shared", {"priority": 1}, "Main edit"
        )

        # Capture each side's view of the contested issue BEFORE the merge
        # so we can assert which side wins under LWW after merging.
        feature_view = _record_on_branch(repo, "feature", "test-shared")
        main_view = _record_on_branch(repo, "main", "test-shared")

        # Merge feature into main
        repo.switch_branch("main")
        result = repo.merge("feature")
        assert result.returncode == 0

        # Verify integrity
        storage = _verify_jsonl_integrity(repo)

        # Both unique issues should exist
        assert storage.get("test-feature1") is not None
        assert storage.get("test-main1") is not None

        # Shared issue: the LATER updated_at must win exactly. The
        # earlier-side's edits are lost — that's the documented LWW
        # contract, and asserting it explicitly guards against a future
        # merge driver that quietly mixes fields.
        shared = storage.get("test-shared")
        assert shared is not None
        _assert_lww_winner(shared, feature_view, main_view)


class TestGitRebase:
    """git rebase (rebase strategy)."""

    def test_rebase_with_multiple_local_commits(self, git_repo: GitRepo) -> None:
        """Local has multiple commits. Rebase replays them.

        Verify JSONL is valid after rebase and records are preserved.
        """
        repo = git_repo
        _install_merge_driver(repo)

        # Create base
        s = repo.storage()
        s.create(Issue(id="base", namespace="test", title="Base"))
        repo.commit_all("Create base")

        # Feature branch with multiple commits
        repo.create_branch("feature")
        _create_issue_on_branch(repo, "feature", "f1", "Feature 1")
        _create_issue_on_branch(repo, "feature", "f2", "Feature 2")
        _create_issue_on_branch(repo, "feature", "f3", "Feature 3")

        # Main branch diverges
        repo.switch_branch("main")
        _create_issue_on_branch(repo, "main", "m1", "Main 1")

        # Rebase feature onto main
        repo.switch_branch("feature")
        result = repo.git("rebase", "main", check=False)

        assert result.returncode == 0, f"Rebase failed: {result.stderr}"

        # Verify integrity AND that each record carries the title its
        # author wrote — a merge driver that drops/swaps fields would
        # leave the records present but with the wrong content. (dogcat-2bt3)
        storage = _verify_jsonl_integrity(repo)
        expected = {
            "test-base": "Base",
            "test-f1": "Feature 1",
            "test-f2": "Feature 2",
            "test-f3": "Feature 3",
            "test-m1": "Main 1",
        }
        for full_id, title in expected.items():
            issue = storage.get(full_id)
            assert issue is not None, f"{full_id} missing after rebase"
            assert issue.title == title, f"{full_id} title swapped: {issue.title!r}"

    def test_rebase_with_same_issue_edits(self, git_repo: GitRepo) -> None:
        """Both branches edit the same issue. Rebase should resolve cleanly.

        The merge driver should handle LWW semantics during rebase.
        """
        repo = git_repo
        _install_merge_driver(repo)

        # Create shared issue
        s = repo.storage()
        s.create(Issue(id="shared", namespace="test", title="Shared"))
        repo.commit_all("Create shared")

        # Feature branch edits shared
        repo.create_branch("feature")
        _update_issue_on_branch(
            repo, "feature", "test-shared", {"status": "in_progress"}, "Feature edit"
        )

        # Main branch edits shared
        repo.switch_branch("main")
        _update_issue_on_branch(
            repo, "main", "test-shared", {"priority": 1}, "Main edit"
        )

        # Capture both sides' views of the contested issue before rebase.
        feature_view = _record_on_branch(repo, "feature", "test-shared")
        main_view = _record_on_branch(repo, "main", "test-shared")

        # Rebase feature onto main
        repo.switch_branch("feature")
        result = repo.git("rebase", "main", check=False)

        assert result.returncode == 0, f"Rebase failed: {result.stderr}"

        # Verify integrity and that the later-updated_at side won.
        storage = _verify_jsonl_integrity(repo)
        shared = storage.get("test-shared")
        assert shared is not None
        _assert_lww_winner(shared, feature_view, main_view)


class TestBranchMergeStrategies:
    """Test different branch merge strategies."""

    def test_merge_with_sequential_commits(self, git_repo: GitRepo) -> None:
        """Merge branches with sequential commits on each side.

        Verify all commits from both branches are preserved.
        """
        repo = git_repo
        _install_merge_driver(repo)

        # Main branch: create issues in sequence
        s = repo.storage()
        s.create(Issue(id="m1", namespace="test", title="Main 1"))
        repo.commit_all("Create main-m1")
        s.create(Issue(id="m2", namespace="test", title="Main 2"))
        repo.commit_all("Create main-m2")

        # Feature branch: diverge and create issues
        repo.create_branch("feature")
        s = repo.storage()
        s.create(Issue(id="f1", namespace="test", title="Feature 1"))
        repo.commit_all("Create feature-f1")
        s.create(Issue(id="f2", namespace="test", title="Feature 2"))
        repo.commit_all("Create feature-f2")

        # Merge feature into main
        repo.switch_branch("main")
        result = repo.merge("feature")

        assert result.returncode == 0

        # Verify integrity, all issues exist with author-written titles. (dogcat-2bt3)
        storage = _verify_jsonl_integrity(repo)
        expected = {
            "test-m1": "Main 1",
            "test-m2": "Main 2",
            "test-f1": "Feature 1",
            "test-f2": "Feature 2",
        }
        for full_id, title in expected.items():
            issue = storage.get(full_id)
            assert issue is not None, f"{full_id} missing after merge"
            assert issue.title == title


class TestMergeConflictResolution:
    """Test how merge driver handles conflict resolution."""

    def test_fast_forward_merge(self, git_repo: GitRepo) -> None:
        """Fast-forward merge should succeed without invoking merge driver.

        When feature branch is directly ahead of main.
        """
        repo = git_repo
        _install_merge_driver(repo)

        # Create base on main
        s = repo.storage()
        s.create(Issue(id="base", namespace="test", title="Base"))
        repo.commit_all("Create base")

        # Feature branch: extends main linearly
        repo.create_branch("feature")
        _create_issue_on_branch(repo, "feature", "f1", "Feature 1")
        _create_issue_on_branch(repo, "feature", "f2", "Feature 2")

        # Merge feature into main (fast-forward, no real merge invoked)
        repo.switch_branch("main")
        result = repo.merge("feature")

        assert result.returncode == 0

        # Verify all commits integrated and title content survived. (dogcat-2bt3)
        storage = _verify_jsonl_integrity(repo)
        expected = {"test-base": "Base", "test-f1": "Feature 1", "test-f2": "Feature 2"}
        for full_id, title in expected.items():
            issue = storage.get(full_id)
            assert issue is not None, f"{full_id} missing after fast-forward"
            assert issue.title == title

    def test_diverged_branches_merge(self, git_repo: GitRepo) -> None:
        """When branches diverge, merge driver handles conflict resolution.

        Both sides add different issues and edit same issue.
        """
        repo = git_repo
        _install_merge_driver(repo)

        # Base
        s = repo.storage()
        s.create(Issue(id="shared", namespace="test", title="Shared"))
        repo.commit_all("Create shared")

        # Main diverges
        repo.create_branch("feature")
        repo.switch_branch("main")
        _create_issue_on_branch(repo, "main", "m1", "Main 1")
        _update_issue_on_branch(
            repo, "main", "test-shared", {"priority": 1}, "Main edit"
        )

        # Feature diverges
        repo.switch_branch("feature")
        _create_issue_on_branch(repo, "feature", "f1", "Feature 1")
        _update_issue_on_branch(
            repo, "feature", "test-shared", {"status": "in_progress"}, "Feature edit"
        )

        # Capture pre-merge views before resolving the conflict.
        feature_view = _record_on_branch(repo, "feature", "test-shared")
        main_view = _record_on_branch(repo, "main", "test-shared")

        # Merge (should use merge driver)
        repo.switch_branch("main")
        result = repo.merge("feature")

        assert result.returncode == 0

        # Verify both unique issues exist + LWW winner on contested record.
        storage = _verify_jsonl_integrity(repo)
        assert storage.get("test-m1") is not None
        assert storage.get("test-f1") is not None
        shared = storage.get("test-shared")
        assert shared is not None
        _assert_lww_winner(shared, feature_view, main_view)


class TestComplexRebaseScenarios:
    """Complex rebase scenarios with multiple branches."""

    def test_rebase_with_multiple_branches(self, git_repo: GitRepo) -> None:
        """Test rebasing a feature branch that's based on another feature branch.

        Verifies nested rebases work correctly.
        """
        repo = git_repo
        _install_merge_driver(repo)

        # Create base
        s = repo.storage()
        s.create(Issue(id="base", namespace="test", title="Base"))
        repo.commit_all("Create base")

        # Feature1 branch
        repo.create_branch("feature1")
        _create_issue_on_branch(repo, "feature1", "f1", "Feature 1")

        # Feature2 branch based on feature1
        repo.create_branch("feature2")
        _create_issue_on_branch(repo, "feature2", "f2", "Feature 2")

        # Main diverges
        repo.switch_branch("main")
        _create_issue_on_branch(repo, "main", "m1", "Main divergence")

        # Rebase feature2 onto main (which rebases feature1 first)
        repo.switch_branch("feature2")
        result = repo.git("rebase", "main", check=False)

        assert result.returncode == 0

        # Verify all issues exist
        storage = _verify_jsonl_integrity(repo)
        assert storage.get("test-base") is not None
        assert storage.get("test-f1") is not None
        assert storage.get("test-f2") is not None
        assert storage.get("test-m1") is not None

    def test_rebase_with_merge_commits(self, git_repo: GitRepo) -> None:
        """Test rebasing a branch that contains a merge commit.

        Verify merge commits in the history are handled correctly.
        """
        repo = git_repo
        _install_merge_driver(repo)

        # Base
        s = repo.storage()
        s.create(Issue(id="base", namespace="test", title="Base"))
        repo.commit_all("Create base")

        # Create and merge a feature branch
        repo.create_branch("merge_feature")
        _create_issue_on_branch(repo, "merge_feature", "mf1", "Merge Feature")
        repo.switch_branch("main")
        repo.merge("merge_feature")

        # Create another branch with the merge commit in history
        repo.create_branch("feature")
        _create_issue_on_branch(repo, "feature", "f1", "Feature")

        # Main diverges
        repo.switch_branch("main")
        _create_issue_on_branch(repo, "main", "m1", "Main after merge")

        # Rebase feature (which includes the earlier merge in its history)
        repo.switch_branch("feature")
        result = repo.git("rebase", "main", check=False)

        assert result.returncode == 0

        # Verify integrity
        storage = _verify_jsonl_integrity(repo)
        assert storage.get("test-base") is not None
        assert storage.get("test-mf1") is not None
        assert storage.get("test-f1") is not None
        assert storage.get("test-m1") is not None
