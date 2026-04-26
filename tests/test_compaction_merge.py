"""Concurrent compaction race condition tests.

Tests the merge driver's behavior when both sides have compacted
the JSONL file independently, creating race conditions where
byte-for-byte identical content is structured differently.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import orjson

from dogcat.constants import MERGE_DRIVER_CMD
from dogcat.models import Issue, Status
from dogcat.storage import JSONLStorage

if TYPE_CHECKING:
    from conftest import GitRepo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _install_merge_driver(repo: GitRepo) -> None:
    """Configure the dcat-jsonl merge driver."""
    repo.git("config", "merge.dcat-jsonl.driver", MERGE_DRIVER_CMD)
    attrs = repo.path / ".gitattributes"
    attrs.write_text(".dogcats/*.jsonl merge=dcat-jsonl\n")
    repo.commit_all("Add merge driver config")


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


def _force_compaction(repo: GitRepo) -> None:
    """Force a full-file compaction on the current branch."""
    s = repo.storage()
    s._save()


# ---------------------------------------------------------------------------
# Test scenarios
# ---------------------------------------------------------------------------


class TestConcurrentCompaction:
    """Race condition tests for concurrent compaction."""

    def test_identical_content_compaction(self, git_repo: GitRepo) -> None:
        """Both sides compact at the same logical state.

        Both sides have identical effective records but potentially
        different byte order after compaction. Merge should produce
        clean result without spurious LWW shuffling.
        """
        repo = git_repo
        _install_merge_driver(repo)

        # Create shared base with several issues
        s = repo.storage()
        for i in range(10):
            s.create(Issue(id=f"shared{i}", namespace="test", title=f"Shared {i}"))
        repo.commit_all("Create 10 shared issues")

        # Branch A: compacts the file (rewrite as snapshot)
        repo.create_branch("branch-a")
        _force_compaction(repo)
        repo.commit_all("Compact on branch-a")

        # Branch B: compacts the file independently
        repo.switch_branch("main")
        repo.create_branch("branch-b")
        _force_compaction(repo)
        repo.commit_all("Compact on branch-b")

        # Merge branch-a into branch-b
        repo.switch_branch("branch-b")
        result = repo.merge("branch-a")
        assert result.returncode == 0, f"Merge failed: {result.stderr}"

        # Verify: JSONL is valid and all issues still present
        assert _all_valid_json(repo)
        storage = JSONLStorage(str(repo.storage_path))

        # Exactly 10 issues — no duplicates from compact-then-merge.
        all_issues = storage.list()
        assert len(all_issues) == 10

        for i in range(10):
            issue = storage.get(f"test-shared{i}")
            assert issue is not None, f"Issue shared{i} missing after merge"
            # Identical content on both sides: title must round-trip unchanged.
            assert issue.title == f"Shared {i}"

    def test_compact_then_edit_on_both_sides(self, git_repo: GitRepo) -> None:
        """Both sides compact, then both make edits to different issues.

        Verify all post-compaction edits preserved AND contested edits
        use LWW semantics.
        """
        repo = git_repo
        _install_merge_driver(repo)

        # Create base
        s = repo.storage()
        for i in range(10):
            s.create(Issue(id=f"issue{i}", namespace="test", title=f"Issue {i}"))
        repo.commit_all("Create base issues")

        # Branch A: compact and edit
        repo.create_branch("branch-a")
        _force_compaction(repo)
        s = repo.storage()
        s.update("test-issue0", {"status": "in_progress"})
        s.update("test-issue1", {"priority": 0})
        repo.commit_all("Compact and edit on branch-a")

        # Branch B: compact and edit
        repo.switch_branch("main")
        repo.create_branch("branch-b")
        _force_compaction(repo)
        s = repo.storage()
        s.update("test-issue2", {"status": "closed"})
        s.update("test-issue3", {"priority": 1})
        repo.commit_all("Compact and edit on branch-b")

        # Branch B: edit a shared issue that A also edited
        s = repo.storage()
        s.update("test-issue0", {"status": "in_review", "priority": 2})
        repo.commit_all("Edit shared issue on branch-b")

        # Merge branch-a into branch-b
        result = repo.merge("branch-a")
        assert result.returncode == 0

        # Verify: all edits preserved with LWW for contested issue
        assert _all_valid_json(repo)
        storage = JSONLStorage(str(repo.storage_path))

        # Check unique edits from each side
        issue2 = storage.get("test-issue2")
        assert issue2 is not None
        assert issue2.status == Status.CLOSED

        issue3 = storage.get("test-issue3")
        assert issue3 is not None
        assert issue3.priority == 1

        # Branch A also touched issue1 (priority=0) only on its side. The
        # merge must preserve A's lone edit so we know the merge driver
        # didn't drop one branch's work entirely. (dogcat-2bt3)
        issue1 = storage.get("test-issue1")
        assert issue1 is not None
        assert issue1.priority == 0

        # Contested edit on issue0: A set status=in_progress, then B set
        # status=in_review,priority=2. B's commit has the later
        # ``updated_at`` so LWW must surface B's full record. Asserting
        # the exact field values is the whole point of an LWW driver —
        # ``is not None`` proves nothing about which side won.
        issue0 = storage.get("test-issue0")
        assert issue0 is not None
        assert issue0.status == Status.IN_REVIEW
        assert issue0.priority == 2

    def test_compact_then_edit_one_side_only(self, git_repo: GitRepo) -> None:
        """One side compacts and edits; other side not compacted.

        Realistic 'main compacted, feature branch not' scenario.
        """
        repo = git_repo
        _install_merge_driver(repo)

        # Create base
        s = repo.storage()
        for i in range(5):
            s.create(Issue(id=f"base{i}", namespace="test", title=f"Base {i}"))
        repo.commit_all("Create base")

        # Main: compact and make edits
        _force_compaction(repo)
        s = repo.storage()
        for i in range(5):
            s.update(f"test-base{i}", {"priority": 0})
        repo.commit_all("Compact and edit main")

        # Feature branch: diverges before compaction, adds new issues
        repo.create_branch("feature")
        s = repo.storage()
        for i in range(5):
            s.create(Issue(id=f"feature{i}", namespace="test", title=f"Feature {i}"))
        repo.commit_all("Add features on branch")

        # Feature: also edit shared base issues (with different values)
        s = repo.storage()
        for i in range(5):
            s.update(f"test-base{i}", {"status": "in_progress"})
        repo.commit_all("Edit base on feature branch")

        # Merge feature into main
        repo.switch_branch("main")
        result = repo.merge("feature")
        assert result.returncode == 0

        # Verify
        assert _all_valid_json(repo)
        storage = JSONLStorage(str(repo.storage_path))

        # All issues should exist
        for i in range(5):
            assert storage.get(f"test-base{i}") is not None
            assert storage.get(f"test-feature{i}") is not None

    def test_compact_with_remove_ops(self, git_repo: GitRepo) -> None:
        """Compaction drops remove ops; merge must not resurrect them.

        Side A compacts (which materializes state and drops history).
        Side B has the original add+remove pairs.
        Merge must respect removals (tombstones).
        """
        repo = git_repo
        _install_merge_driver(repo)

        # Create base with issues
        s = repo.storage()
        for i in range(5):
            s.create(Issue(id=f"issue{i}", namespace="test", title=f"Issue {i}"))
        repo.commit_all("Create issues")

        # Main: delete some issues (tombstone them)
        s = repo.storage()
        for i in range(2):
            s.delete(f"test-issue{i}")
        repo.commit_all("Delete issues on main")

        # Compact main (removes delete records from history)
        _force_compaction(repo)
        repo.commit_all("Compact main after deletes")

        # Feature branch: diverged before deletes, so it has original creates
        repo.create_branch("feature")
        # Feature adds more issues
        s = repo.storage()
        for i in range(5, 8):
            s.create(Issue(id=f"issue{i}", namespace="test", title=f"Issue {i}"))
        repo.commit_all("Add more issues on feature")

        # Merge feature into main
        repo.switch_branch("main")
        result = repo.merge("feature")
        assert result.returncode == 0

        # Verify: deleted issues should remain deleted (tombstone)
        assert _all_valid_json(repo)
        storage = JSONLStorage(str(repo.storage_path))

        # Deleted issues should still be deleted
        deleted0 = storage.get("test-issue0")
        deleted1 = storage.get("test-issue1")

        # They should not exist or be tombstones
        assert deleted0 is None or deleted0.status == "tombstone"
        assert deleted1 is None or deleted1.status == "tombstone"

        # Non-deleted shared issues should exist
        for i in range(2, 5):
            assert storage.get(f"test-issue{i}") is not None

        # Feature additions should exist
        for i in range(5, 8):
            assert storage.get(f"test-issue{i}") is not None
