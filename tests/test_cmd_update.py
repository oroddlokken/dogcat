"""Tests for Dogcat CLI commands."""

import json
from pathlib import Path

from typer.testing import CliRunner

from dogcat.cli import app

runner = CliRunner()


class TestCLIUpdate:
    """Test update command."""

    def test_update_title(self, tmp_path: Path) -> None:
        """Test updating issue title."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        create_result = runner.invoke(
            app,
            ["create", "Original title", "--dogcats-dir", str(dogcats_dir)],
        )
        issue_id = create_result.stdout.split(": ")[0].split()[-1]

        result = runner.invoke(
            app,
            [
                "update",
                issue_id,
                "--title",
                "Updated title",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0

        show_result = runner.invoke(
            app,
            ["show", issue_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert "Updated title" in show_result.stdout

    def test_update_status(self, tmp_path: Path) -> None:
        """Test updating issue status."""
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
                "update",
                issue_id,
                "--status",
                "in_progress",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0

    def test_update_priority_pint(self, tmp_path: Path) -> None:
        """Test updating priority with pINT notation (e.g., -p p1)."""
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
        data = json.loads(create_result.stdout)
        issue_id = f"{data['namespace']}-{data['id']}"

        # Update with pINT notation
        result = runner.invoke(
            app,
            [
                "update",
                issue_id,
                "-p",
                "p1",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        updated = json.loads(result.stdout)
        assert updated["priority"] == 1

        # Update with bare int
        result = runner.invoke(
            app,
            [
                "update",
                issue_id,
                "-p",
                "4",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        updated = json.loads(result.stdout)
        assert updated["priority"] == 4

        # Invalid pINT
        result = runner.invoke(
            app,
            [
                "update",
                issue_id,
                "-p",
                "p7",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code != 0

    def test_update_priority_string_name(self, tmp_path: Path) -> None:
        """Test updating priority with string name (e.g., -p critical)."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        create_result = runner.invoke(
            app,
            ["create", "Test issue", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        data = json.loads(create_result.stdout)
        issue_id = f"{data['namespace']}-{data['id']}"

        result = runner.invoke(
            app,
            [
                "update",
                issue_id,
                "-p",
                "critical",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        updated = json.loads(result.stdout)
        assert updated["priority"] == 0

    def test_update_nonexistent_issue(self, tmp_path: Path) -> None:
        """Test updating nonexistent issue."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

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

    def test_update_no_changes(self, tmp_path: Path) -> None:
        """Test update with no changes."""
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
            ["update", issue_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code != 0

    def test_update_output_includes_title(self, tmp_path: Path) -> None:
        """Test that update output includes the issue title."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        create_result = runner.invoke(
            app,
            ["create", "My important task", "--dogcats-dir", str(dogcats_dir)],
        )
        issue_id = create_result.stdout.split(": ")[0].split()[-1]

        result = runner.invoke(
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
        assert result.exit_code == 0
        assert issue_id in result.stdout
        assert "My important task" in result.stdout

    def test_update_parent(self, tmp_path: Path) -> None:
        """Test updating an issue's parent to make it a subtask."""
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
        parent_id = parent_data["id"]
        parent_full_id = f"{parent_data['namespace']}-{parent_id}"

        # Create child issue without parent
        result = runner.invoke(
            app,
            [
                "create",
                "Child issue",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        child_data = json.loads(result.stdout)
        child_id = child_data["id"]
        assert child_data["parent"] is None

        # Update child to have parent
        result = runner.invoke(
            app,
            [
                "update",
                child_id,
                "--parent",
                parent_id,
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        updated_data = json.loads(result.stdout)
        # Parent is now stored as full ID
        assert updated_data["parent"] == parent_full_id

    def test_update_parent_with_partial_id_resolves_to_full(
        self,
        tmp_path: Path,
    ) -> None:
        """Test updating issue's parent with partial ID resolves to full ID."""
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
        parent_hash = parent_data["id"]
        parent_namespace = parent_data["namespace"]
        parent_full_id = f"{parent_namespace}-{parent_hash}"

        # Create child issue
        result = runner.invoke(
            app,
            [
                "create",
                "Child issue",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        child_data = json.loads(result.stdout)
        child_id = child_data["id"]

        # Update child with partial parent ID
        result = runner.invoke(
            app,
            [
                "update",
                child_id,
                "--parent",
                parent_hash,
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        updated_data = json.loads(result.stdout)
        assert updated_data["parent"] == parent_full_id

    def test_update_parent_nonexistent_fails(self, tmp_path: Path) -> None:
        """Test updating issue's parent to nonexistent ID fails."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Create issue
        result = runner.invoke(
            app,
            [
                "create",
                "Test issue",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        issue_data = json.loads(result.stdout)
        issue_id = issue_data["id"]

        result = runner.invoke(
            app,
            [
                "update",
                issue_id,
                "--parent",
                "nonexistent",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 1
        assert "Parent issue nonexistent not found" in result.output

    def test_update_duplicate_of_with_partial_id_resolves_to_full(
        self,
        tmp_path: Path,
    ) -> None:
        """Test updating issue's duplicate_of with partial ID resolves to full ID."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Create original issue
        result = runner.invoke(
            app,
            [
                "create",
                "Original issue",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        original_data = json.loads(result.stdout)
        original_hash = original_data["id"]
        original_namespace = original_data["namespace"]
        original_full_id = f"{original_namespace}-{original_hash}"

        # Create duplicate issue
        result = runner.invoke(
            app,
            [
                "create",
                "Duplicate issue",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        dup_data = json.loads(result.stdout)
        dup_id = dup_data["id"]

        # Mark as duplicate using partial ID
        result = runner.invoke(
            app,
            [
                "update",
                dup_id,
                "--duplicate-of",
                original_hash,
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        updated_data = json.loads(result.stdout)
        assert updated_data["duplicate_of"] == original_full_id

    def test_update_duplicate_of_nonexistent_fails(self, tmp_path: Path) -> None:
        """Test updating issue's duplicate_of to nonexistent ID fails."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Create issue
        result = runner.invoke(
            app,
            [
                "create",
                "Test issue",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        issue_data = json.loads(result.stdout)
        issue_id = issue_data["id"]

        result = runner.invoke(
            app,
            [
                "update",
                issue_id,
                "--duplicate-of",
                "nonexistent",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 1
        assert "Issue nonexistent not found" in result.output

    def test_update_auto_populates_updated_by(self, tmp_path: Path) -> None:
        """Test that update auto-populates updated_by from git config."""
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
                "update",
                issue_id,
                "--title",
                "Updated title",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        updated_data = json.loads(result.stdout)
        # updated_by should be auto-populated
        assert updated_data["updated_by"] is not None
        assert updated_data["updated_by"] != ""


class TestUpdateAlignedOptions:
    """Test --design, --external-ref, --depends-on, --blocks, --editor on update."""

    def test_update_design(self, tmp_path: Path) -> None:
        """Test updating issue design notes."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        create_result = runner.invoke(
            app,
            ["create", "Test issue", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        data = json.loads(create_result.stdout)
        issue_id = f"{data['namespace']}-{data['id']}"

        result = runner.invoke(
            app,
            [
                "update",
                issue_id,
                "--design",
                "Use observer pattern",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0

        show_result = runner.invoke(
            app,
            ["show", issue_id, "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        show_data = json.loads(show_result.stdout)
        assert show_data["design"] == "Use observer pattern"

    def test_update_external_ref(self, tmp_path: Path) -> None:
        """Test updating issue external reference."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        create_result = runner.invoke(
            app,
            ["create", "Test issue", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        data = json.loads(create_result.stdout)
        issue_id = f"{data['namespace']}-{data['id']}"

        result = runner.invoke(
            app,
            [
                "update",
                issue_id,
                "--external-ref",
                "https://jira.example.com/PROJ-123",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0

        show_result = runner.invoke(
            app,
            ["show", issue_id, "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        show_data = json.loads(show_result.stdout)
        assert show_data["external_ref"] == "https://jira.example.com/PROJ-123"

    def test_update_depends_on(self, tmp_path: Path) -> None:
        """Test adding a dependency via update --depends-on."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        create1 = runner.invoke(
            app,
            ["create", "Blocker issue", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        data1 = json.loads(create1.stdout)
        blocker_id = f"{data1['namespace']}-{data1['id']}"

        create2 = runner.invoke(
            app,
            ["create", "Dependent issue", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        data2 = json.loads(create2.stdout)
        dep_id = f"{data2['namespace']}-{data2['id']}"

        result = runner.invoke(
            app,
            [
                "update",
                dep_id,
                "--depends-on",
                blocker_id,
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0

        # Verify dependency exists
        dep_result = runner.invoke(
            app,
            ["dep", dep_id, "list", "--dogcats-dir", str(dogcats_dir)],
        )
        assert blocker_id in dep_result.stdout

    def test_update_blocks(self, tmp_path: Path) -> None:
        """Test adding a dependency via update --blocks."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        create1 = runner.invoke(
            app,
            ["create", "Blocker issue", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        data1 = json.loads(create1.stdout)
        blocker_id = f"{data1['namespace']}-{data1['id']}"

        create2 = runner.invoke(
            app,
            ["create", "Blocked issue", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        data2 = json.loads(create2.stdout)
        blocked_id = f"{data2['namespace']}-{data2['id']}"

        result = runner.invoke(
            app,
            [
                "update",
                blocker_id,
                "--blocks",
                blocked_id,
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0

        # Verify dependency exists on the blocked issue
        dep_result = runner.invoke(
            app,
            ["dep", blocked_id, "list", "--dogcats-dir", str(dogcats_dir)],
        )
        assert blocker_id in dep_result.stdout

    def test_update_depends_on_only_without_field_updates(
        self,
        tmp_path: Path,
    ) -> None:
        """Test that --depends-on works even without any field updates."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        create1 = runner.invoke(
            app,
            ["create", "Issue A", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        d1 = json.loads(create1.stdout)
        id1 = f"{d1['namespace']}-{d1['id']}"

        create2 = runner.invoke(
            app,
            ["create", "Issue B", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        d2 = json.loads(create2.stdout)
        id2 = f"{d2['namespace']}-{d2['id']}"

        # Only --depends-on, no field changes
        result = runner.invoke(
            app,
            [
                "update",
                id2,
                "--depends-on",
                id1,
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0


class TestUpdateLabels:
    """Test --labels option in update command."""

    def test_update_labels_replaces(self, tmp_path: Path) -> None:
        """Test that --labels replaces existing labels."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        create_result = runner.invoke(
            app,
            [
                "create",
                "Test issue",
                "--labels",
                "old1,old2",
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
                "new1,new2",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0

        show_result = runner.invoke(
            app,
            ["show", issue_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert "new1" in show_result.stdout
        assert "new2" in show_result.stdout
        assert "old1" not in show_result.stdout

    def test_update_labels_clear(self, tmp_path: Path) -> None:
        """Test clearing labels with empty string."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

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
                "update",
                issue_id,
                "--labels",
                "",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0

        show_result = runner.invoke(
            app,
            ["show", issue_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert "urgent" not in show_result.stdout


class TestUpdateBodyAlias:
    """Test --body as hidden alias for --description in update."""

    def test_update_with_body(self, tmp_path: Path) -> None:
        """Test that --body sets the description on update."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        create_result = runner.invoke(
            app,
            ["create", "Test issue", "--dogcats-dir", str(dogcats_dir)],
        )
        issue_id = create_result.stdout.split(": ")[0].split()[-1]

        result = runner.invoke(
            app,
            [
                "update",
                issue_id,
                "--body",
                "updated via body",
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
        assert data["description"] == "updated via body"

    def test_update_body_and_description_conflict(self, tmp_path: Path) -> None:
        """Test that --body and --description together produce an error."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        create_result = runner.invoke(
            app,
            ["create", "Test issue", "--dogcats-dir", str(dogcats_dir)],
        )
        issue_id = create_result.stdout.split(": ")[0].split()[-1]

        result = runner.invoke(
            app,
            [
                "update",
                issue_id,
                "--body",
                "b",
                "--description",
                "d",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 1
        assert "Cannot use both" in result.stderr


class TestUpdateMultipleIssues:
    """Test updating multiple issues at once."""

    def test_update_status_multiple_issues(self, tmp_path: Path) -> None:
        """Test updating status on multiple issues."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        ids: list[str] = []
        for i in range(3):
            result = runner.invoke(
                app,
                ["create", f"Issue {i}", "--json", "--dogcats-dir", str(dogcats_dir)],
            )
            data = json.loads(result.stdout)
            ids.append(data["id"])

        result = runner.invoke(
            app,
            [
                "update",
                *ids,
                "--status",
                "in_progress",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert result.stdout.count("✓ Updated") == 3

        # Verify all were updated
        for issue_id in ids:
            show_result = runner.invoke(
                app,
                ["show", issue_id, "--json", "--dogcats-dir", str(dogcats_dir)],
            )
            data = json.loads(show_result.stdout)
            assert data["status"] == "in_progress"

    def test_update_priority_multiple_issues(self, tmp_path: Path) -> None:
        """Test updating priority on multiple issues."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        ids: list[str] = []
        for i in range(2):
            result = runner.invoke(
                app,
                ["create", f"Issue {i}", "--json", "--dogcats-dir", str(dogcats_dir)],
            )
            data = json.loads(result.stdout)
            ids.append(data["id"])

        result = runner.invoke(
            app,
            [
                "update",
                *ids,
                "-p",
                "1",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0

        for issue_id in ids:
            show_result = runner.invoke(
                app,
                ["show", issue_id, "--json", "--dogcats-dir", str(dogcats_dir)],
            )
            data = json.loads(show_result.stdout)
            assert data["priority"] == 1

    def test_update_labels_multiple_issues(self, tmp_path: Path) -> None:
        """Test updating labels on multiple issues."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        ids: list[str] = []
        for i in range(2):
            result = runner.invoke(
                app,
                ["create", f"Issue {i}", "--json", "--dogcats-dir", str(dogcats_dir)],
            )
            data = json.loads(result.stdout)
            ids.append(data["id"])

        result = runner.invoke(
            app,
            [
                "update",
                *ids,
                "--labels",
                "urgent,cli",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0

        for issue_id in ids:
            show_result = runner.invoke(
                app,
                ["show", issue_id, "--json", "--dogcats-dir", str(dogcats_dir)],
            )
            data = json.loads(show_result.stdout)
            assert set(data["labels"]) == {"urgent", "cli"}

    def test_update_multiple_rejects_title(self, tmp_path: Path) -> None:
        """Test that --title is rejected with multiple issue IDs."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        ids: list[str] = []
        for i in range(2):
            result = runner.invoke(
                app,
                ["create", f"Issue {i}", "--json", "--dogcats-dir", str(dogcats_dir)],
            )
            data = json.loads(result.stdout)
            ids.append(data["id"])

        result = runner.invoke(
            app,
            [
                "update",
                *ids,
                "--title",
                "Same title",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 1
        assert "Cannot use --title with multiple issue IDs" in result.stderr

    def test_update_multiple_rejects_description(self, tmp_path: Path) -> None:
        """Test that --description is rejected with multiple issue IDs."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        ids: list[str] = []
        for i in range(2):
            result = runner.invoke(
                app,
                ["create", f"Issue {i}", "--json", "--dogcats-dir", str(dogcats_dir)],
            )
            data = json.loads(result.stdout)
            ids.append(data["id"])

        result = runner.invoke(
            app,
            [
                "update",
                *ids,
                "--description",
                "Same desc",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 1
        assert "Cannot use --description with multiple issue IDs" in result.stderr

    def test_update_multiple_rejects_namespace(self, tmp_path: Path) -> None:
        """Test that --namespace is rejected with multiple issue IDs."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        ids: list[str] = []
        for i in range(2):
            result = runner.invoke(
                app,
                ["create", f"Issue {i}", "--json", "--dogcats-dir", str(dogcats_dir)],
            )
            data = json.loads(result.stdout)
            ids.append(data["id"])

        result = runner.invoke(
            app,
            [
                "update",
                *ids,
                "--namespace",
                "other",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 1
        assert "Cannot use --namespace with multiple issue IDs" in result.stderr

    def test_update_multiple_with_one_bad_id_partial_success(
        self, tmp_path: Path
    ) -> None:
        """Test that one bad ID doesn't prevent others from updating."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            ["create", "Good issue", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        data = json.loads(result.stdout)
        good_id = data["id"]

        result = runner.invoke(
            app,
            [
                "update",
                good_id,
                "nonexistent",
                "--status",
                "in_progress",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 1
        assert "✓ Updated" in result.stdout  # good one succeeded

        # Verify the good one was actually updated
        show_result = runner.invoke(
            app,
            ["show", good_id, "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        show_data = json.loads(show_result.stdout)
        assert show_data["status"] == "in_progress"

    def test_update_single_issue_still_works(self, tmp_path: Path) -> None:
        """Test backward compatibility: single issue ID still works."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        create_result = runner.invoke(
            app,
            ["create", "Test issue", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        data = json.loads(create_result.stdout)
        issue_id = data["id"]

        result = runner.invoke(
            app,
            [
                "update",
                issue_id,
                "--title",
                "New title",
                "--status",
                "in_progress",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "✓ Updated" in result.stdout

    def test_update_multiple_json_output(self, tmp_path: Path) -> None:
        """Test JSON output with multiple issues."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        ids: list[str] = []
        for i in range(2):
            result = runner.invoke(
                app,
                ["create", f"Issue {i}", "--json", "--dogcats-dir", str(dogcats_dir)],
            )
            data = json.loads(result.stdout)
            ids.append(data["id"])

        result = runner.invoke(
            app,
            [
                "update",
                *ids,
                "--status",
                "in_progress",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        lines = [line for line in result.stdout.strip().split("\n") if line]
        assert len(lines) == 2
        for line in lines:
            data = json.loads(line)
            assert data["status"] == "in_progress"
