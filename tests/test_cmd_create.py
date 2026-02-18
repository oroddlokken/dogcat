"""Tests for Dogcat CLI commands."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from dogcat.cli import app

runner = CliRunner()


class TestCLICreate:
    """Test create command."""

    def test_create_issue(self, tmp_path: Path) -> None:
        """Test creating an issue."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            [
                "create",
                "Test issue",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Created" in result.stdout
        assert "Test issue" in result.stdout
        # Default type is task, default priority is 2
        assert "[task, pri 2]" in result.stdout

    def test_create_with_options(self, tmp_path: Path) -> None:
        """Test creating an issue with all options."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            [
                "create",
                "Bug fix",
                "--type",
                "bug",
                "--priority",
                "1",
                "--owner",
                "dev@example.com",
                "--labels",
                "urgent,backend",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0

    def test_create_with_namespace(self, tmp_path: Path) -> None:
        """Test creating an issue with explicit --namespace."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            [
                "create",
                "Namespaced issue",
                "--namespace",
                "myproj",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["title"] == "Namespaced issue"
        assert data["namespace"] == "myproj"

    def test_create_json_output(self, tmp_path: Path) -> None:
        """Test create with JSON output."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

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
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["title"] == "Test issue"
        assert "id" in data

    def test_create_with_manual(self, tmp_path: Path) -> None:
        """Test create with --manual sets metadata."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            [
                "create",
                "Agent skip test",
                "--manual",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["title"] == "Agent skip test"
        assert data["metadata"]["manual"] is True

    def test_create_without_manual_has_empty_metadata(self, tmp_path: Path) -> None:
        """Test create without --manual has empty metadata."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            [
                "create",
                "Normal issue",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["metadata"] == {}

    def test_create_with_notes(self, tmp_path: Path) -> None:
        """Test create with --notes option."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            [
                "create",
                "Issue with notes",
                "--notes",
                "Some implementation notes",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["notes"] == "Some implementation notes"

    def test_create_missing_title(self, tmp_path: Path) -> None:
        """Test create without title raises error."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["create", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code != 0

    def test_create_with_title_flag(self, tmp_path: Path) -> None:
        """Test creating an issue using --title flag instead of positional arg."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            [
                "create",
                "--title",
                "Title from flag",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["title"] == "Title from flag"

    def test_create_with_title_flag_and_shorthand_rejected(
        self,
        tmp_path: Path,
    ) -> None:
        """Test that create rejects extra positional args (shorthands)."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        # create only accepts one positional arg, so extra args are rejected
        result = runner.invoke(
            app,
            [
                "create",
                "b",
                "1",
                "--title",
                "Bug from flag",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code != 0

    def test_create_with_title_flag_and_positional_title_errors(
        self,
        tmp_path: Path,
    ) -> None:
        """Test that using both positional title and --title flag errors."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            [
                "create",
                "Positional title",
                "--title",
                "Flag title",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code != 0
        assert "Cannot use both positional title and --title flag" in result.output

    def test_create_priority_shorthand_rejected(self, tmp_path: Path) -> None:
        """Test that create rejects extra positional args (priority shorthand)."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # create only accepts one positional arg
        result = runner.invoke(
            app,
            [
                "create",
                "High priority issue",
                "1",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code != 0

    def test_create_priority_pint_flag(self, tmp_path: Path) -> None:
        """Test creating an issue with -p p1 (pINT notation)."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # p1 notation
        result = runner.invoke(
            app,
            [
                "create",
                "pINT test",
                "-p",
                "p1",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["priority"] == 1

        # p0 notation
        result = runner.invoke(
            app,
            [
                "create",
                "pINT test p0",
                "-p",
                "p0",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["priority"] == 0

        # Bare int still works
        result = runner.invoke(
            app,
            [
                "create",
                "bare int test",
                "-p",
                "3",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["priority"] == 3

        # Invalid pINT
        result = runner.invoke(
            app,
            [
                "create",
                "invalid pINT",
                "-p",
                "p9",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code != 0

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("critical", 0),
            ("high", 1),
            ("medium", 2),
            ("low", 3),
            ("minimal", 4),
        ],
    )
    def test_create_priority_string_name(
        self, tmp_path: Path, name: str, expected: int
    ) -> None:
        """Test creating an issue with -p critical/high/medium/low/minimal."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            [
                "create",
                f"{name} priority issue",
                "-p",
                name,
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0, f"Failed for {name}: {result.output}"
        data = json.loads(result.stdout)
        assert data["priority"] == expected

    @pytest.mark.parametrize(
        "name",
        ["Critical", "HIGH", "Medium", "LOW", "MINIMAL"],
    )
    def test_create_priority_string_case_insensitive(
        self, tmp_path: Path, name: str
    ) -> None:
        """Test that priority string names are case-insensitive."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            [
                "create",
                f"{name} case test",
                "-p",
                name,
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0, f"Failed for {name}: {result.output}"

    def test_create_priority_invalid_string(self, tmp_path: Path) -> None:
        """Test that invalid priority string names fail."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            [
                "create",
                "bad priority",
                "-p",
                "urgent",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code != 0

    def test_create_type_shorthand_rejected(self, tmp_path: Path) -> None:
        """Test that create rejects extra positional args (type shorthands)."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        for shorthand in ("b", "f", "e", "s", "q"):
            result = runner.invoke(
                app,
                [
                    "create",
                    "Some issue",
                    shorthand,
                    "--dogcats-dir",
                    str(dogcats_dir),
                ],
            )
            assert result.exit_code != 0, f"shorthand '{shorthand}' was not rejected"

    def test_create_shorthand_and_explicit_option_errors_for_priority(
        self,
        tmp_path: Path,
    ) -> None:
        """Extra positional arg rejected even with explicit --priority."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # create only accepts one positional arg
        result = runner.invoke(
            app,
            [
                "create",
                "Override test",
                "1",
                "--priority",
                "3",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code != 0

    def test_create_shorthand_and_explicit_option_errors_for_type(
        self,
        tmp_path: Path,
    ) -> None:
        """Extra positional arg rejected even with explicit --type."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # create only accepts one positional arg
        result = runner.invoke(
            app,
            [
                "create",
                "Override test",
                "b",
                "--type",
                "feature",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code != 0

    def test_create_shorthand_before_title_rejected(self, tmp_path: Path) -> None:
        """Test that create rejects extra positional args (shorthand before title)."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # create only accepts one positional arg
        result = runner.invoke(
            app,
            [
                "create",
                "0",
                "Critical issue",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code != 0

        result = runner.invoke(
            app,
            ["create", "b", "Bug report", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code != 0

    def test_create_combined_shorthands_rejected(self, tmp_path: Path) -> None:
        """Test that create rejects extra positional args (combined shorthands)."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # create only accepts one positional arg
        result = runner.invoke(
            app,
            [
                "create",
                "0",
                "b",
                "Critical bug",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code != 0

    def test_create_invalid_shorthand_errors(self, tmp_path: Path) -> None:
        """Test that extra positional args cause an error (including invalid ones)."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # create only accepts one positional arg
        result = runner.invoke(
            app,
            ["create", "Invalid title", "p", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code != 0

    def test_create_ambiguous_triple_shorthand_errors(self, tmp_path: Path) -> None:
        """Test that extra positional args are rejected by create."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # create only accepts one positional arg
        result = runner.invoke(
            app,
            ["create", "b", "0", "b", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code != 0

        result = runner.invoke(
            app,
            ["create", "b", "0", "Fix bug", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code != 0

    def test_create_with_initial_status(self, tmp_path: Path) -> None:
        """Test creating an issue with initial status."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Create with in_progress status
        result = runner.invoke(
            app,
            [
                "create",
                "In progress task",
                "--status",
                "in_progress",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["status"] == "in_progress"

        # Create with blocked status using short flag
        result = runner.invoke(
            app,
            [
                "create",
                "Blocked task",
                "-s",
                "blocked",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["status"] == "blocked"

    def test_create_with_depends_on(self, tmp_path: Path) -> None:
        """Test creating an issue with --depends-on."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Create parent issue
        result = runner.invoke(
            app,
            ["create", "Parent", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        parent_data = json.loads(result.stdout)
        parent_full_id = f"{parent_data['namespace']}-{parent_data['id']}"

        # Create child that depends on parent
        result = runner.invoke(
            app,
            [
                "create",
                "Child",
                "--depends-on",
                parent_full_id,
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        child_id = result.stdout.split()[2].rstrip(":")

        # Verify dependency was created
        result = runner.invoke(
            app,
            ["dep", child_id, "list", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        deps = json.loads(result.stdout)
        assert len(deps) == 1
        assert deps[0]["depends_on_id"] == parent_full_id

    def test_create_with_depends_on_nonexistent_fails_atomically(
        self,
        tmp_path: Path,
    ) -> None:
        """Test create with --depends-on nonexistent fails without creating issue."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Try to create issue with nonexistent dependency
        result = runner.invoke(
            app,
            [
                "create",
                "Test issue",
                "--depends-on",
                "nonexistent",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 1
        # Error message goes to stderr, captured in result.output
        assert "not found" in result.output

        # Verify no issue was created
        result = runner.invoke(
            app,
            ["list", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        issues = json.loads(result.stdout)
        assert len(issues) == 0

    def test_create_with_blocks_nonexistent_fails_atomically(
        self,
        tmp_path: Path,
    ) -> None:
        """Test that create with --blocks nonexistent fails without creating issue."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Try to create issue with nonexistent blocks target
        result = runner.invoke(
            app,
            [
                "create",
                "Test issue",
                "--blocks",
                "nonexistent",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 1
        # Error message goes to stderr, captured in result.output
        assert "not found" in result.output

        # Verify no issue was created
        result = runner.invoke(
            app,
            ["list", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        issues = json.loads(result.stdout)
        assert len(issues) == 0

    def test_create_with_blocks(self, tmp_path: Path) -> None:
        """Test creating an issue with --blocks."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Create issue that will be blocked
        result = runner.invoke(
            app,
            ["create", "Blocked", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        blocked_id = json.loads(result.stdout)["id"]

        # Create blocker issue
        result = runner.invoke(
            app,
            [
                "create",
                "Blocker",
                "--blocks",
                blocked_id,
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0

        # Verify dependency was created on the blocked issue
        result = runner.invoke(
            app,
            ["dep", blocked_id, "list", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        deps = json.loads(result.stdout)
        assert len(deps) == 1

    def test_create_with_parent(self, tmp_path: Path) -> None:
        """Test creating an issue with a parent (subtask)."""
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
        assert result.exit_code == 0
        parent_data = json.loads(result.stdout)
        parent_id = parent_data["id"]
        parent_full_id = f"{parent_data['namespace']}-{parent_id}"

        # Create subtask with parent
        result = runner.invoke(
            app,
            [
                "create",
                "Subtask",
                "--parent",
                parent_id,
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        subtask_data = json.loads(result.stdout)
        # Parent is now stored as full ID
        assert subtask_data["parent"] == parent_full_id

    def test_create_with_partial_parent_id_resolves_to_full(
        self,
        tmp_path: Path,
    ) -> None:
        """Test creating issue with partial parent ID resolves to full ID."""
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
        assert result.exit_code == 0
        parent_data = json.loads(result.stdout)
        parent_hash = parent_data["id"]  # e.g., "abc1"
        parent_namespace = parent_data["namespace"]  # e.g., "dc"
        parent_full_id = f"{parent_namespace}-{parent_hash}"

        # Create subtask with partial (hash-only) parent ID
        result = runner.invoke(
            app,
            [
                "create",
                "Subtask",
                "--parent",
                parent_hash,
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        subtask_data = json.loads(result.stdout)
        # Parent should be stored as full ID, not partial
        assert subtask_data["parent"] == parent_full_id

    def test_create_with_nonexistent_parent_fails(self, tmp_path: Path) -> None:
        """Test creating issue with nonexistent parent ID fails."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            [
                "create",
                "Subtask",
                "--parent",
                "nonexistent",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 1
        assert "Parent issue nonexistent not found" in result.output

    def test_create_auto_populates_owner_and_created_by(self, tmp_path: Path) -> None:
        """Test that create auto-populates owner and created_by from git config."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            [
                "create",
                "Auto owner test",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        # Should be auto-populated with git email or username
        assert data["owner"] is not None
        assert data["owner"] != ""
        assert data["created_by"] is not None
        assert data["created_by"] != ""

    def test_create_explicit_owner_overrides_auto(self, tmp_path: Path) -> None:
        """Test that explicit --owner overrides auto-population."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            [
                "create",
                "Explicit owner test",
                "--owner",
                "explicit@test.com",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["owner"] == "explicit@test.com"
        # created_by should still be auto-populated
        assert data["created_by"] is not None

    def test_c_alias_creates_issue(self, tmp_path: Path) -> None:
        """Test that 'c' command is an alias for 'create'."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["c", "Alias test issue", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["title"] == "Alias test issue"
        assert data["priority"] == 2
        assert data["issue_type"] == "task"

    def test_c_alias_with_shorthands(self, tmp_path: Path) -> None:
        """Test that 'c' alias works with priority and type shorthands."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            [
                "c",
                "0",
                "b",
                "Critical bug",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["title"] == "Critical bug"
        assert data["priority"] == 0
        assert data["issue_type"] == "bug"

    def test_add_alias_creates_issue(self, tmp_path: Path) -> None:
        """Test that 'add' command is an alias for 'create'."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["add", "Add alias test", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["title"] == "Add alias test"
        assert data["priority"] == 2
        assert data["issue_type"] == "task"

    def test_add_alias_with_shorthands_rejected(self, tmp_path: Path) -> None:
        """Test that 'add' alias rejects extra positional args like 'create'."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # add only accepts one positional arg (same as create)
        result = runner.invoke(
            app,
            [
                "add",
                "1",
                "f",
                "New feature",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code != 0

    def test_create_title_starting_with_dashes_using_sentinel(
        self,
        tmp_path: Path,
    ) -> None:
        """Test that titles starting with -- work when using -- sentinel."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            [
                "create",
                "--dogcats-dir",
                str(dogcats_dir),
                "--json",
                "--",
                "--tree and --table comparison",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["title"] == "--tree and --table comparison"

    def test_create_options_before_positional_args(self, tmp_path: Path) -> None:
        """Test that options work when placed before positional args."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            [
                "create",
                "--dogcats-dir",
                str(dogcats_dir),
                "--priority",
                "1",
                "--type",
                "bug",
                "--json",
                "Important bug fix",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["title"] == "Important bug fix"
        assert data["priority"] == 1
        assert data["issue_type"] == "bug"


class TestCreateAlignedOptions:
    """Test --design, --external-ref, --duplicate-of on create command."""

    def test_create_with_design(self, tmp_path: Path) -> None:
        """Test creating an issue with --design."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            [
                "create",
                "Test issue",
                "--design",
                "Use a factory pattern",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["design"] == "Use a factory pattern"

    def test_create_with_external_ref(self, tmp_path: Path) -> None:
        """Test creating an issue with --external-ref."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            [
                "create",
                "Test issue",
                "--external-ref",
                "https://example.com/issue/42",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["external_ref"] == "https://example.com/issue/42"

    def test_create_with_duplicate_of(self, tmp_path: Path) -> None:
        """Test creating an issue with --duplicate-of."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        # Create original issue
        orig = runner.invoke(
            app,
            ["create", "Original issue", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        orig_data = json.loads(orig.stdout)
        orig_id = f"{orig_data['namespace']}-{orig_data['id']}"

        # Create duplicate
        result = runner.invoke(
            app,
            [
                "create",
                "Duplicate issue",
                "--duplicate-of",
                orig_id,
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["duplicate_of"] == orig_id

    def test_create_duplicate_of_nonexistent_fails(self, tmp_path: Path) -> None:
        """Test that --duplicate-of with a nonexistent ID fails."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            [
                "create",
                "Dup issue",
                "--duplicate-of",
                "nonexistent",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 1


class TestEditAlias:
    """Test 'e' alias for edit command."""

    def test_e_alias_routes_to_edit(self, tmp_path: Path) -> None:
        """Test that 'e' command is an alias for 'edit'."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        # Create an issue to edit
        result = runner.invoke(
            app,
            ["create", "Test issue", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        issue_id = json.loads(result.stdout)["id"]

        mock_issue = MagicMock()
        mock_issue.full_id = issue_id
        mock_issue.title = "Edited title"

        with patch(
            "dogcat.tui.editor.edit_issue",
            return_value=mock_issue,
        ) as mock_edit:
            result = runner.invoke(
                app,
                ["e", issue_id, "--dogcats-dir", str(dogcats_dir)],
            )
            assert result.exit_code == 0
            mock_edit.assert_called_once_with(issue_id, mock_edit.call_args[0][1])
            assert "Updated" in result.stdout

    def test_e_alias_nonexistent_issue(self, tmp_path: Path) -> None:
        """Test that 'e' alias shows error for nonexistent issue."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            ["e", "nonexistent", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 1
        assert (
            "not found" in result.stdout.lower()
            or "not found" in (result.stderr or "").lower()
        )


class TestCreateBodyAlias:
    """Test --body as hidden alias for --description in create."""

    def test_create_with_body(self, tmp_path: Path) -> None:
        """Test that --body sets the description."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            [
                "create",
                "Body test",
                "--body",
                "description via body",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        issue_id = result.stdout.split(": ")[0].split()[-1]

        show_result = runner.invoke(
            app,
            ["show", issue_id, "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        data = json.loads(show_result.stdout)
        assert data["description"] == "description via body"

    def test_create_body_and_description_conflict(self, tmp_path: Path) -> None:
        """Test that --body and --description together produce an error."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            [
                "create",
                "Conflict test",
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
