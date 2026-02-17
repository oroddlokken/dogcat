"""Tests for Dogcat CLI commands."""

import json
from pathlib import Path

from typer.testing import CliRunner

from dogcat.cli import app

runner = CliRunner()


class TestCLIStatus:
    """Test status command."""

    def test_status_shows_prefix_and_counts(self, tmp_path: Path) -> None:
        """Test that status shows prefix and issue counts."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            [
                "init",
                "--namespace",
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
                "--namespace",
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
                "--namespace",
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

    def test_status_shows_inbox_counts(self, tmp_path: Path) -> None:
        """Test that status includes inbox proposal counts."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--namespace", "test", "--dogcats-dir", str(dogcats_dir)],
        )

        # Create a proposal in the inbox
        runner.invoke(
            app,
            ["propose", "Test proposal", "--to", str(tmp_path)],
        )

        result = runner.invoke(
            app,
            ["status", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Inbox: 1 proposal(s)" in result.stdout
        assert "open" in result.stdout

    def test_status_json_includes_inbox(self, tmp_path: Path) -> None:
        """Test that status JSON includes inbox counts when proposals exist."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--namespace", "test", "--dogcats-dir", str(dogcats_dir)],
        )

        runner.invoke(
            app,
            ["propose", "Test proposal", "--to", str(tmp_path)],
        )

        result = runner.invoke(
            app,
            ["status", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["inbox_total"] == 1
        assert data["inbox_by_status"]["open"] == 1

    def test_status_no_inbox_when_empty(self, tmp_path: Path) -> None:
        """Test that status JSON omits inbox fields when no proposals exist."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--namespace", "test", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["status", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "inbox_total" not in data


class TestCLIGit:
    """Test git integration guide command."""

    def test_git_guide_output(self) -> None:
        """Test that git guide subcommand outputs the integration guide."""
        result = runner.invoke(app, ["git", "guide"])
        assert result.exit_code == 0
        assert "DOGCAT + GIT INTEGRATION GUIDE" in result.stdout
        assert "Committing .dogcats" in result.stdout
        assert "Resolving Merge Conflicts" in result.stdout
        assert "Best Practices" in result.stdout

    def test_git_guide_covers_gitignore(self) -> None:
        """Test that git guide includes .gitignore instructions."""
        result = runner.invoke(app, ["git", "guide"])
        assert ".gitignore" in result.stdout

    def test_git_no_args_shows_help(self) -> None:
        """Test that 'dcat git' with no subcommand shows help."""
        result = runner.invoke(app, ["git"])
        # Typer's no_args_is_help exits with code 0 after showing help
        assert "guide" in result.stdout
        assert "check" in result.stdout
        assert "setup" in result.stdout


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

    def test_guide_contains_manual_section(self) -> None:
        """Test that guide includes the manual issues section."""
        result = runner.invoke(app, ["guide"])
        assert "--manual" in result.stdout


class TestCLIVersion:
    """Test version command."""

    def test_version_displays_version(self) -> None:
        """Test that version command outputs the package version."""
        from dogcat._version import version as v

        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert v in result.stdout


class TestCLICommandAliases:
    """Test shorthand command aliases (l, lt, rc, b, d)."""

    def test_l_alias_shows_tree(self, tmp_path: Path) -> None:
        """Test that 'l' shows list in tree mode."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])
        runner.invoke(
            app,
            ["create", "Parent issue", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["l", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Parent issue" in result.stdout

    def test_l_alias_passes_filters(self, tmp_path: Path) -> None:
        """Test that 'l' passes through filter options."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])
        runner.invoke(
            app,
            [
                "create",
                "Bug issue",
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
                "Feature issue",
                "--type",
                "feature",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["l", "--type", "bug", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Bug issue" in result.stdout
        assert "Feature issue" not in result.stdout

    def test_lt_alias_shows_table(self, tmp_path: Path) -> None:
        """Test that 'lt' shows list in table mode."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])
        runner.invoke(
            app,
            ["create", "Table issue", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["lt", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Table issue" in result.stdout

    def test_rc_alias_shows_recently_closed(self, tmp_path: Path) -> None:
        """Test that 'rc' shows recently closed issues."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])
        create_result = runner.invoke(
            app,
            ["create", "Closed issue", "--dogcats-dir", str(dogcats_dir)],
        )
        issue_id = create_result.stdout.split(": ")[0].split()[-1]
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
            ["rc", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Closed issue" in result.stdout

    def test_rc_alias_no_closed_issues(self, tmp_path: Path) -> None:
        """Test 'rc' with no closed issues."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            ["rc", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No recently closed issues" in result.stdout

    def test_b_alias_shows_blocked(self, tmp_path: Path) -> None:
        """Test that 'b' shows blocked issues."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            ["b", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No blocked issues" in result.stdout

    def test_d_alias_shows_deferred(self, tmp_path: Path) -> None:
        """Test that 'd' shows deferred issues."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            ["d", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No deferred issues" in result.stdout

    def test_d_alias_with_deferred_issue(self, tmp_path: Path) -> None:
        """Test 'd' with a deferred issue."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])
        create_result = runner.invoke(
            app,
            ["create", "Deferred task", "--dogcats-dir", str(dogcats_dir)],
        )
        issue_id = create_result.stdout.split(": ")[0].split()[-1]
        runner.invoke(
            app,
            [
                "update",
                "--status",
                "deferred",
                issue_id,
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["d", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Deferred task" in result.stdout


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
        assert "Set namespace: imported" in result.stdout

        # Verify config was updated
        config_file = dogcats_dir / "config.toml"
        content = config_file.read_text()
        assert 'namespace = "imported"' in content

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
        assert "Set namespace: latest" in result.stdout

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
                "--namespace",
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
        assert 'namespace = "keepme"' in content


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

    def test_blocked_by_tag_shown_when_blocked(self) -> None:
        """Test that [blocked by: ...] tag appears for blocked issues."""
        from dogcat.cli import format_issue_brief
        from dogcat.models import Issue

        issue = Issue(id="abc4", namespace="dc", title="Blocked issue")
        blocked_ids = {"dc-abc4"}
        blocked_by_map = {"dc-abc4": ["dc-xyz1", "dc-xyz2"]}
        result = format_issue_brief(issue, blocked_ids, blocked_by_map)
        assert "[blocked by: dc-xyz1, dc-xyz2]" in result
        # red ANSI code is \x1b[31m
        assert "\x1b[31m" in result

    def test_blocked_by_tag_absent_when_not_blocked(self) -> None:
        """Test that [blocked by: ...] tag is absent for non-blocked issues."""
        from dogcat.cli import format_issue_brief
        from dogcat.models import Issue

        issue = Issue(id="abc5", namespace="dc", title="Normal issue")
        blocked_ids: set[str] = set()
        blocked_by_map: dict[str, list[str]] = {}
        result = format_issue_brief(issue, blocked_ids, blocked_by_map)
        assert "[blocked by:" not in result
