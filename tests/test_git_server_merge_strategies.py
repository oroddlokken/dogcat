"""Tests for GitHub server-side merge strategies with dogcat.

Tests the merge driver behavior when using GitHub's merge strategies:
- Squash and merge
- Rebase and merge
- Create a merge commit
- Update branch (fast-forward)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dogcat.constants import MERGE_DRIVER_CMD
from dogcat.models import Issue
from dogcat.storage import JSONLStorage

if TYPE_CHECKING:
    from conftest import GitRepo


def _install_merge_driver(repo: GitRepo) -> None:
    """Configure the dcat-jsonl merge driver in a git repo."""
    repo.git("config", "merge.dcat-jsonl.driver", MERGE_DRIVER_CMD)
    attrs = repo.path / ".gitattributes"
    attrs.write_text(".dogcats/*.jsonl merge=dcat-jsonl\n")
    repo.commit_all("Add merge driver config")


class TestGitHubMergeStrategies:
    """Tests for GitHub server-side merge strategies."""

    def test_squash_and_merge_strategy(self, git_repo: GitRepo) -> None:
        """Simulate GitHub 'squash and merge' strategy."""
        repo = git_repo
        _install_merge_driver(repo)

        # Create initial commit
        s = repo.storage()
        s.create(Issue(id="pr1", namespace="test", title="PR Issue 1"))
        repo.commit_all("Create PR issue")

        # Create feature branch with multiple commits
        repo.create_branch("feature-branch")
        s = repo.storage()
        s.create(Issue(id="feat1", namespace="test", title="Feature 1"))
        repo.commit_all("Add feature 1")

        s = repo.storage()
        s.update("test-feat1", {"description": "Feature 1 updated"})
        repo.commit_all("Update feature 1")

        # Squash commits
        repo.switch_branch("main")
        result = repo.git("merge", "--squash", "feature-branch")
        assert result.returncode == 0

        # This creates a squashed commit
        result = repo.git("commit", "-m", "Squash merge feature-branch")
        assert result.returncode == 0

        # Verify both issues exist
        storage = JSONLStorage(str(repo.dogcats_dir / "issues.jsonl"))
        issues = storage.list()
        issue_ids = {i.id for i in issues}
        assert "pr1" in issue_ids
        assert "feat1" in issue_ids

    def test_rebase_and_merge_strategy(self, git_repo: GitRepo) -> None:
        """Simulate GitHub 'rebase and merge' strategy."""
        repo = git_repo
        _install_merge_driver(repo)

        # Create initial commit
        s = repo.storage()
        s.create(Issue(id="base1", namespace="test", title="Base Issue 1"))
        repo.commit_all("Create base issue")

        # Create feature branch
        repo.create_branch("rebase-feature")
        s = repo.storage()
        s.create(Issue(id="rebase1", namespace="test", title="Rebase Issue 1"))
        repo.commit_all("Create rebase issue")

        # Rebase onto main
        repo.switch_branch("main")
        result = repo.git("rebase", "rebase-feature")
        assert result.returncode == 0

        # Verify all issues exist
        storage = JSONLStorage(str(repo.dogcats_dir / "issues.jsonl"))
        issues = storage.list()
        issue_ids = {i.id for i in issues}
        assert "base1" in issue_ids
        assert "rebase1" in issue_ids

    def test_create_merge_commit_strategy(self, git_repo: GitRepo) -> None:
        """Simulate GitHub 'create a merge commit' strategy (--no-ff)."""
        repo = git_repo
        _install_merge_driver(repo)

        # Create initial issue
        s = repo.storage()
        s.create(Issue(id="main1", namespace="test", title="Main Issue 1"))
        repo.commit_all("Create main issue")

        # Create and update feature branch
        repo.create_branch("merge-feature")
        s = repo.storage()
        s.create(Issue(id="merge1", namespace="test", title="Merge Issue 1"))
        repo.commit_all("Create merge issue")

        # Force merge commit (no fast-forward)
        repo.switch_branch("main")
        result = repo.git(
            "merge", "--no-ff", "-m", "Merge merge-feature", "merge-feature"
        )
        assert result.returncode == 0

        # Verify merge commit was created
        result = repo.git("log", "--oneline", "-n", "2")
        assert "Merge merge-feature" in result.stdout

        # Verify all issues exist
        storage = JSONLStorage(str(repo.dogcats_dir / "issues.jsonl"))
        issues = storage.list()
        issue_ids = {i.id for i in issues}
        assert "main1" in issue_ids
        assert "merge1" in issue_ids

    def test_fast_forward_merge(self, git_repo: GitRepo) -> None:
        """Test fast-forward merge (simulates 'update branch')."""
        repo = git_repo
        _install_merge_driver(repo)

        # Create initial commit
        s = repo.storage()
        s.create(Issue(id="ff1", namespace="test", title="FF Issue 1"))
        repo.commit_all("Create FF issue")

        # Create feature branch ahead of main
        repo.create_branch("ff-feature")
        s = repo.storage()
        s.create(Issue(id="ff2", namespace="test", title="FF Issue 2"))
        repo.commit_all("Create FF issue 2")

        # Fast-forward merge (ff-feature is ahead)
        repo.switch_branch("main")
        result = repo.git("merge", "--ff-only", "ff-feature")
        assert result.returncode == 0

        # Verify fast-forward happened (main is now at ff-feature tip)
        result = repo.git("rev-parse", "HEAD")
        main_sha = result.stdout.strip()

        result = repo.git("rev-parse", "ff-feature")
        ff_sha = result.stdout.strip()

        assert main_sha == ff_sha, "Fast-forward should update main to ff-feature tip"

        # Verify both issues exist
        storage = JSONLStorage(str(repo.dogcats_dir / "issues.jsonl"))
        issues = storage.list()
        issue_ids = {i.id for i in issues}
        assert "ff1" in issue_ids
        assert "ff2" in issue_ids
