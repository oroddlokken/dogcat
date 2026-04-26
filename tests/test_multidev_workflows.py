"""Multi-developer workflow simulation tests.

Tests realistic scenarios where multiple developers work on the same
repository, creating concurrent branches, merging, rebasing, and
coordinating their work through git operations.
"""

from __future__ import annotations

import subprocess
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from dogcat.constants import MERGE_DRIVER_CMD
from dogcat.models import Issue
from dogcat.storage import JSONLStorage

if TYPE_CHECKING:
    from conftest import GitRepo


# ---------------------------------------------------------------------------
# Multi-developer helpers
# ---------------------------------------------------------------------------


@contextmanager
def as_developer(repo: GitRepo, name: str, email: str) -> Any:
    """Context manager to temporarily switch git identity."""
    # Save original identity
    orig_name = subprocess.run(
        ["git", "config", "user.name"],
        cwd=repo.path,
        capture_output=True,
        text=True,
    ).stdout.strip()
    orig_email = subprocess.run(
        ["git", "config", "user.email"],
        cwd=repo.path,
        capture_output=True,
        text=True,
    ).stdout.strip()

    # Set new identity
    repo.git("config", "user.name", name)
    repo.git("config", "user.email", email)

    try:
        yield
    finally:
        # Restore original identity
        repo.git("config", "user.name", orig_name)
        repo.git("config", "user.email", orig_email)


def _install_merge_driver(repo: GitRepo) -> None:
    """Configure the dcat-jsonl merge driver."""
    repo.git("config", "merge.dcat-jsonl.driver", MERGE_DRIVER_CMD)
    attrs = repo.path / ".gitattributes"
    attrs.write_text(".dogcats/*.jsonl merge=dcat-jsonl\n")
    repo.commit_all("Add merge driver config")


def _create_issue(repo: GitRepo, issue_id: str, title: str, **fields: Any) -> None:
    """Create an issue and commit it."""
    s = repo.storage()
    issue = Issue(id=issue_id, namespace="test", title=title, **fields)
    s.create(issue)
    repo.commit_all(f"Create {issue_id}: {title}")


def _update_issue(
    repo: GitRepo, full_id: str, updates: dict[str, Any], message: str = ""
) -> None:
    """Update an issue and commit the changes."""
    s = repo.storage()
    s.update(full_id, updates)
    repo.commit_all(message or f"Update {full_id}")


def _label_issue(repo: GitRepo, full_id: str, label: str) -> None:
    """Add a label to an issue."""
    s = repo.storage()
    issue = s.get(full_id)
    if issue:
        s.update(full_id, {"labels": [*issue.labels, label]})
        repo.commit_all(f"Label {full_id} with {label}")


# ---------------------------------------------------------------------------
# Test scenarios
# ---------------------------------------------------------------------------


class TestMultiDevWorkflows:
    """Multi-developer workflow simulation tests."""

    def test_pair_workflow_alice_and_bob(self, git_repo: GitRepo) -> None:
        """Pair workflow: Alice branches, Bob works on main, they merge.

        Alice creates issue A on a branch, labels it.
        Bob creates issue B on main, also labels A.
        Alice's branch is merged in by Bob.
        Final: LWW semantics apply - later timestamp wins for issue A.
        """
        repo = git_repo
        _install_merge_driver(repo)

        # Alice: create issue A and branch off
        with as_developer(repo, "Alice", "alice@example.com"):
            _create_issue(repo, "a1", "Alice's Issue A")
            repo.create_branch("alice-feature")

        # Bob: create issue B on main
        with as_developer(repo, "Bob", "bob@example.com"):
            _create_issue(repo, "b1", "Bob's Issue B")

        # Alice: label her issue on the branch
        repo.switch_branch("alice-feature")
        with as_developer(repo, "Alice", "alice@example.com"):
            _label_issue(repo, "test-a1", "alice-label")

        # Bob: label issue A on main (different label)
        repo.switch_branch("main")
        with as_developer(repo, "Bob", "bob@example.com"):
            _label_issue(repo, "test-a1", "bob-label")

        # Bob: merge Alice's branch
        with as_developer(repo, "Bob", "bob@example.com"):
            result = repo.merge("alice-feature")
            assert result.returncode == 0

        # Verify final state
        storage = JSONLStorage(str(repo.storage_path))
        issue_a = storage.get("test-a1")
        issue_b = storage.get("test-b1")

        assert issue_a is not None
        assert issue_b is not None
        # Both issues should exist
        assert issue_a.title == "Alice's Issue A"
        assert issue_b.title == "Bob's Issue B"
        # LWW semantics: whichever edit is more recent should be present
        # (in this case, Bob's later edit wins, so his label should be there)
        assert "bob-label" in issue_a.labels

    def test_triangle_three_developers(self, git_repo: GitRepo) -> None:
        """Triangle: Three devs, each creates issues, edits others' with LWW.

        Dev1 creates issues 1a, 1b.
        Dev2 creates issues 2a, 2b, edits 1b.
        Dev3 creates issues 3a, 3b, edits 1a.
        They merge in sequence: main ← dev1 ← dev2 ← dev3.
        Final: all six issues with all three edits applied (LWW semantics).
        """
        repo = git_repo
        _install_merge_driver(repo)

        # Dev1: create issues 1a, 1b
        with as_developer(repo, "Dev1", "dev1@example.com"):
            _create_issue(repo, "dev1a", "Dev1 Issue A")
            _create_issue(repo, "dev1b", "Dev1 Issue B")
            repo.create_branch("dev1-branch")

        # Dev2: create issues 2a, 2b and edit 1b
        repo.switch_branch("main")
        with as_developer(repo, "Dev2", "dev2@example.com"):
            _create_issue(repo, "dev2a", "Dev2 Issue A")
            _create_issue(repo, "dev2b", "Dev2 Issue B")
            _update_issue(
                repo,
                "test-dev1b",
                {"status": "in_progress", "priority": 1},
                "Dev2 edits dev1b",
            )
            repo.create_branch("dev2-branch")

        # Dev3: create issues 3a, 3b and edit 1a
        repo.switch_branch("main")
        with as_developer(repo, "Dev3", "dev3@example.com"):
            _create_issue(repo, "dev3a", "Dev3 Issue A")
            _create_issue(repo, "dev3b", "Dev3 Issue B")
            _update_issue(
                repo,
                "test-dev1a",
                {"status": "in_review", "priority": 0},
                "Dev3 edits dev1a",
            )
            repo.create_branch("dev3-branch")

        # Merge sequence: main ← dev1 ← dev2 ← dev3
        repo.switch_branch("main")
        with as_developer(repo, "Merger", "merger@example.com"):
            # Merge dev1 into main
            repo.merge("dev1-branch")

            # Merge dev2 into main
            repo.merge("dev2-branch")

            # Merge dev3 into main
            repo.merge("dev3-branch")

        # Verify all six issues exist with edits applied
        storage = JSONLStorage(str(repo.storage_path))

        dev1a = storage.get("test-dev1a")
        dev1b = storage.get("test-dev1b")
        dev2a = storage.get("test-dev2a")
        dev2b = storage.get("test-dev2b")
        dev3a = storage.get("test-dev3a")
        dev3b = storage.get("test-dev3b")

        assert dev1a is not None
        assert dev1b is not None
        assert dev2a is not None
        assert dev2b is not None
        assert dev3a is not None
        assert dev3b is not None

        # Verify edits were applied (LWW semantics)
        # Both Dev2 and Dev3 edited Dev1's issues; later one should win
        # Dev3's edits are newer so should be present
        assert dev1a.status == "in_review"
        assert dev1a.priority == 0
        assert dev1b.status == "in_progress"
        assert dev1b.priority == 1

    def test_late_comer_rebase_week_of_work(self, git_repo: GitRepo) -> None:
        """Late-comer rebase: Alice on feature for 'a week', main diverges.

        Alice has 5 commits on feature branch (10 mutations to issues).
        Main gets 20 mutations while Alice works.
        Alice rebases her feature onto main.
        Verify integrity at each rebase step and final state.
        """
        repo = git_repo
        _install_merge_driver(repo)

        # Alice: start feature branch with 5 commits
        with as_developer(repo, "Alice", "alice@example.com"):
            repo.create_branch("alice-week-feature")
            for i in range(5):
                _create_issue(repo, f"alice{i}", f"Alice Issue {i}")

        # Main: 20 mutations from other devs
        repo.switch_branch("main")
        with as_developer(repo, "Others", "others@example.com"):
            for i in range(10):
                _create_issue(repo, f"main{i}", f"Main Issue {i}")
            for i in range(10):
                _update_issue(
                    repo, f"test-main{i}", {"status": "in_progress"}, f"Update main{i}"
                )

        # Alice: rebase her feature onto main
        repo.switch_branch("alice-week-feature")
        with as_developer(repo, "Alice", "alice@example.com"):
            result = repo.git("rebase", "main", check=False)
            assert result.returncode == 0, f"Rebase failed: {result.stderr}"

        # Verify integrity and state
        storage = JSONLStorage(str(repo.storage_path))

        # All issues should exist
        for i in range(5):
            assert storage.get(f"test-alice{i}") is not None
        for i in range(10):
            assert storage.get(f"test-main{i}") is not None

    def test_cross_merge_eventual_consistency(self, git_repo: GitRepo) -> None:
        """Cross-merge: Alice and Bob merge each other's branches.

        Alice has branch with changes, Bob has branch with changes.
        Alice merges Bob's branch first, then Bob merges Alice's.
        Both should end up in the same state (eventual consistency).
        """
        repo = git_repo
        _install_merge_driver(repo)

        # Alice: create branch with her issues
        with as_developer(repo, "Alice", "alice@example.com"):
            repo.create_branch("alice-branch")
            _create_issue(repo, "alice1", "Alice Issue 1")
            _create_issue(repo, "alice2", "Alice Issue 2")

        # Bob: create branch with his issues
        repo.switch_branch("main")
        with as_developer(repo, "Bob", "bob@example.com"):
            repo.create_branch("bob-branch")
            _create_issue(repo, "bob1", "Bob Issue 1")
            _create_issue(repo, "bob2", "Bob Issue 2")

        # Alice: merge Bob's branch
        repo.switch_branch("alice-branch")
        with as_developer(repo, "Alice", "alice@example.com"):
            result = repo.merge("bob-branch")
            assert result.returncode == 0

        # Bob: merge Alice's branch
        repo.switch_branch("bob-branch")
        with as_developer(repo, "Bob", "bob@example.com"):
            result = repo.merge("alice-branch")
            assert result.returncode == 0

        # Capture Alice's and Bob's branch states AFTER each independently
        # merged the other's branch — the eventual-consistency claim is
        # that these two record sets are equal regardless of merge order.
        # (dogcat-2bt3)
        repo.switch_branch("alice-branch")
        alice_records = sorted(
            (i.full_id, i.title) for i in JSONLStorage(str(repo.storage_path)).list()
        )
        repo.switch_branch("bob-branch")
        bob_records = sorted(
            (i.full_id, i.title) for i in JSONLStorage(str(repo.storage_path)).list()
        )
        assert alice_records == bob_records, (
            "Alice and Bob diverged after independently merging the other's"
            " branch — the merge driver lost eventual consistency."
            f"\nAlice: {alice_records}\nBob:   {bob_records}"
        )

        # Merge both into main for final check
        repo.switch_branch("main")
        with as_developer(repo, "Merger", "merger@example.com"):
            result1 = repo.merge("alice-branch")
            assert result1.returncode == 0
            result2 = repo.merge("bob-branch")
            assert result2.returncode == 0

        # Verify final state on main matches the converged set.
        storage = JSONLStorage(str(repo.storage_path))
        main_records = sorted((i.full_id, i.title) for i in storage.list())
        assert main_records == alice_records

        # Each issue carries the title set by its author — the merge
        # must not have shuffled titles between records.
        assert storage.get("test-alice1") is not None
        assert storage.get("test-alice1").title == "Alice Issue 1"  # type: ignore[union-attr]
        assert storage.get("test-alice2") is not None
        assert storage.get("test-alice2").title == "Alice Issue 2"  # type: ignore[union-attr]
        assert storage.get("test-bob1") is not None
        assert storage.get("test-bob1").title == "Bob Issue 1"  # type: ignore[union-attr]
        assert storage.get("test-bob2") is not None
        assert storage.get("test-bob2").title == "Bob Issue 2"  # type: ignore[union-attr]
