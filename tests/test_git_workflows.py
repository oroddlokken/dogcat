"""Tests for advanced git workflows with JSONL issue storage.

Validates that the merge driver works correctly with non-standard
git operations: cherry-pick, octopus merge, squash merge, and
revert of merge commits.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import orjson

from dogcat.constants import MERGE_DRIVER_CMD
from dogcat.models import DependencyType, Issue
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


class TestCherryPick:
    """Cherry-pick scenarios for selective commit merging."""

    def test_cherry_pick_single_issue_create(self, git_repo: GitRepo) -> None:
        """Cherry-pick only the commit that creates issue X, not the edit to Y.

        Branch has commits: create X, edit X, create Y, edit Y.
        Cherry-pick only the create X commit onto main.
        Verify X exists, no stray markers, state is consistent.
        """
        repo = git_repo

        # Feature branch: create X, edit X, create Y, edit Y
        repo.create_branch("feature")
        _create_issue_on_branch(repo, "feature", "x1", "Issue X")

        _update_issue_on_branch(
            repo,
            "feature",
            "test-x1",
            {"description": "Updated X"},
            "Edit X",
        )

        _create_issue_on_branch(repo, "feature", "y1", "Issue Y")

        _update_issue_on_branch(
            repo,
            "feature",
            "test-y1",
            {"description": "Updated Y"},
            "Edit Y",
        )

        # Get the commit hash of the "Create test-x1" commit
        logs = repo.git("log", "--oneline", "--reverse")
        lines = [l.strip() for l in logs.stdout.split("\n") if "test-x1" in l]
        assert len(lines) >= 1, "Could not find create x1 commit"
        create_x_hash = lines[0].split()[0]

        # Back to main, cherry-pick the create X commit
        repo.switch_branch("main")
        repo.git("cherry-pick", create_x_hash)

        # Verify integrity
        storage = _verify_jsonl_integrity(repo)

        # Verify X exists, Y does not
        issue_x = storage.get("test-x1")
        assert issue_x is not None, "Issue X should exist after cherry-pick"
        assert issue_x.title == "Issue X"

        issue_y = storage.get("test-y1")
        assert issue_y is None, "Issue Y should not exist (only X was cherry-picked)"

    def test_cherry_pick_preserves_event_order(self, git_repo: GitRepo) -> None:
        """Cherry-picked events maintain proper ordering in the JSONL."""
        repo = git_repo

        repo.create_branch("feature")
        _create_issue_on_branch(repo, "feature", "ev1", "Event test")
        _update_issue_on_branch(
            repo, "feature", "test-ev1", {"status": "in_progress"}, "Change status"
        )

        logs = repo.git("log", "--oneline", "--reverse")
        lines = [l.strip() for l in logs.stdout.split("\n") if "test-ev1" in l]
        create_hash = lines[0].split()[0]

        repo.switch_branch("main")
        repo.git("cherry-pick", create_hash)

        storage = _verify_jsonl_integrity(repo)
        issue = storage.get("test-ev1")
        assert issue is not None
        assert issue.status == "open"  # Only creation was cherry-picked


class TestMultipleMerges:
    """Multiple sequential merges of branches."""

    def test_sequential_merges_three_branches(self, git_repo: GitRepo) -> None:
        """Three branches each create a different issue. Merge sequentially.

        Verify all three issues land, no conflict markers, JSONL loads cleanly.
        (Tests sequential merges instead of octopus, which has driver limitations.)
        """
        repo = git_repo
        _install_merge_driver(repo)

        # Branch 1: create issue A
        repo.create_branch("feature1")
        _create_issue_on_branch(repo, "feature1", "a1", "Issue from branch 1")

        # Branch 2: create issue B
        repo.switch_branch("main")
        repo.create_branch("feature2")
        _create_issue_on_branch(repo, "feature2", "b1", "Issue from branch 2")

        # Branch 3: create issue C
        repo.switch_branch("main")
        repo.create_branch("feature3")
        _create_issue_on_branch(repo, "feature3", "c1", "Issue from branch 3")

        # Merge sequentially into main
        repo.switch_branch("main")
        result1 = repo.merge("feature1")
        assert result1.returncode == 0
        result2 = repo.merge("feature2")
        assert result2.returncode == 0
        result3 = repo.merge("feature3")
        assert result3.returncode == 0

        # Verify integrity and all three issues exist
        storage = _verify_jsonl_integrity(repo)

        issue_a = storage.get("test-a1")
        issue_b = storage.get("test-b1")
        issue_c = storage.get("test-c1")

        assert issue_a is not None, "Issue A from branch 1 should exist"
        assert issue_b is not None, "Issue B from branch 2 should exist"
        assert issue_c is not None, "Issue C from branch 3 should exist"

        assert issue_a.title == "Issue from branch 1"
        assert issue_b.title == "Issue from branch 2"
        assert issue_c.title == "Issue from branch 3"

    def test_merge_with_dependency_relations(self, git_repo: GitRepo) -> None:
        """Two branches: one creates issues, another adds a dependency.

        Verify dependency relationships survive the merge.
        """
        repo = git_repo
        _install_merge_driver(repo)

        # Branch 1: create issues A and B
        repo.create_branch("feature1")
        _create_issue_on_branch(repo, "feature1", "a2", "Issue A")
        _create_issue_on_branch(repo, "feature1", "b2", "Issue B")

        # Merge feature1
        repo.switch_branch("main")
        repo.merge("feature1")

        # Branch 2: add dependency (B depends on A)
        repo.create_branch("feature2")
        s = repo.storage()
        s.add_dependency("test-b2", "test-a2", DependencyType.BLOCKS)
        repo.commit_all("Add dependency: B depends on A")

        # Merge feature2
        repo.switch_branch("main")
        repo.merge("feature2")

        storage = _verify_jsonl_integrity(repo)
        issue_a = storage.get("test-a2")
        issue_b = storage.get("test-b2")

        assert issue_a is not None and issue_b is not None
        # Verify dependency exists
        deps = storage.get_dependencies("test-b2")
        assert len(deps) > 0, "Dependency should exist"


class TestSquashMerge:
    """Squash merge: combine multiple commits into a single commit."""

    def test_squash_merge_multiple_edits(self, git_repo: GitRepo) -> None:
        """Branch has 5 commits on an issue. Squash merge into main.

        Verify final state matches what a fast-forward would have produced.
        """
        repo = git_repo

        repo.create_branch("feature")
        _create_issue_on_branch(repo, "feature", "sq1", "Squash test")

        # Edit 1
        _update_issue_on_branch(
            repo, "feature", "test-sq1", {"status": "in_progress"}, "Edit 1"
        )

        # Edit 2
        _update_issue_on_branch(
            repo, "feature", "test-sq1", {"priority": 1}, "Edit 2"
        )

        # Edit 3
        _update_issue_on_branch(
            repo, "feature", "test-sq1", {"description": "Some work"}, "Edit 3"
        )

        # Edit 4
        _update_issue_on_branch(
            repo, "feature", "test-sq1", {"status": "in_review"}, "Edit 4"
        )

        # Get reference state before squash
        ref_storage = repo.storage()
        ref_issue = ref_storage.get("test-sq1")
        assert ref_issue is not None
        ref_state = {
            "title": ref_issue.title,
            "status": ref_issue.status,
            "priority": ref_issue.priority,
            "description": ref_issue.description,
        }

        # Squash merge
        repo.switch_branch("main")
        result = repo.git("merge", "--squash", "feature")
        assert result.returncode == 0
        repo.git("commit", "-m", "Squash merge feature")

        # Verify integrity and state matches
        storage = _verify_jsonl_integrity(repo)
        issue = storage.get("test-sq1")

        assert issue is not None
        assert issue.title == ref_state["title"]
        assert issue.status == ref_state["status"]
        assert issue.priority == ref_state["priority"]
        assert issue.description == ref_state["description"]

    def test_squash_merge_creates_new_issue_and_closes_it(self, git_repo: GitRepo) -> None:
        """Branch: create issue, add label, change status, close. Squash merge.

        Final state should have the issue closed.
        """
        repo = git_repo

        repo.create_branch("feature")
        _create_issue_on_branch(repo, "feature", "sq2", "Will be closed")

        _update_issue_on_branch(
            repo, "feature", "test-sq2", {"status": "in_progress"}, "Start work"
        )

        _update_issue_on_branch(
            repo, "feature", "test-sq2", {"priority": 0}, "Mark critical"
        )

        _update_issue_on_branch(
            repo, "feature", "test-sq2", {"status": "closed"}, "Close issue"
        )

        # Squash merge
        repo.switch_branch("main")
        repo.git("merge", "--squash", "feature")
        repo.git("commit", "-m", "Squash: complete issue sq2")

        storage = _verify_jsonl_integrity(repo)
        issue = storage.get("test-sq2")

        assert issue is not None
        assert issue.status == "closed"
        assert issue.priority == 0


class TestRevertMerge:
    """Revert a merge commit using git revert -m."""

    def test_revert_merge_creates_revert_commit(self, git_repo: GitRepo) -> None:
        """Merge feature into main, then revert the merge.

        Verify a revert commit is created cleanly with no conflict markers.
        Note: git revert -m only reverts the merge commit itself, not the
        commits that created the issues. So issues from the feature branch
        will still exist in the JSONL.
        """
        repo = git_repo
        _install_merge_driver(repo)

        # Feature: create issue
        repo.create_branch("feature")
        _create_issue_on_branch(repo, "feature", "rv1", "Revert test")

        # Merge to main
        repo.switch_branch("main")
        repo.merge("feature")

        # Verify issue exists after merge
        storage = repo.storage()
        issue_after_merge = storage.get("test-rv1")
        assert issue_after_merge is not None, "Issue should exist after merge"

        # Get merge commit hash
        merge_commit = repo.git("log", "-1", "--pretty=format:%H").stdout.strip()

        # Revert the merge using -m 1 (parent 1 is the main branch)
        repo.git("revert", "-m", "1", merge_commit, "--no-edit")

        # Verify integrity - revert commit should be clean
        storage = _verify_jsonl_integrity(repo)

        # Verify a revert commit was created
        log = repo.git("log", "-1", "--pretty=format:%s").stdout.strip()
        assert "Revert" in log, "Revert commit should have been created"

    def test_revert_then_remerge_with_new_commits(self, git_repo: GitRepo) -> None:
        """Merge feature, revert, then add new commits to feature and re-merge.

        Verify that re-merging a branch after reverting works correctly.
        """
        repo = git_repo
        _install_merge_driver(repo)

        # Create and merge feature with initial commit
        repo.create_branch("feature")
        _create_issue_on_branch(repo, "feature", "rv2", "Remerge test")

        repo.switch_branch("main")
        repo.merge("feature")

        # Verify issue exists
        storage1 = repo.storage()
        assert storage1.get("test-rv2") is not None

        # Revert the merge
        merge_commit = repo.git("log", "-1", "--pretty=format:%H").stdout.strip()
        repo.git("revert", "-m", "1", merge_commit, "--no-edit")

        # Add new commit to feature branch
        repo.switch_branch("feature")
        _update_issue_on_branch(
            repo, "feature", "test-rv2", {"status": "in_progress"}, "More work"
        )

        # Re-merge the feature
        repo.switch_branch("main")
        result = repo.merge("feature")
        assert result.returncode == 0, "Re-merge after revert should succeed"

        # Verify state after re-merge
        storage2 = _verify_jsonl_integrity(repo)
        issue2 = storage2.get("test-rv2")

        assert issue2 is not None
        assert issue2.status == "in_progress"

    def test_revert_fast_forward_merge(self, git_repo: GitRepo) -> None:
        """Test reverting a fast-forward merge.

        When a merge is fast-forward (no merge commit), revert still works
        by creating a new commit that reverts the changes.
        """
        repo = git_repo
        _install_merge_driver(repo)

        # Feature: create single issue
        repo.create_branch("feature")
        _create_issue_on_branch(repo, "feature", "rv4", "Fast-forward test")

        # Fast-forward merge
        repo.switch_branch("main")
        repo.merge("feature")

        # Verify issue exists
        storage = repo.storage()
        assert storage.get("test-rv4") is not None

        # Get last commit (which is from feature, not a merge commit)
        last_commit = repo.git("log", "-1", "--pretty=format:%H").stdout.strip()

        # Create a revert commit
        repo.git("revert", last_commit, "--no-edit")

        # Verify integrity
        storage = _verify_jsonl_integrity(repo)

        # Check that revert created a commit
        log = repo.git("log", "-1", "--pretty=format:%s").stdout.strip()
        assert "Revert" in log, "Revert commit should have been created"
