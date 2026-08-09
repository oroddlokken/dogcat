"""Tests for `dcat git rebase` — auto-resolving JSONL merge conflicts."""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import orjson

from dogcat.models import Issue

if TYPE_CHECKING:
    from collections.abc import Generator

    import pytest
    from conftest import GitRepo
    from typer.testing import Result


def _has_conflict_markers(path: Path) -> bool:
    """Return True if the file contains git conflict markers."""
    raw = path.read_text()
    return "<<<<<<<" in raw or "=======" in raw


def _invoke_dcat_rebase() -> Result:
    """Run `dcat git rebase` via CLI invoke, returning the whole Result.

    ``Result.output`` interleaves stdout and stderr, so the per-file report
    and ``echo_error``'s stderr both land in it.
    """
    from typer.testing import CliRunner

    from dogcat.cli import app

    return CliRunner().invoke(app, ["git", "rebase"], catch_exceptions=False)


def _run_dcat_rebase() -> tuple[int, str]:
    """Run `dcat git rebase` via CLI invoke."""
    result = _invoke_dcat_rebase()
    return result.exit_code, result.output


def _conflict_bytes() -> bytes:
    """Two issue records in conflict — resolvable, so a resolve is expected."""
    issue_a = orjson.dumps(
        {"record_type": "issue", "id": "a", "namespace": "test", "title": "A"}
    )
    issue_b = orjson.dumps(
        {"record_type": "issue", "id": "b", "namespace": "test", "title": "B"}
    )
    return (
        b"<<<<<<< HEAD\n" + issue_a + b"\n=======\n" + issue_b + b"\n>>>>>>> branch\n"
    )


@contextmanager
def _store_lock_held(dogcats_dir: Path) -> Generator[None, None, None]:
    """Hold the store's advisory lock in a thread for the duration of the body.

    A separate thread, not a separate process: ``flock`` is per open file
    description, so a second ``open`` in this process contends with it just
    as another ``dcat`` would.
    """
    from dogcat.constants import LOCK_FILENAME
    from dogcat.locking import advisory_file_lock

    holding = threading.Event()
    release = threading.Event()

    def hold_lock() -> None:
        with advisory_file_lock(dogcats_dir / LOCK_FILENAME):
            holding.set()
            release.wait(10)

    holder = threading.Thread(target=hold_lock)
    holder.start()
    try:
        assert holding.wait(10), "lock holder thread never acquired the lock"
        yield
    finally:
        release.set()
        holder.join(10)


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

    def test_preserves_file_mode(self, git_repo: GitRepo) -> None:
        """A 0644-shared store keeps mode 0644 after the resolve.

        The resolve replaces the file via a tempfile rename, and a tempfile
        is created 0600 — so without carrying the original mode across, a
        store shared with the rest of the team comes back readable only by
        whoever rebased. (dogcat-64nd)
        """
        repo = git_repo

        repo.create_branch("branch-a")
        s = repo.storage()
        s.create(Issue(id="m1", namespace="test", title="M1"))
        repo.commit_all("Add m1")

        repo.switch_branch("main")
        repo.create_branch("branch-b")
        s = repo.storage()
        s.create(Issue(id="m2", namespace="test", title="M2"))
        repo.commit_all("Add m2")

        repo.switch_branch("main")
        repo.merge("branch-a")
        repo.merge("branch-b")
        assert _has_conflict_markers(repo.storage_path)

        repo.storage_path.chmod(0o644)

        old_cwd = _in_repo(repo)
        try:
            exit_code, _output = _run_dcat_rebase()
        finally:
            os.chdir(old_cwd)

        assert exit_code == 0
        assert repo.storage_path.stat().st_mode & 0o777 == 0o644


class TestGitRebaseSafety:
    """The advisory lock, the unreadable-file paths, and the skip report.

    All of it is about `dcat git rebase` not making a bad situation worse:
    it overwrites whole files, so it has to exclude concurrent writers, and
    it must never exit 0 next to a file that still holds markers
    (dogcat-1n4x). The failure path has to stay legible too — the user is
    mid-rebase, so a traceback or a name they cannot act on is its own cost
    (dogcat-3qw3).
    """

    def test_waits_for_the_store_lock(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A concurrent holder of the store lock blocks the resolve.

        Without the lock, an append from another dcat process lands in a
        file this command is about to replace wholesale and is lost — the
        one case AGENTS.md promises concurrent dcat processes are safe from.
        """
        repo = git_repo
        monkeypatch.chdir(repo.path)
        monkeypatch.setenv("DCAT_LOCK_TIMEOUT_SECS", "0.2")

        repo.storage_path.write_bytes(_conflict_bytes())

        with _store_lock_held(repo.dogcats_dir):
            result = _invoke_dcat_rebase()

        assert result.exit_code != 0
        # Never got as far as the rewrite, so the conflict is still there.
        assert _has_conflict_markers(repo.storage_path)

    def test_lock_timeout_is_reported_not_raised(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Failing to get the lock names the lock file instead of tracing back.

        This fires mid-rebase, and the likely cause is a lock file left by a
        process that is already gone — something the user can clear once
        they are told where it is. A traceback tells them nothing and looks
        like dcat crashed on their conflicted store. (dogcat-3qw3)
        """
        from dogcat.constants import LOCK_FILENAME

        repo = git_repo
        monkeypatch.chdir(repo.path)
        monkeypatch.setenv("DCAT_LOCK_TIMEOUT_SECS", "0.2")

        repo.storage_path.write_bytes(_conflict_bytes())

        with _store_lock_held(repo.dogcats_dir):
            result = _invoke_dcat_rebase()

        assert result.exit_code == 1
        # A clean typer.Exit, not a RuntimeError escaping the command.
        assert isinstance(result.exception, SystemExit)
        assert str(repo.dogcats_dir / LOCK_FILENAME) in result.output
        assert "remove the lock file" in result.output
        assert "Traceback" not in result.output

    def test_vanished_file_is_skipped_silently(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A file gone by the time it is read costs neither output nor exit code.

        rglob returns a snapshot, and a compaction tempfile in it can be
        renamed away before the loop reaches it. That name was never the
        user's business, so reporting it mid-rebase — and failing the
        command over it — gave them something they could not act on.
        (dogcat-3qw3)
        """
        repo = git_repo

        archive = repo.dogcats_dir / "archive" / "closed-2026-01-01T00-00-00.jsonl"
        archive.parent.mkdir(parents=True)
        conflict = _conflict_bytes()
        # Sorts after archive/, so the resolve above it has already happened.
        vanishing = repo.dogcats_dir / "zz-vanishing.jsonl"
        archive.write_bytes(conflict)
        vanishing.write_bytes(conflict)

        real_read_bytes = Path.read_bytes

        def read_bytes_after_vanishing(self: Path) -> bytes:
            if self.name == vanishing.name:
                self.unlink()
            return real_read_bytes(self)

        monkeypatch.setattr(Path, "read_bytes", read_bytes_after_vanishing)

        old_cwd = _in_repo(repo)
        try:
            exit_code, output = _run_dcat_rebase()
        finally:
            os.chdir(old_cwd)

        assert exit_code == 0, output
        assert f"Resolved {archive.name}" in output
        assert vanishing.name not in output
        assert not _has_conflict_markers(archive)

    def test_unreadable_file_is_still_an_error(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A file that exists but will not open is reported and exits 1.

        The vanished-file skip keys on FileNotFoundError alone. A
        permissions or I/O failure names a file that is still sitting there,
        possibly still holding conflict markers, so it has to stay loud.
        (dogcat-3qw3)
        """
        repo = git_repo

        unreadable = repo.dogcats_dir / "zz-unreadable.jsonl"
        unreadable.write_bytes(_conflict_bytes())

        real_read_bytes = Path.read_bytes

        def read_bytes_denied(self: Path) -> bytes:
            if self.name == unreadable.name:
                raise PermissionError(13, "Permission denied")
            return real_read_bytes(self)

        monkeypatch.setattr(Path, "read_bytes", read_bytes_denied)

        old_cwd = _in_repo(repo)
        try:
            exit_code, output = _run_dcat_rebase()
        finally:
            os.chdir(old_cwd)

        assert exit_code == 1
        assert unreadable.name in output
        assert "Permission denied" in output
        assert _has_conflict_markers(unreadable)

    def test_unparseable_conflict_is_reported_not_skipped(
        self,
        git_repo: GitRepo,
    ) -> None:
        """Markers with no readable records exit non-zero and name the file.

        The skip itself is right — there is nothing to merge — but it used
        to print "No JSONL conflicts found" and exit 0 while the file still
        held <<<<<<<, sending the user into `git rebase --continue` on it.
        """
        repo = git_repo
        repo.storage_path.write_bytes(
            b"<<<<<<< HEAD\nnot-json\n=======\nalso-not-json\n>>>>>>> branch\n",
        )

        old_cwd = _in_repo(repo)
        try:
            exit_code, output = _run_dcat_rebase()
        finally:
            os.chdir(old_cwd)

        assert exit_code == 1
        assert "issues.jsonl" in output
        assert "No JSONL conflicts found" not in output
        assert _has_conflict_markers(repo.storage_path)


class TestGitRebaseThreeWayBase:
    """Where the common ancestor comes from, and what happens without one.

    Git's default merge.conflictStyle writes no ||||||| section, so the
    markers alone never carry a base and the dep/link merge degrades to a
    union that restores deletions. (dogcat-5cvm)
    """

    def test_dependency_removal_survives_a_real_rebase(
        self,
        git_repo: GitRepo,
    ) -> None:
        """A `dcat dep remove` on the rebased branch is not resurrected.

        The base comes from index stage 1, which git populates for every
        conflicted path while the rebase is in progress. Nothing here sets
        merge.conflictStyle, so this is the default-config path that used
        to silently restore the dependency.
        """
        repo = git_repo

        s = repo.storage()
        s.create(Issue(id="x", namespace="test", title="X"))
        s.create(Issue(id="y", namespace="test", title="Y"))
        s.add_dependency("test-x", "test-y", "blocks")
        repo.commit_all("Seed two issues and a dependency")

        # Upstream: an unrelated edit, so the rebase has to replay onto it.
        repo.create_branch("upstream")
        s = repo.storage()
        s.update("test-y", {"title": "Y edited upstream"})
        repo.commit_all("Edit Y upstream")

        repo.switch_branch("main")
        repo.create_branch("feature")
        s = repo.storage()
        s.remove_dependency("test-x", "test-y")
        repo.commit_all("Drop the dependency")

        rebase = repo.git("rebase", "upstream", check=False)
        assert rebase.returncode != 0, "expected the rebase to conflict"
        assert _has_conflict_markers(repo.storage_path)

        old_cwd = _in_repo(repo)
        try:
            exit_code, output = _run_dcat_rebase()
        finally:
            os.chdir(old_cwd)

        assert exit_code == 0, output
        assert not _has_conflict_markers(repo.storage_path)

        s = repo.storage()
        assert s.get_dependencies("test-x") == []

    def test_warns_when_no_base_is_reachable(
        self,
        git_repo: GitRepo,
    ) -> None:
        """Markers outside a conflicted operation get a union + a warning.

        There is no stage 1 to read here, so the resolve cannot honor a
        deletion. It says so rather than reporting a clean resolve.
        """
        repo = git_repo

        dep = orjson.dumps(
            {
                "record_type": "dependency",
                "issue_id": "test-x",
                "depends_on_id": "test-y",
                "type": "blocks",
                "created_at": "2026-01-01T00:00:00+00:00",
            }
        )
        other = orjson.dumps(
            {"record_type": "issue", "id": "z", "namespace": "test", "title": "Z"}
        )
        repo.storage_path.write_bytes(
            b"<<<<<<< HEAD\n" + dep + b"\n=======\n" + other + b"\n>>>>>>> branch\n",
        )

        old_cwd = _in_repo(repo)
        try:
            exit_code, output = _run_dcat_rebase()
        finally:
            os.chdir(old_cwd)

        assert exit_code == 0, output
        assert "Resolved issues.jsonl" in output
        assert "no common ancestor" in output
        assert not _has_conflict_markers(repo.storage_path)

    def test_unknown_record_kinds_survive_the_resolve(
        self,
        git_repo: GitRepo,
    ) -> None:
        """A record kind this dcat does not know is still in the file after.

        `dcat git rebase` writes merge_jsonl's output over the file, so the
        preservation guarantee from dogcat-68ij only holds if this caller
        keeps it too.
        """
        repo = git_repo

        future = orjson.dumps(
            {"record_type": "milestone", "id": "m1", "name": "v9"},
        )
        issue = orjson.dumps(
            {"record_type": "issue", "id": "a", "namespace": "test", "title": "A"}
        )
        repo.storage_path.write_bytes(
            future
            + b"\n<<<<<<< HEAD\n"
            + issue
            + b"\n=======\n"
            + issue
            + b"\n>>>>>>> b\n",
        )

        old_cwd = _in_repo(repo)
        try:
            exit_code, output = _run_dcat_rebase()
        finally:
            os.chdir(old_cwd)

        assert exit_code == 0, output
        records = [
            orjson.loads(line)
            for line in repo.storage_path.read_bytes().splitlines()
            if line.strip()
        ]
        assert any(r.get("record_type") == "milestone" for r in records)


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

    def test_malformed_records_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        """Malformed JSONL inside conflict sections produces a warning."""
        import logging

        from dogcat.merge_driver import parse_conflicted_jsonl

        good = orjson.dumps({"record_type": "issue", "id": "ok", "namespace": "t"})
        raw = b"<<<<<<< HEAD\nnot-json-data\n=======\n" + good + b"\n>>>>>>> branch\n"

        with caplog.at_level(logging.WARNING, logger="dogcat.merge_driver"):
            _, ours, theirs = parse_conflicted_jsonl(raw)

        assert len(ours) == 0
        assert len(theirs) == 1
        assert any(
            "malformed JSONL" in r.message and "ours" in r.message
            for r in caplog.records
        )

    def test_malformed_in_all_three_sections(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """diff3-style conflict with garbage in ours, base, AND theirs sections."""
        import logging

        from dogcat.merge_driver import parse_conflicted_jsonl

        raw = (
            b"<<<<<<< HEAD\n"
            b"{not-json-ours}\n"
            b"||||||| base\n"
            b"<<not-json-base>>\n"
            b"=======\n"
            b"=)not-json-theirs\n"
            b">>>>>>> branch\n"
        )
        with caplog.at_level(logging.WARNING, logger="dogcat.merge_driver"):
            base, ours, theirs = parse_conflicted_jsonl(raw)
        assert (base, ours, theirs) == ([], [], [])
        # Each warning expands its second %s arg (section name) into the
        # rendered message, so we just look for the section name in the text.
        rendered = " ".join(r.getMessage() for r in caplog.records)
        for section in ("ours", "base", "theirs"):
            assert section in rendered

    def test_repeated_conflict_blocks(self) -> None:
        """Two separate conflict regions in the same file both resolve."""
        from dogcat.merge_driver import parse_conflicted_jsonl

        a1 = orjson.dumps({"record_type": "issue", "id": "a1", "namespace": "t"})
        b1 = orjson.dumps({"record_type": "issue", "id": "b1", "namespace": "t"})
        a2 = orjson.dumps({"record_type": "issue", "id": "a2", "namespace": "t"})
        b2 = orjson.dumps({"record_type": "issue", "id": "b2", "namespace": "t"})

        raw = (
            b"<<<<<<< HEAD\n" + a1 + b"\n=======\n" + b1 + b"\n>>>>>>> branch\n"
            b"<<<<<<< HEAD\n" + a2 + b"\n=======\n" + b2 + b"\n>>>>>>> branch\n"
        )
        _, ours, theirs = parse_conflicted_jsonl(raw)
        assert {r["id"] for r in ours} == {"a1", "a2"}
        assert {r["id"] for r in theirs} == {"b1", "b2"}

    def test_conflict_with_only_dependency_records(self) -> None:
        """Conflict containing only dependency records (no issue records) parses."""
        from dogcat.merge_driver import parse_conflicted_jsonl

        dep_a = orjson.dumps(
            {
                "record_type": "dependency",
                "issue_id": "t-a",
                "depends_on_id": "t-b",
                "type": "blocks",
                "created_at": "2026-01-01T00:00:00",
            }
        )
        dep_b = orjson.dumps(
            {
                "record_type": "dependency",
                "issue_id": "t-c",
                "depends_on_id": "t-d",
                "type": "blocks",
                "created_at": "2026-01-02T00:00:00",
            }
        )
        raw = b"<<<<<<< HEAD\n" + dep_a + b"\n=======\n" + dep_b + b"\n>>>>>>> branch\n"
        _, ours, theirs = parse_conflicted_jsonl(raw)
        assert ours[0]["issue_id"] == "t-a"
        assert theirs[0]["issue_id"] == "t-c"

    def test_conflict_with_only_link_records(self) -> None:
        """Conflict containing only link records (no issue records) parses."""
        from dogcat.merge_driver import parse_conflicted_jsonl

        link_a = orjson.dumps(
            {
                "record_type": "link",
                "from_id": "t-a",
                "to_id": "t-b",
                "link_type": "relates_to",
                "created_at": "2026-01-01T00:00:00",
            }
        )
        link_b = orjson.dumps(
            {
                "record_type": "link",
                "from_id": "t-c",
                "to_id": "t-d",
                "link_type": "duplicates",
                "created_at": "2026-01-02T00:00:00",
            }
        )
        raw = (
            b"<<<<<<< HEAD\n" + link_a + b"\n=======\n" + link_b + b"\n>>>>>>> branch\n"
        )
        _, ours, theirs = parse_conflicted_jsonl(raw)
        assert ours[0]["from_id"] == "t-a"
        assert theirs[0]["from_id"] == "t-c"

    def test_dependency_with_unknown_issue_ids_still_parses(self) -> None:
        """Parser doesn't validate references — typo'd issue_ids still parse.

        Reference integrity is a separate validation pass; the parser's job
        is to faithfully extract records so downstream code can decide what
        to do.
        """
        from dogcat.merge_driver import parse_conflicted_jsonl

        dep = orjson.dumps(
            {
                "record_type": "dependency",
                "issue_id": "t-typo-aaa",
                "depends_on_id": "t-also-typo-bbb",
                "type": "blocks",
                "created_at": "2026-01-01T00:00:00",
            }
        )
        good = orjson.dumps({"record_type": "issue", "id": "ok", "namespace": "t"})
        raw = b"<<<<<<< HEAD\n" + dep + b"\n=======\n" + good + b"\n>>>>>>> branch\n"
        _, ours, theirs = parse_conflicted_jsonl(raw)
        assert ours[0]["issue_id"] == "t-typo-aaa"
        assert theirs[0]["id"] == "ok"
