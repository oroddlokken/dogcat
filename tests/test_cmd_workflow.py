"""Tests for Dogcat CLI commands."""

import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from dogcat.cli import app

runner = CliRunner()


class TestCLIDependency:
    """Test dependency commands."""

    def test_dep_add(self, tmp_path: Path) -> None:
        """Test adding a dependency."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        create1 = runner.invoke(
            app,
            ["create", "Issue 1", "--dogcats-dir", str(dogcats_dir)],
        )
        issue1_id = create1.stdout.split(": ")[0].split()[-1]

        create2 = runner.invoke(
            app,
            ["create", "Issue 2", "--dogcats-dir", str(dogcats_dir)],
        )
        issue2_id = create2.stdout.split(": ")[0].split()[-1]

        result = runner.invoke(
            app,
            [
                "dep",
                issue2_id,
                "add",
                "--depends-on",
                issue1_id,
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Added dependency" in result.stdout

    def test_dep_list(self, tmp_path: Path) -> None:
        """Test listing dependencies."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        create1 = runner.invoke(
            app,
            ["create", "Issue 1", "--dogcats-dir", str(dogcats_dir)],
        )
        issue1_id = create1.stdout.split(": ")[0].split()[-1]

        create2 = runner.invoke(
            app,
            ["create", "Issue 2", "--dogcats-dir", str(dogcats_dir)],
        )
        issue2_id = create2.stdout.split(": ")[0].split()[-1]

        runner.invoke(
            app,
            [
                "dep",
                issue2_id,
                "add",
                "--depends-on",
                issue1_id,
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            [
                "dep",
                issue2_id,
                "list",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert issue1_id in result.stdout


class TestCLIReady:
    """Test ready work command."""

    def test_ready_no_issues(self, tmp_path: Path) -> None:
        """Test ready with no issues."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["ready", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No ready work" in result.stdout

    def test_ready_shows_unblocked(self, tmp_path: Path) -> None:
        """Test that ready shows unblocked issues."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        create1 = runner.invoke(
            app,
            ["create", "Issue 1", "--dogcats-dir", str(dogcats_dir)],
        )
        issue1_id = create1.stdout.split(": ")[0].split()[-1]

        result = runner.invoke(
            app,
            ["ready", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert issue1_id in result.stdout

    def test_ready_agent_only(self, tmp_path: Path) -> None:
        """Test that ready --agent-only filters out manual issues."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Create a normal issue
        create1 = runner.invoke(
            app,
            ["create", "Normal issue", "--dogcats-dir", str(dogcats_dir)],
        )
        normal_id = create1.stdout.split(": ")[0].split()[-1]

        # Create an issue marked as manual
        create2 = runner.invoke(
            app,
            [
                "create",
                "Agent skip issue",
                "--manual",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        skip_id = create2.stdout.split(": ")[0].split()[-1]

        # Without filter, both should appear
        result = runner.invoke(
            app,
            ["ready", "--dogcats-dir", str(dogcats_dir)],
        )
        assert normal_id in result.stdout
        assert skip_id in result.stdout

        # With filter, only normal should appear
        result = runner.invoke(
            app,
            ["ready", "--agent-only", "--dogcats-dir", str(dogcats_dir)],
        )
        assert normal_id in result.stdout
        assert skip_id not in result.stdout


class TestCLIBlocked:
    """Test blocked command."""

    def test_blocked_no_issues(self, tmp_path: Path) -> None:
        """Test blocked with no blocked issues."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            ["blocked", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No blocked issues" in result.stdout

    def test_blocked_shows_issue_details(self, tmp_path: Path) -> None:
        """Test blocked output includes title, type, and priority."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        # Create blocker issue
        create1 = runner.invoke(
            app,
            ["create", "Blocker task", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        data1 = json.loads(create1.stdout)
        blocker_id = f"{data1['namespace']}-{data1['id']}"

        # Create blocked issue with dependency
        create2 = runner.invoke(
            app,
            [
                "create",
                "Blocked task",
                "--type",
                "bug",
                "--priority",
                "1",
                "--depends-on",
                blocker_id,
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        data2 = json.loads(create2.stdout)
        blocked_id = f"{data2['namespace']}-{data2['id']}"

        result = runner.invoke(
            app,
            ["blocked", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert blocked_id in result.stdout
        assert "Blocked task" in result.stdout
        assert "bug" in result.stdout
        assert blocker_id in result.stdout
        assert "Blocker task" in result.stdout
        assert "blocked by" in result.stdout

    def test_blocked_uses_format_issue_brief(self, tmp_path: Path) -> None:
        """Blocked uses format_issue_brief for both issues.

        Ensures blocked output stays in sync with list when
        format_issue_brief is updated.
        """
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        create1 = runner.invoke(
            app,
            ["create", "Blocker", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        data1 = json.loads(create1.stdout)
        blocker_id = f"{data1['namespace']}-{data1['id']}"

        runner.invoke(
            app,
            [
                "create",
                "Blocked",
                "--depends-on",
                blocker_id,
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        with patch(
            "dogcat.cli._cmd_workflow.format_issue_brief",
            wraps=__import__(
                "dogcat.cli._formatting",
                fromlist=["format_issue_brief"],
            ).format_issue_brief,
        ) as mock_fmt:
            runner.invoke(
                app,
                ["blocked", "--dogcats-dir", str(dogcats_dir)],
            )
            # Called for both the blocked issue and the blocker
            assert mock_fmt.call_count == 2


class TestCLIInProgress:
    """Test in-progress command."""

    def test_in_progress_no_issues(self, tmp_path: Path) -> None:
        """Test in-progress with no in-progress issues."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["in-progress", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No in-progress issues" in result.stdout

    def test_in_progress_shows_only_in_progress(self, tmp_path: Path) -> None:
        """Test that in-progress shows only in_progress issues."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Create two issues
        create1 = runner.invoke(
            app,
            ["create", "Open issue", "--dogcats-dir", str(dogcats_dir)],
        )
        open_id = create1.stdout.split(": ")[0].split()[-1]

        create2 = runner.invoke(
            app,
            [
                "create",
                "WIP issue",
                "--status",
                "in_progress",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        wip_id = create2.stdout.split(": ")[0].split()[-1]

        result = runner.invoke(
            app,
            ["in-progress", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert wip_id in result.stdout
        assert open_id not in result.stdout

    def test_in_progress_json_output(self, tmp_path: Path) -> None:
        """Test in-progress with --json flag."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        runner.invoke(
            app,
            [
                "create",
                "WIP issue",
                "--status",
                "in_progress",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["in-progress", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        import json

        data = json.loads(result.stdout)
        assert len(data) == 1
        assert data[0]["status"] == "in_progress"


class TestCLIInReview:
    """Test in-review command."""

    def test_in_review_no_issues(self, tmp_path: Path) -> None:
        """Test in-review with no in-review issues."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            ["in-review", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No in-review issues" in result.stdout

    def test_in_review_shows_only_in_review(self, tmp_path: Path) -> None:
        """Test that in-review shows only in_review issues."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        # Create an open issue
        create1 = runner.invoke(
            app,
            ["create", "Open issue", "--dogcats-dir", str(dogcats_dir)],
        )
        open_id = create1.stdout.split(": ")[0].split()[-1]

        # Create an in_review issue
        create2 = runner.invoke(
            app,
            [
                "create",
                "Review issue",
                "--status",
                "in_review",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        review_id = create2.stdout.split(": ")[0].split()[-1]

        result = runner.invoke(
            app,
            ["in-review", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert review_id in result.stdout
        assert open_id not in result.stdout

    def test_in_review_json_output(self, tmp_path: Path) -> None:
        """Test in-review with --json flag."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        runner.invoke(
            app,
            [
                "create",
                "Review issue",
                "--status",
                "in_review",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["in-review", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert len(data) == 1
        assert data[0]["status"] == "in_review"


class TestCLIStatusShortcuts:
    """Test ir and ip status listing shortcut commands."""

    def test_ir_lists_in_review_issues(self, tmp_path: Path) -> None:
        """Test that 'ir' lists issues with in_review status."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        create_result = runner.invoke(
            app,
            ["create", "Review issue", "--dogcats-dir", str(dogcats_dir)],
        )
        issue_id = create_result.stdout.split(": ")[0].split()[-1]
        runner.invoke(
            app,
            [
                "update",
                issue_id,
                "--status",
                "in_review",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["ir", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "In Review (1):" in result.stdout
        assert "Review issue" in result.stdout

    def test_ir_empty(self, tmp_path: Path) -> None:
        """Test ir with no in-review issues."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            ["ir", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No in-review issues" in result.stdout

    def test_ir_json_output(self, tmp_path: Path) -> None:
        """Test ir with --json flag."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        create_result = runner.invoke(
            app,
            ["create", "Review issue", "--dogcats-dir", str(dogcats_dir)],
        )
        issue_id = create_result.stdout.split(": ")[0].split()[-1]
        runner.invoke(
            app,
            [
                "update",
                issue_id,
                "--status",
                "in_review",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["ir", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert len(data) == 1
        assert data[0]["status"] == "in_review"

    def test_ip_lists_in_progress_issues(self, tmp_path: Path) -> None:
        """Test that 'ip' lists issues with in_progress status."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        create_result = runner.invoke(
            app,
            ["create", "Progress issue", "--dogcats-dir", str(dogcats_dir)],
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
            ["ip", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "In Progress (1):" in result.stdout
        assert "Progress issue" in result.stdout

    def test_ip_empty(self, tmp_path: Path) -> None:
        """Test ip with no in-progress issues."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            ["ip", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No in-progress issues" in result.stdout


class TestCLIDeferred:
    """Test deferred command."""

    def test_deferred_no_issues(self, tmp_path: Path) -> None:
        """Test deferred with no deferred issues."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            ["deferred", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No deferred issues" in result.stdout

    def test_deferred_shows_only_deferred(self, tmp_path: Path) -> None:
        """Test that deferred shows only deferred issues."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        # Create an open issue
        create1 = runner.invoke(
            app,
            ["create", "Open issue", "--dogcats-dir", str(dogcats_dir)],
        )
        open_id = create1.stdout.split(": ")[0].split()[-1]

        # Create a deferred issue
        create2 = runner.invoke(
            app,
            [
                "create",
                "Deferred issue",
                "--status",
                "deferred",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        deferred_id = create2.stdout.split(": ")[0].split()[-1]

        result = runner.invoke(
            app,
            ["deferred", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert deferred_id in result.stdout
        assert open_id not in result.stdout

    def test_deferred_json_output(self, tmp_path: Path) -> None:
        """Test deferred with --json flag."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        runner.invoke(
            app,
            [
                "create",
                "Deferred issue",
                "--status",
                "deferred",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["deferred", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert len(data) == 1
        assert data[0]["status"] == "deferred"


class TestCLIDeferShortcut:
    """Test defer shortcut command."""

    def test_defer_sets_status_to_deferred(self, tmp_path: Path) -> None:
        """Test that 'defer' sets issue status to deferred."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        create_result = runner.invoke(
            app,
            ["create", "Test issue", "--dogcats-dir", str(dogcats_dir)],
        )
        issue_id = create_result.stdout.split(": ")[0].split()[-1]

        result = runner.invoke(
            app,
            ["defer", issue_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "✓ Deferred" in result.stdout

        # Verify status changed
        show_result = runner.invoke(
            app,
            ["show", issue_id, "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        data = json.loads(show_result.stdout)
        assert data["status"] == "deferred"

    def test_defer_json_output(self, tmp_path: Path) -> None:
        """Test defer with --json flag."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        create_result = runner.invoke(
            app,
            ["create", "Test issue", "--dogcats-dir", str(dogcats_dir)],
        )
        issue_id = create_result.stdout.split(": ")[0].split()[-1]

        result = runner.invoke(
            app,
            ["defer", issue_id, "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["status"] == "deferred"

    def test_defer_nonexistent_issue(self, tmp_path: Path) -> None:
        """Test defer with nonexistent issue."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            ["defer", "nonexistent", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 1
        assert "Error" in result.stdout or "Error" in result.stderr


class TestCLIManualList:
    """Test manual command."""

    def test_manual_no_issues(self, tmp_path: Path) -> None:
        """Test manual with no manual issues."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            ["manual", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No manual issues" in result.stdout

    def test_manual_shows_only_manual(self, tmp_path: Path) -> None:
        """Test that manual shows only manual-flagged issues."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        # Create a normal issue
        create1 = runner.invoke(
            app,
            ["create", "Normal issue", "--dogcats-dir", str(dogcats_dir)],
        )
        normal_id = create1.stdout.split(": ")[0].split()[-1]

        # Create a manual issue
        create2 = runner.invoke(
            app,
            [
                "create",
                "Manual issue",
                "--manual",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        manual_id = create2.stdout.split(": ")[0].split()[-1]

        result = runner.invoke(
            app,
            ["manual", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert manual_id in result.stdout
        assert normal_id not in result.stdout

    def test_manual_excludes_closed(self, tmp_path: Path) -> None:
        """Test that manual excludes closed manual issues."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        # Create a manual issue and close it
        create_result = runner.invoke(
            app,
            [
                "create",
                "Closed manual issue",
                "--manual",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        issue_id = create_result.stdout.split(": ")[0].split()[-1]
        runner.invoke(
            app,
            ["close", issue_id, "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["manual", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No manual issues" in result.stdout

    def test_manual_json_output(self, tmp_path: Path) -> None:
        """Test manual with --json flag."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        runner.invoke(
            app,
            [
                "create",
                "Manual issue",
                "--manual",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["manual", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert len(data) == 1
        assert data[0]["metadata"]["manual"] is True


class TestCLIMarkManualShortcut:
    """Test mark-manual shortcut command."""

    def test_mark_manual_sets_flag(self, tmp_path: Path) -> None:
        """Test that 'mark-manual' sets the manual metadata flag."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        create_result = runner.invoke(
            app,
            ["create", "Test issue", "--dogcats-dir", str(dogcats_dir)],
        )
        issue_id = create_result.stdout.split(": ")[0].split()[-1]

        result = runner.invoke(
            app,
            ["mark-manual", issue_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "✓ Marked manual" in result.stdout

        # Verify metadata changed
        show_result = runner.invoke(
            app,
            ["show", issue_id, "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        data = json.loads(show_result.stdout)
        assert data["metadata"]["manual"] is True

    def test_mark_manual_json_output(self, tmp_path: Path) -> None:
        """Test mark-manual with --json flag."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        create_result = runner.invoke(
            app,
            ["create", "Test issue", "--dogcats-dir", str(dogcats_dir)],
        )
        issue_id = create_result.stdout.split(": ")[0].split()[-1]

        result = runner.invoke(
            app,
            ["mark-manual", issue_id, "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["metadata"]["manual"] is True

    def test_mark_manual_nonexistent_issue(self, tmp_path: Path) -> None:
        """Test mark-manual with nonexistent issue."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            ["mark-manual", "nonexistent", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 1
        assert "Error" in result.stdout or "Error" in result.stderr


class TestStatusHeaderCounts:
    """Test item counts in status listing headers."""

    def test_pr_shows_counts_in_headers(self, tmp_path: Path) -> None:
        """Test that pr shows counts in section headers."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        runner.invoke(
            app,
            [
                "create",
                "WIP issue",
                "--status",
                "in_progress",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["pr", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "In Progress (1):" in result.stdout
        assert "In Review (0):" in result.stdout

    def test_pr_shows_zero_counts(self, tmp_path: Path) -> None:
        """Test that pr shows (0) counts when no issues."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            ["pr", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "In Progress (0):" in result.stdout
        assert "In Review (0):" in result.stdout

    def test_in_progress_shows_count_header(self, tmp_path: Path) -> None:
        """Test that in-progress shows count header when issues exist."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        runner.invoke(
            app,
            [
                "create",
                "WIP 1",
                "--status",
                "in_progress",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        runner.invoke(
            app,
            [
                "create",
                "WIP 2",
                "--status",
                "in_progress",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["in-progress", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "In Progress (2):" in result.stdout

    def test_in_review_shows_count_header(self, tmp_path: Path) -> None:
        """Test that in-review shows count header when issues exist."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        runner.invoke(
            app,
            [
                "create",
                "Review issue",
                "--status",
                "in_review",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["in-review", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "In Review (1):" in result.stdout

    def test_ready_shows_count_header(self, tmp_path: Path) -> None:
        """Test that ready shows count header when issues exist."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        runner.invoke(
            app,
            ["create", "Ready 1", "--dogcats-dir", str(dogcats_dir)],
        )
        runner.invoke(
            app,
            ["create", "Ready 2", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["ready", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Ready (2):" in result.stdout


class TestIncludeInbox:
    """Test --include-inbox flag on ready and list commands."""

    def test_ready_include_inbox_shows_proposals(self, tmp_path: Path) -> None:
        """Test that ready --include-inbox shows inbox proposals."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--namespace", "test", "--dogcats-dir", str(dogcats_dir)],
        )

        runner.invoke(
            app,
            ["propose", "Inbox proposal", "--to", str(tmp_path)],
        )

        result = runner.invoke(
            app,
            ["ready", "--include-inbox", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Inbox (1):" in result.stdout
        assert "Inbox proposal" in result.stdout

    def test_ready_without_include_inbox_hides_proposals(self, tmp_path: Path) -> None:
        """Test that ready without --include-inbox doesn't show proposals."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--namespace", "test", "--dogcats-dir", str(dogcats_dir)],
        )

        runner.invoke(
            app,
            ["propose", "Hidden proposal", "--to", str(tmp_path)],
        )

        result = runner.invoke(
            app,
            ["ready", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Inbox" not in result.stdout
        assert "Hidden proposal" not in result.stdout

    def test_list_include_inbox_shows_proposals(self, tmp_path: Path) -> None:
        """Test that list --include-inbox shows inbox proposals."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--namespace", "test", "--dogcats-dir", str(dogcats_dir)],
        )

        runner.invoke(
            app,
            ["propose", "Listed proposal", "--to", str(tmp_path)],
        )

        result = runner.invoke(
            app,
            ["list", "--include-inbox", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Inbox (1):" in result.stdout
        assert "Listed proposal" in result.stdout

    def test_list_without_include_inbox_hides_proposals(self, tmp_path: Path) -> None:
        """Test that list without --include-inbox doesn't show proposals."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--namespace", "test", "--dogcats-dir", str(dogcats_dir)],
        )

        runner.invoke(
            app,
            ["propose", "Hidden proposal", "--to", str(tmp_path)],
        )

        result = runner.invoke(
            app,
            ["list", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Inbox" not in result.stdout

    def test_list_include_inbox_filters_foreign_namespace(self, tmp_path: Path) -> None:
        """Test that list --include-inbox hides proposals from other namespaces."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--namespace", "test", "--dogcats-dir", str(dogcats_dir)],
        )

        # Create a proposal with the local namespace
        runner.invoke(
            app,
            ["propose", "Local proposal", "--to", str(tmp_path)],
        )
        # Create a proposal with a foreign namespace
        runner.invoke(
            app,
            [
                "propose",
                "Foreign proposal",
                "--namespace",
                "other",
                "--to",
                str(tmp_path),
            ],
        )

        result = runner.invoke(
            app,
            ["list", "--include-inbox", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Local proposal" in result.stdout
        assert "Foreign proposal" not in result.stdout

    def test_list_include_inbox_all_namespaces_shows_foreign(
        self, tmp_path: Path
    ) -> None:
        """Test that list --include-inbox -A shows proposals from all namespaces."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--namespace", "test", "--dogcats-dir", str(dogcats_dir)],
        )

        runner.invoke(
            app,
            ["propose", "Local proposal", "--to", str(tmp_path)],
        )
        runner.invoke(
            app,
            [
                "propose",
                "Foreign proposal",
                "--namespace",
                "other",
                "--to",
                str(tmp_path),
            ],
        )

        result = runner.invoke(
            app,
            [
                "list",
                "--include-inbox",
                "-A",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Local proposal" in result.stdout
        assert "Foreign proposal" in result.stdout

    def test_ready_include_inbox_filters_foreign_namespace(
        self, tmp_path: Path
    ) -> None:
        """Test that ready --include-inbox hides proposals from other namespaces."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--namespace", "test", "--dogcats-dir", str(dogcats_dir)],
        )

        runner.invoke(
            app,
            ["propose", "Local ready", "--to", str(tmp_path)],
        )
        runner.invoke(
            app,
            [
                "propose",
                "Foreign ready",
                "--namespace",
                "other",
                "--to",
                str(tmp_path),
            ],
        )

        result = runner.invoke(
            app,
            ["ready", "--include-inbox", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Local ready" in result.stdout
        assert "Foreign ready" not in result.stdout

    def test_list_include_inbox_shows_remote_proposals(self, tmp_path: Path) -> None:
        """Test that list --include-inbox shows remote inbox proposals."""
        from dogcat.config import save_config, save_local_config

        local_dir = tmp_path / "local"
        local_dir.mkdir()
        local_dogcats = local_dir / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(local_dogcats)])
        save_config(str(local_dogcats), {"namespace": "myproj"})

        remote_dir = tmp_path / "remote"
        remote_dir.mkdir()
        remote_dogcats = remote_dir / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(remote_dogcats)])

        save_local_config(str(local_dogcats), {"inbox_remote": str(remote_dir)})

        # Create a proposal in the remote inbox targeting our namespace
        runner.invoke(
            app,
            [
                "propose",
                "Remote feature idea",
                "--to",
                str(remote_dir),
                "--namespace",
                "myproj",
            ],
        )

        result = runner.invoke(
            app,
            ["list", "--include-inbox", "--dogcats-dir", str(local_dogcats)],
        )
        assert result.exit_code == 0
        assert "Remote Inbox" in result.stdout
        assert "Remote feature idea" in result.stdout

    def test_list_include_inbox_hides_foreign_remote_proposals(
        self, tmp_path: Path
    ) -> None:
        """--include-inbox hides remote proposals from other namespaces."""
        from dogcat.config import save_config, save_local_config

        local_dir = tmp_path / "local"
        local_dir.mkdir()
        local_dogcats = local_dir / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(local_dogcats)])
        save_config(str(local_dogcats), {"namespace": "myproj"})

        remote_dir = tmp_path / "remote"
        remote_dir.mkdir()
        remote_dogcats = remote_dir / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(remote_dogcats)])

        save_local_config(str(local_dogcats), {"inbox_remote": str(remote_dir)})

        # Create proposals for different namespaces
        runner.invoke(
            app,
            [
                "propose",
                "Our proposal",
                "--to",
                str(remote_dir),
                "--namespace",
                "myproj",
            ],
        )
        runner.invoke(
            app,
            [
                "propose",
                "Other proposal",
                "--to",
                str(remote_dir),
                "--namespace",
                "other",
            ],
        )

        result = runner.invoke(
            app,
            ["list", "--include-inbox", "--dogcats-dir", str(local_dogcats)],
        )
        assert result.exit_code == 0
        assert "Our proposal" in result.stdout
        assert "Other proposal" not in result.stdout
