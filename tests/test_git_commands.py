"""Tests for git integration commands (dcat git check / dcat git setup).

Tests the git sub-app commands in dogcat.cli._cmd_docs.
"""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from dogcat.cli import app

if TYPE_CHECKING:
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
        repo.git("config", "merge.dcat-jsonl.driver", "dcat-merge-jsonl %O %A %B")

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
        repo.git("config", "merge.dcat-jsonl.driver", "dcat-merge-jsonl %O %A %B")
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
        repo.git("config", "merge.dcat-jsonl.driver", "dcat-merge-jsonl %O %A %B")

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
        repo.git("config", "merge.dcat-jsonl.driver", "dcat-merge-jsonl %O %A %B")
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
        assert "not configured" in result.stdout
        assert "missing" in result.stdout.lower()


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
        assert "dcat-merge-jsonl" in result.stdout

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
