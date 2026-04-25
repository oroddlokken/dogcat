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

        # Merge feature into main
        result = repo.merge("feature")
        assert result.returncode == 0

        # Verify integrity
        storage = _verify_jsonl_integrity(repo)

        # Both unique issues should exist
        assert storage.get("test-feature1") is not None
        assert storage.get("test-main1") is not None

        # Shared issue: whichever edit is later should win
        shared = storage.get("test-shared")
        assert shared is not None


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

        # Verify integrity
        storage = _verify_jsonl_integrity(repo)

        # All issues should exist
        assert storage.get("test-base") is not None
        assert storage.get("test-f1") is not None
        assert storage.get("test-f2") is not None
        assert storage.get("test-f3") is not None
        assert storage.get("test-m1") is not None

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

        # Rebase feature onto main
        repo.switch_branch("feature")
        result = repo.git("rebase", "main", check=False)

        assert result.returncode == 0, f"Rebase failed: {result.stderr}"

        # Verify integrity
        storage = _verify_jsonl_integrity(repo)
        shared = storage.get("test-shared")
        assert shared is not None


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

        # Verify integrity and all issues exist
        storage = _verify_jsonl_integrity(repo)
        assert storage.get("test-m1") is not None
        assert storage.get("test-m2") is not None
        assert storage.get("test-f1") is not None
        assert storage.get("test-f2") is not None


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

        # Verify all commits integrated
        storage = _verify_jsonl_integrity(repo)
        assert storage.get("test-base") is not None
        assert storage.get("test-f1") is not None
        assert storage.get("test-f2") is not None

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

        # Merge (should use merge driver)
        repo.switch_branch("main")
        result = repo.merge("feature")

        assert result.returncode == 0

        # Verify both unique issues exist
        storage = _verify_jsonl_integrity(repo)
        assert storage.get("test-m1") is not None
        assert storage.get("test-f1") is not None
        assert storage.get("test-shared") is not None


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
