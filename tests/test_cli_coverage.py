"""Additional CLI tests to improve coverage on uncovered commands and paths."""

import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from dogcat.cli import app

runner = CliRunner()


def _init_and_create(
    tmp_path: Path,
    *titles: str,
    close_ids: list[str] | None = None,
) -> tuple[Path, list[str]]:
    """Initialize a repo and create issues, returning (dogcats_dir, issue_ids)."""
    dogcats_dir = tmp_path / ".dogcats"
    runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

    ids: list[str] = []
    for title in titles:
        result = runner.invoke(
            app,
            ["create", title, "--dogcats-dir", str(dogcats_dir)],
        )
        # Extract issue ID from output like "✓ Created dc-xxxx: Title"
        line = result.stdout.strip()
        issue_id = line.split(": ")[0].split()[-1]
        ids.append(issue_id)

    if close_ids:
        for issue_id in close_ids:
            runner.invoke(
                app,
                [
                    "close",
                    issue_id,
                    "--reason",
                    "Done",
                    "--dogcats-dir",
                    str(dogcats_dir),
                ],
            )

    return dogcats_dir, ids


class TestRecentlyClosed:
    """Test the recently-closed command."""

    def test_recently_closed_shows_issues(self, tmp_path: Path) -> None:
        """Test that recently-closed shows closed issues."""
        dogcats_dir, ids = _init_and_create(
            tmp_path,
            "Issue A",
            "Issue B",
            close_ids=None,
        )
        # Close both
        for issue_id in ids:
            runner.invoke(
                app,
                [
                    "close",
                    issue_id,
                    "--reason",
                    "Fixed",
                    "--dogcats-dir",
                    str(dogcats_dir),
                ],
            )

        result = runner.invoke(
            app,
            ["recently-closed", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Issue A" in result.stdout
        assert "Issue B" in result.stdout
        assert "Closed" in result.stdout

    def test_recently_closed_empty(self, tmp_path: Path) -> None:
        """Test recently-closed with no closed issues."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Open issue")

        result = runner.invoke(
            app,
            ["recently-closed", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No recently closed" in result.stdout

    def test_recently_closed_json(self, tmp_path: Path) -> None:
        """Test recently-closed with JSON output."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue A")
        runner.invoke(
            app,
            [
                "close",
                ids[0],
                "--reason",
                "Done",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["recently-closed", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data: list[Any] = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["title"] == "Issue A"

    def test_recently_closed_with_limit(self, tmp_path: Path) -> None:
        """Test recently-closed respects --limit."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue A", "Issue B", "Issue C")
        for issue_id in ids:
            runner.invoke(
                app,
                [
                    "close",
                    issue_id,
                    "--reason",
                    "Done",
                    "--dogcats-dir",
                    str(dogcats_dir),
                ],
            )

        result = runner.invoke(
            app,
            [
                "recently-closed",
                "--limit",
                "1",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        # Should only show 1 issue
        lines = [
            line for line in result.stdout.strip().split("\n") if line.startswith("✓")
        ]
        assert len(lines) == 1

    def test_recently_closed_with_n_shorthand(self, tmp_path: Path) -> None:
        """Test recently-closed respects -n shorthand for --limit."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue A", "Issue B", "Issue C")
        for issue_id in ids:
            runner.invoke(
                app,
                [
                    "close",
                    issue_id,
                    "--reason",
                    "Done",
                    "--dogcats-dir",
                    str(dogcats_dir),
                ],
            )

        result = runner.invoke(
            app,
            [
                "recently-closed",
                "-n",
                "1",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        lines = [
            line for line in result.stdout.strip().split("\n") if line.startswith("✓")
        ]
        assert len(lines) == 1


class TestSearch:
    """Test the search command."""

    def test_search_finds_by_title(self, tmp_path: Path) -> None:
        """Test that search finds issues by title."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Fix login bug", "Add dashboard")

        result = runner.invoke(
            app,
            ["search", "login", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Fix login bug" in result.stdout
        assert "Add dashboard" not in result.stdout

    def test_search_no_results(self, tmp_path: Path) -> None:
        """Test search with no matching results."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Some issue")

        result = runner.invoke(
            app,
            ["search", "nonexistent", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No issues found" in result.stdout

    def test_search_json_output(self, tmp_path: Path) -> None:
        """Test search with JSON output."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Fix login bug")

        result = runner.invoke(
            app,
            ["search", "login", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data: list[Any] = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["title"] == "Fix login bug"

    def test_search_with_status_filter(self, tmp_path: Path) -> None:
        """Test search with status filter."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Bug one", "Bug two")
        runner.invoke(
            app,
            [
                "update",
                ids[0],
                "--status",
                "in_progress",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            [
                "search",
                "Bug",
                "--status",
                "in_progress",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Bug one" in result.stdout
        assert "Bug two" not in result.stdout

    def test_search_with_type_filter(self, tmp_path: Path) -> None:
        """Test search with type filter."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])
        runner.invoke(
            app,
            [
                "create",
                "Bug in login",
                "--type",
                "bug",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        runner.invoke(
            app,
            [
                "create",
                "Feature for login",
                "--type",
                "feature",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            [
                "search",
                "login",
                "--type",
                "bug",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Bug in login" in result.stdout
        assert "Feature for login" not in result.stdout

    def test_search_excludes_closed_by_default(self, tmp_path: Path) -> None:
        """Test search excludes closed issues by default."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Open issue", "Closed issue")
        runner.invoke(
            app,
            [
                "close",
                ids[1],
                "--reason",
                "Done",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["search", "issue", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Open issue" in result.stdout
        assert "Closed issue" not in result.stdout


class TestExport:
    """Test the export command."""

    def test_export_json(self, tmp_path: Path) -> None:
        """Test export in JSON format."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue A", "Issue B")
        # Add a dependency
        runner.invoke(
            app,
            [
                "dep",
                ids[0],
                "add",
                "--depends-on",
                ids[1],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["export", "--format", "json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "issues" in data
        assert "dependencies" in data
        assert "links" in data
        assert len(data["issues"]) == 2

    def test_export_jsonl(self, tmp_path: Path) -> None:
        """Test export in JSONL format."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Issue A")

        result = runner.invoke(
            app,
            ["export", "--format", "jsonl", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        lines = [line for line in result.stdout.strip().split("\n") if line]
        assert len(lines) >= 1
        # Each line should be valid JSON
        for line in lines:
            json.loads(line)

    def test_export_unknown_format(self, tmp_path: Path) -> None:
        """Test export with unknown format."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Issue A")

        result = runner.invoke(
            app,
            ["export", "--format", "xml", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 1


class TestLabelCommand:
    """Test the label subcommand for add/remove/list."""

    def test_label_add_missing_label_flag(self, tmp_path: Path) -> None:
        """Test that label add without --label flag fails."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue A")

        result = runner.invoke(
            app,
            ["label", ids[0], "add", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 1

    def test_label_add_nonexistent_issue(self, tmp_path: Path) -> None:
        """Test label add on nonexistent issue."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            [
                "label",
                "nonexistent",
                "add",
                "--label",
                "test",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 1

    def test_label_add_duplicate(self, tmp_path: Path) -> None:
        """Test adding a label that already exists."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue A")
        # Add label first time
        runner.invoke(
            app,
            [
                "label",
                ids[0],
                "add",
                "--label",
                "urgent",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        # Add same label again
        result = runner.invoke(
            app,
            [
                "label",
                ids[0],
                "add",
                "--label",
                "urgent",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "already on" in result.stdout

    def test_label_add_with_by(self, tmp_path: Path) -> None:
        """Test adding a label with --by flag."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue A")

        result = runner.invoke(
            app,
            [
                "label",
                ids[0],
                "add",
                "--label",
                "urgent",
                "--by",
                "alice",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Added label" in result.stdout

    def test_label_remove_missing_label_flag(self, tmp_path: Path) -> None:
        """Test that label remove without --label flag fails."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue A")

        result = runner.invoke(
            app,
            ["label", ids[0], "remove", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 1

    def test_label_remove_nonexistent_issue(self, tmp_path: Path) -> None:
        """Test label remove on nonexistent issue."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            [
                "label",
                "nonexistent",
                "remove",
                "--label",
                "test",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 1

    def test_label_remove_not_present(self, tmp_path: Path) -> None:
        """Test removing a label that isn't on the issue."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue A")

        result = runner.invoke(
            app,
            [
                "label",
                ids[0],
                "remove",
                "--label",
                "nonexistent",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "not on" in result.stdout

    def test_label_remove_with_by(self, tmp_path: Path) -> None:
        """Test removing a label with --by flag."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue A")
        runner.invoke(
            app,
            [
                "label",
                ids[0],
                "add",
                "--label",
                "urgent",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            [
                "label",
                ids[0],
                "remove",
                "--label",
                "urgent",
                "--by",
                "alice",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Removed label" in result.stdout

    def test_label_list(self, tmp_path: Path) -> None:
        """Test listing labels on an issue."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue A")
        runner.invoke(
            app,
            [
                "label",
                ids[0],
                "add",
                "--label",
                "urgent",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        runner.invoke(
            app,
            [
                "label",
                ids[0],
                "add",
                "--label",
                "bug",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["label", ids[0], "list", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "urgent" in result.stdout
        assert "bug" in result.stdout

    def test_label_list_empty(self, tmp_path: Path) -> None:
        """Test listing labels when issue has none."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue A")

        result = runner.invoke(
            app,
            ["label", ids[0], "list", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No labels" in result.stdout

    def test_label_list_nonexistent_issue(self, tmp_path: Path) -> None:
        """Test listing labels on nonexistent issue."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            [
                "label",
                "nonexistent",
                "list",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 1

    def test_label_list_json(self, tmp_path: Path) -> None:
        """Test listing labels with JSON output."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue A")
        runner.invoke(
            app,
            [
                "label",
                ids[0],
                "add",
                "--label",
                "urgent",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            [
                "label",
                ids[0],
                "list",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "urgent" in data

    def test_label_unknown_subcommand(self, tmp_path: Path) -> None:
        """Test label with unknown subcommand."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue A")

        result = runner.invoke(
            app,
            ["label", ids[0], "invalid", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 1


class TestLabelsCommand:
    """Test the labels (aggregate) command."""

    def test_labels_with_tombstone_skip(self, tmp_path: Path) -> None:
        """Test that labels command skips tombstoned issues."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue A", "Issue B")
        runner.invoke(
            app,
            [
                "label",
                ids[0],
                "add",
                "--label",
                "keep",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        runner.invoke(
            app,
            [
                "label",
                ids[1],
                "add",
                "--label",
                "gone",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        # Delete issue B
        runner.invoke(
            app,
            ["delete", ids[1], "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["labels", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "keep" in result.stdout
        # Tombstoned issue labels should not appear
        assert "gone" not in result.stdout


class TestReadyJsonOutput:
    """Test ready command with JSON output."""

    def test_ready_json(self, tmp_path: Path) -> None:
        """Test ready command with --json flag."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Ready issue")

        result = runner.invoke(
            app,
            ["ready", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data: list[Any] = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) >= 1


class TestBlockedJsonOutput:
    """Test blocked command with JSON output."""

    def test_blocked_json(self, tmp_path: Path) -> None:
        """Test blocked command with --json flag."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Blocker", "Blocked")
        runner.invoke(
            app,
            [
                "dep",
                ids[1],
                "add",
                "--depends-on",
                ids[0],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["blocked", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data: list[Any] = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) >= 1


class TestInProgressJsonOutput:
    """Test in-progress command with JSON output."""

    def test_in_progress_json(self, tmp_path: Path) -> None:
        """Test in-progress with --json flag."""
        dogcats_dir, ids = _init_and_create(tmp_path, "WIP issue")
        runner.invoke(
            app,
            [
                "update",
                ids[0],
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
        data: list[Any] = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) == 1


class TestInReviewJsonOutput:
    """Test in-review command with JSON output."""

    def test_in_review_json(self, tmp_path: Path) -> None:
        """Test in-review with --json flag."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Review issue")
        runner.invoke(
            app,
            [
                "update",
                ids[0],
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
        data: list[Any] = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) == 1


class TestDeferredJsonOutput:
    """Test deferred command with JSON output."""

    def test_deferred_json(self, tmp_path: Path) -> None:
        """Test deferred with --json flag."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Deferred issue")
        runner.invoke(
            app,
            [
                "update",
                ids[0],
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
        data: list[Any] = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) == 1


class TestManualListJsonOutput:
    """Test manual-list command with JSON output."""

    def test_manual_list_json(self, tmp_path: Path) -> None:
        """Test manual-list with --json flag."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Manual issue")
        runner.invoke(
            app,
            [
                "mark-manual",
                ids[0],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["manual", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data: list[Any] = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) == 1


class TestShowOptionalFields:
    """Test that show displays optional fields."""

    def test_show_with_duplicate_of(self, tmp_path: Path) -> None:
        """Test show displays duplicate_of field."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Original", "Duplicate")

        # Mark as duplicate using update
        runner.invoke(
            app,
            [
                "update",
                ids[1],
                "--duplicate-of",
                ids[0],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["show", ids[1], "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Duplicate of" in result.stdout

    def test_show_with_acceptance(self, tmp_path: Path) -> None:
        """Test show displays acceptance criteria."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue with AC")
        runner.invoke(
            app,
            [
                "update",
                ids[0],
                "--acceptance",
                "Must pass all tests",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["show", ids[0], "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Acceptance" in result.stdout
        assert "Must pass all tests" in result.stdout

    def test_show_with_notes(self, tmp_path: Path) -> None:
        """Test show displays notes."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue with notes")
        runner.invoke(
            app,
            [
                "update",
                ids[0],
                "--notes",
                "Important context",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["show", ids[0], "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Notes" in result.stdout
        assert "Important context" in result.stdout


class TestDependencySubcommands:
    """Test dependency command edge cases."""

    def test_dep_list_json(self, tmp_path: Path) -> None:
        """Test dep list with JSON output."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Alpha", "Bravo")
        runner.invoke(
            app,
            [
                "dep",
                ids[0],
                "add",
                "--depends-on",
                ids[1],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            [
                "dep",
                ids[0],
                "list",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        data: list[Any] = json.loads(result.stdout)
        assert isinstance(data, list)

    def test_dep_add_missing_depends_on(self, tmp_path: Path) -> None:
        """Test dep add without --depends-on flag."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue A")

        result = runner.invoke(
            app,
            ["dep", ids[0], "add", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 1

    def test_dep_unknown_subcommand(self, tmp_path: Path) -> None:
        """Test dep with unknown subcommand."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue A")

        result = runner.invoke(
            app,
            ["dep", ids[0], "invalid", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 1


class TestLinkSubcommands:
    """Test link command edge cases."""

    def test_link_list_json(self, tmp_path: Path) -> None:
        """Test link list with JSON output."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Alpha", "Bravo")
        runner.invoke(
            app,
            [
                "link",
                ids[0],
                "add",
                "--related",
                ids[1],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            [
                "link",
                ids[0],
                "list",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "outgoing" in data or "incoming" in data

    def test_link_add_missing_related(self, tmp_path: Path) -> None:
        """Test link add without --related flag."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue A")

        result = runner.invoke(
            app,
            ["link", ids[0], "add", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 1


class TestShowLinks:
    """Test that show command displays link info."""

    def test_show_displays_links(self, tmp_path: Path) -> None:
        """Test show displays outgoing and incoming links."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue A", "Issue B")
        runner.invoke(
            app,
            [
                "link",
                ids[0],
                "add",
                "--related",
                ids[1],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["show", ids[0], "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Links" in result.stdout or "relates_to" in result.stdout


class TestDoctorDanglingDeps:
    """Test doctor command with dangling dependencies."""

    def test_doctor_with_dangling_deps_fix(self, tmp_path: Path) -> None:
        """Test doctor --fix cleans up dangling dependencies."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Alpha", "Bravo")
        runner.invoke(
            app,
            [
                "dep",
                ids[0],
                "add",
                "--depends-on",
                ids[1],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        # Delete issue B to create a dangling dependency
        runner.invoke(
            app,
            ["delete", ids[1], "--dogcats-dir", str(dogcats_dir)],
        )
        # Prune the tombstone
        runner.invoke(
            app,
            ["prune", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["doctor", "--fix", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0


class TestPruneDryRun:
    """Test prune command with dry-run."""

    def test_prune_dry_run(self, tmp_path: Path) -> None:
        """Test prune --dry-run shows what would be removed."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Keep me", "Delete me")
        runner.invoke(
            app,
            ["delete", ids[1], "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["prune", "--dry-run", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Would remove" in result.stdout
        assert "Delete me" in result.stdout

    def test_prune_no_tombstones(self, tmp_path: Path) -> None:
        """Test prune with no tombstoned issues."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Alive issue")

        result = runner.invoke(
            app,
            ["prune", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No tombstoned issues" in result.stdout

    def test_prune_json_output(self, tmp_path: Path) -> None:
        """Test prune --json returns structured output."""
        dogcats_dir, ids = _init_and_create(tmp_path, "To prune")
        runner.invoke(
            app,
            ["delete", ids[0], "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["prune", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["pruned"] == 1
        assert ids[0] in data["ids"]

    def test_prune_dry_run_json(self, tmp_path: Path) -> None:
        """Test prune --dry-run --json returns structured output."""
        dogcats_dir, ids = _init_and_create(tmp_path, "To prune dry")
        runner.invoke(
            app,
            ["delete", ids[0], "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["prune", "--dry-run", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["dry_run"] is True
        assert data["count"] == 1

    def test_prune_no_tombstones_json(self, tmp_path: Path) -> None:
        """Test prune --json with no tombstones."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Alive")

        result = runner.invoke(
            app,
            ["prune", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["pruned"] == 0

    def test_prune_inbox_tombstones(self, tmp_path: Path) -> None:
        """Test prune removes tombstoned inbox proposals."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Keep me")

        # Create and delete a proposal
        propose_result = runner.invoke(
            app,
            ["propose", "Prune me", "--to", str(tmp_path), "--json"],
        )
        proposal_data = json.loads(propose_result.stdout)
        proposal_id = f"{proposal_data['namespace']}-inbox-{proposal_data['id']}"
        runner.invoke(
            app,
            ["inbox", "delete", proposal_id, "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["prune", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["inbox_pruned"] == 1
        assert proposal_id in data["inbox_ids"]

    def test_prune_inbox_tombstones_dry_run(self, tmp_path: Path) -> None:
        """Test prune --dry-run shows tombstoned proposals."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Keep me")

        propose_result = runner.invoke(
            app,
            ["propose", "Dry run prune", "--to", str(tmp_path), "--json"],
        )
        proposal_data = json.loads(propose_result.stdout)
        proposal_id = f"{proposal_data['namespace']}-inbox-{proposal_data['id']}"
        runner.invoke(
            app,
            ["inbox", "delete", proposal_id, "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["prune", "--dry-run", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Would remove 1 tombstoned proposal(s)" in result.stdout
        assert "Dry run prune" in result.stdout

    def test_prune_no_tombstones_message(self, tmp_path: Path) -> None:
        """Test prune with no tombstones at all shows combined message."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Alive")

        result = runner.invoke(
            app,
            ["prune", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No tombstoned issues or proposals to prune" in result.stdout


class TestShowDescription:
    """Test show displays description."""

    def test_show_with_description(self, tmp_path: Path) -> None:
        """Test show displays description field."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue with desc")
        runner.invoke(
            app,
            [
                "update",
                ids[0],
                "--description",
                "Detailed description here",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["show", ids[0], "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Description" in result.stdout
        assert "Detailed description here" in result.stdout


class TestDepRemoveSubcommand:
    """Test dep remove subcommand."""

    def test_dep_remove(self, tmp_path: Path) -> None:
        """Test dep remove removes dependency."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Alpha", "Bravo")
        runner.invoke(
            app,
            [
                "dep",
                ids[0],
                "add",
                "--depends-on",
                ids[1],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            [
                "dep",
                ids[0],
                "remove",
                "--depends-on",
                ids[1],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Removed dependency" in result.stdout

    def test_dep_remove_missing_depends_on(self, tmp_path: Path) -> None:
        """Test dep remove without --depends-on flag."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue")

        result = runner.invoke(
            app,
            ["dep", ids[0], "remove", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 1


class TestLinkRemoveSubcommand:
    """Test link remove subcommand."""

    def test_link_remove(self, tmp_path: Path) -> None:
        """Test link remove removes link."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Alpha", "Bravo")
        runner.invoke(
            app,
            [
                "link",
                ids[0],
                "add",
                "--related",
                ids[1],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            [
                "link",
                ids[0],
                "remove",
                "--related",
                ids[1],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Removed link" in result.stdout

    def test_link_remove_missing_related(self, tmp_path: Path) -> None:
        """Test link remove without --related flag."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue")

        result = runner.invoke(
            app,
            ["link", ids[0], "remove", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 1

    def test_link_list_text_output(self, tmp_path: Path) -> None:
        """Test link list with text output (not JSON)."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Alpha", "Bravo")
        runner.invoke(
            app,
            [
                "link",
                ids[0],
                "add",
                "--related",
                ids[1],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["link", ids[0], "list", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Outgoing links" in result.stdout

    def test_link_list_no_links(self, tmp_path: Path) -> None:
        """Test link list when no links exist."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue")

        result = runner.invoke(
            app,
            ["link", ids[0], "list", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No links" in result.stdout


class TestPrimeCommand:
    """Test prime command (guide output)."""

    def test_prime_outputs_guide(self) -> None:
        """Test that prime command outputs the workflow guide."""
        result = runner.invoke(app, ["prime"])
        assert result.exit_code == 0
        assert "DOGCAT WORKFLOW GUIDE" in result.stdout
        assert "Quick Start" in result.stdout

    def test_prime_includes_label_commands(self) -> None:
        """Test that prime includes label commands in Essential Commands."""
        result = runner.invoke(app, ["prime"])
        assert result.exit_code == 0
        assert "dcat label <id> add -l <label>" in result.stdout
        assert "dcat label <id> remove -l <label>" in result.stdout

    def test_prime_includes_labels_section(self) -> None:
        """Test that prime includes the Labels section."""
        result = runner.invoke(app, ["prime"])
        assert result.exit_code == 0
        assert "## Labels" in result.stdout
        assert "Freeform tags" in result.stdout


class TestStatusCommand:
    """Test status command."""

    def test_status_shows_counts(self, tmp_path: Path) -> None:
        """Test status shows issue counts."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Issue one", "Issue two")

        result = runner.invoke(
            app,
            ["status", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Total issues: 2" in result.stdout
        assert "By status:" in result.stdout

    def test_status_json(self, tmp_path: Path) -> None:
        """Test status with JSON output."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Issue one")

        result = runner.invoke(
            app,
            ["status", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "total" in data
        assert "by_status" in data


class TestSearchDescription:
    """Test search matches in description."""

    def test_search_matches_description(self, tmp_path: Path) -> None:
        """Test search finds issues by description content."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Generic title")
        runner.invoke(
            app,
            [
                "update",
                ids[0],
                "--description",
                "The login page crashes on Safari",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["search", "Safari", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Generic title" in result.stdout


class TestInfoCommand:
    """Test the info command."""

    def test_info_text_output(self) -> None:
        """Test info command shows types, statuses, and priorities."""
        result = runner.invoke(app, ["info"])
        assert result.exit_code == 0
        assert "Issue Types:" in result.stdout
        assert "Statuses:" in result.stdout
        assert "Priorities:" in result.stdout
        assert "Shorthands" in result.stdout

    def test_info_json_output(self) -> None:
        """Test info command with JSON output."""
        result = runner.invoke(app, ["info", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "types" in data
        assert "statuses" in data
        assert "priorities" in data
        assert "type_shorthands" in data


class TestCommentCommand:
    """Test the comment command."""

    def test_comment_add(self, tmp_path: Path) -> None:
        """Test adding a comment to an issue."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Commented issue")

        result = runner.invoke(
            app,
            [
                "comment",
                ids[0],
                "add",
                "--text",
                "This is a comment",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Added comment" in result.stdout

    def test_comment_add_with_author(self, tmp_path: Path) -> None:
        """Test adding a comment with author."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue")

        result = runner.invoke(
            app,
            [
                "comment",
                ids[0],
                "add",
                "--text",
                "Note",
                "--by",
                "alice",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Added comment" in result.stdout

    def test_comment_add_json(self, tmp_path: Path) -> None:
        """Test adding a comment with JSON output."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue")

        result = runner.invoke(
            app,
            [
                "comment",
                ids[0],
                "add",
                "--text",
                "Note",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "comments" in data

    def test_comment_add_missing_text(self, tmp_path: Path) -> None:
        """Test comment add without --text flag fails."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue")

        result = runner.invoke(
            app,
            ["comment", ids[0], "add", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 1

    def test_comment_list_text(self, tmp_path: Path) -> None:
        """Test listing comments in text format."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue")
        runner.invoke(
            app,
            [
                "comment",
                ids[0],
                "add",
                "--text",
                "First comment",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["comment", ids[0], "list", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "First comment" in result.stdout

    def test_comment_list_json(self, tmp_path: Path) -> None:
        """Test listing comments in JSON format."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue")
        runner.invoke(
            app,
            [
                "comment",
                ids[0],
                "add",
                "--text",
                "A comment",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            [
                "comment",
                ids[0],
                "list",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        data: list[Any] = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["text"] == "A comment"

    def test_comment_list_empty(self, tmp_path: Path) -> None:
        """Test listing comments when none exist."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue")

        result = runner.invoke(
            app,
            ["comment", ids[0], "list", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No comments" in result.stdout

    def test_comment_delete(self, tmp_path: Path) -> None:
        """Test deleting a comment."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue")
        runner.invoke(
            app,
            [
                "comment",
                ids[0],
                "add",
                "--text",
                "To delete",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        # Get the comment ID
        list_result = runner.invoke(
            app,
            [
                "comment",
                ids[0],
                "list",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        comments = json.loads(list_result.stdout)
        comment_id = comments[0]["id"]

        result = runner.invoke(
            app,
            [
                "comment",
                ids[0],
                "delete",
                "--comment-id",
                comment_id,
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Deleted comment" in result.stdout

    def test_comment_delete_missing_comment_id(self, tmp_path: Path) -> None:
        """Test comment delete without --comment-id fails."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue")

        result = runner.invoke(
            app,
            ["comment", ids[0], "delete", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 1

    def test_comment_delete_nonexistent_id(self, tmp_path: Path) -> None:
        """Test deleting a comment with nonexistent ID."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue")

        result = runner.invoke(
            app,
            [
                "comment",
                ids[0],
                "delete",
                "--comment-id",
                "fake-id",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 1

    def test_comment_on_nonexistent_issue(self, tmp_path: Path) -> None:
        """Test comment on nonexistent issue."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            [
                "comment",
                "nonexistent",
                "add",
                "--text",
                "Test",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 1

    def test_comment_unknown_action(self, tmp_path: Path) -> None:
        """Test comment with unknown action."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue")

        result = runner.invoke(
            app,
            ["comment", ids[0], "invalid", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 1


class TestUpdateFieldPaths:
    """Test update command with various field options."""

    def test_update_issue_type(self, tmp_path: Path) -> None:
        """Test updating issue type."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue")

        result = runner.invoke(
            app,
            [
                "update",
                ids[0],
                "--type",
                "bug",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Updated" in result.stdout

    def test_update_owner(self, tmp_path: Path) -> None:
        """Test updating owner."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue")

        result = runner.invoke(
            app,
            [
                "update",
                ids[0],
                "--owner",
                "alice",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Updated" in result.stdout

    def test_update_clear_duplicate_of(self, tmp_path: Path) -> None:
        """Test clearing duplicate_of by passing empty string."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Original", "Dup")
        runner.invoke(
            app,
            [
                "update",
                ids[1],
                "--duplicate-of",
                ids[0],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            [
                "update",
                ids[1],
                "--duplicate-of",
                "",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0

    def test_update_parent(self, tmp_path: Path) -> None:
        """Test setting parent."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Parent", "Child")

        result = runner.invoke(
            app,
            [
                "update",
                ids[1],
                "--parent",
                ids[0],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0

    def test_update_clear_parent(self, tmp_path: Path) -> None:
        """Test clearing parent by passing empty string."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Parent", "Child")
        runner.invoke(
            app,
            [
                "update",
                ids[1],
                "--parent",
                ids[0],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            [
                "update",
                ids[1],
                "--parent",
                "",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0


class TestUpdateNamespace:
    """Test update --namespace option."""

    def test_update_namespace(self, tmp_path: Path) -> None:
        """Test changing an issue's namespace via CLI."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Test issue")

        result = runner.invoke(
            app,
            [
                "update",
                ids[0],
                "--namespace",
                "newns",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Updated" in result.stdout
        assert "newns" in result.stdout

    def test_update_namespace_cascades_parent(self, tmp_path: Path) -> None:
        """Test that namespace change cascades to child parent references."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Parent", "Child")

        # Get the hash part of the parent ID (everything after the last hyphen)
        # IDs are in format <namespace>-<hash>, where namespace may contain hyphens
        result = runner.invoke(
            app,
            ["show", ids[0], "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        parent_data = json.loads(result.stdout)
        parent_hash = parent_data["id"]

        # Set child's parent
        runner.invoke(
            app,
            [
                "update",
                ids[1],
                "--parent",
                ids[0],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        # Change parent namespace
        result = runner.invoke(
            app,
            [
                "update",
                ids[0],
                "--namespace",
                "newns",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0

        # Verify child's parent reference was updated
        result = runner.invoke(
            app,
            ["show", ids[1], "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["parent"] == f"newns-{parent_hash}"


class TestListTreeAndTable:
    """Test list with --tree and --table options."""

    def test_list_tree_and_table_mutually_exclusive(self, tmp_path: Path) -> None:
        """Test that --tree and --table can't be used together."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Issue")

        result = runner.invoke(
            app,
            [
                "list",
                "--tree",
                "--table",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 1

    def test_list_table_format(self, tmp_path: Path) -> None:
        """Test list with --table format."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Table issue")

        result = runner.invoke(
            app,
            ["list", "--table", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Table issue" in result.stdout

    def test_list_tree_format(self, tmp_path: Path) -> None:
        """Test list with --tree format."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Parent", "Child")
        runner.invoke(
            app,
            [
                "update",
                ids[1],
                "--parent",
                ids[0],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["list", "--tree", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Parent" in result.stdout


class TestLinkIncomingText:
    """Test link list showing incoming links in text mode."""

    def test_link_list_incoming_text(self, tmp_path: Path) -> None:
        """Test link list shows incoming links in text output."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Target", "Source")
        runner.invoke(
            app,
            [
                "link",
                ids[1],
                "add",
                "--related",
                ids[0],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["link", ids[0], "list", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Incoming links" in result.stdout

    def test_link_unknown_subcommand(self, tmp_path: Path) -> None:
        """Test link with unknown subcommand."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue")

        result = runner.invoke(
            app,
            ["link", ids[0], "invalid", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 1


class TestBlockedTextOutput:
    """Test blocked command text output."""

    def test_blocked_text_with_blockers(self, tmp_path: Path) -> None:
        """Test blocked text output shows blocker details."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Blocker", "Blocked")
        runner.invoke(
            app,
            [
                "dep",
                ids[1],
                "add",
                "--depends-on",
                ids[0],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["blocked", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Blocked" in result.stdout
        assert "blocked by" in result.stdout


class TestDemoCommand:
    """Test demo command."""

    def test_demo_creates_issues(self, tmp_path: Path) -> None:
        """Test demo command creates sample issues."""
        dogcats_dir = tmp_path / ".dogcats"

        result = runner.invoke(
            app,
            ["demo", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Created" in result.stdout
        assert "demo issues" in result.stdout

    def test_demo_refuses_existing(self, tmp_path: Path) -> None:
        """Test demo refuses to run on existing project."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Existing")

        result = runner.invoke(
            app,
            ["demo", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 1

    def test_demo_force_on_existing(self, tmp_path: Path) -> None:
        """Test demo --force adds to existing project."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Existing")

        result = runner.invoke(
            app,
            ["demo", "--force", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Created" in result.stdout


class TestArchiveCommand:
    """Test archive command."""

    def test_archive_dry_run(self, tmp_path: Path) -> None:
        """Test archive --dry-run shows what would be archived."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Closed one", "Open one")
        runner.invoke(
            app,
            [
                "close",
                ids[0],
                "--reason",
                "Done",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["archive", "--dry-run", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Will archive" in result.stdout
        assert "dry run" in result.stdout

    def test_archive_no_closed_issues(self, tmp_path: Path) -> None:
        """Test archive when no closed issues exist."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Open issue")

        result = runner.invoke(
            app,
            ["archive", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No closed issues" in result.stdout

    def test_archive_with_confirm(self, tmp_path: Path) -> None:
        """Test archive --confirm actually archives."""
        dogcats_dir, ids = _init_and_create(tmp_path, "To archive")
        runner.invoke(
            app,
            [
                "close",
                ids[0],
                "--reason",
                "Done",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["archive", "--yes", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Archived" in result.stdout

    def test_archive_older_than(self, tmp_path: Path) -> None:
        """Test archive --older-than filter."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Recently closed")
        runner.invoke(
            app,
            [
                "close",
                ids[0],
                "--reason",
                "Done",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        # Just closed, so --older-than 1d should find nothing
        result = runner.invoke(
            app,
            [
                "archive",
                "--older-than",
                "1d",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "No closed issues older than" in result.stdout

    def test_archive_invalid_older_than(self, tmp_path: Path) -> None:
        """Test archive --older-than with invalid format."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Issue")

        result = runner.invoke(
            app,
            [
                "archive",
                "--older-than",
                "30x",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 1

    def test_archive_skips_with_open_children(self, tmp_path: Path) -> None:
        """Test archive skips issues with open children."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Parent", "Child")
        runner.invoke(
            app,
            [
                "update",
                ids[1],
                "--parent",
                ids[0],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        # Close parent but leave child open
        runner.invoke(
            app,
            [
                "close",
                ids[0],
                "--reason",
                "Done",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["archive", "--dry-run", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "open child" in result.stdout or "No issues can be" in result.stdout

    def test_archive_with_deps_and_links(self, tmp_path: Path) -> None:
        """Test archive handles issues with deps and links."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue A", "Issue B", "Issue C")
        # Add dependency and link between A and B
        runner.invoke(
            app,
            [
                "dep",
                ids[0],
                "add",
                "--depends-on",
                ids[1],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        runner.invoke(
            app,
            [
                "link",
                ids[0],
                "add",
                "--related",
                ids[1],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        # Close A and B but leave C open
        for i in [0, 1]:
            runner.invoke(
                app,
                [
                    "close",
                    ids[i],
                    "--reason",
                    "Done",
                    "--dogcats-dir",
                    str(dogcats_dir),
                ],
            )

        result = runner.invoke(
            app,
            ["archive", "--yes", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Archived" in result.stdout


class TestShowWithDepsAndChildren:
    """Test show command displays deps and children."""

    def test_show_with_dependencies(self, tmp_path: Path) -> None:
        """Test show displays dependencies."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Alpha", "Bravo")
        runner.invoke(
            app,
            [
                "dep",
                ids[0],
                "add",
                "--depends-on",
                ids[1],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["show", ids[0], "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Dependencies:" in result.stdout

    def test_show_with_blocks(self, tmp_path: Path) -> None:
        """Test show displays issues blocked by the viewed issue."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Alpha", "Bravo")
        # Bravo depends on Alpha, so Alpha blocks Bravo
        runner.invoke(
            app,
            [
                "dep",
                ids[1],
                "add",
                "--depends-on",
                ids[0],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["show", ids[0], "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Blocks:" in result.stdout
        assert ids[1] in result.stdout

    def test_show_with_children(self, tmp_path: Path) -> None:
        """Test show displays children."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Parent", "Child")
        runner.invoke(
            app,
            [
                "update",
                ids[1],
                "--parent",
                ids[0],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["show", ids[0], "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Children:" in result.stdout

    def test_show_with_metadata(self, tmp_path: Path) -> None:
        """Test show displays metadata."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue")
        runner.invoke(
            app,
            [
                "mark-manual",
                ids[0],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["show", ids[0], "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Metadata:" in result.stdout

    def test_show_with_incoming_links(self, tmp_path: Path) -> None:
        """Test show displays incoming links with ← arrow."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Target", "Source")
        runner.invoke(
            app,
            [
                "link",
                ids[1],
                "add",
                "--related",
                ids[0],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["show", ids[0], "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "←" in result.stdout


class TestExportWithDepsAndLinks:
    """Test export JSONL includes deps and links."""

    def test_export_jsonl_with_deps_and_links(self, tmp_path: Path) -> None:
        """Test export JSONL includes dependency and link records."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Alpha", "Bravo")
        runner.invoke(
            app,
            [
                "dep",
                ids[0],
                "add",
                "--depends-on",
                ids[1],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        runner.invoke(
            app,
            [
                "link",
                ids[0],
                "add",
                "--related",
                ids[1],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["export", "--format", "jsonl", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        lines = [line for line in result.stdout.strip().split("\n") if line]
        # Should have 2 issues + 1 dep + 1 link = 4 lines
        assert len(lines) >= 4


class TestExportInbox:
    """Test export includes inbox proposals."""

    def test_export_json_includes_proposals(self, tmp_path: Path) -> None:
        """Test that JSON export includes proposals key."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Issue A")
        runner.invoke(
            app,
            ["propose", "Proposal B", "--to", str(tmp_path)],
        )
        result = runner.invoke(
            app,
            ["export", "--format", "json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "proposals" in data
        assert len(data["proposals"]) == 1
        assert data["proposals"][0]["title"] == "Proposal B"

    def test_export_jsonl_includes_proposals(self, tmp_path: Path) -> None:
        """Test that JSONL export includes proposal records."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Issue A")
        runner.invoke(
            app,
            ["propose", "Proposal B", "--to", str(tmp_path)],
        )
        result = runner.invoke(
            app,
            ["export", "--format", "jsonl", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        lines = [json.loads(ln) for ln in result.stdout.strip().split("\n") if ln]
        proposals = [ln for ln in lines if ln.get("record_type") == "proposal"]
        assert len(proposals) == 1
        assert proposals[0]["title"] == "Proposal B"

    def test_export_no_inbox_flag(self, tmp_path: Path) -> None:
        """Test --no-inbox excludes proposals from export."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Issue A")
        runner.invoke(
            app,
            ["propose", "Hidden proposal", "--to", str(tmp_path)],
        )
        result = runner.invoke(
            app,
            [
                "export",
                "--format",
                "json",
                "--no-inbox",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "proposals" not in data

    def test_export_json_no_inbox_file(self, tmp_path: Path) -> None:
        """Test export works when no inbox.jsonl exists."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Issue A")
        result = runner.invoke(
            app,
            ["export", "--format", "json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "proposals" in data
        assert len(data["proposals"]) == 0


class TestInitExistingDir:
    """Test init when directory already exists."""

    def test_init_existing_issues_file(self, tmp_path: Path) -> None:
        """Test init when issues.jsonl already exists."""
        dogcats_dir = tmp_path / ".dogcats"
        dogcats_dir.mkdir()
        (dogcats_dir / "issues.jsonl").touch()

        result = runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "already exists" in result.stdout


class TestDoctorJsonOutput:
    """Test doctor command with JSON output."""

    def test_doctor_json(self, tmp_path: Path) -> None:
        """Test doctor with JSON output."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Issue")

        result = runner.invoke(
            app,
            ["doctor", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        # doctor exits with 0 or 1 depending on checks
        data = json.loads(result.stdout)
        assert "status" in data
        assert "checks" in data


class TestListOwnerFilter:
    """Test list with --owner filter."""

    def test_list_owner_filter(self, tmp_path: Path) -> None:
        """Test list with --owner filter."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Alice issue", "Bob issue")
        runner.invoke(
            app,
            [
                "update",
                ids[0],
                "--owner",
                "alice",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        runner.invoke(
            app,
            [
                "update",
                ids[1],
                "--owner",
                "bob",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            [
                "list",
                "--owner",
                "alice",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Alice issue" in result.stdout
        assert "Bob issue" not in result.stdout


class TestReadyWithLimit:
    """Test ready command with --limit."""

    def test_ready_with_limit(self, tmp_path: Path) -> None:
        """Test ready respects --limit flag."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Issue A", "Issue B", "Issue C")

        result = runner.invoke(
            app,
            [
                "ready",
                "--limit",
                "1",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        # Should limit output


class TestImportBeadsCommand:
    """Test import-beads command."""

    def test_import_beads_fresh(self, tmp_path: Path) -> None:
        """Test importing beads JSONL into a fresh project."""
        beads_file = tmp_path / "beads.jsonl"
        beads_file.write_text(
            json.dumps(
                {
                    "id": "test-abc123",
                    "title": "Beads Issue",
                    "status": "open",
                    "priority": 2,
                    "issue_type": "task",
                    "created_at": "2026-01-01T12:00:00+00:00",
                    "created_by": "User",
                    "updated_at": "2026-01-01T12:00:00+00:00",
                },
            )
            + "\n",
        )
        dogcats_dir = tmp_path / ".dogcats"

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
        assert "Import complete" in result.stdout
        assert "Imported: 1" in result.stdout

    def test_import_beads_existing_no_force(self, tmp_path: Path) -> None:
        """Test import-beads fails on existing project without --force."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Existing issue")
        beads_file = tmp_path / "beads.jsonl"
        beads_file.write_text(
            json.dumps(
                {
                    "id": "test-abc123",
                    "title": "New Issue",
                    "status": "open",
                    "priority": 2,
                    "issue_type": "task",
                    "created_at": "2026-01-01T12:00:00+00:00",
                    "created_by": "User",
                    "updated_at": "2026-01-01T12:00:00+00:00",
                },
            )
            + "\n",
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
        assert result.exit_code == 1

    def test_import_beads_force_merge(self, tmp_path: Path) -> None:
        """Test import-beads --force merges into existing project."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Existing issue")
        beads_file = tmp_path / "beads.jsonl"
        beads_file.write_text(
            json.dumps(
                {
                    "id": "test-abc123",
                    "title": "New Issue",
                    "status": "open",
                    "priority": 2,
                    "issue_type": "task",
                    "created_at": "2026-01-01T12:00:00+00:00",
                    "created_by": "User",
                    "updated_at": "2026-01-01T12:00:00+00:00",
                },
            )
            + "\n",
        )

        result = runner.invoke(
            app,
            [
                "import-beads",
                str(beads_file),
                "--force",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Import complete" in result.stdout

    def test_import_beads_file_not_found(self, tmp_path: Path) -> None:
        """Test import-beads with nonexistent file."""
        dogcats_dir = tmp_path / ".dogcats"

        result = runner.invoke(
            app,
            [
                "import-beads",
                str(tmp_path / "nonexistent.jsonl"),
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 1

    def test_import_beads_with_skipped(self, tmp_path: Path) -> None:
        """Test import-beads reports skipped count on merge."""
        beads_file = tmp_path / "beads.jsonl"
        beads_file.write_text(
            json.dumps(
                {
                    "id": "test-abc123",
                    "title": "Beads Issue",
                    "status": "open",
                    "priority": 2,
                    "issue_type": "task",
                    "created_at": "2026-01-01T12:00:00+00:00",
                    "created_by": "User",
                    "updated_at": "2026-01-01T12:00:00+00:00",
                },
            )
            + "\n",
        )
        dogcats_dir = tmp_path / ".dogcats"

        # First import
        runner.invoke(
            app,
            [
                "import-beads",
                str(beads_file),
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        # Second import with force (merge) - should skip
        result = runner.invoke(
            app,
            [
                "import-beads",
                str(beads_file),
                "--force",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Skipped" in result.stdout


class TestListClosedDateFilters:
    """Test list with --closed-after and --closed-before filters."""

    def test_list_closed_after(self, tmp_path: Path) -> None:
        """Test list with --closed-after filter."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue A")
        runner.invoke(
            app,
            [
                "close",
                ids[0],
                "--reason",
                "Done",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            [
                "list",
                "--closed-after",
                "2020-01-01",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Issue A" in result.stdout

    def test_list_closed_before(self, tmp_path: Path) -> None:
        """Test list with --closed-before filter."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue A")
        runner.invoke(
            app,
            [
                "close",
                ids[0],
                "--reason",
                "Done",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

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
        assert "Issue A" in result.stdout

    def test_list_closed_after_invalid_date(self, tmp_path: Path) -> None:
        """Test list with invalid --closed-after date."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue")
        # Close it so there's a closed issue to trigger date parsing
        runner.invoke(
            app,
            [
                "close",
                ids[0],
                "--reason",
                "Done",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            [
                "list",
                "--closed-after",
                "not-a-date",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        # Should error on bad date format
        assert result.exit_code == 1


class TestArchiveSkipPaths:
    """Test archive command skip paths for dependents and incoming links."""

    def test_archive_skips_depended_on_by_open(self, tmp_path: Path) -> None:
        """Test archive skips issues that open issues depend on."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Closed dep", "Open issue")
        # Open issue depends on closed dep
        runner.invoke(
            app,
            [
                "dep",
                ids[1],
                "add",
                "--depends-on",
                ids[0],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        runner.invoke(
            app,
            [
                "close",
                ids[0],
                "--reason",
                "Done",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["archive", "--dry-run", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "depended on by" in result.stdout or "No issues can be" in result.stdout

    def test_archive_skips_linked_to_open(self, tmp_path: Path) -> None:
        """Test archive skips issues linked to open issues."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Closed linked", "Open issue")
        runner.invoke(
            app,
            [
                "link",
                ids[0],
                "add",
                "--related",
                ids[1],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        runner.invoke(
            app,
            [
                "close",
                ids[0],
                "--reason",
                "Done",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["archive", "--dry-run", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert (
            "links to non-archived" in result.stdout
            or "No issues can be" in result.stdout
        )

    def test_archive_skips_incoming_links_from_open(self, tmp_path: Path) -> None:
        """Test archive skips issues with incoming links from open issues."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Closed target", "Open source")
        runner.invoke(
            app,
            [
                "link",
                ids[1],
                "add",
                "--related",
                ids[0],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        runner.invoke(
            app,
            [
                "close",
                ids[0],
                "--reason",
                "Done",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["archive", "--dry-run", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "incoming links" in result.stdout or "No issues can be" in result.stdout

    def test_archive_skips_depends_on_open(self, tmp_path: Path) -> None:
        """Test archive skips issues that depend on open issues."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Closed blocker", "Open dep")
        runner.invoke(
            app,
            [
                "dep",
                ids[0],
                "add",
                "--depends-on",
                ids[1],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        runner.invoke(
            app,
            [
                "close",
                ids[0],
                "--reason",
                "Done",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["archive", "--dry-run", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert (
            "depends on non-archived" in result.stdout
            or "No issues can be" in result.stdout
        )


class TestListClosedFilter:
    """Test list with --closed flag."""

    def test_list_closed(self, tmp_path: Path) -> None:
        """Test list --closed shows only closed issues."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Keep open", "Mark closed")
        runner.invoke(
            app,
            [
                "close",
                ids[1],
                "--reason",
                "Done",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["list", "--closed", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Mark closed" in result.stdout
        assert "Keep open" not in result.stdout

    def test_list_all(self, tmp_path: Path) -> None:
        """Test list --all shows open and closed."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Open", "Closed")
        runner.invoke(
            app,
            [
                "close",
                ids[1],
                "--reason",
                "Done",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["list", "--all", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Open" in result.stdout


class TestUpdateManualOnNonexistent:
    """Test update --manual on nonexistent issue."""

    def test_update_manual_nonexistent(self, tmp_path: Path) -> None:
        """Test update --manual on nonexistent issue fails."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            [
                "update",
                "nonexistent",
                "--manual",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 1


class TestUpdateRemoveDependencies:
    """Test update --remove-depends-on and --remove-blocks."""

    def test_update_remove_depends_on(self, tmp_path: Path) -> None:
        """Test removing a dependency with --remove-depends-on."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Alpha", "Bravo")
        # Add dependency: Alpha depends on Bravo
        runner.invoke(
            app,
            [
                "update",
                ids[0],
                "--depends-on",
                ids[1],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        # Remove dependency
        result = runner.invoke(
            app,
            [
                "update",
                ids[0],
                "--remove-depends-on",
                ids[1],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Updated" in result.stdout

        # Verify dependency is gone
        show_result = runner.invoke(
            app,
            ["show", ids[0], "--dogcats-dir", str(dogcats_dir)],
        )
        assert (
            ids[1] not in show_result.stdout
            or "depends on" not in show_result.stdout.lower()
        )

    def test_update_remove_blocks(self, tmp_path: Path) -> None:
        """Test removing a blocks relationship with --remove-blocks."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Alpha", "Bravo")
        # Add: Alpha blocks Bravo
        runner.invoke(
            app,
            [
                "update",
                ids[0],
                "--blocks",
                ids[1],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        # Remove blocks relationship
        result = runner.invoke(
            app,
            [
                "update",
                ids[0],
                "--remove-blocks",
                ids[1],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Updated" in result.stdout

        # Verify blocks relationship is gone
        show_result = runner.invoke(
            app,
            ["show", ids[1], "--dogcats-dir", str(dogcats_dir)],
        )
        assert (
            ids[0] not in show_result.stdout
            or "blocks" not in show_result.stdout.lower()
        )

    def test_update_remove_depends_on_nonexistent(self, tmp_path: Path) -> None:
        """Test removing a dependency that doesn't exist gives a clear error."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Alpha", "Bravo")

        result = runner.invoke(
            app,
            [
                "update",
                ids[0],
                "--remove-depends-on",
                ids[1],
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 1
        assert "does not depend on" in result.output


class TestListJsonOutput:
    """Test list with JSON output."""

    def test_list_json(self, tmp_path: Path) -> None:
        """Test list --json outputs valid JSON."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Issue A")

        result = runner.invoke(
            app,
            ["list", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data: list[Any] = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) >= 1


class TestDoctorTextOutput:
    """Test doctor command text output paths."""

    def test_doctor_text_all_passed(self, tmp_path: Path) -> None:
        """Test doctor text output when most checks pass."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Issue")

        result = runner.invoke(
            app,
            ["doctor", "--dogcats-dir", str(dogcats_dir)],
        )
        # Doctor shows health check text
        assert "Dogcat Health Check" in result.stdout
        assert "All checks passed" in result.stdout


class TestDoctorDanglingDepsDetection:
    """Test doctor detects and fixes dangling dependencies."""

    def test_doctor_detects_dangling_deps(self, tmp_path: Path) -> None:
        """Test doctor detects dangling deps by injecting one in JSONL."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Alpha")

        # Inject a dangling dependency directly into the JSONL file
        import orjson

        issues_file = dogcats_dir / "issues.jsonl"
        dangling_dep = {
            "id": "dep-fake",
            "record_type": "dependency",
            "issue_id": ids[0],
            "depends_on_id": "nonexistent-issue",
            "dep_type": "blocks",
            "created_at": "2026-01-01T12:00:00+00:00",
        }
        with issues_file.open("ab") as f:
            f.write(orjson.dumps(dangling_dep) + b"\n")

        result = runner.invoke(
            app,
            ["doctor", "--dogcats-dir", str(dogcats_dir)],
        )
        # Doctor should detect the dangling dependency
        assert "Dogcat Health Check" in result.stdout
        assert "dangling" in result.stdout.lower() or "✗" in result.stdout

    def test_doctor_fix_with_dangling_deps(self, tmp_path: Path) -> None:
        """Test doctor --fix with dangling deps shows fix output."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Alpha")

        # Inject a dangling dependency directly into the JSONL file
        import orjson

        issues_file = dogcats_dir / "issues.jsonl"
        dangling_dep = {
            "id": "dep-fake",
            "record_type": "dependency",
            "issue_id": ids[0],
            "depends_on_id": "nonexistent-issue",
            "dep_type": "blocks",
            "created_at": "2026-01-01T12:00:00+00:00",
        }
        with issues_file.open("ab") as f:
            f.write(orjson.dumps(dangling_dep) + b"\n")

        result = runner.invoke(
            app,
            ["doctor", "--fix", "--dogcats-dir", str(dogcats_dir)],
        )
        # Doctor should detect the problem even if fix doesn't fully succeed
        assert "Dogcat Health Check" in result.stdout
        assert "✗" in result.stdout


class TestReadyTextOutput:
    """Test ready command text output."""

    def test_ready_text_no_issues(self, tmp_path: Path) -> None:
        """Test ready text output when no ready work exists."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            ["ready", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No ready work" in result.stdout


class TestInProgressTextOutput:
    """Test in-progress text output when empty."""

    def test_in_progress_empty(self, tmp_path: Path) -> None:
        """Test in-progress when no issues in progress."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Open issue")

        result = runner.invoke(
            app,
            ["in-progress", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No in-progress" in result.stdout


class TestInReviewTextOutput:
    """Test in-review text output when empty."""

    def test_in_review_empty(self, tmp_path: Path) -> None:
        """Test in-review when no issues in review."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Open issue")

        result = runner.invoke(
            app,
            ["in-review", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No in-review" in result.stdout


class TestDeferredTextOutput:
    """Test deferred text output when empty."""

    def test_deferred_empty(self, tmp_path: Path) -> None:
        """Test deferred when no deferred issues."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Open issue")

        result = runner.invoke(
            app,
            ["deferred", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No deferred" in result.stdout


class TestManualListTextOutput:
    """Test manual list text output when empty."""

    def test_manual_empty(self, tmp_path: Path) -> None:
        """Test manual when no manual issues."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Open issue")

        result = runner.invoke(
            app,
            ["manual", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No manual" in result.stdout


class TestShowJsonOutput:
    """Test show command with JSON output."""

    def test_show_json(self, tmp_path: Path) -> None:
        """Test show with --json flag."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue A")

        result = runner.invoke(
            app,
            ["show", ids[0], "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["title"] == "Issue A"


class TestListLabelFilter:
    """Test list with --label filter."""

    def test_list_label_filter(self, tmp_path: Path) -> None:
        """Test list with --label filter."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Backend", "Frontend")
        runner.invoke(
            app,
            [
                "label",
                ids[0],
                "add",
                "--label",
                "backend",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            [
                "list",
                "--label",
                "backend",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Backend" in result.stdout
        assert "Frontend" not in result.stdout


class TestRecentlyAdded:
    """Test the recently-added command."""

    def test_recently_added_shows_issues(self, tmp_path: Path) -> None:
        """Test that recently-added shows created issues."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Issue A", "Issue B")

        result = runner.invoke(
            app,
            ["recently-added", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Issue A" in result.stdout
        assert "Issue B" in result.stdout

    def test_recently_added_empty(self, tmp_path: Path) -> None:
        """Test recently-added with no issues."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            ["recently-added", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No recently added" in result.stdout

    def test_recently_added_json(self, tmp_path: Path) -> None:
        """Test recently-added with JSON output."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Issue A")

        result = runner.invoke(
            app,
            ["recently-added", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data: list[Any] = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["title"] == "Issue A"

    def test_recently_added_with_limit(self, tmp_path: Path) -> None:
        """Test recently-added respects --limit."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Issue A", "Issue B", "Issue C")

        result = runner.invoke(
            app,
            [
                "recently-added",
                "--limit",
                "1",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        # Should show header + 1 issue
        assert "Recently Added (1):" in result.stdout
        lines = [line for line in result.stdout.strip().split("\n") if line.strip()]
        assert len(lines) == 2

    def test_ra_alias(self, tmp_path: Path) -> None:
        """Test that 'ra' alias works for recently-added."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Issue A")

        result = runner.invoke(
            app,
            ["ra", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Issue A" in result.stdout

    def test_recently_added_excludes_tombstoned(self, tmp_path: Path) -> None:
        """Test that recently-added filters out tombstoned (deleted) issues."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Active Issue", "Deleted Issue")

        # Delete (tombstone) the second issue
        runner.invoke(
            app,
            ["delete", ids[1], "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["recently-added", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Active Issue" in result.stdout
        assert "Deleted Issue" not in result.stdout


class TestProgressReview:
    """Test the pr command (in-progress + in-review combined view)."""

    def test_pr_shows_both_sections(self, tmp_path: Path) -> None:
        """Test that pr shows both in-progress and in-review headers."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Task A", "Task B")

        # Set one to in_progress, one to in_review
        runner.invoke(
            app,
            [
                "update",
                ids[0],
                "--status",
                "in_progress",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        runner.invoke(
            app,
            [
                "update",
                ids[1],
                "--status",
                "in_progress",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        runner.invoke(
            app,
            [
                "update",
                ids[1],
                "--status",
                "in_review",
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
        assert "In Review (1):" in result.stdout
        assert "Task A" in result.stdout
        assert "Task B" in result.stdout

    def test_pr_empty(self, tmp_path: Path) -> None:
        """Test pr with no in-progress or in-review issues."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Open issue")

        result = runner.invoke(
            app,
            ["pr", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No in-progress issues" in result.stdout
        assert "No in-review issues" in result.stdout

    def test_pr_json(self, tmp_path: Path) -> None:
        """Test pr with JSON output."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Task A")
        runner.invoke(
            app,
            [
                "update",
                ids[0],
                "--status",
                "in_progress",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["pr", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "in_progress" in data
        assert "in_review" in data
        assert len(data["in_progress"]) == 1
        assert data["in_progress"][0]["title"] == "Task A"
        assert len(data["in_review"]) == 0


class TestRemoveCommand:
    """Test the 'remove' command (alias for delete with single issue_id)."""

    def test_remove_deletes_issue(self, tmp_path: Path) -> None:
        """Test that remove command creates a tombstone for the issue."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Issue to remove")

        result = runner.invoke(
            app,
            [
                "remove",
                ids[0],
                "--reason",
                "Not needed",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Deleted" in result.stdout

    def test_remove_with_json_output(self, tmp_path: Path) -> None:
        """Test that remove command works with JSON output."""
        dogcats_dir, ids = _init_and_create(tmp_path, "JSON remove test")

        result = runner.invoke(
            app,
            [
                "remove",
                ids[0],
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["status"] == "tombstone"

    def test_remove_nonexistent_issue(self, tmp_path: Path) -> None:
        """Test that remove on a nonexistent issue fails."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            [
                "remove",
                "nonexistent",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 1

    def test_remove_with_deleted_by(self, tmp_path: Path) -> None:
        """Test that remove passes deleted_by correctly."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Remove by user")

        result = runner.invoke(
            app,
            [
                "remove",
                ids[0],
                "--by",
                "alice",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0

        # Verify via JSON show
        result = runner.invoke(
            app,
            [
                "show",
                ids[0],
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["deleted_by"] == "alice"


class TestStatusByType:
    """Test 'By type' breakdown in status command (dogcat-12zo)."""

    def test_status_shows_by_type(self, tmp_path: Path) -> None:
        """Test status shows issue counts by type."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])
        runner.invoke(
            app,
            ["create", "Bug one", "--type", "bug", "--dogcats-dir", str(dogcats_dir)],
        )
        runner.invoke(
            app,
            [
                "create",
                "Feature one",
                "--type",
                "feature",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        runner.invoke(
            app,
            [
                "create",
                "Feature two",
                "--type",
                "feature",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["status", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "By type:" in result.stdout
        assert "bug" in result.stdout
        assert "feature" in result.stdout

    def test_status_json_includes_by_type(self, tmp_path: Path) -> None:
        """Test status JSON output includes by_type."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])
        runner.invoke(
            app,
            ["create", "Bug one", "--type", "bug", "--dogcats-dir", str(dogcats_dir)],
        )
        runner.invoke(
            app,
            [
                "create",
                "Task one",
                "--type",
                "task",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["status", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "by_type" in data
        assert data["by_type"]["bug"] == 1
        assert data["by_type"]["task"] == 1


class TestWorkflowTreeView:
    """Test tree view in in-progress, in-review, and pr commands (dogcat-1403)."""

    def test_in_progress_tree_with_parent_child(self, tmp_path: Path) -> None:
        """Test in-progress shows tree when parent-child relationships exist."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        # Create parent
        result = runner.invoke(
            app,
            [
                "create",
                "Epic task",
                "--type",
                "epic",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        parent_id = result.stdout.strip().split(": ")[0].split()[-1]

        # Create child
        result = runner.invoke(
            app,
            [
                "create",
                "Subtask one",
                "--parent",
                parent_id,
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        child_id = result.stdout.strip().split(": ")[0].split()[-1]

        # Set both to in_progress
        runner.invoke(
            app,
            [
                "update",
                parent_id,
                "--status",
                "in_progress",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        runner.invoke(
            app,
            [
                "update",
                child_id,
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
        assert "Epic task" in result.stdout
        assert "Subtask one" in result.stdout
        # Check indentation (child should be indented)
        for line in result.stdout.splitlines():
            if "Subtask one" in line:
                assert line.startswith("  ")
                break

    def test_in_progress_flat_without_parents(self, tmp_path: Path) -> None:
        """Test in-progress shows flat list when no parent-child relationships."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Task A", "Task B")
        for issue_id in ids:
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
            ["in-progress", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Task A" in result.stdout
        assert "Task B" in result.stdout

    def test_in_review_tree_with_parent_child(self, tmp_path: Path) -> None:
        """Test in-review shows tree when parent-child relationships exist."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        # Create parent
        result = runner.invoke(
            app,
            [
                "create",
                "Epic review",
                "--type",
                "epic",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        parent_id = result.stdout.strip().split(": ")[0].split()[-1]

        # Create child
        result = runner.invoke(
            app,
            [
                "create",
                "Review subtask",
                "--parent",
                parent_id,
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        child_id = result.stdout.strip().split(": ")[0].split()[-1]

        # Set both to in_review
        for iid in [parent_id, child_id]:
            runner.invoke(
                app,
                [
                    "update",
                    iid,
                    "--status",
                    "in_progress",
                    "--dogcats-dir",
                    str(dogcats_dir),
                ],
            )
            runner.invoke(
                app,
                [
                    "update",
                    iid,
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
        assert "Epic review" in result.stdout
        assert "Review subtask" in result.stdout

    def test_pr_tree_view(self, tmp_path: Path) -> None:
        """Test pr command shows tree view when parent-child relationships exist."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        # Create parent and child
        result = runner.invoke(
            app,
            [
                "create",
                "PR Epic",
                "--type",
                "epic",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        parent_id = result.stdout.strip().split(": ")[0].split()[-1]

        result = runner.invoke(
            app,
            [
                "create",
                "PR Subtask",
                "--parent",
                parent_id,
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        child_id = result.stdout.strip().split(": ")[0].split()[-1]

        # Set both to in_progress
        for iid in [parent_id, child_id]:
            runner.invoke(
                app,
                [
                    "update",
                    iid,
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
        assert "In Progress (2):" in result.stdout
        assert "PR Epic" in result.stdout
        assert "PR Subtask" in result.stdout

    def test_orphaned_child_shown_as_root(self, tmp_path: Path) -> None:
        """Test that child whose parent isn't in filtered set is treated as root."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        # Create parent (will stay open, not in in-progress set)
        result = runner.invoke(
            app,
            ["create", "Parent task", "--dogcats-dir", str(dogcats_dir)],
        )
        parent_id = result.stdout.strip().split(": ")[0].split()[-1]

        # Create child with parent
        result = runner.invoke(
            app,
            [
                "create",
                "Child task",
                "--parent",
                parent_id,
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        child_id = result.stdout.strip().split(": ")[0].split()[-1]

        # Only set child to in_progress (parent stays open)
        runner.invoke(
            app,
            [
                "update",
                child_id,
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
        assert "Child task" in result.stdout
        # Should not crash, child is shown even though parent isn't in the set


class TestSearchContextSnippets:
    """Test search context snippets (dogcat-5u7x)."""

    def test_search_shows_description_snippet(self, tmp_path: Path) -> None:
        """Test search shows context snippet from description."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Generic title")
        runner.invoke(
            app,
            [
                "update",
                ids[0],
                "--description",
                "The login page crashes on Safari browser when clicking submit",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["search", "Safari", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Generic title" in result.stdout
        assert "Description:" in result.stdout
        assert "Safari" in result.stdout

    def test_search_shows_notes_snippet(self, tmp_path: Path) -> None:
        """Test search shows context snippet from notes field."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Some issue")
        runner.invoke(
            app,
            [
                "update",
                ids[0],
                "--notes",
                "Investigated and found the foobar module is causing issues",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["search", "foobar", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Some issue" in result.stdout
        assert "Notes:" in result.stdout
        assert "foobar" in result.stdout

    def test_search_shows_acceptance_snippet(self, tmp_path: Path) -> None:
        """Test search shows context snippet from acceptance field."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Feature X")
        runner.invoke(
            app,
            [
                "update",
                ids[0],
                "--acceptance",
                "User must be able to use bazqux endpoint",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["search", "bazqux", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Feature X" in result.stdout
        assert "Acceptance:" in result.stdout
        assert "bazqux" in result.stdout

    def test_search_title_match_no_extra_snippet(self, tmp_path: Path) -> None:
        """Test search with title-only match does not show Title: snippet."""
        dogcats_dir, _ = _init_and_create(tmp_path, "Fix login bug")

        result = runner.invoke(
            app,
            ["search", "login", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Fix login bug" in result.stdout
        # Should not show a "Title:" snippet since title is already visible
        assert "Title:" not in result.stdout

    def test_search_design_field(self, tmp_path: Path) -> None:
        """Test search matches in design field."""
        dogcats_dir, ids = _init_and_create(tmp_path, "Design issue")
        runner.invoke(
            app,
            [
                "update",
                ids[0],
                "--design",
                "We should use the quuxflop architecture pattern",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["search", "quuxflop", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Design issue" in result.stdout
        assert "Design:" in result.stdout
        assert "quuxflop" in result.stdout
