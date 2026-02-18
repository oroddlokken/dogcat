"""Tests for Dogcat CLI commands."""

import json
from pathlib import Path

from typer.testing import CliRunner

from dogcat.cli import app

runner = CliRunner()


class TestCLIShow:
    """Test show command."""

    def test_show_issue(self, tmp_path: Path) -> None:
        """Test showing an issue."""
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
            ["show", issue_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Test issue" in result.stdout
        assert issue_id in result.stdout

    def test_show_nonexistent_issue(self, tmp_path: Path) -> None:
        """Test showing nonexistent issue."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["show", "nonexistent", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_show_json_output(self, tmp_path: Path) -> None:
        """Test show with JSON output."""
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
            ["show", issue_id, "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["title"] == "Test issue"

    def test_show_displays_metadata(self, tmp_path: Path) -> None:
        """Test show displays metadata in text output."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        create_result = runner.invoke(
            app,
            [
                "create",
                "Issue with metadata",
                "--manual",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        issue_id = create_result.stdout.split(": ")[0].split()[-1]

        result = runner.invoke(
            app,
            ["show", issue_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Metadata:" in result.stdout
        assert "manual: True" in result.stdout

    def test_show_closed_issue_field_order(self, tmp_path: Path) -> None:
        """Test Created before Closed, close reason next to date."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        create_result = runner.invoke(
            app,
            ["create", "Field order test", "--dogcats-dir", str(dogcats_dir)],
        )
        issue_id = create_result.stdout.split(": ")[0].split()[-1]

        runner.invoke(
            app,
            ["close", issue_id, "--reason", "Done", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["show", issue_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        lines = result.stdout.splitlines()

        created_idx = next(
            i for i, line in enumerate(lines) if line.startswith("Created:")
        )
        closed_idx = next(
            i for i, line in enumerate(lines) if line.startswith("Closed:")
        )

        # Created should appear before Closed
        assert created_idx < closed_idx

        # Close reason should be on the same line as the Closed date
        closed_line = lines[closed_idx]
        assert "(Done)" in closed_line

    def test_show_displays_children(self, tmp_path: Path) -> None:
        """Test that show displays child issues."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Create parent issue
        parent_result = runner.invoke(
            app,
            ["create", "Parent issue", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        parent_data = json.loads(parent_result.stdout)
        parent_full_id = f"{parent_data['namespace']}-{parent_data['id']}"

        # Create child issues with parent
        runner.invoke(
            app,
            [
                "create",
                "Child issue 1",
                "--parent",
                parent_full_id,
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        runner.invoke(
            app,
            [
                "create",
                "Child issue 2",
                "--parent",
                parent_full_id,
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        # Show parent should include children
        result = runner.invoke(
            app,
            ["show", parent_full_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Children:" in result.stdout
        assert "Child issue 1" in result.stdout
        assert "Child issue 2" in result.stdout
        # Children should use rich formatting with status emoji and type
        assert "●" in result.stdout  # open status emoji
        assert "[task]" in result.stdout  # default type

    def test_show_displays_parent(self, tmp_path: Path) -> None:
        """Test that show displays parent for child issues."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Create parent issue
        parent_result = runner.invoke(
            app,
            ["create", "Parent issue", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        parent_data = json.loads(parent_result.stdout)
        parent_id = parent_data["id"]
        parent_full_id = f"{parent_data['namespace']}-{parent_id}"

        # Create child issue with parent
        child_result = runner.invoke(
            app,
            [
                "create",
                "Child issue",
                "--parent",
                parent_id,
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        child_data = json.loads(child_result.stdout)
        child_id = child_data["id"]

        # Show child should include parent (full ID)
        result = runner.invoke(
            app,
            ["show", child_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert f"Parent: {parent_full_id}" in result.stdout


class TestShowFullOption:
    """Test --full hidden option on show command."""

    def test_show_with_full_flag(self, tmp_path: Path) -> None:
        """Test that --full is accepted and produces the same output."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        create_result = runner.invoke(
            app,
            ["create", "Test issue", "--dogcats-dir", str(dogcats_dir)],
        )
        issue_id = create_result.stdout.split(": ")[0].split()[-1]

        # Without --full
        result_normal = runner.invoke(
            app,
            ["show", issue_id, "--dogcats-dir", str(dogcats_dir)],
        )
        # With --full (should produce identical output — it's a no-op)
        result_full = runner.invoke(
            app,
            ["show", issue_id, "--full", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result_full.exit_code == 0
        assert result_normal.stdout == result_full.stdout
