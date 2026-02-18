"""Tests for dcat diff CLI command."""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

import pytest
from conftest import _GIT_TEST_ENV
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
        env=_GIT_TEST_ENV,
    )

    dogcats_dir = tmp_path / ".dogcats"
    result = runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])
    assert result.exit_code == 0

    # Initial commit with empty .dogcats
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", ".dogcats/"],
        check=True,
        capture_output=True,
        env=_GIT_TEST_ENV,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-m", "init"],
        check=True,
        capture_output=True,
        env=_GIT_TEST_ENV,
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


def _create_proposal(workspace: Path, _dogcats_dir: Path, title: str) -> str:
    """Create a proposal via CLI and return its full ID."""
    result = runner.invoke(
        app,
        [
            "propose",
            title,
            "--to",
            str(workspace),
            "--json",
        ],
    )
    assert result.exit_code == 0
    import json as _json

    data = _json.loads(result.stdout)
    return f"{data['namespace']}-inbox-{data['id']}"


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
            env=_GIT_TEST_ENV,
        )
        subprocess.run(
            ["git", "-C", str(git_workspace), "commit", "-m", "add issue"],
            check=True,
            capture_output=True,
            env=_GIT_TEST_ENV,
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
            env=_GIT_TEST_ENV,
        )
        subprocess.run(
            ["git", "-C", str(git_workspace), "commit", "-m", "add issue"],
            check=True,
            capture_output=True,
            env=_GIT_TEST_ENV,
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
        legend_prefixes = ("Legend", "Event:", "Status:")
        lines = [
            line
            for line in result.stdout.splitlines()
            if line.strip() and not line.strip().startswith(legend_prefixes)
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
        assert len(data) >= 1  # type: ignore[reportUnknownArgumentType]
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
            env=_GIT_TEST_ENV,
        )
        subprocess.run(
            ["git", "-C", str(git_workspace), "commit", "-m", "add issue"],
            check=True,
            capture_output=True,
            env=_GIT_TEST_ENV,
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

    def test_diff_shows_status_symbol_for_new_issue(
        self,
        git_workspace: Path,
    ) -> None:
        """New issue should show open status symbol ● alongside event symbol."""
        dogcats_dir = git_workspace / ".dogcats"
        _create_issue(dogcats_dir, "Status symbol test")

        result = runner.invoke(
            app,
            ["diff", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        # The open status symbol ● should appear in the output
        assert "\u25cf" in result.stdout

    def test_diff_shows_status_symbol_for_in_progress(
        self,
        git_workspace: Path,
    ) -> None:
        """Updated-to-in_progress issue should show ◐ status symbol."""
        dogcats_dir = git_workspace / ".dogcats"
        issue_id = _create_issue(dogcats_dir, "Progress test")

        # Commit the creation
        subprocess.run(
            ["git", "-C", str(git_workspace), "add", ".dogcats/"],
            check=True,
            capture_output=True,
            env=_GIT_TEST_ENV,
        )
        subprocess.run(
            ["git", "-C", str(git_workspace), "commit", "-m", "add issue"],
            check=True,
            capture_output=True,
            env=_GIT_TEST_ENV,
        )

        # Update to in_progress
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
        # The in_progress status symbol ◐ should appear in the output
        assert "\u25d0" in result.stdout

    def test_diff_legend_shows_event_and_status(
        self,
        git_workspace: Path,
    ) -> None:
        """Legend should include both event and status symbols."""
        dogcats_dir = git_workspace / ".dogcats"
        _create_issue(dogcats_dir, "Legend test")

        result = runner.invoke(
            app,
            ["diff", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Event:" in result.stdout
        assert "Status:" in result.stdout


class TestDiffInbox:
    """Tests for diff with inbox.jsonl proposals."""

    def test_diff_shows_new_proposal(self, git_workspace: Path) -> None:
        """Test diff shows a newly created proposal."""
        dogcats_dir = git_workspace / ".dogcats"
        _create_proposal(git_workspace, dogcats_dir, "New proposal")

        result = runner.invoke(
            app,
            ["diff", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Created" in result.stdout
        assert "New proposal" in result.stdout

    def test_diff_shows_closed_proposal(self, git_workspace: Path) -> None:
        """Test diff shows a closed proposal."""
        dogcats_dir = git_workspace / ".dogcats"
        prop_id = _create_proposal(git_workspace, dogcats_dir, "To close")

        # Commit the proposal
        subprocess.run(
            ["git", "-C", str(git_workspace), "add", ".dogcats/"],
            check=True,
            capture_output=True,
            env=_GIT_TEST_ENV,
        )
        subprocess.run(
            ["git", "-C", str(git_workspace), "commit", "-m", "add proposal"],
            check=True,
            capture_output=True,
            env=_GIT_TEST_ENV,
        )

        # Close the proposal
        runner.invoke(
            app,
            [
                "inbox",
                "close",
                prop_id,
                "--reason",
                "accepted",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["diff", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Closed" in result.stdout
        assert "To close" in result.stdout

    def test_diff_shows_deleted_proposal(self, git_workspace: Path) -> None:
        """Test diff shows a deleted (tombstoned) proposal."""
        dogcats_dir = git_workspace / ".dogcats"
        prop_id = _create_proposal(git_workspace, dogcats_dir, "To delete")

        # Commit the proposal
        subprocess.run(
            ["git", "-C", str(git_workspace), "add", ".dogcats/"],
            check=True,
            capture_output=True,
            env=_GIT_TEST_ENV,
        )
        subprocess.run(
            ["git", "-C", str(git_workspace), "commit", "-m", "add proposal"],
            check=True,
            capture_output=True,
            env=_GIT_TEST_ENV,
        )

        # Delete the proposal
        runner.invoke(
            app,
            [
                "inbox",
                "delete",
                prop_id,
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["diff", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Deleted" in result.stdout

    def test_diff_json_shows_proposal(self, git_workspace: Path) -> None:
        """Test diff JSON output includes proposal events."""
        dogcats_dir = git_workspace / ".dogcats"
        _create_proposal(git_workspace, dogcats_dir, "JSON proposal")

        result = runner.invoke(
            app,
            ["diff", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        # Find the proposal event
        proposal_events: list[dict[str, str]] = [
            e
            for e in data  # pyright: ignore[reportUnknownVariableType]
            if "inbox" in e["issue_id"]
        ]
        assert len(proposal_events) == 1
        assert proposal_events[0]["event_type"] == "created"
        assert proposal_events[0]["title"] == "JSON proposal"

    def test_diff_no_inbox_no_error(self, git_workspace: Path) -> None:
        """Test diff works fine when inbox.jsonl doesn't exist."""
        dogcats_dir = git_workspace / ".dogcats"
        # No proposals created, inbox.jsonl doesn't exist
        result = runner.invoke(
            app,
            ["diff", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No changes" in result.stdout

    def test_diff_mixed_issues_and_proposals(self, git_workspace: Path) -> None:
        """Test diff shows both issue and proposal changes together."""
        dogcats_dir = git_workspace / ".dogcats"
        _create_issue(dogcats_dir, "Issue change")
        _create_proposal(git_workspace, dogcats_dir, "Proposal change")

        result = runner.invoke(
            app,
            ["diff", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        issue_events = [e for e in data if "inbox" not in e["issue_id"]]
        proposal_events = [e for e in data if "inbox" in e["issue_id"]]
        assert len(issue_events) >= 1
        assert len(proposal_events) >= 1
