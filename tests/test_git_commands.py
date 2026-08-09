"""Tests for git integration commands (dcat git check / dcat git setup).

Tests the git sub-app commands in dogcat.cli._cmd_docs.
"""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from dogcat.cli import app
from dogcat.constants import (
    GITATTRIBUTES_ENTRY,
    GITATTRIBUTES_LEGACY_ENTRIES,
    MAX_PRIME_TOKENS,
    MAX_PRIME_TOKENS_OPINIONATED,
    MERGE_DRIVER_CMD,
)
from dogcat.utils import estimate_tokens

if TYPE_CHECKING:
    from pathlib import Path

    import pytest
    from conftest import GitRepo

runner = CliRunner()


class TestGitCheck:
    """Test dcat git check command."""

    def test_check_all_pass(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """All checks pass when everything is configured."""
        repo = git_repo
        monkeypatch.chdir(repo.path)

        # Set up .gitignore with lock file
        (repo.path / ".gitignore").write_text(".dogcats/.issues.lock\n")

        # Set up merge driver
        repo.git("config", "merge.dcat-jsonl.driver", MERGE_DRIVER_CMD)

        # Set up .gitattributes
        (repo.path / ".gitattributes").write_text(
            f"{GITATTRIBUTES_ENTRY}\n",
        )

        result = runner.invoke(app, ["git", "check"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "All checks passed" in result.stdout

    def test_check_fails_no_gitignore(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Fails when .gitignore doesn't cover .issues.lock."""
        repo = git_repo
        monkeypatch.chdir(repo.path)

        # Set up merge driver + gitattributes but no gitignore
        repo.git("config", "merge.dcat-jsonl.driver", MERGE_DRIVER_CMD)
        (repo.path / ".gitattributes").write_text(
            f"{GITATTRIBUTES_ENTRY}\n",
        )

        result = runner.invoke(app, ["git", "check"], catch_exceptions=False)
        assert result.exit_code == 1
        assert ".issues.lock" in result.stdout

    def test_check_fails_no_merge_driver(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Fails when merge driver is not configured."""
        repo = git_repo
        monkeypatch.chdir(repo.path)

        (repo.path / ".gitignore").write_text(".dogcats/.issues.lock\n")

        result = runner.invoke(app, ["git", "check"], catch_exceptions=False)
        assert result.exit_code == 1
        assert "merge driver" in result.stdout.lower()

    def test_check_fails_no_gitattributes(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Fails when .gitattributes is missing merge driver entry."""
        repo = git_repo
        monkeypatch.chdir(repo.path)

        (repo.path / ".gitignore").write_text(".dogcats/.issues.lock\n")
        repo.git("config", "merge.dcat-jsonl.driver", MERGE_DRIVER_CMD)

        result = runner.invoke(app, ["git", "check"], catch_exceptions=False)
        assert result.exit_code == 1
        assert ".gitattributes" in result.stdout

    def test_check_json_output(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """JSON output includes all check results."""
        monkeypatch.chdir(git_repo.path)

        result = runner.invoke(
            app,
            ["git", "check", "--json"],
            catch_exceptions=False,
        )
        data = json.loads(result.stdout)
        assert "status" in data
        assert "checks" in data
        assert "git_repo" in data["checks"]
        assert "lock_ignored" in data["checks"]
        assert "merge_driver" in data["checks"]
        assert "gitattributes" in data["checks"]

    def test_check_gitignore_line_based_matching(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Adding .dogcats/.issues.lock should NOT trigger the dogcats-ignored warning.

        This is a regression test for a substring matching bug where
        '.dogcats/' inside '.dogcats/.issues.lock' was falsely detected
        as the entire .dogcats/ directory being ignored.
        """
        repo = git_repo
        monkeypatch.chdir(repo.path)

        (repo.path / ".gitignore").write_text(".dogcats/.issues.lock\n")

        # Set up merge driver + gitattributes so those checks pass
        repo.git("config", "merge.dcat-jsonl.driver", MERGE_DRIVER_CMD)
        (repo.path / ".gitattributes").write_text(
            f"{GITATTRIBUTES_ENTRY}\n",
        )

        result = runner.invoke(app, ["git", "check"], catch_exceptions=False)
        assert result.exit_code == 0
        # Should say "shared with team", NOT "in .gitignore"
        assert "shared with team" in result.stdout
        assert "not shared with team" not in result.stdout

    def test_check_dogcats_in_gitignore_shows_warning(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When .dogcats/ is fully in .gitignore, show informational warning."""
        repo = git_repo
        monkeypatch.chdir(repo.path)

        (repo.path / ".gitignore").write_text(".dogcats/\n")

        result = runner.invoke(app, ["git", "check"], catch_exceptions=False)
        # Optional check — shown as informational warning
        assert "not shared with team" in result.stdout

    def test_check_fails_wrong_merge_driver_command(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Fails when merge driver is configured with the old command."""
        repo = git_repo
        monkeypatch.chdir(repo.path)

        (repo.path / ".gitignore").write_text(".dogcats/.issues.lock\n")
        # Configure with old/wrong command
        repo.git("config", "merge.dcat-jsonl.driver", "dcat-merge-jsonl %O %A %B")
        (repo.path / ".gitattributes").write_text(
            f"{GITATTRIBUTES_ENTRY}\n",
        )

        result = runner.invoke(app, ["git", "check"], catch_exceptions=False)
        assert result.exit_code == 1
        assert "wrong command" in result.stdout.lower()

    def test_check_fail_description_shown(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Failed checks show the fail description, not the pass description."""
        monkeypatch.chdir(git_repo.path)
        # No gitignore, no merge driver, no gitattributes

        result = runner.invoke(app, ["git", "check"], catch_exceptions=False)
        assert result.exit_code == 1
        # Should show fail descriptions
        assert "does not include .issues.lock" in result.stdout
        assert "Not in a git repository" not in result.stdout  # we ARE in a git repo
        assert "not configured" in result.stdout
        assert "missing" in result.stdout.lower()

    def test_check_not_in_git_repo_shows_fail_description(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Outside a git repo, shows 'Not in a git repository'."""
        monkeypatch.chdir(tmp_path)
        # Create .dogcats so find_dogcats_dir works
        dogcats_dir = tmp_path / ".dogcats"
        dogcats_dir.mkdir()
        (dogcats_dir / "issues.jsonl").touch()

        result = runner.invoke(app, ["git", "check"], catch_exceptions=False)
        assert result.exit_code == 1
        assert "Not in a git repository" in result.stdout

    def test_check_flags_narrow_only_gitattributes(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A pre-widening .gitattributes must not pass green.

        The narrow pattern still spells 'merge=dcat-jsonl', so the old
        substring test called it configured while every
        .dogcats/archive/*.jsonl merged with git's default text driver.
        (dogcat-3lnu)
        """
        repo = git_repo
        monkeypatch.chdir(repo.path)

        (repo.path / ".gitignore").write_text(".dogcats/.issues.lock\n")
        repo.git("config", "merge.dcat-jsonl.driver", MERGE_DRIVER_CMD)
        (repo.path / ".gitattributes").write_text(
            f"{GITATTRIBUTES_LEGACY_ENTRIES[0]}\n",
        )

        result = runner.invoke(app, ["git", "check"], catch_exceptions=False)
        assert result.exit_code == 1
        assert "archive" in result.stdout
        assert "dcat git setup" in result.stdout

    def test_check_accepts_a_hand_written_equivalent_pattern(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A user-written pattern with the same effect passes.

        The check asks `git check-attr` what the rules resolve to rather
        than matching dcat's exact spelling, so a broader hand-written
        pattern is not reported as a misconfiguration. (dogcat-3lnu)
        """
        repo = git_repo
        monkeypatch.chdir(repo.path)

        (repo.path / ".gitignore").write_text(".dogcats/.issues.lock\n")
        repo.git("config", "merge.dcat-jsonl.driver", MERGE_DRIVER_CMD)
        (repo.path / ".gitattributes").write_text(".dogcats/** merge=dcat-jsonl\n")

        result = runner.invoke(app, ["git", "check"], catch_exceptions=False)
        assert result.exit_code == 0, result.stdout
        assert "All checks passed" in result.stdout

    def test_check_skipped_when_git_tracking_disabled(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Git check exits cleanly when git_tracking=false."""
        from dogcat.config import DogcatConfig, save_config

        monkeypatch.chdir(git_repo.path)
        save_config(
            str(git_repo.dogcats_dir),
            DogcatConfig.from_dict({"git_tracking": False}),
        )

        result = runner.invoke(app, ["git", "check"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Git tracking is disabled" in result.stdout

    def test_check_skipped_json_when_git_tracking_disabled(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Git check --json returns skipped status when git_tracking=false."""
        from dogcat.config import DogcatConfig, save_config

        monkeypatch.chdir(git_repo.path)
        save_config(
            str(git_repo.dogcats_dir),
            DogcatConfig.from_dict({"git_tracking": False}),
        )

        result = runner.invoke(
            app,
            ["git", "check", "--json"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["status"] == "skipped"


class TestGitSetup:
    """Test dcat git setup command."""

    def test_setup_creates_gitattributes(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Setup creates .gitattributes with merge driver entry."""
        repo = git_repo
        monkeypatch.chdir(repo.path)

        result = runner.invoke(app, ["git", "setup"], catch_exceptions=False)
        assert result.exit_code == 0

        gitattrs = repo.path / ".gitattributes"
        assert gitattrs.exists()
        assert "merge=dcat-jsonl" in gitattrs.read_text()

    def test_setup_covers_archive_subdirectory(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The written pattern must reach .dogcats/archive/*.jsonl.

        A gitattributes glob without `**` does not cross a directory
        separator, so the old `.dogcats/*.jsonl` left the tracked archive
        files on git's default text merge, free to take conflict markers.
        `git check-attr` is the only thing that proves the pattern, since
        the file contents look plausible either way. (dogcat-1xgi)
        """
        repo = git_repo
        monkeypatch.chdir(repo.path)

        result = runner.invoke(app, ["git", "setup"], catch_exceptions=False)
        assert result.exit_code == 0

        archive = repo.path / ".dogcats" / "archive"
        archive.mkdir(parents=True, exist_ok=True)
        (archive / "closed-2026-01-01T00-00-00.jsonl").touch()
        (repo.path / ".dogcats" / "issues.jsonl").touch()

        checked = subprocess.run(
            [
                "git",
                "check-attr",
                "merge",
                ".dogcats/issues.jsonl",
                ".dogcats/archive/closed-2026-01-01T00-00-00.jsonl",
            ],
            cwd=repo.path,
            capture_output=True,
            text=True,
            check=True,
        )
        lines = checked.stdout.strip().splitlines()
        assert len(lines) == 2
        for line in lines:
            assert line.endswith("merge: dcat-jsonl"), line

    def test_setup_qualifies_what_the_driver_resolves(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The closing line must not promise unconditional auto-resolution.

        It read "The merge driver will auto-resolve JSONL conflicts."
        `dcat git guide` says *most* conflicts and that a rebase does not
        invoke the driver at all, so a reader who trusted the setup line
        would skip `dcat git rebase` and hand-resolve the JSONL — the edit
        that corrupts the event log. (dogcat-1trf)
        """
        monkeypatch.chdir(git_repo.path)

        result = runner.invoke(app, ["git", "setup"], catch_exceptions=False)

        assert result.exit_code == 0
        assert "auto-resolves most JSONL conflicts on merge" in result.stdout
        assert "dcat git rebase" in result.stdout
        assert "will auto-resolve JSONL conflicts" not in result.stdout

    def test_setup_configures_merge_driver(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Setup configures the merge driver in git config."""
        repo = git_repo
        monkeypatch.chdir(repo.path)

        runner.invoke(app, ["git", "setup"], catch_exceptions=False)

        result = subprocess.run(
            ["git", "config", "merge.dcat-jsonl.driver"],
            cwd=repo.path,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0
        assert MERGE_DRIVER_CMD in result.stdout

    def test_setup_idempotent(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Running setup twice doesn't duplicate .gitattributes entries."""
        monkeypatch.chdir(git_repo.path)

        runner.invoke(app, ["git", "setup"], catch_exceptions=False)
        runner.invoke(app, ["git", "setup"], catch_exceptions=False)

        gitattrs = git_repo.path / ".gitattributes"
        content = gitattrs.read_text()
        assert content.count("merge=dcat-jsonl") == 1

    def test_setup_replaces_narrow_entry_in_place(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Upgrading leaves one entry, the widened one — not two.

        The guard tested the NEW string for membership, so a file holding
        the old narrow line never matched and setup appended beside it,
        accumulating a stale line per upgrade. (dogcat-12v8)
        """
        repo = git_repo
        monkeypatch.chdir(repo.path)

        gitattrs = repo.path / ".gitattributes"
        gitattrs.write_text(f"*.txt text\n{GITATTRIBUTES_LEGACY_ENTRIES[0]}\n")

        result = runner.invoke(app, ["git", "setup"], catch_exceptions=False)
        assert result.exit_code == 0

        content = gitattrs.read_text()
        assert content.count("merge=dcat-jsonl") == 1
        assert GITATTRIBUTES_ENTRY in content
        assert GITATTRIBUTES_LEGACY_ENTRIES[0] not in content
        assert "*.txt text" in content

    def test_setup_collapses_an_already_duplicated_entry(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A checkout already carrying both lines comes back with one.

        This is the state the append bug left behind, so setup has to be
        the way out of it and not just refuse to make it worse.
        (dogcat-12v8)
        """
        repo = git_repo
        monkeypatch.chdir(repo.path)

        gitattrs = repo.path / ".gitattributes"
        gitattrs.write_text(
            f"{GITATTRIBUTES_LEGACY_ENTRIES[0]}\n{GITATTRIBUTES_ENTRY}\n",
        )

        result = runner.invoke(app, ["git", "setup"], catch_exceptions=False)
        assert result.exit_code == 0
        assert gitattrs.read_text().count("merge=dcat-jsonl") == 1

    def test_setup_leaves_a_hand_written_equivalent_alone(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Only dcat's own old spelling is rewritten; the user's line stays.

        Setup adds its entry beside a broader hand-written rule rather
        than replacing it — an extra visible line beats deleting a rule
        the user may be relying on for other paths. (dogcat-12v8)
        """
        repo = git_repo
        monkeypatch.chdir(repo.path)

        gitattrs = repo.path / ".gitattributes"
        gitattrs.write_text(".dogcats/** merge=dcat-jsonl\n")

        result = runner.invoke(app, ["git", "setup"], catch_exceptions=False)
        assert result.exit_code == 0

        content = gitattrs.read_text()
        assert ".dogcats/** merge=dcat-jsonl" in content
        assert GITATTRIBUTES_ENTRY in content

    def test_setup_appends_to_existing_gitattributes(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Setup appends to an existing .gitattributes without overwriting."""
        repo = git_repo
        monkeypatch.chdir(repo.path)

        gitattrs = repo.path / ".gitattributes"
        gitattrs.write_text("*.txt text\n")

        runner.invoke(app, ["git", "setup"], catch_exceptions=False)

        content = gitattrs.read_text()
        assert "*.txt text" in content
        assert "merge=dcat-jsonl" in content

    def test_setup_keeps_crlf_endings_when_replacing_the_narrow_entry(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A CRLF .gitattributes comes back CRLF, one line changed.

        The rewrite went through `splitlines()` and rejoined on LF, so every
        line of a CRLF file changed and the user reviewed a whole-file diff
        for a one-line upgrade. (dogcat-5xyt)
        """
        repo = git_repo
        monkeypatch.chdir(repo.path)

        gitattrs = repo.path / ".gitattributes"
        gitattrs.write_bytes(
            f"*.txt text\r\n{GITATTRIBUTES_LEGACY_ENTRIES[0]}\r\n".encode(),
        )

        result = runner.invoke(app, ["git", "setup"], catch_exceptions=False)
        assert result.exit_code == 0

        assert gitattrs.read_bytes() == (
            f"*.txt text\r\n{GITATTRIBUTES_ENTRY}\r\n".encode()
        )

    def test_setup_keeps_lf_endings_when_replacing_the_narrow_entry(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """An LF file stays LF — the CRLF fix must not invert the bug."""
        repo = git_repo
        monkeypatch.chdir(repo.path)

        gitattrs = repo.path / ".gitattributes"
        gitattrs.write_bytes(
            f"*.txt text\n{GITATTRIBUTES_LEGACY_ENTRIES[0]}\n".encode(),
        )

        result = runner.invoke(app, ["git", "setup"], catch_exceptions=False)
        assert result.exit_code == 0

        assert gitattrs.read_bytes() == (
            f"*.txt text\n{GITATTRIBUTES_ENTRY}\n".encode()
        )

    def test_setup_leaves_mixed_endings_as_mixed_as_it_found_them(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Each surviving line keeps its own terminator.

        Rejoining on one dominant ending would rewrite the minority lines —
        the same whole-file diff the fix exists to avoid, just narrower.
        (dogcat-5xyt)
        """
        repo = git_repo
        monkeypatch.chdir(repo.path)

        gitattrs = repo.path / ".gitattributes"
        gitattrs.write_bytes(
            f"*.txt text\r\n*.md text\n{GITATTRIBUTES_LEGACY_ENTRIES[0]}\r\n".encode(),
        )

        result = runner.invoke(app, ["git", "setup"], catch_exceptions=False)
        assert result.exit_code == 0

        assert gitattrs.read_bytes() == (
            f"*.txt text\r\n*.md text\n{GITATTRIBUTES_ENTRY}\r\n".encode()
        )

    def test_setup_appends_without_a_blank_line(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The added path emitted its separator newline unconditionally.

        A file already ending in a newline therefore gained an empty line
        along with the entry. (dogcat-5xyt)
        """
        repo = git_repo
        monkeypatch.chdir(repo.path)

        gitattrs = repo.path / ".gitattributes"
        gitattrs.write_bytes(b"*.txt text\n")

        result = runner.invoke(app, ["git", "setup"], catch_exceptions=False)
        assert result.exit_code == 0

        assert gitattrs.read_bytes() == (
            f"*.txt text\n{GITATTRIBUTES_ENTRY}\n".encode()
        )

    def test_setup_appends_to_a_file_with_no_trailing_newline(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A missing final newline is supplied, not doubled (dogcat-5xyt)."""
        repo = git_repo
        monkeypatch.chdir(repo.path)

        gitattrs = repo.path / ".gitattributes"
        gitattrs.write_bytes(b"*.txt text")

        result = runner.invoke(app, ["git", "setup"], catch_exceptions=False)
        assert result.exit_code == 0

        assert gitattrs.read_bytes() == (
            f"*.txt text\n{GITATTRIBUTES_ENTRY}\n".encode()
        )

    def test_setup_appends_with_the_endings_the_file_already_uses(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A CRLF file gets a CRLF-terminated entry on the added path."""
        repo = git_repo
        monkeypatch.chdir(repo.path)

        gitattrs = repo.path / ".gitattributes"
        gitattrs.write_bytes(b"*.txt text\r\n")

        result = runner.invoke(app, ["git", "setup"], catch_exceptions=False)
        assert result.exit_code == 0

        assert gitattrs.read_bytes() == (
            f"*.txt text\r\n{GITATTRIBUTES_ENTRY}\r\n".encode()
        )

    def test_setup_leaves_an_already_configured_file_byte_identical(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The present path must not touch the file at all, CRLF included."""
        repo = git_repo
        monkeypatch.chdir(repo.path)

        original = f"*.txt text\r\n{GITATTRIBUTES_ENTRY}\r\n".encode()
        gitattrs = repo.path / ".gitattributes"
        gitattrs.write_bytes(original)

        result = runner.invoke(app, ["git", "setup"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "already configured" in result.stdout
        assert gitattrs.read_bytes() == original

    def test_setup_then_check_passes(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """After setup, the merge driver checks in git check should pass."""
        repo = git_repo
        monkeypatch.chdir(repo.path)

        # Add .gitignore for complete pass
        (repo.path / ".gitignore").write_text(".dogcats/.issues.lock\n")

        runner.invoke(app, ["git", "setup"], catch_exceptions=False)

        result = runner.invoke(app, ["git", "check"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "All checks passed" in result.stdout

    def test_setup_from_subdirectory_creates_gitattributes_at_root(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Setup from a subdirectory creates .gitattributes at repo root."""
        repo = git_repo
        subdir = repo.path / "some" / "nested" / "dir"
        subdir.mkdir(parents=True)
        monkeypatch.chdir(subdir)

        result = runner.invoke(app, ["git", "setup"], catch_exceptions=False)
        assert result.exit_code == 0

        # .gitattributes should be at repo root, NOT in subdirectory
        assert (repo.path / ".gitattributes").exists()
        assert "merge=dcat-jsonl" in (repo.path / ".gitattributes").read_text()
        assert not (subdir / ".gitattributes").exists()

    def test_check_from_subdirectory_finds_gitattributes_at_root(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Check from a subdirectory finds .gitattributes at repo root."""
        repo = git_repo

        # Configure everything at repo root
        (repo.path / ".gitignore").write_text(".dogcats/.issues.lock\n")
        repo.git("config", "merge.dcat-jsonl.driver", MERGE_DRIVER_CMD)
        (repo.path / ".gitattributes").write_text(
            f"{GITATTRIBUTES_ENTRY}\n",
        )

        # Run check from subdirectory
        subdir = repo.path / "src" / "lib"
        subdir.mkdir(parents=True)
        monkeypatch.chdir(subdir)

        result = runner.invoke(app, ["git", "check"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "All checks passed" in result.stdout


class TestGitMergeDriver:
    """Test dcat git merge-driver subcommand."""

    def test_merge_driver_merges_non_overlapping_issues(
        self,
        tmp_path: Path,
    ) -> None:
        """Merge driver merges two files with non-overlapping issues."""
        import orjson

        base = tmp_path / "base.jsonl"
        ours = tmp_path / "ours.jsonl"
        theirs = tmp_path / "theirs.jsonl"

        base.write_text("")
        ours.write_bytes(
            orjson.dumps(
                {
                    "record_type": "issue",
                    "id": "aaa",
                    "namespace": "dc",
                    "title": "Issue A",
                    "updated_at": "2025-01-01T00:00:00",
                },
            )
            + b"\n",
        )
        theirs.write_bytes(
            orjson.dumps(
                {
                    "record_type": "issue",
                    "id": "bbb",
                    "namespace": "dc",
                    "title": "Issue B",
                    "updated_at": "2025-01-01T00:00:00",
                },
            )
            + b"\n",
        )

        result = runner.invoke(
            app,
            ["git", "merge-driver", str(base), str(ours), str(theirs)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0

        merged = [orjson.loads(line) for line in ours.read_bytes().splitlines() if line]
        ids = {r["id"] for r in merged}
        assert ids == {"aaa", "bbb"}

    def test_merge_driver_is_hidden(self) -> None:
        """Merge-driver command should not appear in git help output."""
        result = runner.invoke(app, ["git", "--help"], catch_exceptions=False)
        assert "merge-driver" not in result.stdout


def _archive_issue_line(issue_id: str) -> bytes:
    """Serialize one closed issue record the way an archive file holds it."""
    import orjson

    return (
        orjson.dumps(
            {
                "record_type": "issue",
                "id": issue_id,
                "namespace": "test",
                "title": f"Issue {issue_id}",
                "status": "closed",
                "priority": 2,
                "issue_type": "task",
                "updated_at": "2026-01-01T00:00:00+00:00",
            },
        )
        + b"\n"
    )


class TestArchiveFileMerging:
    """End-to-end coverage for .dogcats/archive/*.jsonl (dogcat-5tc1).

    The widened .gitattributes pattern and `dcat git rebase`'s switch to
    rglob both exist to bring tracked archive files under dogcat's merge
    driver. Everything below the archive line in the rest of the suite
    exercises issues.jsonl, which the pre-widening pattern already covered,
    so these are the only tests that would fail if the widening were
    reverted.
    """

    def test_conflicted_archive_file_merges_without_markers(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Two branches editing one tracked archive file merge cleanly."""
        repo = git_repo
        monkeypatch.chdir(repo.path)

        archive = repo.dogcats_dir / "archive" / "closed-2026-01-01T00-00-00.jsonl"
        archive.parent.mkdir(parents=True)
        archive.write_bytes(_archive_issue_line("seed"))
        repo.git("config", "merge.dcat-jsonl.driver", MERGE_DRIVER_CMD)
        (repo.path / ".gitattributes").write_text(f"{GITATTRIBUTES_ENTRY}\n")
        repo.commit_all("Seed archive and merge driver config")

        repo.create_branch("branch-a")
        archive.write_bytes(_archive_issue_line("seed") + _archive_issue_line("aaa"))
        repo.commit_all("Archive an issue on branch-a")

        repo.switch_branch("main")
        repo.create_branch("branch-b")
        archive.write_bytes(_archive_issue_line("seed") + _archive_issue_line("bbb"))
        repo.commit_all("Archive an issue on branch-b")

        repo.switch_branch("main")
        assert repo.merge("branch-a").returncode == 0
        merged = repo.merge("branch-b")
        assert merged.returncode == 0, f"{merged.stdout}\n{merged.stderr}"

        content = archive.read_text()
        assert "<<<<<<<" not in content
        assert ">>>>>>>" not in content
        ids = {json.loads(line)["id"] for line in content.splitlines() if line.strip()}
        assert ids == {"seed", "aaa", "bbb"}

    def test_rebase_reaches_an_archive_file(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """`dcat git rebase` resolves a conflicted file under archive/.

        The scan is rglob rather than glob precisely so it descends into
        archive/; with glob the file below keeps its markers and the
        command reports no conflicts at all.
        """
        repo = git_repo
        monkeypatch.chdir(repo.path)

        archive = repo.dogcats_dir / "archive" / "closed-2026-02-02T00-00-00.jsonl"
        archive.parent.mkdir(parents=True)
        archive.write_bytes(
            b"<<<<<<< HEAD\n"
            + _archive_issue_line("aaa")
            + b"=======\n"
            + _archive_issue_line("bbb")
            + b">>>>>>> branch-b\n",
        )

        result = runner.invoke(app, ["git", "rebase"], catch_exceptions=False)

        assert result.exit_code == 0, result.stdout
        assert f"Resolved {archive.name}" in result.stdout
        content = archive.read_text()
        assert "<<<<<<<" not in content
        ids = {json.loads(line)["id"] for line in content.splitlines() if line.strip()}
        assert ids == {"aaa", "bbb"}


class TestPrimeGitHealth:
    """Test git health checks in dcat prime."""

    def test_prime_in_git_repo_shows_git_health(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Standard prime in a git repo shows git health section."""
        monkeypatch.chdir(git_repo.path)
        result = runner.invoke(app, ["prime"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "DOGCAT WORKFLOW GUIDE" in result.stdout
        assert "Dogcat Health Check" in result.stdout

    def test_prime_shows_failing_checks_with_gentle_nudge(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """In a git repo with issues, shows failing checks and gentle suggestions."""
        monkeypatch.chdir(git_repo.path)
        # No gitignore, no merge driver, no gitattributes
        result = runner.invoke(
            app,
            ["prime"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Dogcat Health Check" in result.stdout
        assert "Suggestion:" in result.stdout
        assert "merge driver" in result.stdout.lower()
        assert "dcat config set git_tracking false" in result.stdout

    def test_prime_in_git_repo_all_pass(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """In a fully configured git repo, shows all checks passed."""
        repo = git_repo
        monkeypatch.chdir(repo.path)

        (repo.path / ".gitignore").write_text(".dogcats/.issues.lock\n")
        repo.git("config", "merge.dcat-jsonl.driver", MERGE_DRIVER_CMD)
        (repo.path / ".gitattributes").write_text(
            f"{GITATTRIBUTES_ENTRY}\n",
        )

        result = runner.invoke(
            app,
            ["prime"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "✓" in result.stdout
        assert "dcat config set git_tracking false" not in result.stdout

    def test_prime_outside_git_repo_skips_git_checks(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Outside a git repo, skips git checks gracefully."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(
            app,
            ["prime"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Dogcat Health Check" not in result.stdout

    def test_prime_skips_git_checks_when_tracking_disabled(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When git_tracking=false in config, prime skips git health section."""
        from dogcat.config import DogcatConfig, save_config

        monkeypatch.chdir(git_repo.path)
        save_config(
            str(git_repo.dogcats_dir),
            DogcatConfig.from_dict({"git_tracking": False}),
        )

        result = runner.invoke(
            app,
            ["prime"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Dogcat Health Check" not in result.stdout

    def test_prime_opinionated_includes_extra_rules(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--opinionated flag injects prescriptive rules into Rules section."""
        monkeypatch.chdir(git_repo.path)
        result = runner.invoke(
            app,
            ["prime", "--opinionated"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Before setting in_review" in result.stdout
        assert "Dogcat Health Check" in result.stdout

    def test_prime_base_excludes_opinionated_rules(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Base prime does not include opinionated rules."""
        monkeypatch.chdir(git_repo.path)
        result = runner.invoke(
            app,
            ["prime"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Before setting in_review" not in result.stdout

    def test_prime_token_count_within_limit(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Dcat prime output stays within the MAX_PRIME_TOKENS budget."""
        repo = git_repo
        monkeypatch.chdir(repo.path)

        # Set up a repo where all health checks pass
        (repo.path / ".gitignore").write_text(".dogcats/.issues.lock\n")
        repo.git("config", "merge.dcat-jsonl.driver", MERGE_DRIVER_CMD)
        (repo.path / ".gitattributes").write_text(
            f"{GITATTRIBUTES_ENTRY}\n",
        )

        result = runner.invoke(app, ["prime"], catch_exceptions=False)
        assert result.exit_code == 0

        estimated_tokens = estimate_tokens(result.stdout)
        assert estimated_tokens <= MAX_PRIME_TOKENS, (
            f"dcat prime output is ~{estimated_tokens} estimated tokens, "
            f"exceeds limit of {MAX_PRIME_TOKENS}"
        )

    def test_prime_opinionated_token_count_within_limit(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Opinionated prime output stays within token budget."""
        repo = git_repo
        monkeypatch.chdir(repo.path)

        # Set up a repo where all health checks pass
        (repo.path / ".gitignore").write_text(".dogcats/.issues.lock\n")
        repo.git("config", "merge.dcat-jsonl.driver", MERGE_DRIVER_CMD)
        (repo.path / ".gitattributes").write_text(
            f"{GITATTRIBUTES_ENTRY}\n",
        )

        result = runner.invoke(
            app,
            ["prime", "--opinionated"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0

        estimated_tokens = estimate_tokens(result.stdout)
        assert estimated_tokens <= MAX_PRIME_TOKENS_OPINIONATED, (
            f"dcat prime --opinionated output is "
            f"~{estimated_tokens} estimated tokens, "
            f"exceeds limit of {MAX_PRIME_TOKENS_OPINIONATED}"
        )

    def test_prime_replay_preserves_opinionated(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--replay replays --opinionated from a previous prime invocation."""
        monkeypatch.chdir(git_repo.path)

        # First call with --opinionated saves the flag
        result = runner.invoke(app, ["prime", "--opinionated"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Before setting in_review" in result.stdout

        # Replay without explicit --opinionated should still include it
        result = runner.invoke(app, ["prime", "--replay"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Before setting in_review" in result.stdout

    def test_prime_replay_without_prior_invocation(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--replay with no saved flags falls back to defaults."""
        monkeypatch.chdir(git_repo.path)

        result = runner.invoke(app, ["prime", "--replay"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Before setting in_review" not in result.stdout

    def test_prime_replay_after_plain_prime(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--replay after a plain prime does not include opinionated rules."""
        monkeypatch.chdir(git_repo.path)

        # First call without --opinionated
        runner.invoke(app, ["prime"], catch_exceptions=False)

        # Replay should not include opinionated rules
        result = runner.invoke(app, ["prime", "--replay"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Before setting in_review" not in result.stdout

    def test_plain_prime_overwrites_opinionated_cache(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A plain 'dcat prime' overwrites a saved --opinionated flag."""
        monkeypatch.chdir(git_repo.path)

        # Save --opinionated to cache
        runner.invoke(app, ["prime", "--opinionated"], catch_exceptions=False)

        # Plain prime overwrites the cache
        runner.invoke(app, ["prime"], catch_exceptions=False)

        # Replay should reflect the last invocation (plain, no --opinionated)
        result = runner.invoke(app, ["prime", "--replay"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Before setting in_review" not in result.stdout
