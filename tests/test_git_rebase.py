"""Tests for `dcat git rebase` — auto-resolving JSONL merge conflicts."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import orjson

from dogcat.models import Issue

if TYPE_CHECKING:
    from conftest import GitRepo


def _has_conflict_markers(path: Path) -> bool:
    """Return True if the file contains git conflict markers."""
    raw = path.read_text()
    return "<<<<<<<" in raw or "=======" in raw


def _run_dcat_rebase() -> tuple[int, str]:
    """Run `dcat git rebase` via CLI invoke."""
    from typer.testing import CliRunner

    from dogcat.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["git", "rebase"], catch_exceptions=False)
    return result.exit_code, result.output


def _in_repo(repo: GitRepo) -> os.PathLike[str]:
    """Context-manager-style helper: chdir to repo, return old cwd for finally."""
    old = Path.cwd()
    os.chdir(repo.path)
    return old


class TestGitRebase:
    """Tests for `dcat git rebase` command."""

    def test_resolves_non_overlapping_adds(self, git_repo: GitRepo) -> None:
        """Two branches appending different issues — rebase resolves the conflict."""
        repo = git_repo

        # Branch A: create issue a1
        repo.create_branch("branch-a")
        s = repo.storage()
        s.create(Issue(id="a1", namespace="test", title="Issue A1"))
        repo.commit_all("Add issue on branch-a")

        # Branch B (from main): create issue b1
        repo.switch_branch("main")
        repo.create_branch("branch-b")
        s = repo.storage()
        s.create(Issue(id="b1", namespace="test", title="Issue B1"))
        repo.commit_all("Add issue on branch-b")

        # Merge branch-a into main (fast-forward)
        repo.switch_branch("main")
        result_a = repo.merge("branch-a")
        assert result_a.returncode == 0

        # Merge branch-b: conflicts
        result_b = repo.merge("branch-b")
        assert result_b.returncode != 0
        assert _has_conflict_markers(repo.storage_path)

        # Run dcat git rebase — should resolve the conflict
        old_cwd = _in_repo(repo)
        try:
            exit_code, output = _run_dcat_rebase()
        finally:
            os.chdir(old_cwd)

        assert exit_code == 0
        assert "Resolved issues.jsonl" in output

        # Verify the file is clean and both issues are present
        assert not _has_conflict_markers(repo.storage_path)
        s = repo.storage()
        ids = s.get_issue_ids()
        assert "test-a1" in ids
        assert "test-b1" in ids

    def test_resolves_same_issue_edits(self, git_repo: GitRepo) -> None:
        """Both branches editing the same issue — last-write-wins resolution."""
        repo = git_repo

        # Create shared issue on main
        s = repo.storage()
        s.create(Issue(id="shared", namespace="test", title="Original"))
        repo.commit_all("Create shared issue")

        # Branch A: update title
        repo.create_branch("branch-a")
        s = repo.storage()
        s.update("test-shared", {"title": "Title from A"})
        repo.commit_all("Update on branch-a")

        # Branch B (from main): update title differently
        repo.switch_branch("main")
        repo.create_branch("branch-b")
        s = repo.storage()
        s.update("test-shared", {"title": "Title from B"})
        repo.commit_all("Update on branch-b")

        # Merge A then B
        repo.switch_branch("main")
        repo.merge("branch-a")
        result_b = repo.merge("branch-b")
        assert result_b.returncode != 0

        old_cwd = _in_repo(repo)
        try:
            exit_code, _output = _run_dcat_rebase()
        finally:
            os.chdir(old_cwd)

        assert exit_code == 0
        assert not _has_conflict_markers(repo.storage_path)

        # Both versions should merge — last-write-wins picks one
        s = repo.storage()
        issue = s.get("test-shared")
        assert issue is not None
        assert issue.title in ("Title from A", "Title from B")

    def test_no_conflicts_found(self, git_repo: GitRepo) -> None:
        """No conflict markers — prints message and exits cleanly."""
        repo = git_repo

        # Create a clean issue file
        s = repo.storage()
        s.create(Issue(id="clean", namespace="test", title="Clean"))
        repo.commit_all("Clean state")

        old_cwd = _in_repo(repo)
        try:
            exit_code, output = _run_dcat_rebase()
        finally:
            os.chdir(old_cwd)

        assert exit_code == 0
        assert "No JSONL conflicts found" in output

    def test_stages_resolved_file(self, git_repo: GitRepo) -> None:
        """Resolved file is staged with git add."""
        repo = git_repo

        # Create a conflict
        repo.create_branch("branch-a")
        s = repo.storage()
        s.create(Issue(id="x1", namespace="test", title="X1"))
        repo.commit_all("Add x1")

        repo.switch_branch("main")
        repo.create_branch("branch-b")
        s = repo.storage()
        s.create(Issue(id="x2", namespace="test", title="X2"))
        repo.commit_all("Add x2")

        repo.switch_branch("main")
        repo.merge("branch-a")
        repo.merge("branch-b")

        old_cwd = _in_repo(repo)
        try:
            exit_code, _output = _run_dcat_rebase()
        finally:
            os.chdir(old_cwd)

        assert exit_code == 0

        # Check that the file is staged (not in unmerged list)
        result = repo.git("diff", "--cached", "--name-only")
        assert ".dogcats/issues.jsonl" in result.stdout

    def test_resolves_inbox_conflicts(self, git_repo: GitRepo) -> None:
        """Conflicts in inbox.jsonl are also resolved."""
        repo = git_repo
        inbox_path = repo.dogcats_dir / "inbox.jsonl"

        # Create conflicting inbox files manually
        proposal_a = {
            "record_type": "proposal",
            "namespace": "test",
            "id": "pa",
            "title": "Proposal A",
            "status": "open",
            "created_at": "2026-01-01T00:00:00",
        }
        proposal_b = {
            "record_type": "proposal",
            "namespace": "test",
            "id": "pb",
            "title": "Proposal B",
            "status": "open",
            "created_at": "2026-01-02T00:00:00",
        }

        # Write a conflicted inbox file
        conflict_content = (
            b"<<<<<<< HEAD\n"
            + orjson.dumps(proposal_a)
            + b"\n"
            + b"=======\n"
            + orjson.dumps(proposal_b)
            + b"\n"
            + b">>>>>>> branch-b\n"
        )
        inbox_path.write_bytes(conflict_content)

        old_cwd = _in_repo(repo)
        try:
            exit_code, output = _run_dcat_rebase()
        finally:
            os.chdir(old_cwd)

        assert exit_code == 0
        assert "Resolved inbox.jsonl" in output
        assert not _has_conflict_markers(inbox_path)

        # Both proposals should be in the resolved file
        records = [
            orjson.loads(line)
            for line in inbox_path.read_bytes().splitlines()
            if line.strip()
        ]
        proposal_ids = {r.get("id") for r in records}
        assert "pa" in proposal_ids
        assert "pb" in proposal_ids


class TestParseConflictedJsonl:
    """Unit tests for parse_conflicted_jsonl."""

    def test_standard_conflict(self) -> None:
        """Standard two-way conflict markers."""
        from dogcat.merge_driver import parse_conflicted_jsonl

        issue_a = orjson.dumps({"record_type": "issue", "id": "a", "namespace": "t"})
        issue_b = orjson.dumps({"record_type": "issue", "id": "b", "namespace": "t"})

        raw = (
            b"<<<<<<< HEAD\n"
            + issue_a
            + b"\n"
            + b"=======\n"
            + issue_b
            + b"\n"
            + b">>>>>>> branch\n"
        )

        base, ours, theirs = parse_conflicted_jsonl(raw)
        assert base == []
        assert len(ours) == 1
        assert ours[0]["id"] == "a"
        assert len(theirs) == 1
        assert theirs[0]["id"] == "b"

    def test_diff3_conflict(self) -> None:
        """diff3-style conflict with base section."""
        from dogcat.merge_driver import parse_conflicted_jsonl

        issue_base = orjson.dumps(
            {"record_type": "issue", "id": "x", "namespace": "t", "title": "original"}
        )
        issue_ours = orjson.dumps(
            {"record_type": "issue", "id": "x", "namespace": "t", "title": "ours"}
        )
        issue_theirs = orjson.dumps(
            {"record_type": "issue", "id": "x", "namespace": "t", "title": "theirs"}
        )

        raw = (
            b"<<<<<<< HEAD\n"
            + issue_ours
            + b"\n"
            + b"||||||| merged common ancestor\n"
            + issue_base
            + b"\n"
            + b"=======\n"
            + issue_theirs
            + b"\n"
            + b">>>>>>> branch\n"
        )

        base, ours, theirs = parse_conflicted_jsonl(raw)
        assert len(base) == 1
        assert base[0]["title"] == "original"
        assert len(ours) == 1
        assert ours[0]["title"] == "ours"
        assert len(theirs) == 1
        assert theirs[0]["title"] == "theirs"

    def test_shared_context_included(self) -> None:
        """Non-conflicted lines are included in both ours and theirs."""
        from dogcat.merge_driver import parse_conflicted_jsonl

        shared = orjson.dumps(
            {"record_type": "issue", "id": "shared", "namespace": "t"}
        )
        issue_a = orjson.dumps({"record_type": "issue", "id": "a", "namespace": "t"})
        issue_b = orjson.dumps({"record_type": "issue", "id": "b", "namespace": "t"})

        raw = (
            shared
            + b"\n"
            + b"<<<<<<< HEAD\n"
            + issue_a
            + b"\n"
            + b"=======\n"
            + issue_b
            + b"\n"
            + b">>>>>>> branch\n"
        )

        _base, ours, theirs = parse_conflicted_jsonl(raw)
        assert len(ours) == 2  # shared + a
        assert len(theirs) == 2  # shared + b
        ours_ids = {r["id"] for r in ours}
        theirs_ids = {r["id"] for r in theirs}
        assert "shared" in ours_ids
        assert "shared" in theirs_ids

    def test_no_conflicts_returns_empty(self) -> None:
        """File with no conflict markers returns empty tuples."""
        from dogcat.merge_driver import parse_conflicted_jsonl

        record = orjson.dumps({"record_type": "issue", "id": "ok", "namespace": "t"})
        base, ours, theirs = parse_conflicted_jsonl(record + b"\n")
        assert base == []
        assert ours == []
        assert theirs == []
