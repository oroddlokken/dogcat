"""Tests for the dcat propose CLI command."""

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


class TestPropose:
    """Test the propose command."""

    def test_propose_to_self(self, tmp_path: Path) -> None:
        """Test proposing to the current repo's inbox."""
        _init(tmp_path)

        result = runner.invoke(
            app,
            [
                "propose",
                "Add dark mode",
                "--to",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0, result.stdout
        assert "Proposed" in result.stdout
        assert "Add dark mode" in result.stdout

    def test_propose_with_description(self, tmp_path: Path) -> None:
        """Test proposing with a description."""
        _init(tmp_path)

        result = runner.invoke(
            app,
            [
                "propose",
                "Add dark mode",
                "--description",
                "Support dark color scheme",
                "--to",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0, result.stdout
        assert "Proposed" in result.stdout

    def test_propose_with_by(self, tmp_path: Path) -> None:
        """Test proposing with explicit --by."""
        _init(tmp_path)

        result = runner.invoke(
            app,
            [
                "propose",
                "Fix bug",
                "--by",
                "alice@example.com",
                "--to",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0, result.stdout
        assert "Proposed" in result.stdout

    def test_propose_with_namespace(self, tmp_path: Path) -> None:
        """Test proposing with an explicit namespace."""
        _init(tmp_path)

        result = runner.invoke(
            app,
            [
                "propose",
                "Namespaced proposal",
                "--namespace",
                "myns",
                "--to",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0, result.stdout
        assert "Proposed" in result.stdout
        assert "myns-inbox-" in result.stdout

    def test_propose_json_output(self, tmp_path: Path) -> None:
        """Test proposing with --json output."""
        _init(tmp_path)

        result = runner.invoke(
            app,
            [
                "propose",
                "JSON proposal",
                "--json",
                "--to",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0, result.stdout
        data = json.loads(result.stdout)
        assert data["title"] == "JSON proposal"
        assert data["status"] == "open"
        assert "id" in data

    def test_propose_creates_inbox_file(self, tmp_path: Path) -> None:
        """Test that propose creates inbox.jsonl in the target."""
        dogcats_dir = _init(tmp_path)

        runner.invoke(
            app,
            [
                "propose",
                "New proposal",
                "--to",
                str(tmp_path),
            ],
        )
        inbox_file = dogcats_dir / "inbox.jsonl"
        assert inbox_file.exists()

    def test_propose_to_dogcats_dir_directly(self, tmp_path: Path) -> None:
        """Test --to pointing directly at a .dogcats directory."""
        dogcats_dir = _init(tmp_path)

        result = runner.invoke(
            app,
            [
                "propose",
                "Direct path proposal",
                "--to",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0, result.stdout
        assert "Proposed" in result.stdout

    def test_propose_to_nonexistent_path(self) -> None:
        """Test proposing to a nonexistent path fails."""
        result = runner.invoke(
            app,
            [
                "propose",
                "Will fail",
                "--to",
                "/nonexistent/path",
            ],
        )
        assert result.exit_code == 1

    def test_propose_to_dir_without_dogcats(self, tmp_path: Path) -> None:
        """Test proposing to a directory without .dogcats fails."""
        result = runner.invoke(
            app,
            [
                "propose",
                "Will fail",
                "--to",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 1

    def test_propose_visible_in_inbox_list(self, tmp_path: Path) -> None:
        """Test that a proposal shows up in inbox list."""
        dogcats_dir = _init(tmp_path)

        runner.invoke(
            app,
            [
                "propose",
                "Visible proposal",
                "--to",
                str(tmp_path),
            ],
        )

        result = runner.invoke(
            app,
            [
                "inbox",
                "list",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Visible proposal" in result.stdout
