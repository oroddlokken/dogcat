"""Tests for Dogcat CLI commands."""

import json
from pathlib import Path

from cli_test_helpers import _create_multi_ns_issues, _set_ns_config
from typer.testing import CliRunner

from dogcat.cli import app

runner = CliRunner()


class TestCLIList:
    """Test list command."""

    def test_list_empty(self, tmp_path: Path) -> None:
        """Test listing empty repository."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["list", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No issues" in result.stdout

    def test_list_issues(self, tmp_path: Path) -> None:
        """Test listing issues."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        runner.invoke(
            app,
            ["create", "Issue 1", "--dogcats-dir", str(dogcats_dir)],
        )
        runner.invoke(
            app,
            ["create", "Issue 2", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["list", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Issue 1" in result.stdout
        assert "Issue 2" in result.stdout

    def test_list_filter_by_status(self, tmp_path: Path) -> None:
        """Test filtering issues by status."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        create_result = runner.invoke(
            app,
            ["create", "Issue 1", "--dogcats-dir", str(dogcats_dir)],
        )
        issue_id = create_result.stdout.split(": ")[0].split()[-1]

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
            ["list", "--status", "open", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No issues" in result.stdout

    def test_list_json_output(self, tmp_path: Path) -> None:
        """Test list with JSON output."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        runner.invoke(
            app,
            ["create", "Issue 1", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["list", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert len(data) == 1
        assert data[0]["title"] == "Issue 1"

    def test_list_closed_issues(self, tmp_path: Path) -> None:
        """Test listing only closed issues."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Create open and closed issues
        create_result = runner.invoke(
            app,
            ["create", "Open issue", "--dogcats-dir", str(dogcats_dir)],
        )
        create_result.stdout.split(": ")[0].split()[-1]

        create_result = runner.invoke(
            app,
            ["create", "Closed issue", "--dogcats-dir", str(dogcats_dir)],
        )
        closed_issue_id = create_result.stdout.split(": ")[0].split()[-1]

        runner.invoke(
            app,
            ["close", closed_issue_id, "--dogcats-dir", str(dogcats_dir)],
        )

        # List closed issues only
        result = runner.invoke(
            app,
            ["list", "--closed", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Closed issue" in result.stdout
        assert "Open issue" not in result.stdout

    def test_list_closed_issues_shows_closed_date(self, tmp_path: Path) -> None:
        """Test that closed issues display the closed date in brief format."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        # Create and close an issue
        result = runner.invoke(
            app,
            ["create", "Will close", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        issue_data = json.loads(result.stdout)
        issue_full_id = f"{issue_data['namespace']}-{issue_data['id']}"

        runner.invoke(
            app,
            ["close", issue_full_id, "--dogcats-dir", str(dogcats_dir)],
        )

        # List closed issues
        result = runner.invoke(
            app,
            ["list", "--closed", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "[closed " in result.stdout, "Closed issues should show closed date"

    def test_list_open_issues(self, tmp_path: Path) -> None:
        """Test listing only open issues."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Create open and closed issues
        runner.invoke(
            app,
            ["create", "Open issue", "--dogcats-dir", str(dogcats_dir)],
        )

        create_result = runner.invoke(
            app,
            ["create", "Closed issue", "--dogcats-dir", str(dogcats_dir)],
        )
        closed_issue_id = create_result.stdout.split(": ")[0].split()[-1]

        runner.invoke(
            app,
            ["close", closed_issue_id, "--dogcats-dir", str(dogcats_dir)],
        )

        # List open issues only
        result = runner.invoke(
            app,
            ["list", "--open", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Open issue" in result.stdout
        assert "Closed issue" not in result.stdout

    def test_list_closed_after_filter(self, tmp_path: Path) -> None:
        """Test that --closed-after filter finds issues closed after a date."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Create and close an issue
        result = runner.invoke(
            app,
            [
                "create",
                "Closed issue",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        issue_data = json.loads(result.stdout)
        issue_id = issue_data["id"]

        runner.invoke(
            app,
            ["close", issue_id, "--dogcats-dir", str(dogcats_dir)],
        )

        # Filter for issues closed after yesterday - should find the issue
        result = runner.invoke(
            app,
            ["list", "--closed-after", "2020-01-01", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert issue_id in result.stdout

        # Filter for issues closed after tomorrow - should not find it
        result = runner.invoke(
            app,
            ["list", "--closed-after", "2099-01-01", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No issues found" in result.stdout

    def test_list_closed_before_filter(self, tmp_path: Path) -> None:
        """Test that --closed-before filter finds issues closed before a date."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Create and close an issue
        result = runner.invoke(
            app,
            [
                "create",
                "Closed issue",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        issue_data = json.loads(result.stdout)
        issue_id = issue_data["id"]

        runner.invoke(
            app,
            ["close", issue_id, "--dogcats-dir", str(dogcats_dir)],
        )

        # Filter for issues closed before tomorrow - should find the issue
        result = runner.invoke(
            app,
            [
                "list",
                "--closed-before",
                "2099-01-01",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert issue_id in result.stdout

        # Filter for issues closed before yesterday - should not find it
        result = runner.invoke(
            app,
            [
                "list",
                "--closed-before",
                "2020-01-01",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "No issues found" in result.stdout

    def test_list_agent_only(self, tmp_path: Path) -> None:
        """Test list --agent-only filters out manual issues."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Create normal issue
        runner.invoke(
            app,
            ["create", "Normal issue", "--dogcats-dir", str(dogcats_dir)],
        )

        # Create manual issue
        runner.invoke(
            app,
            [
                "create",
                "Agent skip issue",
                "--manual",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        # Without filter, both should appear
        result = runner.invoke(
            app,
            ["list", "--dogcats-dir", str(dogcats_dir)],
        )
        assert "Normal issue" in result.stdout
        assert "Agent skip issue" in result.stdout

        # With filter, only normal should appear
        result = runner.invoke(
            app,
            ["list", "--agent-only", "--dogcats-dir", str(dogcats_dir)],
        )
        assert "Normal issue" in result.stdout
        assert "Agent skip issue" not in result.stdout

    def test_list_tree_indents_subtasks(self, tmp_path: Path) -> None:
        """Test list --tree indents subtasks under their parents."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Create parent issue
        result = runner.invoke(
            app,
            [
                "create",
                "Parent issue",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        parent_data = json.loads(result.stdout)
        parent_full_id = f"{parent_data['namespace']}-{parent_data['id']}"

        # Create subtask with parent
        runner.invoke(
            app,
            [
                "create",
                "Subtask issue",
                "--parent",
                parent_full_id,
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        # List with tree format
        result = runner.invoke(
            app,
            ["list", "--tree", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        # Subtask should be indented (has leading spaces before it)
        lines = result.stdout.split("\n")
        subtask_line = next(line for line in lines if "Subtask issue" in line)
        assert subtask_line.startswith("  "), "Subtask should be indented"

    def test_list_tree_shows_closed_parent_with_open_children(
        self,
        tmp_path: Path,
    ) -> None:
        """Test that --tree shows closed parents when they have visible children."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        # Create parent issue
        result = runner.invoke(
            app,
            ["create", "Parent issue", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        parent_data = json.loads(result.stdout)
        parent_full_id = f"{parent_data['namespace']}-{parent_data['id']}"

        # Create child issue under that parent
        runner.invoke(
            app,
            [
                "create",
                "Child issue",
                "--parent",
                parent_full_id,
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        # Close the parent
        runner.invoke(
            app,
            ["close", parent_full_id, "--dogcats-dir", str(dogcats_dir)],
        )

        # In tree mode, closed parent should still appear with its open child
        result = runner.invoke(
            app,
            ["list", "--tree", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Parent issue" in result.stdout, (
            "Closed parent should appear in tree when it has visible children"
        )
        assert "Child issue" in result.stdout

        # Child should be indented under the parent
        lines = result.stdout.split("\n")
        child_line = next(line for line in lines if "Child issue" in line)
        assert child_line.startswith("  "), "Child should be indented under parent"

    def test_list_flat_hides_closed_parent_with_open_children(
        self,
        tmp_path: Path,
    ) -> None:
        """Test that flat list mode still hides closed parents by default."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        # Create parent and child
        result = runner.invoke(
            app,
            ["create", "Parent issue", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        parent_data = json.loads(result.stdout)
        parent_full_id = f"{parent_data['namespace']}-{parent_data['id']}"

        runner.invoke(
            app,
            [
                "create",
                "Child issue",
                "--parent",
                parent_full_id,
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        # Close the parent
        runner.invoke(
            app,
            ["close", parent_full_id, "--dogcats-dir", str(dogcats_dir)],
        )

        # In flat mode, closed parent should NOT appear
        result = runner.invoke(
            app,
            ["list", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Parent issue" not in result.stdout
        assert "Child issue" in result.stdout

    def test_list_shows_blocked_symbol_for_issues_with_open_dependencies(
        self,
        tmp_path: Path,
    ) -> None:
        """Test that blocked issues show ■ symbol in list output."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Create a blocker issue
        result = runner.invoke(
            app,
            [
                "create",
                "Blocker task",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        blocker_data = json.loads(result.stdout)
        blocker_id = blocker_data["id"]

        # Create a dependent issue that depends on the blocker
        result = runner.invoke(
            app,
            [
                "create",
                "Dependent task",
                "--depends-on",
                blocker_id,
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        dependent_data = json.loads(result.stdout)
        dependent_id = dependent_data["id"]

        # Regular list should show ■ for the dependent issue
        result = runner.invoke(
            app,
            ["list", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        lines = result.stdout.split("\n")
        dependent_line = next(line for line in lines if dependent_id in line)
        assert dependent_line.startswith(
            "■",
        ), f"Blocked issue should show ■ symbol, got: {dependent_line}"
        blocker_line = next(line for line in lines if "Blocker task" in line)
        assert blocker_line.startswith(
            "●",
        ), f"Blocker issue should show ● symbol, got: {blocker_line}"

    def test_list_table_shows_blocked_symbol_for_issues_with_open_dependencies(
        self,
        tmp_path: Path,
    ) -> None:
        """Test that blocked issues show ■ symbol in table list output."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Create a blocker issue
        result = runner.invoke(
            app,
            [
                "create",
                "Blocker task",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        blocker_data = json.loads(result.stdout)
        blocker_id = blocker_data["id"]

        # Create a dependent issue
        result = runner.invoke(
            app,
            [
                "create",
                "Dependent task",
                "--depends-on",
                blocker_id,
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        dependent_data = json.loads(result.stdout)
        dependent_id = dependent_data["id"]

        # table list should show ■ for the dependent issue
        result = runner.invoke(
            app,
            ["list", "--table", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        lines = result.stdout.split("\n")
        dependent_line = next(line for line in lines if dependent_id in line)
        assert "■" in dependent_line, (
            f"Blocked issue should show ■ symbol in table output, got: {dependent_line}"
        )

    def test_list_blocked_symbol_clears_when_blocker_closed(
        self,
        tmp_path: Path,
    ) -> None:
        """Test that blocked symbol clears when blocker is closed."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Create a blocker issue
        result = runner.invoke(
            app,
            [
                "create",
                "Blocker task",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        blocker_data = json.loads(result.stdout)
        blocker_id = blocker_data["id"]

        # Create a dependent issue
        result = runner.invoke(
            app,
            [
                "create",
                "Dependent task",
                "--depends-on",
                blocker_id,
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        dependent_data = json.loads(result.stdout)
        dependent_id = dependent_data["id"]

        # Close the blocker
        runner.invoke(
            app,
            ["close", blocker_id, "--dogcats-dir", str(dogcats_dir)],
        )

        # Now the dependent issue should show ● (no longer blocked)
        result = runner.invoke(
            app,
            ["list", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        lines = result.stdout.split("\n")
        dependent_line = next(line for line in lines if dependent_id in line)
        assert dependent_line.startswith(
            "●",
        ), f"Issue should show ● after blocker is closed, got: {dependent_line}"


class TestCLICommandOrder:
    """Test that CLI commands are listed in alphabetical order."""

    def test_commands_are_alphabetically_sorted(self) -> None:
        """Test that the app lists commands in sorted order."""
        import click
        import typer.main

        # Get the underlying Click group from the Typer app
        group = typer.main.get_group(app)
        ctx = click.Context(group)
        commands = group.list_commands(ctx)
        assert len(commands) > 0
        assert commands == sorted(
            commands,
        ), f"Commands are not alphabetically sorted: {commands}"


class TestLabelsInListOutput:
    """Test that labels appear in list output."""

    def test_labels_in_brief(self, tmp_path: Path) -> None:
        """Test labels appear in brief list output."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        runner.invoke(
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

        result = runner.invoke(app, ["list", "--dogcats-dir", str(dogcats_dir)])
        assert result.exit_code == 0
        assert "urgent" in result.stdout
        assert "backend" in result.stdout

    def test_labels_in_table(self, tmp_path: Path) -> None:
        """Test labels appear in table list output."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        runner.invoke(
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

        result = runner.invoke(
            app,
            ["list", "--table", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "urgent" in result.stdout


class TestMultiLabelFilter:
    """Test multi-label filtering in dcat list."""

    def test_filter_single_label(self, tmp_path: Path) -> None:
        """Test filtering by single label still works."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        runner.invoke(
            app,
            [
                "create",
                "Backend issue",
                "--labels",
                "backend",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        runner.invoke(
            app,
            [
                "create",
                "Frontend issue",
                "--labels",
                "frontend",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["list", "--label", "backend", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Backend issue" in result.stdout
        assert "Frontend issue" not in result.stdout

    def test_filter_multiple_labels(self, tmp_path: Path) -> None:
        """Test filtering by multiple comma-separated labels (OR)."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        runner.invoke(
            app,
            [
                "create",
                "Backend issue",
                "--labels",
                "backend",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        runner.invoke(
            app,
            [
                "create",
                "Frontend issue",
                "--labels",
                "frontend",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        runner.invoke(
            app,
            [
                "create",
                "Unrelated issue",
                "--labels",
                "docs",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            [
                "list",
                "--label",
                "backend,frontend",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Backend issue" in result.stdout
        assert "Frontend issue" in result.stdout
        assert "Unrelated issue" not in result.stdout

    def test_create_with_space_separated_labels(self, tmp_path: Path) -> None:
        """Test that --labels accepts space-separated labels."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        create_result = runner.invoke(
            app,
            [
                "create",
                "Space labels test",
                "--labels",
                "bug fix urgent",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert create_result.exit_code == 0
        issue_id = create_result.stdout.split(": ")[0].split()[-1]

        show_result = runner.invoke(
            app,
            ["show", issue_id, "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        data = json.loads(show_result.stdout)
        assert data["labels"] == ["bug", "fix", "urgent"]

    def test_update_with_space_separated_labels(self, tmp_path: Path) -> None:
        """Test that update --labels accepts space-separated labels."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        create_result = runner.invoke(
            app,
            [
                "create",
                "Update labels test",
                "--labels",
                "old",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        issue_id = create_result.stdout.split(": ")[0].split()[-1]

        result = runner.invoke(
            app,
            [
                "update",
                issue_id,
                "--labels",
                "new1 new2",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0

        show_result = runner.invoke(
            app,
            ["show", issue_id, "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        data = json.loads(show_result.stdout)
        assert data["labels"] == ["new1", "new2"]

    def test_filter_with_space_separated_labels(self, tmp_path: Path) -> None:
        """Test that list --label accepts space-separated labels."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        runner.invoke(
            app,
            [
                "create",
                "Backend issue",
                "--labels",
                "backend",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        runner.invoke(
            app,
            [
                "create",
                "Frontend issue",
                "--labels",
                "frontend",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        runner.invoke(
            app,
            [
                "create",
                "Docs issue",
                "--labels",
                "docs",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            [
                "list",
                "--label",
                "backend frontend",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Backend issue" in result.stdout
        assert "Frontend issue" in result.stdout
        assert "Docs issue" not in result.stdout


class TestListNamespaceFilter:
    """Test namespace filtering in list command."""

    def test_namespace_flag_filters(self, tmp_path: Path) -> None:
        """--namespace proj-a → only that namespace's issues."""
        dogcats_dir = tmp_path / ".dogcats"
        _create_multi_ns_issues(dogcats_dir)

        result = runner.invoke(
            app,
            [
                "list",
                "--namespace",
                "proj-a",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        issues = json.loads(result.stdout)
        assert len(issues) == 2
        assert all(i["namespace"] == "proj-a" for i in issues)

    def test_namespace_nonexistent_empty(self, tmp_path: Path) -> None:
        """--namespace nonexistent → empty result, no error."""
        dogcats_dir = tmp_path / ".dogcats"
        _create_multi_ns_issues(dogcats_dir)

        result = runner.invoke(
            app,
            [
                "list",
                "--namespace",
                "nonexistent",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "No issues found" in result.stdout

    def test_namespace_overrides_hidden_config(self, tmp_path: Path) -> None:
        """--namespace overrides hidden_namespaces config."""
        dogcats_dir = tmp_path / ".dogcats"
        _create_multi_ns_issues(dogcats_dir)
        _set_ns_config(dogcats_dir, "hidden_namespaces", ["proj-b"])

        result = runner.invoke(
            app,
            [
                "list",
                "--namespace",
                "proj-b",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        issues = json.loads(result.stdout)
        assert len(issues) == 1
        assert issues[0]["namespace"] == "proj-b"

    def test_namespace_overrides_visible_config(self, tmp_path: Path) -> None:
        """--namespace overrides visible_namespaces config."""
        dogcats_dir = tmp_path / ".dogcats"
        _create_multi_ns_issues(dogcats_dir)
        _set_ns_config(dogcats_dir, "visible_namespaces", ["proj-a"])

        result = runner.invoke(
            app,
            [
                "list",
                "--namespace",
                "proj-b",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        issues = json.loads(result.stdout)
        assert len(issues) == 1
        assert issues[0]["namespace"] == "proj-b"

    def test_namespace_combined_with_status(self, tmp_path: Path) -> None:
        """--namespace combined with --status → both apply."""
        dogcats_dir = tmp_path / ".dogcats"
        _create_multi_ns_issues(dogcats_dir)

        result = runner.invoke(
            app,
            [
                "list",
                "--namespace",
                "proj-a",
                "--status",
                "open",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        issues = json.loads(result.stdout)
        assert all(i["namespace"] == "proj-a" for i in issues)
        assert all(i["status"] == "open" for i in issues)

    def test_visible_config_filters_list(self, tmp_path: Path) -> None:
        """visible_namespaces config → list excludes unlisted namespaces."""
        dogcats_dir = tmp_path / ".dogcats"
        _create_multi_ns_issues(dogcats_dir)
        _set_ns_config(dogcats_dir, "visible_namespaces", ["proj-a"])

        result = runner.invoke(
            app,
            ["list", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        issues = json.loads(result.stdout)
        assert all(i["namespace"] == "proj-a" for i in issues)

    def test_hidden_config_filters_list(self, tmp_path: Path) -> None:
        """hidden_namespaces config → list excludes hidden namespaces."""
        dogcats_dir = tmp_path / ".dogcats"
        _create_multi_ns_issues(dogcats_dir)
        _set_ns_config(dogcats_dir, "hidden_namespaces", ["proj-b"])

        result = runner.invoke(
            app,
            ["list", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        issues = json.loads(result.stdout)
        assert all(i["namespace"] != "proj-b" for i in issues)

    def test_no_config_shows_all(self, tmp_path: Path) -> None:
        """No config → shows all (backward compat)."""
        dogcats_dir = tmp_path / ".dogcats"
        _create_multi_ns_issues(dogcats_dir)

        result = runner.invoke(
            app,
            ["list", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        issues = json.loads(result.stdout)
        namespaces = {i["namespace"] for i in issues}
        assert "proj-a" in namespaces
        assert "proj-b" in namespaces

    def test_primary_visible_even_if_in_hidden(self, tmp_path: Path) -> None:
        """Primary always visible even if in hidden_namespaces."""
        dogcats_dir = tmp_path / ".dogcats"
        _create_multi_ns_issues(dogcats_dir)
        _set_ns_config(dogcats_dir, "hidden_namespaces", ["proj-a", "proj-b"])

        result = runner.invoke(
            app,
            ["list", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        issues = json.loads(result.stdout)
        # Primary proj-a should still be visible
        assert any(i["namespace"] == "proj-a" for i in issues)
        # proj-b should be hidden
        assert not any(i["namespace"] == "proj-b" for i in issues)


class TestListCollapseDeferredSubtrees:
    """Test that dcat list collapses children of deferred parents."""

    def _setup_deferred_parent_with_children(
        self,
        tmp_path: Path,
    ) -> tuple[str, str, str, str]:
        """Create a deferred parent with two children.

        Returns:
            (dogcats_dir, parent_full_id, child1_full_id, child2_full_id)
        """
        dogcats_dir = str(tmp_path / ".dogcats")
        runner.invoke(app, ["init", "--dogcats-dir", dogcats_dir])

        # Create parent
        result = runner.invoke(
            app,
            ["create", "Parent task", "--json", "--dogcats-dir", dogcats_dir],
        )
        parent_data = json.loads(result.stdout)
        parent_full_id = f"{parent_data['namespace']}-{parent_data['id']}"

        # Create child 1
        result = runner.invoke(
            app,
            [
                "create",
                "Child one",
                "--parent",
                parent_data["id"],
                "--json",
                "--dogcats-dir",
                dogcats_dir,
            ],
        )
        child1_data = json.loads(result.stdout)
        child1_full_id = f"{child1_data['namespace']}-{child1_data['id']}"

        # Create child 2
        result = runner.invoke(
            app,
            [
                "create",
                "Child two",
                "--parent",
                parent_data["id"],
                "--json",
                "--dogcats-dir",
                dogcats_dir,
            ],
        )
        child2_data = json.loads(result.stdout)
        child2_full_id = f"{child2_data['namespace']}-{child2_data['id']}"

        # Defer the parent
        runner.invoke(
            app,
            [
                "update",
                parent_full_id,
                "--status",
                "deferred",
                "--dogcats-dir",
                dogcats_dir,
            ],
        )

        return dogcats_dir, parent_full_id, child1_full_id, child2_full_id

    def test_list_collapses_deferred_children(self, tmp_path: Path) -> None:
        """Children of deferred parents are shown as preview subtasks."""
        dogcats_dir, parent_full_id, child1_full_id, child2_full_id = (
            self._setup_deferred_parent_with_children(tmp_path)
        )

        result = runner.invoke(
            app,
            ["list", "--dogcats-dir", dogcats_dir],
        )
        assert result.exit_code == 0
        # Parent should be visible
        assert parent_full_id in result.stdout
        # With ≤3 children, all are shown as previews (no hidden count on parent)
        assert "hidden subtasks" not in result.stdout
        # Children should be visible as preview subtasks
        assert child1_full_id in result.stdout
        assert child2_full_id in result.stdout

    def test_list_shows_deferred_blocker_annotation(self, tmp_path: Path) -> None:
        """Non-child issue blocked by deferred gets annotation."""
        dogcats_dir, parent_full_id, _child1, _child2 = (
            self._setup_deferred_parent_with_children(tmp_path)
        )

        # Create an external issue that depends on the deferred parent
        result = runner.invoke(
            app,
            [
                "create",
                "External blocked issue",
                "--json",
                "--dogcats-dir",
                dogcats_dir,
            ],
        )
        ext_data = json.loads(result.stdout)
        ext_full_id = f"{ext_data['namespace']}-{ext_data['id']}"

        # Add dependency: external issue depends on deferred parent
        dep_result = runner.invoke(
            app,
            [
                "dep",
                ext_full_id,
                "add",
                "--depends-on",
                parent_full_id,
                "--dogcats-dir",
                dogcats_dir,
            ],
        )
        assert dep_result.exit_code == 0

        result = runner.invoke(
            app,
            ["list", "--dogcats-dir", dogcats_dir],
        )
        assert result.exit_code == 0
        assert "blocked by deferred" in result.stdout
        assert parent_full_id in result.stdout

    def test_list_json_not_affected_by_collapse(self, tmp_path: Path) -> None:
        """JSON output still shows all issues including children of deferred."""
        dogcats_dir, parent_full_id, child1_full_id, child2_full_id = (
            self._setup_deferred_parent_with_children(tmp_path)
        )

        result = runner.invoke(
            app,
            ["list", "--json", "--dogcats-dir", dogcats_dir],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        all_ids = {f"{i['namespace']}-{i['id']}" for i in data}
        # All issues should be present in JSON output
        assert parent_full_id in all_ids
        assert child1_full_id in all_ids
        assert child2_full_id in all_ids

    def test_list_expand_shows_deferred_children(self, tmp_path: Path) -> None:
        """--expand shows children of deferred parents."""
        dogcats_dir, parent_full_id, child1_full_id, child2_full_id = (
            self._setup_deferred_parent_with_children(tmp_path)
        )

        result = runner.invoke(
            app,
            ["list", "--expand", "--dogcats-dir", dogcats_dir],
        )
        assert result.exit_code == 0
        assert parent_full_id in result.stdout
        assert child1_full_id in result.stdout
        assert child2_full_id in result.stdout
        # No hidden subtasks annotation when expanded
        assert "hidden subtasks" not in result.stdout

    def test_list_expand_does_not_show_closed(self, tmp_path: Path) -> None:
        """--expand does not show closed or deleted issues."""
        dogcats_dir, _parent_full_id, child1_full_id, _child2_full_id = (
            self._setup_deferred_parent_with_children(tmp_path)
        )

        # Create and close an unrelated issue
        result = runner.invoke(
            app,
            ["create", "Closed issue", "--json", "--dogcats-dir", dogcats_dir],
        )
        closed_data = json.loads(result.stdout)
        closed_full_id = f"{closed_data['namespace']}-{closed_data['id']}"
        runner.invoke(
            app,
            ["close", closed_full_id, "--dogcats-dir", dogcats_dir],
        )

        result = runner.invoke(
            app,
            ["list", "--expand", "--dogcats-dir", dogcats_dir],
        )
        assert result.exit_code == 0
        # Deferred children are visible
        assert child1_full_id in result.stdout
        # Closed issue should NOT be visible
        assert closed_full_id not in result.stdout

    def test_list_legend_shows_hidden_count(self, tmp_path: Path) -> None:
        """Legend shows hidden count only for non-previewed subtasks."""
        dogcats_dir, _parent, _child1, _child2 = (
            self._setup_deferred_parent_with_children(tmp_path)
        )

        result = runner.invoke(
            app,
            ["list", "--dogcats-dir", dogcats_dir],
        )
        assert result.exit_code == 0
        # With 2 children, both shown as previews, no hidden line in legend
        assert "hidden under deferred" not in result.stdout

    def test_list_legend_no_hidden_line_when_no_deferred(
        self,
        tmp_path: Path,
    ) -> None:
        """Legend does not show hidden line when no deferred parents exist."""
        dogcats_dir = str(tmp_path / ".dogcats")
        runner.invoke(app, ["init", "--dogcats-dir", dogcats_dir])

        runner.invoke(
            app,
            ["create", "Normal issue", "--dogcats-dir", dogcats_dir],
        )

        result = runner.invoke(
            app,
            ["list", "--dogcats-dir", dogcats_dir],
        )
        assert result.exit_code == 0
        assert "hidden under deferred" not in result.stdout

    def test_list_expand_legend_no_hidden_line(self, tmp_path: Path) -> None:
        """--expand should not show hidden count in legend."""
        dogcats_dir, _parent, _child1, _child2 = (
            self._setup_deferred_parent_with_children(tmp_path)
        )

        result = runner.invoke(
            app,
            ["list", "--expand", "--dogcats-dir", dogcats_dir],
        )
        assert result.exit_code == 0
        assert "hidden under deferred" not in result.stdout

    def test_list_preview_subtasks_with_summary(self, tmp_path: Path) -> None:
        """Deferred parent with >3 children shows preview + summary line."""
        dogcats_dir = str(tmp_path / ".dogcats")
        runner.invoke(app, ["init", "--dogcats-dir", dogcats_dir])

        # Create parent
        result = runner.invoke(
            app,
            ["create", "Big parent", "--json", "--dogcats-dir", dogcats_dir],
        )
        parent_data = json.loads(result.stdout)
        parent_id = parent_data["id"]
        parent_full_id = f"{parent_data['namespace']}-{parent_id}"

        # Create 5 children
        child_full_ids: list[str] = []
        for i in range(5):
            result = runner.invoke(
                app,
                [
                    "create",
                    f"Child {i}",
                    "--parent",
                    parent_id,
                    "--json",
                    "--dogcats-dir",
                    dogcats_dir,
                ],
            )
            cdata = json.loads(result.stdout)
            child_full_ids.append(f"{cdata['namespace']}-{cdata['id']}")

        # Defer the parent
        runner.invoke(
            app,
            [
                "update",
                parent_full_id,
                "--status",
                "deferred",
                "--dogcats-dir",
                dogcats_dir,
            ],
        )

        result = runner.invoke(
            app,
            ["list", "--dogcats-dir", dogcats_dir],
        )
        assert result.exit_code == 0
        assert parent_full_id in result.stdout
        # Should show 3 preview children
        shown_count = sum(1 for cid in child_full_ids if cid in result.stdout)
        assert shown_count == 3
        # Should show summary line for the remaining 2
        assert "...and 2 more hidden subtasks" in result.stdout
        # Legend should reflect only the truly hidden count (5 - 3 = 2)
        assert "2 issues hidden under deferred parents" in result.stdout

    def test_list_preview_subtasks_no_summary_when_all_fit(
        self,
        tmp_path: Path,
    ) -> None:
        """Deferred parent with <=3 children shows all with no summary."""
        dogcats_dir, _parent_full_id, child1_full_id, child2_full_id = (
            self._setup_deferred_parent_with_children(tmp_path)
        )

        result = runner.invoke(
            app,
            ["list", "--dogcats-dir", dogcats_dir],
        )
        assert result.exit_code == 0
        # Both children shown as previews
        assert child1_full_id in result.stdout
        assert child2_full_id in result.stdout
        # No summary line
        assert "more hidden subtasks" not in result.stdout

    def test_list_parent_option(self, tmp_path: Path) -> None:
        """Test list --parent shows parent and its children only."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        # Create parent issue
        result = runner.invoke(
            app,
            ["create", "Parent issue", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        parent_data = json.loads(result.stdout)
        parent_full_id = f"{parent_data['namespace']}-{parent_data['id']}"

        # Create child under parent
        runner.invoke(
            app,
            [
                "create",
                "Child issue",
                "--parent",
                parent_full_id,
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        # Create unrelated issue
        runner.invoke(
            app,
            ["create", "Unrelated issue", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["list", "--parent", parent_full_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Parent issue" in result.stdout
        assert "Child issue" in result.stdout
        assert "Unrelated issue" not in result.stdout

    def test_list_parent_positional(self, tmp_path: Path) -> None:
        """Test list with positional argument as shorthand for --parent."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            ["create", "Parent issue", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        parent_data = json.loads(result.stdout)
        parent_full_id = f"{parent_data['namespace']}-{parent_data['id']}"

        runner.invoke(
            app,
            [
                "create",
                "Child issue",
                "--parent",
                parent_full_id,
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        runner.invoke(
            app,
            ["create", "Unrelated issue", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["list", parent_full_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Parent issue" in result.stdout
        assert "Child issue" in result.stdout
        assert "Unrelated issue" not in result.stdout

    def test_list_parent_not_found(self, tmp_path: Path) -> None:
        """Test list --parent with nonexistent issue ID."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            ["list", "--parent", "nonexistent-xxxx", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_list_parent_combined_with_status(self, tmp_path: Path) -> None:
        """Test list --parent combined with --status filters children."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            ["create", "Parent issue", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        parent_data = json.loads(result.stdout)
        parent_full_id = f"{parent_data['namespace']}-{parent_data['id']}"

        # Create child and move it to in_progress
        result = runner.invoke(
            app,
            [
                "create",
                "Active child",
                "--parent",
                parent_full_id,
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        child_data = json.loads(result.stdout)
        child_full_id = f"{child_data['namespace']}-{child_data['id']}"
        runner.invoke(
            app,
            [
                "update",
                child_full_id,
                "--status",
                "in_progress",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        # Create another child that stays open
        runner.invoke(
            app,
            [
                "create",
                "Open child",
                "--parent",
                parent_full_id,
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            [
                "list",
                "--parent",
                parent_full_id,
                "--status",
                "in_progress",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Active child" in result.stdout
        assert "Open child" not in result.stdout

    def test_list_parent_no_children(self, tmp_path: Path) -> None:
        """Test list --parent with issue that has no children shows just the parent."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            ["create", "Lone issue", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        issue_data = json.loads(result.stdout)
        issue_full_id = f"{issue_data['namespace']}-{issue_data['id']}"

        result = runner.invoke(
            app,
            ["list", "--parent", issue_full_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Lone issue" in result.stdout

    def test_list_parent_json(self, tmp_path: Path) -> None:
        """Test list --parent with --json output."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            ["create", "Parent issue", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        parent_data = json.loads(result.stdout)
        parent_full_id = f"{parent_data['namespace']}-{parent_data['id']}"

        runner.invoke(
            app,
            [
                "create",
                "Child issue",
                "--parent",
                parent_full_id,
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        runner.invoke(
            app,
            ["create", "Unrelated issue", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            [
                "list",
                "--parent",
                parent_full_id,
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        issues = json.loads(result.stdout)
        titles = [i["title"] for i in issues]
        assert "Parent issue" in titles
        assert "Child issue" in titles
        assert "Unrelated issue" not in titles
