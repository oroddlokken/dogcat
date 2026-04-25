"""Tests for git bisect with dogcat state changes.

Validates that the merge driver works correctly when using git bisect
with detached HEAD states and rapid checkout operations.
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


class TestGitBisect:
    """Tests for git bisect with dogcat state."""

    def test_bisect_detached_head_checkout(self, git_repo: GitRepo) -> None:
        """Git bisect creates detached HEAD and rapidly checks out commits."""
        repo = git_repo
        _install_merge_driver(repo)

        # Create initial issue
        s = repo.storage()
        s.create(Issue(id="bisect1", namespace="test", title="Bisect Test 1"))
        repo.commit_all("Create bisect1 - good")

        # Edit issue
        s = repo.storage()
        s.update("test-bisect1", {"priority": 1})
        repo.commit_all("Update priority")

        # Add another issue
        s = repo.storage()
        s.create(Issue(id="bisect2", namespace="test", title="Bisect Test 2"))
        repo.commit_all("Create bisect2 - bad")

        # Get commit hashes
        result = repo.git("log", "--oneline", "-n", "3")
        lines = result.stdout.strip().split("\n")
        bad_sha = lines[0].split()[0]
        good_sha = lines[2].split()[0]

        # Checkout the good commit (detached HEAD)
        result = repo.git("checkout", good_sha)
        assert result.returncode == 0

        # Verify we're in detached HEAD state
        result = repo.git("rev-parse", "--abbrev-ref", "HEAD")
        assert "HEAD" in result.stdout

        # Verify correct issue state at this commit
        storage = JSONLStorage(str(repo.dogcats_dir / "issues.jsonl"))
        issues = storage.list()
        bisect1 = next((i for i in issues if i.id == "bisect1"), None)
        assert bisect1 is not None
        assert bisect1.priority == 2  # Default, before the edit

        # Checkout bad commit
        result = repo.git("checkout", bad_sha)
        assert result.returncode == 0

        # Verify updated state
        storage = JSONLStorage(str(repo.dogcats_dir / "issues.jsonl"))
        issues = storage.list()
        bisect1 = next((i for i in issues if i.id == "bisect1"), None)
        bisect2 = next((i for i in issues if i.id == "bisect2"), None)
        assert bisect1 is not None
        assert bisect1.priority == 1  # After the edit
        assert bisect2 is not None  # Exists at this commit

        # Go back to main
        repo.switch_branch("main")

    def test_rapid_checkout_operations(self, git_repo: GitRepo) -> None:
        """Rapid checkout operations maintain valid JSONL state."""
        repo = git_repo
        _install_merge_driver(repo)

        # Create a chain of commits with issue modifications
        for i in range(5):
            s = repo.storage()
            s.create(Issue(id=f"rapid{i}", namespace="test", title=f"Rapid Test {i}"))
            repo.commit_all(f"Create rapid{i}")

        # Get commit hashes
        result = repo.git("log", "--oneline", "-n", "10")
        commits = [line.split()[0] for line in result.stdout.strip().split("\n")]

        # Rapidly checkout different commits
        for sha in commits[:4]:
            result = repo.git("checkout", sha)
            assert result.returncode == 0

            # Verify JSONL is always valid
            storage = JSONLStorage(str(repo.dogcats_dir / "issues.jsonl"))
            issues = storage.list()
            # Should have committed count at this point
            assert len(issues) <= 5

        # Back to main
        repo.switch_branch("main")
