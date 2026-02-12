"""Tests for dcat diff CLI command."""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from dogcat.cli import app

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()


@pytest.fixture
def git_workspace(tmp_path: Path) -> Path:
    """Create a temporary git repo with initialized .dogcats."""
    subprocess.run(
        ["git", "init", str(tmp_path)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "test@test.com"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.name", "Test"],
        check=True,
        capture_output=True,
    )

    dogcats_dir = tmp_path / ".dogcats"
    result = runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])
    assert result.exit_code == 0

    # Initial commit with empty .dogcats
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", ".dogcats/"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-m", "init"],
        check=True,
        capture_output=True,
    )

    return tmp_path


def _create_issue(dogcats_dir: Path, title: str) -> str:
    args = ["create", title, "--dogcats-dir", str(dogcats_dir)]
    result = runner.invoke(app, args)
    assert result.exit_code == 0
    for word in result.stdout.split():
        if word.startswith("dc-") or (len(word) > 3 and "-" in word):
            return word.rstrip(":")
    msg = f"Could not find issue ID in output: {result.stdout}"
    raise ValueError(msg)


class TestDiff:
    """Tests for diff."""

    def test_diff_no_changes(self, git_workspace: Path) -> None:
        """Test diff no changes."""
        dogcats_dir = git_workspace / ".dogcats"
        result = runner.invoke(
            app,
            ["diff", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No changes" in result.stdout

    def test_diff_shows_new_issue(self, git_workspace: Path) -> None:
        """Test diff shows new issue."""
        dogcats_dir = git_workspace / ".dogcats"
        _create_issue(dogcats_dir, "New bug")

        result = runner.invoke(
            app,
            ["diff", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Created" in result.stdout
        assert "New bug" in result.stdout

    def test_diff_shows_updated_issue(self, git_workspace: Path) -> None:
        """Test diff shows updated issue."""
        dogcats_dir = git_workspace / ".dogcats"
        issue_id = _create_issue(dogcats_dir, "To update")

        # Commit the creation
        subprocess.run(
            ["git", "-C", str(git_workspace), "add", ".dogcats/"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(git_workspace), "commit", "-m", "add issue"],
            check=True,
            capture_output=True,
        )

        # Now update the issue
        runner.invoke(
            app,
            [
                "update",
                issue_id,
                "--status",
                "in_progress",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["diff", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Updated" in result.stdout
        assert "status" in result.stdout

    def test_diff_shows_closed_issue(self, git_workspace: Path) -> None:
        """Test diff shows closed issue."""
        dogcats_dir = git_workspace / ".dogcats"
        issue_id = _create_issue(dogcats_dir, "To close")

        # Commit the creation
        subprocess.run(
            ["git", "-C", str(git_workspace), "add", ".dogcats/"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(git_workspace), "commit", "-m", "add issue"],
            check=True,
            capture_output=True,
        )

        # Close the issue
        runner.invoke(
            app,
            ["close", issue_id, "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["diff", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Closed" in result.stdout

    def test_diff_new_and_closed_shows_closed(self, git_workspace: Path) -> None:
        """Test diff shows closed symbol for issue created and closed since HEAD."""
        dogcats_dir = git_workspace / ".dogcats"
        issue_id = _create_issue(dogcats_dir, "Created then closed")

        # Close the issue without committing creation first
        runner.invoke(
            app,
            ["close", issue_id, "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["diff", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Closed" in result.stdout
        assert "Created then closed" in result.stdout
        # First line should be the closed symbol, not created
        lines = [
            line
            for line in result.stdout.splitlines()
            if line.strip() and "Legend" not in line
        ]
        assert lines[0].startswith("\u2713")

    def test_diff_new_and_closed_json(self, git_workspace: Path) -> None:
        """Test diff JSON output shows closed event_type for new-and-closed issue."""
        dogcats_dir = git_workspace / ".dogcats"
        issue_id = _create_issue(dogcats_dir, "JSON closed test")

        runner.invoke(
            app,
            ["close", issue_id, "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["diff", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert len(data) >= 1
        assert data[0]["event_type"] == "closed"

    def test_diff_json_output(self, git_workspace: Path) -> None:
        """Test diff json output."""
        dogcats_dir = git_workspace / ".dogcats"
        _create_issue(dogcats_dir, "JSON diff test")

        result = runner.invoke(
            app,
            ["diff", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["event_type"] == "created"

    def test_diff_no_git_repo(self, tmp_path: Path) -> None:
        # Create a .dogcats dir in a non-git directory
        """Test diff no git repo."""
        non_git_dir = tmp_path / "no_git"
        non_git_dir.mkdir()
        dogcats_dir = non_git_dir / ".dogcats"
        result = runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])
        assert result.exit_code == 0

        # Run diff outside of git - should fail gracefully
        result = runner.invoke(
            app,
            ["diff", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 1
        assert "git" in result.stdout.lower() or "git" in (result.stderr or "").lower()

    def test_diff_staged_shows_staged_changes(self, git_workspace: Path) -> None:
        """Test --staged shows changes between index and HEAD."""
        dogcats_dir = git_workspace / ".dogcats"
        _create_issue(dogcats_dir, "Staged issue")

        # Stage the change but don't commit
        subprocess.run(
            ["git", "-C", str(git_workspace), "add", ".dogcats/"],
            check=True,
            capture_output=True,
        )

        result = runner.invoke(
            app,
            ["diff", "--staged", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Created" in result.stdout
        assert "Staged issue" in result.stdout

    def test_diff_unstaged_shows_unstaged_changes(self, git_workspace: Path) -> None:
        """Test --unstaged shows changes between working tree and index."""
        dogcats_dir = git_workspace / ".dogcats"
        issue_id = _create_issue(dogcats_dir, "To modify")

        # Commit the creation, then stage it
        subprocess.run(
            ["git", "-C", str(git_workspace), "add", ".dogcats/"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(git_workspace), "commit", "-m", "add issue"],
            check=True,
            capture_output=True,
        )

        # Now modify the issue (working tree changes, index stays at commit)
        runner.invoke(
            app,
            [
                "update",
                issue_id,
                "--status",
                "in_progress",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["diff", "--unstaged", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Updated" in result.stdout
        assert "status" in result.stdout

    def test_diff_staged_no_changes(self, git_workspace: Path) -> None:
        """Test --staged shows no changes when index matches HEAD."""
        dogcats_dir = git_workspace / ".dogcats"
        result = runner.invoke(
            app,
            ["diff", "--staged", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No changes" in result.stdout

    def test_diff_staged_and_unstaged_mutually_exclusive(
        self,
        git_workspace: Path,
    ) -> None:
        """Test that --staged and --unstaged cannot be used together."""
        dogcats_dir = git_workspace / ".dogcats"
        result = runner.invoke(
            app,
            ["diff", "--staged", "--unstaged", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 1
