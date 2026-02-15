"""Tests for Dogcat CLI commands."""

import json
from pathlib import Path

from typer.testing import CliRunner

from dogcat.cli import app

runner = CliRunner()


class TestCLILabel:
    """Test label command."""

    def test_label_add(self, tmp_path: Path) -> None:
        """Test adding a label."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        create_result = runner.invoke(
            app,
            ["create", "Test issue", "--dogcats-dir", str(dogcats_dir)],
        )
        issue_id = create_result.stdout.split(": ")[0].split()[-1]

        result = runner.invoke(
            app,
            [
                "label",
                issue_id,
                "add",
                "--label",
                "urgent",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Added label" in result.stdout

    def test_label_remove(self, tmp_path: Path) -> None:
        """Test removing a label."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        create_result = runner.invoke(
            app,
            [
                "create",
                "Test issue",
                "--labels",
                "urgent",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        issue_id = create_result.stdout.split(": ")[0].split()[-1]

        result = runner.invoke(
            app,
            [
                "label",
                issue_id,
                "remove",
                "--label",
                "urgent",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Removed label" in result.stdout

    def test_label_list(self, tmp_path: Path) -> None:
        """Test listing labels."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        create_result = runner.invoke(
            app,
            [
                "create",
                "Test issue",
                "--labels",
                "urgent,backend",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        issue_id = create_result.stdout.split(": ")[0].split()[-1]

        result = runner.invoke(
            app,
            [
                "label",
                issue_id,
                "list",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "urgent" in result.stdout
        assert "backend" in result.stdout

    def test_update_manual(self, tmp_path: Path) -> None:
        """Test updating issue with --manual flag."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Create issue without manual
        create_result = runner.invoke(
            app,
            ["create", "Test issue", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        data = json.loads(create_result.stdout)
        issue_id = data["id"]
        assert data["metadata"] == {}

        # Update to set manual
        runner.invoke(
            app,
            ["update", issue_id, "--manual", "--dogcats-dir", str(dogcats_dir)],
        )

        # Verify manual is set
        show_result = runner.invoke(
            app,
            ["show", issue_id, "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        data = json.loads(show_result.stdout)
        assert data["metadata"]["manual"] is True

        # Update to remove manual
        runner.invoke(
            app,
            ["update", issue_id, "--no-manual", "--dogcats-dir", str(dogcats_dir)],
        )

        # Verify manual is removed
        show_result = runner.invoke(
            app,
            ["show", issue_id, "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        data = json.loads(show_result.stdout)
        assert "manual" not in data["metadata"]


class TestLabelsCommand:
    """Test dcat labels command."""

    def test_labels_shows_all(self, tmp_path: Path) -> None:
        """Test that labels command shows all labels with counts."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        runner.invoke(
            app,
            [
                "create",
                "Issue 1",
                "--labels",
                "backend,urgent",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        runner.invoke(
            app,
            [
                "create",
                "Issue 2",
                "--labels",
                "backend,frontend",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(app, ["labels", "--dogcats-dir", str(dogcats_dir)])
        assert result.exit_code == 0
        assert "backend (2)" in result.stdout
        assert "urgent (1)" in result.stdout
        assert "frontend (1)" in result.stdout

    def test_labels_json(self, tmp_path: Path) -> None:
        """Test labels command with --json output."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        runner.invoke(
            app,
            [
                "create",
                "Issue 1",
                "--labels",
                "backend",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["labels", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        import json

        data = json.loads(result.stdout)
        assert len(data) == 1
        assert data[0]["label"] == "backend"
        assert data[0]["count"] == 1

    def test_labels_empty(self, tmp_path: Path) -> None:
        """Test labels command with no labels."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(app, ["labels", "--dogcats-dir", str(dogcats_dir)])
        assert result.exit_code == 0
        assert "No labels found" in result.stdout
