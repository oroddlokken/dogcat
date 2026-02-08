"""Additional migration tests to cover error paths and edge cases."""

import json
from pathlib import Path

import pytest

from dogcat.migrate import (
    migrate_from_beads,
    migrate_issue,
    read_beads_jsonl,
)
from dogcat.models import DependencyType, IssueType, Status


class TestReadBeadsJsonlErrors:
    """Test beads JSONL reading error paths."""

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        """Test that invalid JSON in beads file raises ValueError."""
        jsonl_file = tmp_path / "bad.jsonl"
        jsonl_file.write_text("not json at all\n")

        with pytest.raises(ValueError, match="Invalid JSON"):
            read_beads_jsonl(str(jsonl_file))


class TestMigrateIssueEdgeCases:
    """Test edge cases in issue migration."""

    def test_old_format_id_without_namespace(self) -> None:
        """Test migrating issue with old format id (prefix-hash)."""
        beads_issue = {
            "id": "proj-abc123",
            "title": "Old format",
            "created_at": "2026-01-01T12:00:00+00:00",
            "updated_at": "2026-01-01T12:00:00+00:00",
        }
        issue, _deps = migrate_issue(beads_issue)
        assert issue.namespace == "proj"
        assert issue.id == "abc123"

    def test_plain_id_without_dash(self) -> None:
        """Test migrating issue with plain ID (no dash)."""
        beads_issue = {
            "id": "plain123",
            "title": "Plain ID",
            "created_at": "2026-01-01T12:00:00+00:00",
            "updated_at": "2026-01-01T12:00:00+00:00",
        }
        issue, _deps = migrate_issue(beads_issue)
        assert issue.namespace == "dc"
        assert issue.id == "plain123"

    def test_invalid_status_defaults_to_open(self) -> None:
        """Test that invalid status falls back to OPEN."""
        beads_issue = {
            "id": "test-1",
            "title": "Bad status",
            "status": "nonexistent_status",
            "created_at": "2026-01-01T12:00:00+00:00",
            "updated_at": "2026-01-01T12:00:00+00:00",
        }
        issue, _deps = migrate_issue(beads_issue)
        assert issue.status == Status.OPEN

    def test_invalid_issue_type_defaults_to_task(self) -> None:
        """Test that invalid issue type falls back to TASK."""
        beads_issue = {
            "id": "test-1",
            "title": "Bad type",
            "issue_type": "nonexistent_type",
            "created_at": "2026-01-01T12:00:00+00:00",
            "updated_at": "2026-01-01T12:00:00+00:00",
        }
        issue, _deps = migrate_issue(beads_issue)
        assert issue.issue_type == IssueType.TASK

    def test_invalid_dependency_type_defaults_to_blocks(self) -> None:
        """Test that invalid dependency type falls back to BLOCKS."""
        beads_issue = {
            "id": "test-1",
            "title": "Issue",
            "created_at": "2026-01-01T12:00:00+00:00",
            "updated_at": "2026-01-01T12:00:00+00:00",
            "dependencies": [
                {
                    "issue_id": "test-1",
                    "depends_on_id": "test-2",
                    "type": "invalid_dep_type",
                },
            ],
        }
        _issue, deps = migrate_issue(beads_issue)
        assert len(deps) == 1
        assert deps[0].dep_type == DependencyType.BLOCKS

    def test_new_format_with_namespace(self) -> None:
        """Test migrating issue with explicit namespace field."""
        beads_issue = {
            "id": "xyz",
            "namespace": "myns",
            "title": "New format",
            "created_at": "2026-01-01T12:00:00+00:00",
            "updated_at": "2026-01-01T12:00:00+00:00",
        }
        issue, _deps = migrate_issue(beads_issue)
        assert issue.namespace == "myns"
        assert issue.id == "xyz"

    def test_missing_datetime_uses_now(self) -> None:
        """Test that missing datetime fields default to now."""
        beads_issue = {
            "id": "test-1",
            "title": "No dates",
        }
        issue, _deps = migrate_issue(beads_issue)
        assert issue.created_at is not None
        assert issue.updated_at is not None


class TestMigrateFromBeadsVerbose:
    """Test verbose output during migration."""

    def test_verbose_output(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test that verbose mode prints progress."""
        beads_file = tmp_path / "issues.jsonl"
        issue_data = {
            "id": "test-1",
            "title": "Test Issue",
            "status": "open",
            "priority": 2,
            "issue_type": "task",
            "created_at": "2026-01-01T12:00:00+00:00",
            "created_by": "User",
            "updated_at": "2026-01-01T12:00:00+00:00",
        }
        beads_file.write_text(json.dumps(issue_data) + "\n")

        output_dir = tmp_path / ".dogcats"
        migrate_from_beads(str(beads_file), str(output_dir), verbose=True)

        captured = capsys.readouterr()
        assert "Read 1 issues" in captured.out
        assert "Imported test-1" in captured.out

    def test_verbose_merge_skip(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test that verbose mode reports skipped issues in merge mode."""
        beads_file = tmp_path / "issues.jsonl"
        issue_data = {
            "id": "test-1",
            "title": "Test Issue",
            "status": "open",
            "priority": 2,
            "issue_type": "task",
            "created_at": "2026-01-01T12:00:00+00:00",
            "created_by": "User",
            "updated_at": "2026-01-01T12:00:00+00:00",
        }
        beads_file.write_text(json.dumps(issue_data) + "\n")

        output_dir = tmp_path / ".dogcats"
        # First import
        migrate_from_beads(str(beads_file), str(output_dir))
        # Second import with merge - should skip
        _imported, _failed, skipped = migrate_from_beads(
            str(beads_file),
            str(output_dir),
            merge=True,
            verbose=True,
        )

        assert skipped == 1
        captured = capsys.readouterr()
        assert "Skipped" in captured.out

    def test_verbose_dependency_import(
        self,
        tmp_path: Path,
    ) -> None:
        """Test verbose output for dependency import."""
        beads_file = tmp_path / "issues.jsonl"
        issues = [
            {
                "id": "test-1",
                "title": "Issue 1",
                "status": "open",
                "priority": 2,
                "issue_type": "task",
                "created_at": "2026-01-01T12:00:00+00:00",
                "created_by": "User",
                "updated_at": "2026-01-01T12:00:00+00:00",
            },
            {
                "id": "test-2",
                "title": "Issue 2",
                "status": "open",
                "priority": 2,
                "issue_type": "task",
                "created_at": "2026-01-01T12:00:00+00:00",
                "created_by": "User",
                "updated_at": "2026-01-01T12:00:00+00:00",
                "dependencies": [
                    {
                        "issue_id": "test-2",
                        "depends_on_id": "test-1",
                        "type": "blocks",
                        "created_at": "2026-01-01T12:00:00+00:00",
                    },
                ],
            },
        ]
        beads_file.write_text("\n".join(json.dumps(i) for i in issues) + "\n")

        output_dir = tmp_path / ".dogcats"
        imported, failed, _skipped = migrate_from_beads(
            str(beads_file),
            str(output_dir),
            verbose=True,
        )

        assert imported == 2
        assert failed == 0
