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


# ---------------------------------------------------------------------------
# dcat git check
# ---------------------------------------------------------------------------


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
            ".dogcats/*.jsonl merge=dcat-jsonl\n",
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
            ".dogcats/*.jsonl merge=dcat-jsonl\n",
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
            ".dogcats/*.jsonl merge=dcat-jsonl\n",
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
            ".dogcats/*.jsonl merge=dcat-jsonl\n",
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

    def test_check_skipped_when_git_tracking_disabled(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Git check exits cleanly when git_tracking=false."""
        from dogcat.config import save_config

        monkeypatch.chdir(git_repo.path)
        save_config(str(git_repo.dogcats_dir), {"git_tracking": False})

        result = runner.invoke(app, ["git", "check"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Git tracking is disabled" in result.stdout

    def test_check_skipped_json_when_git_tracking_disabled(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Git check --json returns skipped status when git_tracking=false."""
        from dogcat.config import save_config

        monkeypatch.chdir(git_repo.path)
        save_config(str(git_repo.dogcats_dir), {"git_tracking": False})

        result = runner.invoke(
            app,
            ["git", "check", "--json"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["status"] == "skipped"


# ---------------------------------------------------------------------------
# dcat git setup
# ---------------------------------------------------------------------------


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
            ".dogcats/*.jsonl merge=dcat-jsonl\n",
        )

        # Run check from subdirectory
        subdir = repo.path / "src" / "lib"
        subdir.mkdir(parents=True)
        monkeypatch.chdir(subdir)

        result = runner.invoke(app, ["git", "check"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "All checks passed" in result.stdout


# ---------------------------------------------------------------------------
# dcat git merge-driver
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# dcat prime --opinionated
# ---------------------------------------------------------------------------


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
        assert "Git Integration Health" in result.stdout

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
        assert "Git Integration Health" in result.stdout
        assert "Consider running:" in result.stdout
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
            ".dogcats/*.jsonl merge=dcat-jsonl\n",
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
        assert "Git Integration Health" not in result.stdout

    def test_prime_skips_git_checks_when_tracking_disabled(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When git_tracking=false in config, prime skips git health section."""
        from dogcat.config import save_config

        monkeypatch.chdir(git_repo.path)
        save_config(str(git_repo.dogcats_dir), {"git_tracking": False})

        result = runner.invoke(
            app,
            ["prime"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Git Integration Health" not in result.stdout

    def test_prime_opinionated_still_works(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--opinionated flag still works (git checks run in standard prime)."""
        monkeypatch.chdir(git_repo.path)
        result = runner.invoke(
            app,
            ["prime", "--opinionated"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Git Integration Health" in result.stdout

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
            ".dogcats/*.jsonl merge=dcat-jsonl\n",
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
            ".dogcats/*.jsonl merge=dcat-jsonl\n",
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
