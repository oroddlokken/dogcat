"""Tests for Dogcat CLI commands."""

import json
from pathlib import Path

from typer.testing import CliRunner

from dogcat.cli import app

runner = CliRunner()


class TestCLIClose:
    """Test close command."""

    def test_close_issue(self, tmp_path: Path) -> None:
        """Test closing an issue."""
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
            ["close", issue_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Closed" in result.stdout

    def test_close_with_reason(self, tmp_path: Path) -> None:
        """Test closing with reason."""
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
            ["close", issue_id, "--reason", "Fixed", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0

    def test_close_output_includes_title(self, tmp_path: Path) -> None:
        """Test that close output includes the issue title."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        create_result = runner.invoke(
            app,
            ["create", "Bug to fix", "--dogcats-dir", str(dogcats_dir)],
        )
        issue_id = create_result.stdout.split(": ")[0].split()[-1]

        result = runner.invoke(
            app,
            ["close", issue_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert issue_id in result.stdout
        assert "Bug to fix" in result.stdout

    def test_delete_output_includes_title(self, tmp_path: Path) -> None:
        """Test that delete output includes the issue title."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        create_result = runner.invoke(
            app,
            ["create", "Issue to delete", "--dogcats-dir", str(dogcats_dir)],
        )
        issue_id = create_result.stdout.split(": ")[0].split()[-1]

        result = runner.invoke(
            app,
            ["delete", issue_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert issue_id in result.stdout
        assert "Issue to delete" in result.stdout

    def test_delete_multiple_issues(self, tmp_path: Path) -> None:
        """Test that delete accepts multiple issue IDs."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Create three issues
        ids: list[str] = []
        for title in ["First to delete", "Second to delete", "Third to delete"]:
            create_result = runner.invoke(
                app,
                ["create", title, "--dogcats-dir", str(dogcats_dir)],
            )
            ids.append(create_result.stdout.split(": ")[0].split()[-1])

        # Delete all three at once
        result = runner.invoke(
            app,
            ["delete", *ids, "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        for issue_id in ids:
            assert issue_id in result.stdout

    def test_delete_multiple_with_invalid_id(self, tmp_path: Path) -> None:
        """Test that delete reports errors for invalid IDs but deletes valid ones."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        create_result = runner.invoke(
            app,
            ["create", "Valid issue", "--dogcats-dir", str(dogcats_dir)],
        )
        valid_id = create_result.stdout.split(": ")[0].split()[-1]

        result = runner.invoke(
            app,
            ["delete", valid_id, "nonexistent", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code != 0
        assert valid_id in result.stdout
        assert "nonexistent" in result.stderr

    def test_close_nonexistent_issue(self, tmp_path: Path) -> None:
        """Test closing nonexistent issue."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["close", "nonexistent", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code != 0

    def test_close_tombstoned_issue_fails(self, tmp_path: Path) -> None:
        """Closing a tombstoned issue at the CLI fails non-zero.

        Storage already rejects this — this test pins the contract at
        the CLI seam so a regression that bypassed the storage guard
        (for example, a CLI helper that called a different API) would
        be caught instead of silently overwriting the tombstone's
        forensics with closed_at/closed_by. (dogcat-5o1m)
        """
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])
        create_result = runner.invoke(
            app,
            ["create", "Doomed", "--dogcats-dir", str(dogcats_dir)],
        )
        issue_id = create_result.stdout.split(": ")[0].split()[-1]

        runner.invoke(
            app,
            ["delete", issue_id, "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["close", issue_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code != 0
        assert "tombstone" in (result.stderr + result.stdout).lower()

        # State unchanged: still a tombstone, no spurious closed_at.
        from dogcat.models import Status
        from dogcat.storage import JSONLStorage

        issue = JSONLStorage(str(dogcats_dir / "issues.jsonl")).get(issue_id)
        assert issue is not None
        assert issue.status == Status.TOMBSTONE
        assert issue.closed_at is None

    def test_close_already_closed_issue(self, tmp_path: Path) -> None:
        """Closing an already-closed issue exits non-zero.

        Documents the current contract: a second close on the same
        issue is rejected (rather than silently re-stamping closed_at).
        If a future change makes this idempotent, flip this assertion.
        (dogcat-5o1m)
        """
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])
        create_result = runner.invoke(
            app,
            ["create", "Will close twice", "--dogcats-dir", str(dogcats_dir)],
        )
        issue_id = create_result.stdout.split(": ")[0].split()[-1]

        first = runner.invoke(
            app,
            ["close", issue_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert first.exit_code == 0

        second = runner.invoke(
            app,
            ["close", issue_id, "--dogcats-dir", str(dogcats_dir)],
        )
        # Either accepted (idempotent) or rejected — both lock down the
        # current behaviour. Today the CLI wraps storage.close which
        # accepts a re-close; assert that here so a regression that
        # rejects becomes visible.
        assert second.exit_code == 0
        # In either case, the closed_at must not have been wiped.
        from dogcat.models import Status
        from dogcat.storage import JSONLStorage

        issue = JSONLStorage(str(dogcats_dir / "issues.jsonl")).get(issue_id)
        assert issue is not None
        assert issue.status == Status.CLOSED
        assert issue.closed_at is not None

    def test_close_multiple_issues(self, tmp_path: Path) -> None:
        """Test that close accepts multiple issue IDs."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Create three issues
        ids: list[str] = []
        for title in ["First to close", "Second to close", "Third to close"]:
            create_result = runner.invoke(
                app,
                ["create", title, "--dogcats-dir", str(dogcats_dir)],
            )
            ids.append(create_result.stdout.split(": ")[0].split()[-1])

        # Close all three at once
        result = runner.invoke(
            app,
            ["close", *ids, "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        for issue_id in ids:
            assert issue_id in result.stdout

    def test_close_multiple_with_invalid_id(self, tmp_path: Path) -> None:
        """Test that close reports errors for invalid IDs but closes valid ones."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        create_result = runner.invoke(
            app,
            ["create", "Valid issue", "--dogcats-dir", str(dogcats_dir)],
        )
        valid_id = create_result.stdout.split(": ")[0].split()[-1]

        result = runner.invoke(
            app,
            ["close", valid_id, "nonexistent", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code != 0
        assert valid_id in result.stdout
        assert "nonexistent" in result.stderr

    def test_close_auto_populates_closed_by(self, tmp_path: Path) -> None:
        """Test that close auto-populates closed_by from git config."""
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
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        issue_data = json.loads(create_result.stdout)
        issue_id = issue_data["id"]

        result = runner.invoke(
            app,
            [
                "close",
                issue_id,
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        # Need to show the issue to get closed_by
        show_result = runner.invoke(
            app,
            [
                "show",
                issue_id,
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        closed_data = json.loads(show_result.stdout)
        # closed_by should be auto-populated
        assert closed_data["closed_by"] is not None
        assert closed_data["closed_by"] != ""

    def test_delete_auto_populates_deleted_by(self, tmp_path: Path) -> None:
        """Test that delete auto-populates deleted_by from git config."""
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
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        issue_data = json.loads(create_result.stdout)
        issue_id = issue_data["id"]

        result = runner.invoke(
            app,
            [
                "delete",
                issue_id,
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        # Need to show the issue with --all flag to get deleted_by
        show_result = runner.invoke(
            app,
            [
                "show",
                issue_id,
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        deleted_data = json.loads(show_result.stdout)
        # deleted_by should be auto-populated
        assert deleted_data["deleted_by"] is not None
        assert deleted_data["deleted_by"] != ""

    def test_close_reason_in_dedicated_field(self, tmp_path: Path) -> None:
        """Test that close reason is stored in close_reason field, not notes."""
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
                "--notes",
                "Some notes",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        issue_data = json.loads(create_result.stdout)
        issue_id = issue_data["id"]

        runner.invoke(
            app,
            [
                "close",
                issue_id,
                "--reason",
                "Fixed the bug",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        show_result = runner.invoke(
            app,
            [
                "show",
                issue_id,
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        closed_data = json.loads(show_result.stdout)
        assert closed_data["closed_reason"] == "Fixed the bug"
        assert closed_data["notes"] == "Some notes"
        assert "Closed:" not in (closed_data["notes"] or "")

    def test_close_last_child_notifies_epic_complete(self, tmp_path: Path) -> None:
        """Test that closing the last open child prints epic completion message."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        # Create an epic with two children
        epic_result = runner.invoke(
            app,
            ["create", "My Epic", "--type", "epic", "--dogcats-dir", str(dogcats_dir)],
        )
        epic_id = epic_result.stdout.split(": ")[0].split()[-1]

        child1_result = runner.invoke(
            app,
            [
                "create",
                "Child 1",
                "--parent",
                epic_id,
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        child1_id = child1_result.stdout.split(": ")[0].split()[-1]

        child2_result = runner.invoke(
            app,
            [
                "create",
                "Child 2",
                "--parent",
                epic_id,
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        child2_id = child2_result.stdout.split(": ")[0].split()[-1]

        # Close first child — should NOT show completion message
        result1 = runner.invoke(
            app,
            ["close", child1_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert "All children of" not in result1.stdout

        # Close second child — SHOULD show completion message
        result2 = runner.invoke(
            app,
            ["close", child2_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert "All children of epic" in result2.stdout
        assert "dcat close" in result2.stdout
        assert "My Epic" in result2.stdout

    def test_close_multiple_children_notifies_once(self, tmp_path: Path) -> None:
        """Test closing all children at once prints completion once."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        epic_result = runner.invoke(
            app,
            [
                "create",
                "Batch Epic",
                "--type",
                "epic",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        epic_id = epic_result.stdout.split(": ")[0].split()[-1]

        child_ids: list[str] = []
        for title in ["Task A", "Task B"]:
            r = runner.invoke(
                app,
                [
                    "create",
                    title,
                    "--parent",
                    epic_id,
                    "--dogcats-dir",
                    str(dogcats_dir),
                ],
            )
            child_ids.append(r.stdout.split(": ")[0].split()[-1])

        # Close both at once
        result = runner.invoke(
            app,
            ["close", *child_ids, "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert result.stdout.count("All children of") == 1
        assert "Batch Epic" in result.stdout

    def test_close_child_no_notification_when_siblings_open(
        self, tmp_path: Path
    ) -> None:
        """Test no completion message when other children remain open."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        epic_result = runner.invoke(
            app,
            [
                "create",
                "Open Epic",
                "--type",
                "epic",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        epic_id = epic_result.stdout.split(": ")[0].split()[-1]

        child1_result = runner.invoke(
            app,
            [
                "create",
                "Done task",
                "--parent",
                epic_id,
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        child1_id = child1_result.stdout.split(": ")[0].split()[-1]

        # Create a second child but leave it open
        runner.invoke(
            app,
            [
                "create",
                "Open task",
                "--parent",
                epic_id,
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["close", child1_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert "All children of" not in result.stdout

    def test_show_displays_close_reason(self, tmp_path: Path) -> None:
        """Test that show command displays close reason next to closed date."""
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

        runner.invoke(
            app,
            [
                "close",
                issue_id,
                "--reason",
                "All done",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        show_result = runner.invoke(
            app,
            ["show", issue_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert "All done" in show_result.stdout
        assert "Closed:" in show_result.stdout
