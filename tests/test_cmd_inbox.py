"""Tests for the dcat inbox CLI command group."""

import json
from pathlib import Path

from typer.testing import CliRunner

from dogcat.cli import app

runner = CliRunner()


def _init(tmp_path: Path) -> Path:
    """Initialize a .dogcats directory and return its path."""
    dogcats_dir = tmp_path / ".dogcats"
    runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])
    return dogcats_dir


def _create_proposal(tmp_path: Path, title: str = "Test proposal") -> str:
    """Create a proposal and return its full ID."""
    result = runner.invoke(
        app,
        [
            "propose",
            title,
            "--to",
            str(tmp_path),
            "--json",
        ],
    )
    data = json.loads(result.stdout)
    return f"{data['namespace']}-inbox-{data['id']}"


class TestInboxList:
    """Test the inbox list command."""

    def test_list_empty(self, tmp_path: Path) -> None:
        """Test listing with no proposals."""
        dogcats_dir = _init(tmp_path)

        result = runner.invoke(
            app,
            ["inbox", "list", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No proposals" in result.stdout

    def test_list_with_proposals(self, tmp_path: Path) -> None:
        """Test listing with proposals present."""
        dogcats_dir = _init(tmp_path)
        _create_proposal(tmp_path, "First proposal")
        _create_proposal(tmp_path, "Second proposal")

        result = runner.invoke(
            app,
            ["inbox", "list", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "First proposal" in result.stdout
        assert "Second proposal" in result.stdout

    def test_list_json_output(self, tmp_path: Path) -> None:
        """Test list with --json output."""
        dogcats_dir = _init(tmp_path)
        _create_proposal(tmp_path, "JSON list test")

        result = runner.invoke(
            app,
            ["inbox", "list", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data: list[dict[str, object]] = json.loads(result.stdout)
        assert len(data) == 1
        assert data[0]["title"] == "JSON list test"

    def test_list_hides_closed_by_default(self, tmp_path: Path) -> None:
        """Test that closed proposals are hidden by default."""
        dogcats_dir = _init(tmp_path)
        full_id = _create_proposal(tmp_path, "Will be closed")

        runner.invoke(
            app,
            ["inbox", "close", full_id, "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["inbox", "list", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Will be closed" not in result.stdout

    def test_list_all_includes_closed(self, tmp_path: Path) -> None:
        """Test that --all shows closed proposals."""
        dogcats_dir = _init(tmp_path)
        full_id = _create_proposal(tmp_path, "Closed but visible")

        runner.invoke(
            app,
            ["inbox", "close", full_id, "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["inbox", "list", "--all", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Closed but visible" in result.stdout


class TestInboxShow:
    """Test the inbox show command."""

    def test_show_proposal(self, tmp_path: Path) -> None:
        """Test showing a proposal's details."""
        dogcats_dir = _init(tmp_path)
        full_id = _create_proposal(tmp_path, "Show me")

        result = runner.invoke(
            app,
            ["inbox", "show", full_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Show me" in result.stdout
        assert full_id in result.stdout

    def test_show_json_output(self, tmp_path: Path) -> None:
        """Test show with --json output."""
        dogcats_dir = _init(tmp_path)
        full_id = _create_proposal(tmp_path, "JSON show test")

        result = runner.invoke(
            app,
            [
                "inbox",
                "show",
                full_id,
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["title"] == "JSON show test"
        constructed_id = f"{data['namespace']}-inbox-{data['id']}"
        assert constructed_id == full_id

    def test_show_nonexistent(self, tmp_path: Path) -> None:
        """Test showing a nonexistent proposal."""
        dogcats_dir = _init(tmp_path)

        result = runner.invoke(
            app,
            [
                "inbox",
                "show",
                "dc-inbox-xxxx",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 1

    def test_show_displays_status(self, tmp_path: Path) -> None:
        """Test that show displays status field."""
        dogcats_dir = _init(tmp_path)
        full_id = _create_proposal(tmp_path, "Status check")

        result = runner.invoke(
            app,
            ["inbox", "show", full_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "open" in result.stdout


class TestInboxClose:
    """Test the inbox close command."""

    def test_close_proposal(self, tmp_path: Path) -> None:
        """Test closing a proposal."""
        dogcats_dir = _init(tmp_path)
        full_id = _create_proposal(tmp_path, "Close me")

        result = runner.invoke(
            app,
            ["inbox", "close", full_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Closed" in result.stdout
        assert "Close me" in result.stdout

    def test_close_with_reason(self, tmp_path: Path) -> None:
        """Test closing with a reason."""
        dogcats_dir = _init(tmp_path)
        full_id = _create_proposal(tmp_path, "Reasoned close")

        result = runner.invoke(
            app,
            [
                "inbox",
                "close",
                full_id,
                "--reason",
                "Not needed",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Closed" in result.stdout

    def test_close_with_issue(self, tmp_path: Path) -> None:
        """Test closing with a linked issue ID."""
        dogcats_dir = _init(tmp_path)
        full_id = _create_proposal(tmp_path, "Issue link close")

        result = runner.invoke(
            app,
            [
                "inbox",
                "close",
                full_id,
                "--issue",
                "dc-abcd",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0

    def test_close_json_output(self, tmp_path: Path) -> None:
        """Test close with --json output."""
        dogcats_dir = _init(tmp_path)
        full_id = _create_proposal(tmp_path, "JSON close")

        result = runner.invoke(
            app,
            [
                "inbox",
                "close",
                full_id,
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["status"] == "closed"

    def test_close_nonexistent(self, tmp_path: Path) -> None:
        """Test closing a nonexistent proposal."""
        dogcats_dir = _init(tmp_path)

        result = runner.invoke(
            app,
            [
                "inbox",
                "close",
                "dc-inbox-xxxx",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 1


class TestInboxDelete:
    """Test the inbox delete command."""

    def test_delete_proposal(self, tmp_path: Path) -> None:
        """Test deleting a proposal."""
        dogcats_dir = _init(tmp_path)
        full_id = _create_proposal(tmp_path, "Delete me")

        result = runner.invoke(
            app,
            ["inbox", "delete", full_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Deleted" in result.stdout
        assert "Delete me" in result.stdout

    def test_delete_json_output(self, tmp_path: Path) -> None:
        """Test delete with --json output."""
        dogcats_dir = _init(tmp_path)
        full_id = _create_proposal(tmp_path, "JSON delete")

        result = runner.invoke(
            app,
            [
                "inbox",
                "delete",
                full_id,
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["status"] == "tombstone"

    def test_delete_nonexistent(self, tmp_path: Path) -> None:
        """Test deleting a nonexistent proposal."""
        dogcats_dir = _init(tmp_path)

        result = runner.invoke(
            app,
            [
                "inbox",
                "delete",
                "dc-inbox-xxxx",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 1

    def test_deleted_proposal_hidden_from_list(self, tmp_path: Path) -> None:
        """Test that deleted proposals are hidden from default list."""
        dogcats_dir = _init(tmp_path)
        full_id = _create_proposal(tmp_path, "Will be deleted")

        runner.invoke(
            app,
            ["inbox", "delete", full_id, "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["inbox", "list", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Will be deleted" not in result.stdout
