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

    def test_show_multiple_ids_renders_each(self, tmp_path: Path) -> None:
        """Multiple IDs render each issue with a separator between them."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        first = runner.invoke(
            app,
            ["create", "First issue", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        second = runner.invoke(
            app,
            ["create", "Second issue", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        first_id = json.loads(first.stdout)
        second_id = json.loads(second.stdout)
        first_full = f"{first_id['namespace']}-{first_id['id']}"
        second_full = f"{second_id['namespace']}-{second_id['id']}"

        result = runner.invoke(
            app,
            ["show", first_full, second_full, "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "First issue" in result.stdout
        assert "Second issue" in result.stdout
        # Separator carries the ID of the next issue
        assert second_full in result.stdout
        assert "─" in result.stdout
        # First issue body comes before the second
        assert result.stdout.index("First issue") < result.stdout.index("Second issue")

    def test_show_single_id_has_no_separator(self, tmp_path: Path) -> None:
        """Single-ID show is unchanged — no rule, no extra header."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        create_result = runner.invoke(
            app,
            ["create", "Solo issue", "--dogcats-dir", str(dogcats_dir)],
        )
        issue_id = create_result.stdout.split(": ")[0].split()[-1]

        result = runner.invoke(
            app,
            ["show", issue_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "─" not in result.stdout

    def test_show_missing_id_continues_and_exits_nonzero(self, tmp_path: Path) -> None:
        """A missing ID logs an error but does not abort remaining IDs."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        first = runner.invoke(
            app,
            ["create", "Found issue", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        first_data = json.loads(first.stdout)
        first_full = f"{first_data['namespace']}-{first_data['id']}"

        result = runner.invoke(
            app,
            [
                "show",
                first_full,
                "nonexistent-id",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 1
        assert "Found issue" in result.stdout
        assert "not found" in result.output

    def test_show_multiple_json_emits_ndjson(self, tmp_path: Path) -> None:
        """Multiple IDs with --json emit one JSON object per line."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        first = runner.invoke(
            app,
            ["create", "Alpha", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        second = runner.invoke(
            app,
            ["create", "Beta", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        first_full = (
            f"{json.loads(first.stdout)['namespace']}-{json.loads(first.stdout)['id']}"
        )
        second_full = (
            f"{json.loads(second.stdout)['namespace']}-"
            f"{json.loads(second.stdout)['id']}"
        )

        result = runner.invoke(
            app,
            [
                "show",
                first_full,
                second_full,
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        assert len(lines) == 2
        titles = [json.loads(line)["title"] for line in lines]
        assert titles == ["Alpha", "Beta"]

    def test_show_all_filters_and_renders_full_blocks(self, tmp_path: Path) -> None:
        """show-all applies list filters and renders each match as a full block."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        kept_a = runner.invoke(
            app,
            [
                "create",
                "Kept alpha",
                "-d",
                "Body for alpha issue",
                "--type",
                "bug",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        kept_b = runner.invoke(
            app,
            [
                "create",
                "Kept beta",
                "-d",
                "Body for beta issue",
                "--type",
                "bug",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        runner.invoke(
            app,
            [
                "create",
                "Filtered out",
                "-d",
                "Body of filtered issue",
                "--type",
                "feature",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        kept_a_data = json.loads(kept_a.stdout)
        kept_b_data = json.loads(kept_b.stdout)
        kept_a_full = f"{kept_a_data['namespace']}-{kept_a_data['id']}"
        kept_b_full = f"{kept_b_data['namespace']}-{kept_b_data['id']}"

        result = runner.invoke(
            app,
            [
                "show-all",
                "--type",
                "bug",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Kept alpha" in result.stdout
        assert "Kept beta" in result.stdout
        assert "Body for alpha issue" in result.stdout
        assert "Body for beta issue" in result.stdout
        assert "Filtered out" not in result.stdout
        # Separator labeled with the second issue's full ID
        assert "─" in result.stdout
        assert kept_a_full in result.stdout
        assert kept_b_full in result.stdout

    def test_show_all_empty_result_text(self, tmp_path: Path) -> None:
        """Empty filter result prints 'No issues found' and exits 0."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            [
                "show-all",
                "--type",
                "feature",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "No issues found" in result.stdout

    def test_show_all_empty_result_json(self, tmp_path: Path) -> None:
        """Empty filter result with --json emits no output and exits 0."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            [
                "show-all",
                "--type",
                "feature",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert result.stdout.strip() == ""

    def test_show_all_json_emits_ndjson(self, tmp_path: Path) -> None:
        """--json emits one issue per line."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        runner.invoke(
            app,
            ["create", "First", "--dogcats-dir", str(dogcats_dir)],
        )
        runner.invoke(
            app,
            ["create", "Second", "--dogcats-dir", str(dogcats_dir)],
        )
        runner.invoke(
            app,
            ["create", "Third", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["show-all", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        assert len(lines) == 3
        titles = sorted(json.loads(line)["title"] for line in lines)
        assert titles == ["First", "Second", "Third"]

    def test_show_all_respects_limit(self, tmp_path: Path) -> None:
        """--limit caps the number of rendered issues."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        for title in ("One", "Two", "Three", "Four"):
            runner.invoke(
                app,
                ["create", title, "--dogcats-dir", str(dogcats_dir)],
            )

        result = runner.invoke(
            app,
            [
                "show-all",
                "--limit",
                "2",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        assert len(lines) == 2

    def test_show_all_excludes_closed_by_default(self, tmp_path: Path) -> None:
        """Closed issues are hidden unless --closed/--all is passed."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        kept = runner.invoke(
            app,
            ["create", "Open issue", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        gone = runner.invoke(
            app,
            ["create", "Closed issue", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        gone_full = (
            f"{json.loads(gone.stdout)['namespace']}-{json.loads(gone.stdout)['id']}"
        )
        runner.invoke(
            app,
            ["close", gone_full, "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["show-all", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Open issue" in result.stdout
        assert "Closed issue" not in result.stdout
        # And the kept issue's full body actually rendered
        kept_full = (
            f"{json.loads(kept.stdout)['namespace']}-{json.loads(kept.stdout)['id']}"
        )
        assert kept_full in result.stdout

    def test_show_all_comments_flags_mutually_exclusive(self, tmp_path: Path) -> None:
        """--has-comments and --without-comments cannot be combined."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            [
                "show-all",
                "--has-comments",
                "--without-comments",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 1
        assert "mutually exclusive" in result.output

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
