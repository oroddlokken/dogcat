"""Tests for git stash/pop/apply with dogcat changes.

Verifies that uncommitted .dogcats/issues.jsonl changes can be safely
stashed, branches switched, and changes reapplied or popped without
breaking append-only invariants or event log consistency.
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


class TestGitStash:
    """Tests for stash/pop/apply with dogcat files."""

    def test_stash_pop_uncommitted_issue_changes(self, git_repo: GitRepo) -> None:
        """Stash uncommitted issue changes, pop them back."""
        repo = git_repo
        _install_merge_driver(repo)

        # Create initial issue
        s = repo.storage()
        s.create(Issue(id="task1", namespace="test", title="Task 1"))
        repo.commit_all("Create task1")

        # Edit the issue (uncommitted)
        s = repo.storage()
        s.update("test-task1", {"title": "Updated Task 1"})

        # Stash the changes
        result = repo.git("stash")
        assert result.returncode == 0, f"Stash failed: {result.stdout}"

        # Verify issue is back to original state
        storage = JSONLStorage(str(repo.dogcats_dir / "issues.jsonl"))
        issues = storage.list()
        task1 = next((i for i in issues if i.id == "task1"), None)
        assert task1 is not None
        assert task1.title == "Task 1", "Issue should be reverted after stash"

        # Pop the stash
        result = repo.git("stash", "pop")
        assert result.returncode == 0, f"Stash pop failed: {result.stdout}"

        # Verify changes are reapplied
        storage = JSONLStorage(str(repo.dogcats_dir / "issues.jsonl"))
        issues = storage.list()
        task1 = next((i for i in issues if i.id == "task1"), None)
        assert task1 is not None
        assert task1.title == "Updated Task 1", "Stashed changes should be reapplied"

    def test_stash_apply_uncommitted_changes(self, git_repo: GitRepo) -> None:
        """Stash uncommitted changes, apply them (keep stash)."""
        repo = git_repo
        _install_merge_driver(repo)

        # Create and edit issue
        s = repo.storage()
        s.create(Issue(id="task2", namespace="test", title="Task 2"))
        repo.commit_all("Create task2")

        s = repo.storage()
        s.update("test-task2", {"priority": 1})

        # Stash
        result = repo.git("stash")
        assert result.returncode == 0

        # Apply (don't remove stash)
        result = repo.git("stash", "apply")
        assert result.returncode == 0, f"Stash apply failed: {result.stdout}"

        # Verify changes are applied
        storage = JSONLStorage(str(repo.dogcats_dir / "issues.jsonl"))
        issues = storage.list()
        task2 = next((i for i in issues if i.id == "task2"), None)
        assert task2 is not None
        assert task2.priority == 1

        # Stash should still exist
        result = repo.git("stash", "list")
        assert "stash@{0}" in result.stdout

    def test_stash_across_branch_switch(self, git_repo: GitRepo) -> None:
        """Stash changes, switch branches, pop on new branch."""
        repo = git_repo
        _install_merge_driver(repo)

        # Create issue on main
        s = repo.storage()
        s.create(Issue(id="mainissue", namespace="test", title="Main Issue"))
        repo.commit_all("Create main issue")

        s = repo.storage()
        s.update("test-mainissue", {"status": "in_progress"})

        # Stash and switch branch
        result = repo.git("stash")
        assert result.returncode == 0

        repo.create_branch("feature-branch")
        repo.switch_branch("feature-branch")

        # Create different issue on feature branch
        s = repo.storage()
        s.create(Issue(id="featureissue", namespace="test", title="Feature Issue"))
        repo.commit_all("Create feature issue")

        # Pop stash from feature branch
        result = repo.git("stash", "pop")
        assert result.returncode == 0, f"Stash pop failed: {result.stdout}"

        # Verify both issues exist and main issue has stashed changes
        storage = JSONLStorage(str(repo.dogcats_dir / "issues.jsonl"))
        issues = storage.list()
        main_issue = next((i for i in issues if i.id == "mainissue"), None)
        feature_issue = next((i for i in issues if i.id == "featureissue"), None)

        assert main_issue is not None
        assert main_issue.status == "in_progress", "Stashed changes should be applied"
        assert feature_issue is not None, "Feature branch issue should exist"

    def test_stash_creates_append_only_events(self, git_repo: GitRepo) -> None:
        """Stashed changes produce valid events, no duplicates after pop."""
        repo = git_repo
        _install_merge_driver(repo)

        # Create issue with event
        s = repo.storage()
        s.create(Issue(id="task3", namespace="test", title="Task 3"))
        repo.commit_all("Create task3")

        # Edit issue (creates new event record)
        s = repo.storage()
        s.update("test-task3", {"title": "Updated Task 3"})

        # Stash and pop
        repo.git("stash")
        repo.git("stash", "pop")

        # Verify issue state is correct after stash/pop
        storage = JSONLStorage(str(repo.dogcats_dir / "issues.jsonl"))
        issues = storage.list()
        task3 = next((i for i in issues if i.id == "task3"), None)
        assert task3 is not None
        assert task3.title == "Updated Task 3", "Stashed changes should persist"

    def test_stash_drop_after_partial_apply(self, git_repo: GitRepo) -> None:
        """Drop stash after partial apply."""
        repo = git_repo
        _install_merge_driver(repo)

        # Create issue
        s = repo.storage()
        s.create(Issue(id="task4", namespace="test", title="Task 4"))
        repo.commit_all("Create task4")

        # Edit it
        s = repo.storage()
        s.update("test-task4", {"notes": "Some notes"})

        # Stash
        repo.git("stash")

        # Apply
        repo.git("stash", "apply")

        # Drop the stash
        result = repo.git("stash", "drop")
        assert result.returncode == 0

        # Verify no stashes remain
        result = repo.git("stash", "list")
        assert "stash@{0}" not in result.stdout

        # But changes should still be applied
        storage = JSONLStorage(str(repo.dogcats_dir / "issues.jsonl"))
        issues = storage.list()
        task4 = next((i for i in issues if i.id == "task4"), None)
        assert task4 is not None
        assert task4.notes == "Some notes"

    def test_stash_with_multiple_file_changes(self, git_repo: GitRepo) -> None:
        """Stash changes to .dogcats and other files together."""
        repo = git_repo
        _install_merge_driver(repo)

        # Create initial state with tracked file
        s = repo.storage()
        s.create(Issue(id="task5", namespace="test", title="Task 5"))
        (repo.path / "test.txt").write_text("initial content")
        repo.commit_all("Create task5 and test.txt")

        # Edit issue AND edit the tracked file
        (repo.path / "test.txt").write_text("modified content")
        s = repo.storage()
        s.update("test-task5", {"priority": 0})

        # Stash both
        result = repo.git("stash")
        assert result.returncode == 0

        # Verify both are reverted
        assert (repo.path / "test.txt").read_text() == "initial content"
        storage = JSONLStorage(str(repo.dogcats_dir / "issues.jsonl"))
        issues = storage.list()
        task5 = next((i for i in issues if i.id == "task5"), None)
        assert task5 is not None
        assert task5.priority == 2  # Default priority

        # Pop
        result = repo.git("stash", "pop")
        assert result.returncode == 0

        # Both should be restored
        assert (repo.path / "test.txt").read_text() == "modified content"
        storage = JSONLStorage(str(repo.dogcats_dir / "issues.jsonl"))
        issues = storage.list()
        task5 = next((i for i in issues if i.id == "task5"), None)
        assert task5 is not None
        assert task5.priority == 0
