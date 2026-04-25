"""Tests for force-push recovery scenarios with dogcat.

Tests recovery workflows when collaborators force-push rebased branches,
simulating common team workflows where branches are rebased before merging.
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


class TestForcePushRecovery:
    """Tests for recovering from force-pushed branches."""

    def test_collaborator_rebase_force_push(self, git_repo: GitRepo) -> None:
        """Collaborator rebases branch and force-pushes it."""
        repo = git_repo
        _install_merge_driver(repo)

        # Create initial commit
        s = repo.storage()
        s.create(Issue(id="collab1", namespace="test", title="Collab Issue 1"))
        repo.commit_all("Create collab issue")

        # Create branch and make changes
        repo.create_branch("collab-branch")
        s = repo.storage()
        s.create(Issue(id="collab2", namespace="test", title="Collab Issue 2"))
        repo.commit_all("Add collab issue 2")

        # Simulate rebasing the branch (squash commits)
        result = repo.git("rebase", "-i", "main~0")
        # Note: Interactive rebase would need user input, but we can simulate with reset
        # Instead, just create a clean squash
        repo.git("reset", "--soft", "main")
        s = repo.storage()
        s.update("test-collab2", {"priority": 1})
        repo.commit_all("Rebase collab-branch")

        # Go back to main and verify we can still merge
        repo.switch_branch("main")
        result = repo.git("merge", "collab-branch")
        # With merge driver, this should work
        assert result.returncode == 0

        # Verify both issues are present
        storage = JSONLStorage(str(repo.dogcats_dir / "issues.jsonl"))
        issues = storage.list()
        issue_ids = {i.id for i in issues}
        assert "collab1" in issue_ids
        assert "collab2" in issue_ids

    def test_pull_rebase_recovery(self, git_repo: GitRepo) -> None:
        """Pull with rebase when branch has been updated remotely."""
        repo = git_repo
        _install_merge_driver(repo)

        # Create initial commits
        s = repo.storage()
        s.create(Issue(id="pull1", namespace="test", title="Pull Issue 1"))
        repo.commit_all("Create pull issue 1")

        # Create branch
        repo.create_branch("pull-branch")
        s = repo.storage()
        s.create(Issue(id="pull2", namespace="test", title="Pull Issue 2"))
        repo.commit_all("Create pull issue 2")

        # Back on main, make another commit
        repo.switch_branch("main")
        s = repo.storage()
        s.create(Issue(id="pull3", namespace="test", title="Pull Issue 3"))
        repo.commit_all("Create pull issue 3")

        # Simulate pull with rebase on the branch
        repo.switch_branch("pull-branch")
        result = repo.git("rebase", "main")
        assert result.returncode == 0

        # Verify state is correct
        storage = JSONLStorage(str(repo.dogcats_dir / "issues.jsonl"))
        issues = storage.list()
        issue_ids = {i.id for i in issues}
        # Should have all issues from both branches
        assert "pull1" in issue_ids
        assert "pull2" in issue_ids
        assert "pull3" in issue_ids

    def test_merge_after_forced_rebase(self, git_repo: GitRepo) -> None:
        """Merge branch that was forcefully rebased on top of main."""
        repo = git_repo
        _install_merge_driver(repo)

        # Create main with multiple commits
        s = repo.storage()
        s.create(Issue(id="fb1", namespace="test", title="FB Issue 1"))
        repo.commit_all("Commit 1")

        s = repo.storage()
        s.update("test-fb1", {"priority": 1})
        repo.commit_all("Commit 2")

        # Create feature branch
        repo.create_branch("feature")
        s = repo.storage()
        s.create(Issue(id="fb2", namespace="test", title="FB Issue 2"))
        repo.commit_all("Feature commit 1")

        # Back to main, make more changes
        repo.switch_branch("main")
        s = repo.storage()
        s.create(Issue(id="fb3", namespace="test", title="FB Issue 3"))
        repo.commit_all("Main commit 3")

        # Now rebase feature on updated main
        repo.switch_branch("feature")
        result = repo.git("rebase", "main")
        assert result.returncode == 0

        # Merge back to main
        repo.switch_branch("main")
        result = repo.git("merge", "feature")
        assert result.returncode == 0

        # Verify final state
        storage = JSONLStorage(str(repo.dogcats_dir / "issues.jsonl"))
        issues = storage.list()
        issue_ids = {i.id for i in issues}
        assert "fb1" in issue_ids
        assert "fb2" in issue_ids
        assert "fb3" in issue_ids
