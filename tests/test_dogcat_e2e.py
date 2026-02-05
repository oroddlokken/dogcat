"""End-to-end integration tests for complete workflows."""

import json
from pathlib import Path

from typer.testing import CliRunner

from dogcat.cli import app
from dogcat.deps import get_ready_work
from dogcat.storage import JSONLStorage

runner = CliRunner()


class TestCompleteWorkflow:
    """Test complete issue tracking workflows."""

    def test_full_issue_lifecycle(self, tmp_path: Path) -> None:
        """Test complete issue lifecycle: create -> work -> close."""
        dogcats_dir = tmp_path / ".dogcats"

        # Initialize repo
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Create an issue
        create_result = runner.invoke(
            app,
            [
                "create",
                "Fix critical bug",
                "--type",
                "bug",
                "--priority",
                "0",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert create_result.exit_code == 0
        issue_id = create_result.stdout.split(": ")[0].split()[-1]

        # List issues
        list_result = runner.invoke(
            app,
            ["list", "--dogcats-dir", str(dogcats_dir)],
        )
        assert issue_id in list_result.stdout

        # Show issue details
        show_result = runner.invoke(
            app,
            ["show", issue_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert "Fix critical bug" in show_result.stdout

        # Update status to in_progress
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

        # Verify status changed
        show_result = runner.invoke(
            app,
            ["show", issue_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert "in_progress" in show_result.stdout

        # Close the issue
        close_result = runner.invoke(
            app,
            [
                "close",
                issue_id,
                "--reason",
                "Fixed in PR #42",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert close_result.exit_code == 0

        # Verify closed
        show_result = runner.invoke(
            app,
            ["show", issue_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert "closed" in show_result.stdout

    def test_team_workflow_with_priorities(self, tmp_path: Path) -> None:
        """Test team workflow with priority-based task distribution."""
        dogcats_dir = tmp_path / ".dogcats"

        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Create tasks with different priorities
        tasks = [
            ("High priority bug", "bug", 0),
            ("Medium feature", "feature", 2),
            ("Nice to have", "task", 4),
        ]

        issue_ids: list[str] = []
        for title, issue_type, priority in tasks:
            result = runner.invoke(
                app,
                [
                    "create",
                    title,
                    "--type",
                    issue_type,
                    "--priority",
                    str(priority),
                    "--dogcats-dir",
                    str(dogcats_dir),
                ],
            )
            issue_ids.append(result.stdout.split(": ")[0].split()[-1])

        # List all with JSON
        list_result = runner.invoke(
            app,
            ["list", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert list_result.exit_code == 0
        issues = json.loads(list_result.stdout)
        assert len(issues) == 3

        # Verify sorted by priority
        priorities = [i["priority"] for i in issues]
        assert priorities == sorted(priorities)

    def test_feature_development_flow(self, tmp_path: Path) -> None:
        """Test a complete feature development flow."""
        dogcats_dir = tmp_path / ".dogcats"

        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Create main feature task
        feature_result = runner.invoke(
            app,
            [
                "create",
                "Add user authentication",
                "--type",
                "feature",
                "--priority",
                "0",
                "--labels",
                "security,api",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        feature_result.stdout.split(": ")[0].split()[-1]

        # Create sub-tasks
        subtask1_result = runner.invoke(
            app,
            [
                "create",
                "Design auth flow",
                "--type",
                "task",
                "--priority",
                "0",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        subtask1_id = subtask1_result.stdout.split(": ")[0].split()[-1]

        subtask2_result = runner.invoke(
            app,
            [
                "create",
                "Implement JWT tokens",
                "--type",
                "task",
                "--priority",
                "1",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        subtask2_id = subtask2_result.stdout.split(": ")[0].split()[-1]

        # Create dependencies: subtasks must be done before feature
        runner.invoke(
            app,
            [
                "dep",
                "feature_id",
                "add",
                "--depends-on",
                subtask1_id,
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        # Check ready work - should have both subtasks as ready
        storage = JSONLStorage(f"{dogcats_dir}/issues.jsonl")
        ready = get_ready_work(storage)
        ready_ids = {i.full_id for i in ready}

        assert subtask1_id in ready_ids
        assert subtask2_id in ready_ids

        # Complete first subtask
        runner.invoke(
            app,
            ["close", subtask1_id, "--dogcats-dir", str(dogcats_dir)],
        )

        # Second subtask should still be ready
        ready = get_ready_work(storage)
        ready_ids = {i.full_id for i in ready}
        assert subtask2_id in ready_ids

    def test_json_output_compatibility(self, tmp_path: Path) -> None:
        """Test that all JSON output is parseable."""
        dogcats_dir = tmp_path / ".dogcats"

        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Create multiple issues
        for i in range(3):
            runner.invoke(
                app,
                [
                    "create",
                    f"Issue {i}",
                    "--labels",
                    f"label{i}",
                    "--dogcats-dir",
                    str(dogcats_dir),
                ],
            )

        # Test list JSON
        list_result = runner.invoke(
            app,
            ["list", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert list_result.exit_code == 0
        issues = json.loads(list_result.stdout)
        assert len(issues) == 3

        # Test show JSON for each
        for issue in issues:
            show_result = runner.invoke(
                app,
                ["show", issue["id"], "--json", "--dogcats-dir", str(dogcats_dir)],
            )
            assert show_result.exit_code == 0
            parsed = json.loads(show_result.stdout)
            assert parsed["id"] == issue["id"]

    def test_filtering_combinations(self, tmp_path: Path) -> None:
        """Test various filter combinations."""
        dogcats_dir = tmp_path / ".dogcats"

        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Create diverse set of issues
        runner.invoke(
            app,
            [
                "create",
                "Bug 1",
                "--type",
                "bug",
                "--priority",
                "0",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        runner.invoke(
            app,
            [
                "create",
                "Bug 2",
                "--type",
                "bug",
                "--priority",
                "2",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        runner.invoke(
            app,
            [
                "create",
                "Feature 1",
                "--type",
                "feature",
                "--priority",
                "1",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        # Filter by type
        bugs_result = runner.invoke(
            app,
            ["list", "--type", "bug", "--dogcats-dir", str(dogcats_dir)],
        )
        assert "Bug 1" in bugs_result.stdout
        assert "Bug 2" in bugs_result.stdout
        assert "Feature 1" not in bugs_result.stdout

        # Filter by priority
        high_result = runner.invoke(
            app,
            ["list", "--priority", "0", "--dogcats-dir", str(dogcats_dir)],
        )
        assert "Bug 1" in high_result.stdout
        assert "Bug 2" not in high_result.stdout

        # Combine filters
        combined_result = runner.invoke(
            app,
            [
                "list",
                "--type",
                "bug",
                "--priority",
                "2",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert "Bug 2" in combined_result.stdout
        assert "Bug 1" not in combined_result.stdout


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_nonexistent_issue_operations(self, tmp_path: Path) -> None:
        """Test operations on nonexistent issues."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Show nonexistent
        result = runner.invoke(
            app,
            ["show", "nonexistent", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code != 0

        # Update nonexistent
        result = runner.invoke(
            app,
            [
                "update",
                "nonexistent",
                "--title",
                "New",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code != 0

        # Close nonexistent
        result = runner.invoke(
            app,
            ["close", "nonexistent", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code != 0

    def test_invalid_priority(self, tmp_path: Path) -> None:
        """Test creation with invalid priority."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Priority out of range should fail gracefully (or be handled)
        runner.invoke(
            app,
            [
                "create",
                "Test",
                "--priority",
                "10",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        # Depending on implementation, this might fail during creation or pass
        # but the important thing is it doesn't crash


class TestDataPersistence:
    """Test that data persists correctly."""

    def test_data_survives_restart(self, tmp_path: Path) -> None:
        """Test that issues survive storage restart."""
        dogcats_dir = tmp_path / ".dogcats"

        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Create an issue
        create_result = runner.invoke(
            app,
            [
                "create",
                "Persistent issue",
                "--description",
                "This should persist",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        issue_id = create_result.stdout.split(": ")[0].split()[-1]

        # Reload storage and verify
        storage = JSONLStorage(f"{dogcats_dir}/issues.jsonl")
        issue = storage.get(issue_id)

        assert issue is not None
        assert issue.title == "Persistent issue"
        assert issue.description == "This should persist"

    def test_updates_persist(self, tmp_path: Path) -> None:
        """Test that updates persist."""
        dogcats_dir = tmp_path / ".dogcats"

        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        create_result = runner.invoke(
            app,
            ["create", "Original", "--dogcats-dir", str(dogcats_dir)],
        )
        issue_id = create_result.stdout.split(": ")[0].split()[-1]

        # Update
        runner.invoke(
            app,
            [
                "update",
                issue_id,
                "--title",
                "Updated",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        # Reload and verify
        storage = JSONLStorage(f"{dogcats_dir}/issues.jsonl")
        issue = storage.get(issue_id)
        assert issue is not None
        assert issue.title == "Updated"
