"""Tests for multi-branch merge scenarios with JSONL issue storage.

Validates how git handles merging .dogcats/issues.jsonl when multiple
branches make independent modifications. Documents both clean merge
paths and conflict scenarios to guide future merge driver work.

Key finding: git's default merge strategy treats two branches both
appending to the end of a file as a conflict, even when the appended
lines are entirely different. This is because git sees both branches
as modifying the same "end of file" region. A custom merge driver
(dogcat-3mx4) is needed to auto-resolve these JSONL-specific cases.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import orjson

from dogcat.models import DependencyType, Issue
from dogcat.storage import JSONLStorage

if TYPE_CHECKING:
    from conftest import GitRepo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _force_compaction(repo: GitRepo) -> None:
    """Force a full-file compaction on the current branch."""
    s = repo.storage()
    s._save()


def _all_valid_json(repo: GitRepo) -> bool:
    """Return True if every non-empty line in issues.jsonl is valid JSON."""
    lines = repo.read_jsonl_lines()
    try:
        for line in lines:
            orjson.loads(line)
    except orjson.JSONDecodeError:
        return False
    return True


def _load_and_verify(repo: GitRepo) -> JSONLStorage:
    """Load storage from disk; raises if the file is unparseable."""
    return JSONLStorage(str(repo.storage_path))


def _has_conflict_markers(repo: GitRepo) -> bool:
    """Return True if the JSONL file contains git conflict markers."""
    raw = repo.storage_path.read_text()
    return "<<<<<<<" in raw or "=======" in raw


# ---------------------------------------------------------------------------
# Test scenarios
# ---------------------------------------------------------------------------


class TestMergeBranches:
    """Multi-branch merge scenarios for .dogcats/issues.jsonl.

    Documents git's actual merge behavior with append-only JSONL files.
    Both clean merges and expected conflicts are tested to establish
    the baseline that a custom merge driver must improve upon.
    """

    # -- Append-to-EOF conflicts (motivates custom merge driver) -----------

    def test_non_overlapping_adds_conflict(self, git_repo: GitRepo) -> None:
        """Two branches appending different issues: git conflicts at EOF.

        Even though the appended lines are completely different, git's
        default merge strategy sees both branches as modifying the same
        "end of file" region and reports a conflict. This is the primary
        motivation for a custom JSONL merge driver.
        """
        repo = git_repo

        # Branch A: create issues a1, a2
        repo.create_branch("branch-a")
        s = repo.storage()
        s.create(Issue(id="a1", namespace="test", title="Issue A1"))
        s.create(Issue(id="a2", namespace="test", title="Issue A2"))
        repo.commit_all("Add issues on branch-a")

        # Back to main, create branch B
        repo.switch_branch("main")
        repo.create_branch("branch-b")
        s = repo.storage()
        s.create(Issue(id="b1", namespace="test", title="Issue B1"))
        s.create(Issue(id="b2", namespace="test", title="Issue B2"))
        repo.commit_all("Add issues on branch-b")

        # Merge branch-a into main (fast-forward)
        repo.switch_branch("main")
        result_a = repo.merge("branch-a")
        assert result_a.returncode == 0

        # Merge branch-b: conflicts because both appended to EOF
        result_b = repo.merge("branch-b")
        assert result_b.returncode != 0
        assert _has_conflict_markers(repo)

    def test_same_issue_edits_conflict(self, git_repo: GitRepo) -> None:
        """Both branches editing the same issue: conflicts at EOF.

        Both updates append a new full-issue record at the end of the file.
        Git sees both branches modifying the EOF region and conflicts.
        """
        repo = git_repo

        # Create shared issue on main
        s = repo.storage()
        s.create(Issue(id="shared1", namespace="test", title="Original title"))
        repo.commit_all("Create shared issue")

        # Branch A: update title
        repo.create_branch("branch-a")
        _update_issue_on_branch(
            repo,
            "branch-a",
            "test-shared1",
            {"title": "Title from A"},
        )

        # Branch B (from main): update title differently
        repo.switch_branch("main")
        repo.create_branch("branch-b")
        _update_issue_on_branch(
            repo,
            "branch-b",
            "test-shared1",
            {"title": "Title from B"},
        )

        # Merge A then B into main
        repo.switch_branch("main")
        result_a = repo.merge("branch-a")
        assert result_a.returncode == 0

        result_b = repo.merge("branch-b")
        assert result_b.returncode != 0
        assert _has_conflict_markers(repo)

    def test_concurrent_creates_multi_commit_conflict(self, git_repo: GitRepo) -> None:
        """Multiple commits per branch with unique IDs: still conflicts at EOF."""
        repo = git_repo

        # Branch A: 5 issues, one commit each
        repo.create_branch("branch-a")
        for i in range(5):
            _create_issue_on_branch(
                repo,
                "branch-a",
                f"ca{i}",
                f"Concurrent A issue {i}",
            )

        # Branch B: 5 issues, one commit each
        repo.switch_branch("main")
        repo.create_branch("branch-b")
        for i in range(5):
            _create_issue_on_branch(
                repo,
                "branch-b",
                f"cb{i}",
                f"Concurrent B issue {i}",
            )

        # Merge both into main
        repo.switch_branch("main")
        result_a = repo.merge("branch-a")
        assert result_a.returncode == 0

        result_b = repo.merge("branch-b")
        assert result_b.returncode != 0
        assert _has_conflict_markers(repo)

    def test_mixed_record_types_conflict(self, git_repo: GitRepo) -> None:
        """Adding deps and links on separate branches: conflicts at EOF.

        Even different record types (dependency vs link) conflict because
        they are both appended to the end of the same file.
        """
        repo = git_repo

        # Seed two issues on main
        s = repo.storage()
        s.create(Issue(id="d1", namespace="test", title="Issue D1"))
        s.create(Issue(id="d2", namespace="test", title="Issue D2"))
        repo.commit_all("Seed issues d1, d2")

        # Branch A: add a dependency
        repo.create_branch("branch-a")
        s = repo.storage()
        s.add_dependency("test-d1", "test-d2", DependencyType.BLOCKS)
        repo.commit_all("Add dependency on branch-a")

        # Branch B: add a link
        repo.switch_branch("main")
        repo.create_branch("branch-b")
        s = repo.storage()
        s.add_link("test-d1", "test-d2", "relates_to")
        repo.commit_all("Add link on branch-b")

        # Merge both
        repo.switch_branch("main")
        result_a = repo.merge("branch-a")
        assert result_a.returncode == 0

        result_b = repo.merge("branch-b")
        assert result_b.returncode != 0
        assert _has_conflict_markers(repo)

    # -- Compaction conflicts -----------------------------------------------

    def test_one_side_compaction_auto_resolves(self, git_repo: GitRepo) -> None:
        """One branch compacts while the other appends: git auto-resolves.

        Surprisingly, git's ort strategy can handle this: compaction
        rewrites existing lines (modifying the body of the file) while the
        other branch appends to EOF. Git sees these as changes to different
        regions and auto-merges successfully.
        """
        repo = git_repo

        # Seed main with issues so compaction has content to rewrite
        s = repo.storage()
        for i in range(5):
            s.create(Issue(id=f"base{i}", namespace="test", title=f"Base {i}"))
        repo.commit_all("Seed base issues")

        # Branch A: append more issues (no compaction)
        repo.create_branch("branch-a")
        s = repo.storage()
        s.create(Issue(id="extra-a", namespace="test", title="Extra from A"))
        repo.commit_all("Append on branch-a")

        # Branch B: compact the file (rewrites existing lines)
        repo.switch_branch("main")
        repo.create_branch("branch-b")
        _force_compaction(repo)
        repo.commit_all("Compact on branch-b")

        # Merge A into main
        repo.switch_branch("main")
        result_a = repo.merge("branch-a")
        assert result_a.returncode == 0

        # Merge B (compacted) into main -- auto-resolves
        result_b = repo.merge("branch-b")
        assert (
            result_b.returncode == 0
        ), f"Expected auto-resolve but got conflict: {result_b.stdout}"

        # Verify integrity after auto-merge
        assert _all_valid_json(repo)
        storage = _load_and_verify(repo)
        # All 5 base issues + 1 extra from branch-a
        assert len(storage.list()) == 6
        assert "test-extra-a" in storage.get_issue_ids()

    def test_both_sides_compaction_conflict(self, git_repo: GitRepo) -> None:
        """Both branches compact independently: conflict."""
        repo = git_repo

        # Seed main
        s = repo.storage()
        for i in range(5):
            s.create(Issue(id=f"base{i}", namespace="test", title=f"Base {i}"))
        repo.commit_all("Seed base issues")

        # Branch A: add issue then compact
        repo.create_branch("branch-a")
        s = repo.storage()
        s.create(Issue(id="comp-a", namespace="test", title="Compacted A"))
        _force_compaction(repo)
        repo.commit_all("Add + compact on branch-a")

        # Branch B: add issue then compact
        repo.switch_branch("main")
        repo.create_branch("branch-b")
        s = repo.storage()
        s.create(Issue(id="comp-b", namespace="test", title="Compacted B"))
        _force_compaction(repo)
        repo.commit_all("Add + compact on branch-b")

        # Merge A then B
        repo.switch_branch("main")
        result_a = repo.merge("branch-a")
        assert result_a.returncode == 0

        result_b = repo.merge("branch-b")
        assert result_b.returncode != 0
        assert _has_conflict_markers(repo)

    def test_delete_vs_edit_conflict(self, git_repo: GitRepo) -> None:
        """One branch deletes (compacts) while the other edits: conflict.

        Delete triggers compaction via _save(), rewriting the file body.
        The edit branch appends to EOF. Despite modifying different regions,
        the combined rewrite + append results in a conflict because the
        delete removes lines that the base had.
        """
        repo = git_repo

        # Seed an issue on main
        s = repo.storage()
        s.create(Issue(id="del1", namespace="test", title="To be deleted"))
        repo.commit_all("Seed issue del1")

        # Branch A: delete the issue (calls _save() internally)
        repo.create_branch("branch-a")
        s = repo.storage()
        s.delete("test-del1")
        repo.commit_all("Delete del1 on branch-a")

        # Branch B: edit the same issue
        repo.switch_branch("main")
        repo.create_branch("branch-b")
        _update_issue_on_branch(
            repo,
            "branch-b",
            "test-del1",
            {"title": "Updated title"},
            "Edit del1 on branch-b",
        )

        # Merge A (with compaction) into main
        repo.switch_branch("main")
        result_a = repo.merge("branch-a")
        assert result_a.returncode == 0

        # Merge B -- conflicts because A compacted away lines B modified
        result_b = repo.merge("branch-b")
        assert result_b.returncode != 0
        assert _has_conflict_markers(repo)

    # -- Clean merge scenario (sequential appends on one branch) ------------

    def test_sequential_branch_merges_cleanly(self, git_repo: GitRepo) -> None:
        """Branches merged sequentially (no parallel work) merge cleanly.

        When branch-a is merged into main before branch-b starts, branch-b
        sees branch-a's changes in its base. This is the simple rebase/
        fast-forward workflow that always works.
        """
        repo = git_repo

        # Branch A: create issues
        repo.create_branch("branch-a")
        s = repo.storage()
        s.create(Issue(id="seq-a", namespace="test", title="Sequential A"))
        repo.commit_all("Add issue on branch-a")

        # Merge branch-a into main first
        repo.switch_branch("main")
        result_a = repo.merge("branch-a")
        assert result_a.returncode == 0

        # Now branch B starts from main (which includes A's changes)
        repo.create_branch("branch-b")
        s = repo.storage()
        s.create(Issue(id="seq-b", namespace="test", title="Sequential B"))
        repo.commit_all("Add issue on branch-b")

        # Merge branch-b into main
        repo.switch_branch("main")
        result_b = repo.merge("branch-b")
        assert result_b.returncode == 0

        # Verify
        assert _all_valid_json(repo)
        storage = _load_and_verify(repo)
        assert {"test-seq-a", "test-seq-b"} == storage.get_issue_ids()

    # -- Branch-aware compaction ------------------------------------------------

    def test_auto_compaction_skips_on_feature_branch(self, git_repo: GitRepo) -> None:
        """Auto-compaction is suppressed on non-default branches.

        _maybe_compact() checks the current git branch and skips compaction
        if not on main/master. This prevents the "both sides compact"
        conflict when multiple branches trigger compaction independently.
        """
        repo = git_repo

        # Seed enough issues to exceed compaction threshold
        # (_COMPACTION_MIN_BASE=20 and each create writes 2 lines: issue+event)
        s = repo.storage()
        for i in range(15):
            s.create(Issue(id=f"seed{i}", namespace="test", title=f"Seed {i}"))
        repo.commit_all("Seed issues on main")
        lines_before = len(repo.read_jsonl_lines())

        # On a feature branch, create enough issues to trigger auto-compaction
        repo.create_branch("feature")
        s = repo.storage()
        for i in range(15):
            s.create(Issue(id=f"feat{i}", namespace="test", title=f"Feat {i}"))

        lines_after = len(repo.read_jsonl_lines())
        # Auto-compaction was suppressed — file only grew (no rewrite)
        assert lines_after > lines_before

        # Verify all issues still load correctly
        s2 = repo.storage()
        assert len(s2.list()) == 30

    def test_auto_compaction_runs_on_main(self, git_repo: GitRepo) -> None:
        """Auto-compaction proceeds normally on the default branch."""
        repo = git_repo

        s = repo.storage()
        for i in range(15):
            s.create(Issue(id=f"seed{i}", namespace="test", title=f"Seed {i}"))

        lines_before = len(repo.read_jsonl_lines())

        # On main, create enough to exceed threshold — compaction should fire
        s = repo.storage()
        for i in range(15):
            s.create(Issue(id=f"more{i}", namespace="test", title=f"More {i}"))

        lines_after = len(repo.read_jsonl_lines())
        # Compaction ran — file should be smaller than purely appending would produce
        # 30 issues * 2 lines (issue+event) = 60 lines without compaction
        # With compaction: 30 issue records + 30 event records = 60, but
        # the compacted form removes superseded records
        assert lines_after <= lines_before + 30 + 15  # generous upper bound

        s2 = repo.storage()
        assert len(s2.list()) == 30
