"""Tests for migration from beads to dogcat."""

from pathlib import Path

import pytest

from dogcat.migrate import (
    migrate_from_beads,
    migrate_issue,
    parse_datetime,
    read_beads_jsonl,
)
from dogcat.models import DependencyType, IssueType, Status
from dogcat.storage import JSONLStorage


class TestParseDatetime:
    """Test datetime parsing."""

    def test_parse_iso8601_with_timezone(self) -> None:
        """Test parsing ISO8601 datetime with timezone."""
        dt_str = "2026-02-03T13:21:21.529677+01:00"
        result = parse_datetime(dt_str)
        assert result is not None
        assert result.year == 2026
        assert result.month == 2
        assert result.day == 3
        assert result.hour == 13
        assert result.minute == 21
        assert result.second == 21
        assert result.tzinfo is not None

    def test_parse_iso8601_utc_z(self) -> None:
        """Test parsing ISO8601 datetime with Z suffix."""
        dt_str = "2026-02-03T12:00:00Z"
        result = parse_datetime(dt_str)
        assert result is not None
        assert result.year == 2026
        assert result.hour == 12
        assert result.tzinfo is not None

    def test_parse_none(self) -> None:
        """Test parsing None."""
        result = parse_datetime(None)
        assert result is None

    def test_parse_empty_string(self) -> None:
        """Test parsing empty string."""
        result = parse_datetime("")
        assert result is None

    def test_parse_invalid_datetime(self) -> None:
        """Test parsing invalid datetime."""
        result = parse_datetime("not-a-datetime")
        assert result is None


class TestReadBeadsJsonl:
    """Test reading beads JSONL files."""

    def test_read_nonexistent_file(self) -> None:
        """Test reading nonexistent file raises error."""
        with pytest.raises(FileNotFoundError):
            read_beads_jsonl("/nonexistent/path/to/issues.jsonl")

    def test_read_empty_file(self, tmp_path: Path) -> None:
        """Test reading empty file."""
        empty_file = tmp_path / "empty.jsonl"
        empty_file.touch()
        result = read_beads_jsonl(str(empty_file))
        assert result == []

    def test_read_valid_jsonl(self, tmp_path: Path) -> None:
        """Test reading valid JSONL file."""
        jsonl_file = tmp_path / "issues.jsonl"
        jsonl_file.write_text(
            '{"id": "test-1", "title": "Issue 1"}\n'
            '{"id": "test-2", "title": "Issue 2"}\n',
        )
        result = read_beads_jsonl(str(jsonl_file))
        assert len(result) == 2
        assert result[0]["id"] == "test-1"
        assert result[1]["id"] == "test-2"


class TestMigrateIssue:
    """Test issue migration."""

    def test_migrate_basic_issue(self) -> None:
        """Test migrating basic issue."""
        beads_issue = {
            "id": "test-1",
            "title": "Test Issue",
            "status": "open",
            "priority": 2,
            "issue_type": "task",
            "owner": "user@example.com",
            "created_at": "2026-02-03T12:00:00+00:00",
            "created_by": "User Name",
            "updated_at": "2026-02-03T12:00:00+00:00",
        }
        issue, deps = migrate_issue(beads_issue)
        assert issue.namespace == "test"
        assert issue.id == "1"
        assert issue.full_id == "test-1"
        assert issue.title == "Test Issue"
        assert issue.status == Status.OPEN
        assert issue.priority == 2
        assert issue.issue_type == IssueType.TASK
        assert issue.owner == "user@example.com"
        assert len(deps) == 0

    def test_migrate_issue_with_dependencies(self) -> None:
        """Test migrating issue with dependencies."""
        beads_issue = {
            "id": "test-1",
            "title": "Test Issue",
            "status": "open",
            "priority": 2,
            "issue_type": "task",
            "dependencies": [
                {
                    "issue_id": "test-1",
                    "depends_on_id": "test-2",
                    "type": "blocks",
                    "created_at": "2026-02-03T12:00:00+00:00",
                    "created_by": "User",
                },
            ],
            "created_at": "2026-02-03T12:00:00+00:00",
            "created_by": "User Name",
            "updated_at": "2026-02-03T12:00:00+00:00",
        }
        _issue, deps = migrate_issue(beads_issue)
        assert len(deps) == 1
        assert deps[0].issue_id == "test-1"
        assert deps[0].depends_on_id == "test-2"
        assert deps[0].dep_type == DependencyType.BLOCKS

    def test_migrate_tombstone_issue(self) -> None:
        """Test migrating tombstone (deleted) issue."""
        beads_issue = {
            "id": "test-1",
            "title": "Deleted Issue",
            "status": "tombstone",
            "priority": 2,
            "issue_type": "task",
            "created_at": "2026-02-03T12:00:00+00:00",
            "created_by": "User Name",
            "updated_at": "2026-02-03T12:00:00+00:00",
            "deleted_at": "2026-02-03T13:00:00+00:00",
            "deleted_by": "User",
            "delete_reason": "No longer needed",
            "original_type": "task",
        }
        issue, _deps = migrate_issue(beads_issue)
        assert issue.status == Status.TOMBSTONE
        assert issue.deleted_at is not None
        assert issue.original_type == IssueType.TASK


class TestMigrateFromBeads:
    """Test full import process."""

    def test_migrate_complete_workflow(self, tmp_path: Path) -> None:
        """Test complete import workflow."""
        # Create source beads JSONL
        beads_file = tmp_path / "beads_issues.jsonl"
        issue1 = {
            "id": "test-1",
            "title": "Issue 1",
            "status": "open",
            "priority": 2,
            "issue_type": "task",
            "created_at": "2026-02-03T12:00:00+00:00",
            "created_by": "User",
            "updated_at": "2026-02-03T12:00:00+00:00",
        }
        issue2 = {
            "id": "test-2",
            "title": "Issue 2",
            "status": "closed",
            "priority": 1,
            "issue_type": "bug",
            "created_at": "2026-02-03T12:00:00+00:00",
            "created_by": "User",
            "updated_at": "2026-02-03T12:00:00+00:00",
            "closed_at": "2026-02-03T13:00:00+00:00",
        }
        import json

        beads_file.write_text(json.dumps(issue1) + "\n" + json.dumps(issue2) + "\n")

        # Perform import
        output_dir = tmp_path / ".dogcats"
        imported, failed, skipped = migrate_from_beads(str(beads_file), str(output_dir))

        assert imported == 2
        assert failed == 0
        assert skipped == 0

        # Verify output
        storage = JSONLStorage(str(output_dir / "issues.jsonl"))
        issue1_result = storage.get("test-1")
        issue2_result = storage.get("test-2")

        assert issue1_result is not None
        assert issue1_result.title == "Issue 1"
        assert issue2_result is not None
        assert issue2_result.title == "Issue 2"
        assert issue2_result.status == Status.CLOSED

    def test_merge_into_existing_project(self, tmp_path: Path) -> None:
        """Test importing into existing project with merge mode."""
        import json

        output_dir = tmp_path / ".dogcats"
        output_dir.mkdir()

        # Create existing dogcat project with one issue
        existing_issue: dict[str, object] = {
            "id": "dc-0001",
            "title": "Existing Issue",
            "status": "open",
            "priority": 2,
            "issue_type": "task",
            "created_at": "2026-01-01T12:00:00+00:00",
            "created_by": "User",
            "updated_at": "2026-01-01T12:00:00+00:00",
            "labels": [],
            "comments": [],
            "metadata": {},
        }
        issues_file = output_dir / "issues.jsonl"
        issues_file.write_text(json.dumps(existing_issue) + "\n")

        # Create beads file with new and overlapping issues
        beads_file = tmp_path / "beads_issues.jsonl"
        beads_issues = [
            {
                "id": "bd-aaaa",
                "title": "Beads Issue 1",
                "status": "open",
                "priority": 1,
                "issue_type": "bug",
                "created_at": "2026-02-03T12:00:00+00:00",
                "created_by": "User",
                "updated_at": "2026-02-03T12:00:00+00:00",
            },
            {
                "id": "dc-0001",  # Same ID as existing - should be skipped
                "title": "Duplicate Issue",
                "status": "open",
                "priority": 2,
                "issue_type": "task",
                "created_at": "2026-02-03T12:00:00+00:00",
                "created_by": "User",
                "updated_at": "2026-02-03T12:00:00+00:00",
            },
        ]
        beads_file.write_text("\n".join(json.dumps(i) for i in beads_issues) + "\n")

        # Import with merge=True
        imported, failed, skipped = migrate_from_beads(
            str(beads_file),
            str(output_dir),
            merge=True,
        )

        assert imported == 1  # Only bd-aaaa
        assert failed == 0
        assert skipped == 1  # dc-0001 already exists

        # Verify both issues exist
        storage = JSONLStorage(str(issues_file))
        dc_0001 = storage.get("dc-0001")
        assert dc_0001 is not None
        assert dc_0001.title == "Existing Issue"  # Original preserved
        bd_aaaa = storage.get("bd-aaaa")
        assert bd_aaaa is not None
        assert bd_aaaa.title == "Beads Issue 1"
