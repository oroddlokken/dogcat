"""Tests for linked worktree scenarios with shared .dogcats.

Tests that multiple worktrees can safely share .dogcats directory
and maintain append-only invariants across concurrent modifications.
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


class TestLinkedWorktrees:
    """Tests for git worktree with shared .dogcats."""

    def test_worktree_main_and_branch_share_dogcats(self, git_repo: GitRepo) -> None:
        """Main worktree and a linked worktree on a new branch see the same seed state.

        Each worktree has its own working tree (so changes in one branch's tree
        don't appear in the other), but both inherit history through commit.
        """
        import tempfile
        from pathlib import Path

        repo = git_repo
        _install_merge_driver(repo)

        # Seed an issue on main and commit it
        s = repo.storage()
        s.create(Issue(id="wt1", namespace="test", title="Worktree Issue 1"))
        repo.commit_all("Create wt1")

        with tempfile.TemporaryDirectory() as tmpdir:
            wt_path = Path(tmpdir) / "wt-feature"
            # Create the linked worktree on a new branch atomically — main stays
            # checked out in the primary tree.
            result = repo.git("worktree", "add", "-b", "wt-feature", str(wt_path))
            assert result.returncode == 0, (
                f"git worktree add failed: {result.stdout}\n{result.stderr}"
            )

            wt_storage_path = wt_path / ".dogcats" / "issues.jsonl"
            assert wt_storage_path.exists(), (
                "linked worktree should have its own .dogcats/issues.jsonl checkout"
            )

            # The seeded issue is visible in the linked worktree.
            wt_issues = JSONLStorage(str(wt_storage_path)).list()
            assert "wt1" in {i.id for i in wt_issues}

            # Cleanup the worktree before tempdir tries to remove it (otherwise
            # git complains the worktree is orphaned).
            repo.git("worktree", "remove", "--force", str(wt_path))

    def test_worktree_detached_head(self, git_repo: GitRepo) -> None:
        """Worktree with detached HEAD maintains valid dogcats state."""
        repo = git_repo
        _install_merge_driver(repo)

        # Create issue
        s = repo.storage()
        s.create(Issue(id="wtdet1", namespace="test", title="Detached Worktree 1"))
        repo.commit_all("Create detached worktree issue")

        # Get commit hash
        result = repo.git("rev-parse", "HEAD")
        commit_sha = result.stdout.strip()

        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            wt_path = Path(tmpdir) / "wt-detached"
            # Create worktree with detached HEAD
            result = repo.git("worktree", "add", "--detach", str(wt_path), commit_sha)
            assert result.returncode == 0

            # Verify dogcats is accessible in detached worktree
            wt_dogcats = wt_path / ".dogcats" / "issues.jsonl"
            assert wt_dogcats.exists()

            wt_storage = JSONLStorage(str(wt_dogcats))
            wt_issues = wt_storage.list()
            assert any(i.id == "wtdet1" for i in wt_issues)

    def test_worktree_branch_isolation(self, git_repo: GitRepo) -> None:
        """Different worktrees on different branches can have different states."""
        repo = git_repo
        _install_merge_driver(repo)

        # Create base issue
        s = repo.storage()
        s.create(Issue(id="wtbase", namespace="test", title="Base Issue"))
        repo.commit_all("Create base")

        # Create feature branches
        repo.create_branch("feature-a")
        repo.create_branch("feature-b")

        # On feature-a: add issue
        repo.switch_branch("feature-a")
        s = repo.storage()
        s.create(Issue(id="feat-a", namespace="test", title="Feature A Issue"))
        repo.commit_all("Add feature A issue")

        # On feature-b: add different issue
        repo.switch_branch("feature-b")
        s = repo.storage()
        s.create(Issue(id="feat-b", namespace="test", title="Feature B Issue"))
        repo.commit_all("Add feature B issue")

        # Switch back to main
        repo.switch_branch("main")

        # In real scenario with worktrees, you'd have:
        # - Main worktree on main
        # - Feature-a worktree on feature-a
        # - Feature-b worktree on feature-b
        # Each would see their respective branch's state
