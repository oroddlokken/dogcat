"""Tests for Dogcat CLI commands."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from dogcat.cli import app

runner = CliRunner()


class TestCLIInit:
    """Test init command."""

    def test_init_creates_directory(self, tmp_path: Path) -> None:
        """Test that init creates .dogcats directory."""
        dogcats_dir = tmp_path / ".dogcats"
        result = runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert dogcats_dir.exists()
        assert (dogcats_dir / "issues.jsonl").exists()

    def test_init_output(self, tmp_path: Path) -> None:
        """Test init output."""
        dogcats_dir = tmp_path / ".dogcats"
        result = runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )
        assert "Dogcat repository initialized" in result.stdout


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

    def test_create_with_no_agent(self, tmp_path: Path) -> None:
        """Test create with --no-agent sets metadata."""
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
                "--no-agent",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["title"] == "Agent skip test"
        assert data["metadata"]["no_agent"] is True

    def test_create_without_no_agent_has_empty_metadata(self, tmp_path: Path) -> None:
        """Test create without --no-agent has empty metadata."""
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

    def test_create_with_title_flag_and_shorthand(self, tmp_path: Path) -> None:
        """Test --title flag with type/priority shorthands as positional args."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

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
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["title"] == "Bug from flag"
        assert data["issue_type"] == "bug"
        assert data["priority"] == 1

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

    def test_create_priority_shorthand(self, tmp_path: Path) -> None:
        """Test creating an issue with priority shorthand (0-4)."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            [
                "create",
                "High priority issue",
                "1",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["priority"] == 1

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

    def test_create_type_shorthand(self, tmp_path: Path) -> None:
        """Test creating an issue with type shorthand (b/f/e/s)."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Test bug shorthand
        result = runner.invoke(
            app,
            ["create", "Bug issue", "b", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["issue_type"] == "bug"

        # Test feature shorthand
        result = runner.invoke(
            app,
            [
                "create",
                "Feature issue",
                "f",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["issue_type"] == "feature"

        # Test epic shorthand
        result = runner.invoke(
            app,
            ["create", "Epic issue", "e", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["issue_type"] == "epic"

        # Test story shorthand
        result = runner.invoke(
            app,
            ["create", "Story issue", "s", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["issue_type"] == "story"

        # Test question shorthand
        result = runner.invoke(
            app,
            [
                "create",
                "Question issue",
                "q",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["issue_type"] == "question"

    def test_create_shorthand_and_explicit_option_errors_for_priority(
        self,
        tmp_path: Path,
    ) -> None:
        """Test that using both shorthand and explicit option errors for priority."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Shorthand says priority 1, but explicit option says 3 - should error
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
        assert result.exit_code == 1
        assert "Cannot use both priority shorthand" in result.output

    def test_create_shorthand_and_explicit_option_errors_for_type(
        self,
        tmp_path: Path,
    ) -> None:
        """Test that using both shorthand and explicit option errors for type."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Shorthand says type bug, but explicit option says feature - should error
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
        assert result.exit_code == 1
        assert "Cannot use both type shorthand" in result.output

    def test_create_shorthand_before_title(self, tmp_path: Path) -> None:
        """Test that shorthand can come before the title."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Priority shorthand before title
        result = runner.invoke(
            app,
            [
                "create",
                "0",
                "Critical issue",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["title"] == "Critical issue"
        assert data["priority"] == 0

        # Type shorthand before title
        result = runner.invoke(
            app,
            ["create", "b", "Bug report", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["title"] == "Bug report"
        assert data["issue_type"] == "bug"

    def test_create_combined_shorthands(self, tmp_path: Path) -> None:
        """Test that both priority and type shorthands can be used together."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Priority and type shorthand together
        result = runner.invoke(
            app,
            [
                "create",
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

        # Different order: type, priority, title
        result = runner.invoke(
            app,
            [
                "create",
                "f",
                "1",
                "New feature",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["title"] == "New feature"
        assert data["priority"] == 1
        assert data["issue_type"] == "feature"

    def test_create_invalid_shorthand_errors(self, tmp_path: Path) -> None:
        """Test that invalid single-char arguments cause an error."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # 'p' is not a valid shorthand
        result = runner.invoke(
            app,
            ["create", "0", "p", "Invalid", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code != 0
        assert "Invalid shorthand" in result.output

    def test_create_ambiguous_triple_shorthand_errors(self, tmp_path: Path) -> None:
        """Test that three shorthand-like arguments cause an error."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # 'b 0 b' is ambiguous - second 'b' would become title
        result = runner.invoke(
            app,
            ["create", "b", "0", "b", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code != 0
        assert "Ambiguous" in result.output

        # 'f 1 f' same issue
        result = runner.invoke(
            app,
            ["create", "f", "1", "f", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code != 0
        assert "Ambiguous" in result.output

        # But 'b 0 "Fix bug"' should work fine
        result = runner.invoke(
            app,
            ["create", "b", "0", "Fix bug", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Fix bug" in result.stdout

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

    def test_add_alias_with_shorthands(self, tmp_path: Path) -> None:
        """Test that 'add' alias works with priority and type shorthands."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            [
                "add",
                "1",
                "f",
                "New feature",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["title"] == "New feature"
        assert data["priority"] == 1
        assert data["issue_type"] == "feature"

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

        with patch("dogcat.edit.edit_issue", return_value=mock_issue) as mock_edit:
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


class TestCLICreateEditor:
    """Test create --editor flag."""

    def test_create_with_editor_flag_opens_editor(self, tmp_path: Path) -> None:
        """Test that --editor opens the Textual editor after creation."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        mock_issue = MagicMock()
        mock_issue.full_id = "dc-test"
        mock_issue.title = "Edited title"

        with patch("dogcat.edit.edit_issue", return_value=mock_issue) as mock_edit:
            result = runner.invoke(
                app,
                [
                    "create",
                    "Test editor issue",
                    "--editor",
                    "--dogcats-dir",
                    str(dogcats_dir),
                ],
            )
            assert result.exit_code == 0
            assert "Created" in result.stdout
            assert "Updated dc-test: Edited title" in result.stdout
            mock_edit.assert_called_once()

    def test_create_with_e_shorthand_opens_editor(self, tmp_path: Path) -> None:
        """Test that -e shorthand opens the Textual editor after creation."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        mock_issue = MagicMock()
        mock_issue.full_id = "dc-test"
        mock_issue.title = "Edited title"

        with patch("dogcat.edit.edit_issue", return_value=mock_issue) as mock_edit:
            result = runner.invoke(
                app,
                [
                    "create",
                    "Test editor shorthand",
                    "-e",
                    "--dogcats-dir",
                    str(dogcats_dir),
                ],
            )
            assert result.exit_code == 0
            assert "Created" in result.stdout
            assert "Updated dc-test: Edited title" in result.stdout
            mock_edit.assert_called_once()

    def test_create_with_editor_cancelled(self, tmp_path: Path) -> None:
        """Test that cancelling the editor shows cancel message."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        with patch("dogcat.edit.edit_issue", return_value=None) as mock_edit:
            result = runner.invoke(
                app,
                [
                    "create",
                    "Test editor cancel",
                    "--editor",
                    "--dogcats-dir",
                    str(dogcats_dir),
                ],
            )
            assert result.exit_code == 0
            assert "Created" in result.stdout
            assert "Edit cancelled" in result.stdout
            mock_edit.assert_called_once()

    def test_create_without_editor_flag_does_not_open_editor(
        self,
        tmp_path: Path,
    ) -> None:
        """Test that without --editor, the editor is not opened."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        with patch("dogcat.edit.edit_issue") as mock_edit:
            result = runner.invoke(
                app,
                [
                    "create",
                    "Test no editor",
                    "--dogcats-dir",
                    str(dogcats_dir),
                ],
            )
            assert result.exit_code == 0
            assert "Created" in result.stdout
            mock_edit.assert_not_called()


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
        """Test list --agent-only filters out no_agent issues."""
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

        # Create no_agent issue
        runner.invoke(
            app,
            [
                "create",
                "Agent skip issue",
                "--no-agent",
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
        assert (
            "Parent issue" in result.stdout
        ), "Closed parent should appear in tree when it has visible children"
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
        blocker_line = next(line for line in lines if blocker_id in line)
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
        assert (
            "■" in dependent_line
        ), f"Blocked issue should show ■ symbol in table output, got: {dependent_line}"

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
                "--no-agent",
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
        assert "no_agent: True" in result.stdout

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

    def test_update_no_agent(self, tmp_path: Path) -> None:
        """Test updating issue with --no-agent flag."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Create issue without no_agent
        create_result = runner.invoke(
            app,
            ["create", "Test issue", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        data = json.loads(create_result.stdout)
        issue_id = data["id"]
        assert data["metadata"] == {}

        # Update to set no_agent
        runner.invoke(
            app,
            ["update", issue_id, "--no-agent", "--dogcats-dir", str(dogcats_dir)],
        )

        # Verify no_agent is set
        show_result = runner.invoke(
            app,
            ["show", issue_id, "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        data = json.loads(show_result.stdout)
        assert data["metadata"]["no_agent"] is True

        # Update to remove no_agent
        runner.invoke(
            app,
            ["update", issue_id, "--agent", "--dogcats-dir", str(dogcats_dir)],
        )

        # Verify no_agent is removed
        show_result = runner.invoke(
            app,
            ["show", issue_id, "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        data = json.loads(show_result.stdout)
        assert "no_agent" not in data["metadata"]


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
        """Test that ready --agent-only filters out no_agent issues."""
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

        # Create an issue marked as no_agent
        create2 = runner.invoke(
            app,
            [
                "create",
                "Agent skip issue",
                "--no-agent",
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
            "dogcat.cli.format_issue_brief",
            wraps=__import__(
                "dogcat.cli",
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
    """Test ir and ip status shortcut commands."""

    def test_ir_sets_status_to_in_review(self, tmp_path: Path) -> None:
        """Test that 'ir' sets issue status to in_review."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        create_result = runner.invoke(
            app,
            ["create", "Test issue", "--dogcats-dir", str(dogcats_dir)],
        )
        issue_id = create_result.stdout.split(": ")[0].split()[-1]

        result = runner.invoke(
            app,
            ["ir", issue_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "✓ In review" in result.stdout

        # Verify status changed
        show_result = runner.invoke(
            app,
            ["show", issue_id, "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        data = json.loads(show_result.stdout)
        assert data["status"] == "in_review"

    def test_ir_json_output(self, tmp_path: Path) -> None:
        """Test ir with --json flag."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        create_result = runner.invoke(
            app,
            ["create", "Test issue", "--dogcats-dir", str(dogcats_dir)],
        )
        issue_id = create_result.stdout.split(": ")[0].split()[-1]

        result = runner.invoke(
            app,
            ["ir", issue_id, "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["status"] == "in_review"

    def test_ir_nonexistent_issue(self, tmp_path: Path) -> None:
        """Test ir with nonexistent issue."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            ["ir", "nonexistent", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 1
        assert "Error" in result.stdout or "Error" in result.stderr

    def test_ip_sets_status_to_in_progress(self, tmp_path: Path) -> None:
        """Test that 'ip' sets issue status to in_progress."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        create_result = runner.invoke(
            app,
            ["create", "Test issue", "--dogcats-dir", str(dogcats_dir)],
        )
        issue_id = create_result.stdout.split(": ")[0].split()[-1]

        result = runner.invoke(
            app,
            ["ip", issue_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "✓ In progress" in result.stdout

        # Verify status changed
        show_result = runner.invoke(
            app,
            ["show", issue_id, "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        data = json.loads(show_result.stdout)
        assert data["status"] == "in_progress"


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
        ids = []
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
        assert closed_data["close_reason"] == "Fixed the bug"
        assert closed_data["notes"] == "Some notes"
        assert "Closed:" not in (closed_data["notes"] or "")

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


class TestCLIDoctor:
    """Test doctor diagnostic command."""

    def test_doctor_with_proper_setup(self, tmp_path: Path) -> None:
        """Test doctor command with properly configured repository."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["doctor", "--dogcats-dir", str(dogcats_dir)],
        )
        # Should pass basic checks even without git config
        assert ".dogcats/ directory exists" in result.stdout
        assert ".dogcats/issues.jsonl is valid JSON" in result.stdout

    def test_doctor_missing_dogcats(self, tmp_path: Path) -> None:
        """Test doctor command with missing .dogcats directory."""
        dogcats_dir = tmp_path / ".dogcats"

        result = runner.invoke(
            app,
            ["doctor", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code != 0
        assert ".dogcats/ directory exists" in result.stdout
        assert "✗" in result.stdout

    def test_doctor_json_output(self, tmp_path: Path) -> None:
        """Test doctor command with JSON output."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["doctor", "--dogcats-dir", str(dogcats_dir), "--json"],
        )
        # When dogcat is properly installed in venv, all checks pass
        assert result.exit_code == 0

        # Parse JSON output
        output = json.loads(result.stdout)
        assert "status" in output
        assert output["status"] == "ok"
        assert "checks" in output
        assert isinstance(output["checks"], dict)

        # Verify check structure
        for check_data in output["checks"].values():
            assert "passed" in check_data
            assert "description" in check_data
            assert isinstance(check_data["passed"], bool)

    def test_doctor_with_invalid_jsonl(self, tmp_path: Path) -> None:
        """Test doctor command with corrupted JSONL file."""
        dogcats_dir = tmp_path / ".dogcats"
        dogcats_dir.mkdir()

        # Create invalid JSON
        issues_file = dogcats_dir / "issues.jsonl"
        issues_file.write_text("not valid json\n")

        result = runner.invoke(
            app,
            ["doctor", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code != 0
        assert "is valid JSON" in result.stdout
        assert "✗" in result.stdout


class TestCLIComments:
    """Test comment functionality."""

    def test_comment_add(self, tmp_path: Path) -> None:
        """Test adding a comment to an issue."""
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
                "comment",
                issue_id,
                "add",
                "--text",
                "Test comment",
                "--author",
                "testuser",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Added comment" in result.stdout

    def test_comment_stores_full_issue_id(self, tmp_path: Path) -> None:
        """Test that comment stores full issue ID, not partial."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Create issue and get full ID
        create_result = runner.invoke(
            app,
            ["create", "Test issue", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        issue_data = json.loads(create_result.stdout)
        hash_only = issue_data["id"]  # e.g., "abc1"
        namespace = issue_data["namespace"]  # e.g., "dc"
        full_id = f"{namespace}-{hash_only}"

        # Add comment using partial (hash-only) ID
        result = runner.invoke(
            app,
            [
                "comment",
                hash_only,
                "add",
                "--text",
                "Test comment",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0

        # Get the issue and verify comment has full issue_id
        show_result = runner.invoke(
            app,
            ["show", full_id, "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        show_data = json.loads(show_result.stdout)
        assert len(show_data["comments"]) == 1
        # Comment's issue_id should be the full ID, not the partial
        assert show_data["comments"][0]["issue_id"] == full_id

    def test_comment_list(self, tmp_path: Path) -> None:
        """Test listing comments for an issue."""
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

        # Add comments
        runner.invoke(
            app,
            [
                "comment",
                issue_id,
                "add",
                "--text",
                "First comment",
                "--author",
                "user1",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        runner.invoke(
            app,
            [
                "comment",
                issue_id,
                "add",
                "--text",
                "Second comment",
                "--author",
                "user2",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["comment", issue_id, "list", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "First comment" in result.stdout
        assert "Second comment" in result.stdout

    def test_show_displays_comments(self, tmp_path: Path) -> None:
        """Test that show command displays comments."""
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

        # Add comment
        runner.invoke(
            app,
            [
                "comment",
                issue_id,
                "add",
                "--text",
                "Test comment",
                "--author",
                "testuser",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["show", issue_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Comments:" in result.stdout
        assert "Test comment" in result.stdout

    def test_comment_delete(self, tmp_path: Path) -> None:
        """Test deleting a comment."""
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

        # Add comment
        runner.invoke(
            app,
            [
                "comment",
                issue_id,
                "add",
                "--text",
                "Comment to delete",
                "--author",
                "testuser",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        # Get comment ID
        list_result = runner.invoke(
            app,
            ["comment", issue_id, "list", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        comments = json.loads(list_result.stdout)
        comment_id = comments[0]["id"]

        # Delete comment
        result = runner.invoke(
            app,
            [
                "comment",
                issue_id,
                "delete",
                "--comment-id",
                comment_id,
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Deleted comment" in result.stdout


class TestCLIInitPrefix:
    """Test init command with --prefix flag."""

    def test_init_with_explicit_prefix(self, tmp_path: Path) -> None:
        """Test init with --prefix flag sets the prefix."""
        dogcats_dir = tmp_path / ".dogcats"
        result = runner.invoke(
            app,
            [
                "init",
                "--prefix",
                "myapp",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Set issue prefix: myapp" in result.stdout
        assert "myapp-<hash>" in result.stdout

    def test_init_creates_config_file(self, tmp_path: Path) -> None:
        """Test init creates config.toml with prefix."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            [
                "init",
                "--prefix",
                "testprefix",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        config_file = dogcats_dir / "config.toml"
        assert config_file.exists()
        content = config_file.read_text()
        assert "issue_prefix" in content
        assert "testprefix" in content

    def test_init_auto_detects_prefix_from_directory(self, tmp_path: Path) -> None:
        """Test init auto-detects prefix from parent directory name."""
        project_dir = tmp_path / "my-cool-project"
        project_dir.mkdir()
        dogcats_dir = project_dir / ".dogcats"

        result = runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Set issue prefix: my-cool-project" in result.stdout

    def test_init_prefix_strips_trailing_hyphens(self, tmp_path: Path) -> None:
        """Test init strips trailing hyphens from prefix."""
        dogcats_dir = tmp_path / ".dogcats"
        result = runner.invoke(
            app,
            [
                "init",
                "--prefix",
                "myapp-",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Set issue prefix: myapp" in result.stdout

    def test_create_uses_config_prefix(self, tmp_path: Path) -> None:
        """Test that create uses prefix from config."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            [
                "init",
                "--prefix",
                "custom",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["create", "Test issue", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "custom-" in result.stdout

    def test_create_uses_directory_prefix_when_no_config(self, tmp_path: Path) -> None:
        """Test that create uses directory-detected prefix when no config."""
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()
        dogcats_dir = project_dir / ".dogcats"

        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["create", "Test issue", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "myproject-" in result.stdout

    def test_multiple_creates_use_same_prefix(self, tmp_path: Path) -> None:
        """Test that multiple creates use consistent prefix."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            [
                "init",
                "--prefix",
                "proj",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result1 = runner.invoke(
            app,
            ["create", "Issue 1", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        result2 = runner.invoke(
            app,
            ["create", "Issue 2", "--json", "--dogcats-dir", str(dogcats_dir)],
        )

        issue1 = json.loads(result1.stdout)
        issue2 = json.loads(result2.stdout)

        assert issue1["namespace"] == "proj"
        assert issue2["namespace"] == "proj"


class TestCLIImportBeadsPrefix:
    """Test import-beads command updating prefix from imported issues."""

    def test_import_beads_sets_prefix_from_imported_issues(
        self,
        tmp_path: Path,
    ) -> None:
        """Test that import-beads detects and sets prefix from imported issues."""
        dogcats_dir = tmp_path / ".dogcats"

        # Create a JSONL file with issues using a specific prefix
        beads_file = tmp_path / "beads.jsonl"
        beads_file.write_text(
            '{"id": "imported-abc", "title": "Issue 1", "status": "open", '
            '"priority": 2, "issue_type": "task", '
            '"created_at": "2026-01-01T10:00:00Z"}\n'
            '{"id": "imported-def", "title": "Issue 2", "status": "open", '
            '"priority": 2, "issue_type": "task", '
            '"created_at": "2026-01-02T10:00:00Z"}\n',
        )

        # Import into fresh directory
        result = runner.invoke(
            app,
            [
                "import-beads",
                str(beads_file),
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Set issue prefix: imported" in result.stdout

        # Verify config was updated
        config_file = dogcats_dir / "config.toml"
        content = config_file.read_text()
        assert 'issue_prefix = "imported"' in content

    def test_import_beads_new_issues_use_imported_prefix(self, tmp_path: Path) -> None:
        """Test that new issues after import-beads use the imported prefix."""
        dogcats_dir = tmp_path / ".dogcats"

        # Create JSONL with search- prefix
        beads_file = tmp_path / "beads.jsonl"
        beads_file.write_text(
            '{"id": "search-xyz", "title": "Imported", "status": "open", '
            '"priority": 2, "issue_type": "task", '
            '"created_at": "2026-01-01T10:00:00Z"}\n',
        )

        runner.invoke(
            app,
            [
                "import-beads",
                str(beads_file),
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        # Create new issue - should use imported prefix
        result = runner.invoke(
            app,
            ["create", "New issue", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "search-" in result.stdout

    def test_import_beads_detects_prefix_from_newest_issue(
        self,
        tmp_path: Path,
    ) -> None:
        """Test that import-beads uses prefix from newest imported issue."""
        dogcats_dir = tmp_path / ".dogcats"

        # Create JSONL with mixed prefixes, newest has "latest-" prefix
        beads_file = tmp_path / "beads.jsonl"
        beads_file.write_text(
            '{"id": "old-abc", "title": "Old issue", "status": "open", '
            '"priority": 2, "issue_type": "task", '
            '"created_at": "2025-01-01T10:00:00Z"}\n'
            '{"id": "latest-xyz", "title": "Latest issue", "status": "open", '
            '"priority": 2, "issue_type": "task", '
            '"created_at": "2026-06-01T10:00:00Z"}\n',
        )

        result = runner.invoke(
            app,
            [
                "import-beads",
                str(beads_file),
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Set issue prefix: latest" in result.stdout

    def test_import_beads_handles_empty_file(self, tmp_path: Path) -> None:
        """Test that import-beads handles empty JSONL file gracefully."""
        dogcats_dir = tmp_path / ".dogcats"

        # Create empty JSONL
        beads_file = tmp_path / "beads.jsonl"
        beads_file.write_text("")

        result = runner.invoke(
            app,
            [
                "import-beads",
                str(beads_file),
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        # Should not crash, no prefix set (no issues imported)
        assert "Imported: 0 issues" in result.stdout

    def test_import_beads_force_preserves_existing_prefix(
        self,
        tmp_path: Path,
    ) -> None:
        """Test that import-beads --force preserves existing prefix."""
        dogcats_dir = tmp_path / ".dogcats"

        runner.invoke(
            app,
            [
                "init",
                "--prefix",
                "keepme",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        # Create JSONL with valid issues
        beads_file = tmp_path / "beads.jsonl"
        beads_file.write_text(
            '{"id": "bd-abcd", "title": "Beads Issue", "status": "open", '
            '"priority": 2, "issue_type": "task", '
            '"created_at": "2026-01-01T10:00:00Z"}\n',
        )

        result = runner.invoke(
            app,
            [
                "import-beads",
                str(beads_file),
                "--dogcats-dir",
                str(dogcats_dir),
                "--force",
            ],
        )
        assert result.exit_code == 0

        # Prefix should remain unchanged (not changed to bd-)
        config_file = dogcats_dir / "config.toml"
        content = config_file.read_text()
        assert 'issue_prefix = "keepme"' in content


class TestCLIStatus:
    """Test status command."""

    def test_status_shows_prefix_and_counts(self, tmp_path: Path) -> None:
        """Test that status shows prefix and issue counts."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            [
                "init",
                "--prefix",
                "test",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        # Create some issues
        runner.invoke(
            app,
            ["create", "Issue 1", "--dogcats-dir", str(dogcats_dir)],
        )
        create2 = runner.invoke(
            app,
            ["create", "Issue 2", "--dogcats-dir", str(dogcats_dir)],
        )
        issue2_id = create2.stdout.split(": ")[0].split()[-1]

        # Close one issue
        runner.invoke(
            app,
            ["close", issue2_id, "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["status", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Prefix: test" in result.stdout
        assert "Total issues: 2" in result.stdout
        assert "open" in result.stdout
        assert "closed" in result.stdout

    def test_status_empty_repo(self, tmp_path: Path) -> None:
        """Test status on empty repository."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            [
                "init",
                "--prefix",
                "empty",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["status", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Prefix: empty" in result.stdout
        assert "Total issues: 0" in result.stdout

    def test_status_json_output(self, tmp_path: Path) -> None:
        """Test status with JSON output."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            [
                "init",
                "--prefix",
                "jsontest",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        runner.invoke(
            app,
            ["create", "Test Issue", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["status", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["prefix"] == "jsontest"
        assert data["total"] == 1
        assert "by_status" in data
        assert data["by_status"]["open"] == 1


class TestCLIGit:
    """Test git integration guide command."""

    def test_git_guide_output(self) -> None:
        """Test that git command outputs the integration guide."""
        result = runner.invoke(app, ["git"])
        assert result.exit_code == 0
        assert "DOGCAT + GIT INTEGRATION GUIDE" in result.stdout
        assert "Committing .dogcats" in result.stdout
        assert "Resolving Merge Conflicts" in result.stdout
        assert "Best Practices" in result.stdout

    def test_git_guide_covers_gitignore(self) -> None:
        """Test that git guide includes .gitignore instructions."""
        result = runner.invoke(app, ["git"])
        assert ".gitignore" in result.stdout


class TestCLIGuide:
    """Test guide command."""

    def test_guide_output(self) -> None:
        """Test that guide command outputs human-friendly guide."""
        result = runner.invoke(app, ["guide"])
        assert result.exit_code == 0
        assert "DCAT USER GUIDE" in result.stdout
        assert "Getting Started" in result.stdout
        assert "dcat init" in result.stdout
        assert "dcat create" in result.stdout

    def test_guide_does_not_contain_agent_content(self) -> None:
        """Test that guide does not include AI-agent-specific content."""
        result = runner.invoke(app, ["guide"])
        assert "AI agent" not in result.stdout
        assert "--no-agent" not in result.stdout
        assert "--agent-only" not in result.stdout


class TestCLIVersion:
    """Test version command."""

    def test_version_displays_version(self) -> None:
        """Test that version command outputs the package version."""
        from dogcat._version import version as v

        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert v in result.stdout


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


class TestFormatIssueBriefMetadataColors:
    """Test that metadata tags in format_issue_brief are colored dim."""

    def test_parent_tag_is_styled_bright_black(self) -> None:
        """Test that [parent: ...] tag uses bright_black styling."""
        from dogcat.cli import format_issue_brief
        from dogcat.models import Issue

        issue = Issue(id="abc1", title="Test issue", parent="dc-xyz1")
        result = format_issue_brief(issue)
        # bright_black ANSI code is \x1b[90m
        assert "\x1b[90m" in result
        assert "[parent: dc-xyz1]" in result

    def test_closed_tag_is_styled_bright_black(self) -> None:
        """Test that [closed ...] tag uses bright_black styling."""
        from datetime import datetime, timezone

        from dogcat.cli import format_issue_brief
        from dogcat.models import Issue, Status

        closed_time = datetime(2025, 6, 15, 10, 30, tzinfo=timezone.utc)
        issue = Issue(
            id="abc2",
            title="Closed issue",
            status=Status.CLOSED,
            closed_at=closed_time,
        )
        result = format_issue_brief(issue)
        assert "\x1b[90m" in result
        assert "[closed 2025-06-15 10:30]" in result

    def test_no_metadata_tags_when_absent(self) -> None:
        """Test no metadata tags appear when parent/closed_at are None."""
        from dogcat.cli import format_issue_brief
        from dogcat.models import Issue

        issue = Issue(id="abc3", title="Plain issue")
        result = format_issue_brief(issue)
        assert "[parent:" not in result
        assert "[closed" not in result


class TestFindDogcatsDirWithRc:
    """Test find_dogcats_dir() with .dogcatrc support."""

    def test_dogcatrc_in_current_dir(
        self,
        tmp_path: Path,
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """find_dogcats_dir() finds .dogcatrc in current directory."""
        from dogcat.cli import find_dogcats_dir
        from dogcat.constants import DOGCATRC_FILENAME

        external_dir = tmp_path / "external" / ".dogcats"
        external_dir.mkdir(parents=True)

        rc_file = tmp_path / DOGCATRC_FILENAME
        rc_file.write_text(str(external_dir) + "\n")

        monkeypatch.chdir(tmp_path)
        result = find_dogcats_dir()
        assert result == str(external_dir)

    def test_dogcatrc_in_parent_dir(
        self,
        tmp_path: Path,
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """find_dogcats_dir() finds .dogcatrc in parent directory."""
        from dogcat.cli import find_dogcats_dir
        from dogcat.constants import DOGCATRC_FILENAME

        external_dir = tmp_path / "external" / ".dogcats"
        external_dir.mkdir(parents=True)

        rc_file = tmp_path / DOGCATRC_FILENAME
        rc_file.write_text(str(external_dir) + "\n")

        child_dir = tmp_path / "subdir"
        child_dir.mkdir()

        monkeypatch.chdir(child_dir)
        result = find_dogcats_dir()
        assert result == str(external_dir)

    def test_dogcatrc_preferred_over_dogcats_dir(
        self,
        tmp_path: Path,
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """find_dogcats_dir() prefers .dogcatrc over .dogcats/ in same directory."""
        from dogcat.cli import find_dogcats_dir
        from dogcat.constants import DOGCATRC_FILENAME

        # Create both .dogcats/ and .dogcatrc pointing elsewhere
        local_dogcats = tmp_path / ".dogcats"
        local_dogcats.mkdir()

        external_dir = tmp_path / "external" / ".dogcats"
        external_dir.mkdir(parents=True)

        rc_file = tmp_path / DOGCATRC_FILENAME
        rc_file.write_text(str(external_dir) + "\n")

        monkeypatch.chdir(tmp_path)
        result = find_dogcats_dir()
        assert result == str(external_dir)

    def test_no_dogcatrc_falls_back_to_dogcats(
        self,
        tmp_path: Path,
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """find_dogcats_dir() falls back to .dogcats/ when no .dogcatrc exists."""
        from dogcat.cli import find_dogcats_dir

        dogcats_dir = tmp_path / ".dogcats"
        dogcats_dir.mkdir()

        monkeypatch.chdir(tmp_path)
        result = find_dogcats_dir()
        assert result == str(dogcats_dir)

    def test_dogcatrc_nonexistent_target_exits(
        self,
        tmp_path: Path,
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """Exits with error when .dogcatrc points to nonexistent dir."""
        from dogcat.cli import find_dogcats_dir
        from dogcat.constants import DOGCATRC_FILENAME

        rc_file = tmp_path / DOGCATRC_FILENAME
        rc_file.write_text("/nonexistent/path/.dogcats\n")

        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit):
            find_dogcats_dir()

    def test_dogcatrc_empty_file_exits(
        self,
        tmp_path: Path,
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """find_dogcats_dir() exits with error when .dogcatrc is empty."""
        from dogcat.cli import find_dogcats_dir
        from dogcat.constants import DOGCATRC_FILENAME

        rc_file = tmp_path / DOGCATRC_FILENAME
        rc_file.write_text("")

        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit):
            find_dogcats_dir()

    def test_dogcatrc_with_relative_path(
        self,
        tmp_path: Path,
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """find_dogcats_dir() resolves relative paths in .dogcatrc."""
        from dogcat.cli import find_dogcats_dir
        from dogcat.constants import DOGCATRC_FILENAME

        external_dir = tmp_path / "external" / ".dogcats"
        external_dir.mkdir(parents=True)

        rc_file = tmp_path / DOGCATRC_FILENAME
        rc_file.write_text("external/.dogcats\n")

        monkeypatch.chdir(tmp_path)
        result = find_dogcats_dir()
        assert result == str(external_dir.resolve())


class TestCLIInitWithDir:
    """Test init --dir command for .dogcatrc support."""

    def test_init_with_dir_creates_dogcatrc(
        self,
        tmp_path: Path,
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """Init --dir creates .dogcatrc file in current directory."""
        from dogcat.constants import DOGCATRC_FILENAME

        monkeypatch.chdir(tmp_path)
        external_dir = tmp_path / "external" / ".dogcats"

        result = runner.invoke(
            app,
            ["init", "--dir", str(external_dir)],
        )
        assert result.exit_code == 0

        rc_file = tmp_path / DOGCATRC_FILENAME
        assert rc_file.exists()
        assert str(external_dir) in rc_file.read_text()

    def test_init_with_dir_creates_external_directory(
        self,
        tmp_path: Path,
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """Init --dir creates the .dogcats directory at the external path."""
        monkeypatch.chdir(tmp_path)
        external_dir = tmp_path / "external" / ".dogcats"

        result = runner.invoke(
            app,
            ["init", "--dir", str(external_dir)],
        )
        assert result.exit_code == 0
        assert external_dir.exists()
        assert (external_dir / "issues.jsonl").exists()


class TestCLIInitUseExistingFolder:
    """Test init --use-existing-folder command."""

    def test_creates_dogcatrc_for_existing_dir(
        self,
        tmp_path: Path,
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """Creates .dogcatrc pointing to an existing .dogcats directory."""
        from dogcat.constants import DOGCATRC_FILENAME

        # Set up an existing .dogcats directory
        existing = tmp_path / "shared" / ".dogcats"
        existing.mkdir(parents=True)
        (existing / "issues.jsonl").touch()

        project = tmp_path / "myproject"
        project.mkdir()
        monkeypatch.chdir(project)

        result = runner.invoke(
            app,
            ["init", "--use-existing-folder", str(existing)],
        )
        assert result.exit_code == 0
        assert "Linked to existing" in result.stdout

        rc_file = project / DOGCATRC_FILENAME
        assert rc_file.exists()
        assert str(existing) in rc_file.read_text()

    def test_does_not_reinitialize(
        self,
        tmp_path: Path,
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """Does not modify the existing .dogcats directory."""
        existing = tmp_path / "shared" / ".dogcats"
        existing.mkdir(parents=True)
        issues = existing / "issues.jsonl"
        issues.write_text('{"id": "test-abc", "title": "Existing"}\n')

        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            app,
            ["init", "--use-existing-folder", str(existing)],
        )
        assert result.exit_code == 0
        # Original content preserved
        assert "Existing" in issues.read_text()

    def test_errors_on_nonexistent_dir(
        self,
        tmp_path: Path,
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """Errors when the specified directory doesn't exist."""
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            app,
            ["init", "--use-existing-folder", "/nonexistent/path"],
        )
        assert result.exit_code != 0
        assert "does not exist" in result.output

    def test_errors_on_invalid_dogcat_dir(
        self,
        tmp_path: Path,
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """Errors when directory exists but is not a valid dogcat dir."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            app,
            ["init", "--use-existing-folder", str(empty_dir)],
        )
        assert result.exit_code != 0
        assert "missing issues.jsonl" in result.output

    def test_mutually_exclusive_with_dir(
        self,
        tmp_path: Path,
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """--dir and --use-existing-folder are mutually exclusive."""
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            app,
            [
                "init",
                "--dir",
                "/some/path",
                "--use-existing-folder",
                "/other/path",
            ],
        )
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output


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
