"""Tests for JSONL data validation logic.

Tests the validation functions in dogcat.cli._validate and their
integration with the ``dcat doctor`` command.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import orjson
import pytest
from typer.testing import CliRunner

from dogcat.cli import app
from dogcat.cli._validate import (
    detect_concurrent_edits,
    parse_raw_records,
    validate_issue,
    validate_jsonl,
    validate_references,
)
from dogcat.constants import MERGE_DRIVER_CMD
from dogcat.models import Issue

if TYPE_CHECKING:

    from conftest import GitRepo

runner = CliRunner()


@pytest.fixture
def dogcats_dir(tmp_path: Path) -> Path:
    """Create a temporary .dogcats directory."""
    d = tmp_path / ".dogcats"
    d.mkdir()
    return d


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    """Write records to a JSONL file."""
    with path.open("wb") as f:
        for record in records:
            f.write(orjson.dumps(record))
            f.write(b"\n")


def _issue(
    issue_id: str = "abc",
    namespace: str = "test",
    **kwargs: Any,
) -> dict[str, Any]:
    """Build a minimal valid issue record."""
    defaults: dict[str, Any] = {
        "record_type": "issue",
        "id": issue_id,
        "namespace": namespace,
        "title": "Test Issue",
        "status": "open",
        "priority": 2,
        "issue_type": "task",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    defaults.update(kwargs)
    return defaults


def _dep(
    issue_id: str = "test-a",
    depends_on_id: str = "test-b",
    dep_type: str = "blocks",
    **kwargs: Any,
) -> dict[str, Any]:
    """Build a minimal dependency record."""
    defaults: dict[str, Any] = {
        "record_type": "dependency",
        "issue_id": issue_id,
        "depends_on_id": depends_on_id,
        "type": dep_type,
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    defaults.update(kwargs)
    return defaults


def _event(
    issue_id: str = "test-abc",
    event_type: str = "created",
    **kwargs: Any,
) -> dict[str, Any]:
    """Build a minimal event record."""
    defaults: dict[str, Any] = {
        "record_type": "event",
        "issue_id": issue_id,
        "event_type": event_type,
        "timestamp": "2026-01-01T00:00:00+00:00",
    }
    defaults.update(kwargs)
    return defaults


def _errors(results: list[dict[str, str]]) -> list[dict[str, str]]:
    """Filter only error-level results."""
    return [r for r in results if r["level"] == "error"]


def _warnings(results: list[dict[str, str]]) -> list[dict[str, str]]:
    """Filter only warning-level results."""
    return [r for r in results if r["level"] == "warning"]


# ---------------------------------------------------------------------------
# Unit tests for parse_raw_records
# ---------------------------------------------------------------------------


class TestParseRawRecords:
    """Test JSONL parsing and basic structural checks."""

    def test_valid_file(self, tmp_path: Path) -> None:
        """Parse a valid JSONL file."""
        path = tmp_path / "test.jsonl"
        _write_jsonl(path, [_issue()])
        records, errors = parse_raw_records(path)
        assert len(records) == 1
        assert errors == []

    def test_invalid_json(self, tmp_path: Path) -> None:
        """Detect invalid JSON lines."""
        path = tmp_path / "test.jsonl"
        path.write_text("not json at all\n")
        records, errors = parse_raw_records(path)
        assert len(records) == 0
        assert len(_errors(errors)) == 1
        assert "invalid JSON" in errors[0]["message"]

    def test_non_object_json(self, tmp_path: Path) -> None:
        """Detect JSON arrays instead of objects."""
        path = tmp_path / "test.jsonl"
        path.write_text("[1, 2, 3]\n")
        records, errors = parse_raw_records(path)
        assert len(records) == 0
        assert "expected JSON object" in errors[0]["message"]

    def test_missing_record_type(self, tmp_path: Path) -> None:
        """Warn when record_type is missing."""
        record = _issue()
        del record["record_type"]
        path = tmp_path / "test.jsonl"
        _write_jsonl(path, [record])
        records, errors = parse_raw_records(path)
        assert len(records) == 1  # Still parsed
        assert len(_warnings(errors)) == 1
        assert "missing record_type" in errors[0]["message"]

    def test_missing_file(self, tmp_path: Path) -> None:
        """Report error for non-existent file."""
        path = tmp_path / "nonexistent.jsonl"
        records, errors = parse_raw_records(path)
        assert len(records) == 0
        assert len(_errors(errors)) == 1
        assert "does not exist" in errors[0]["message"]

    def test_empty_file(self, tmp_path: Path) -> None:
        """An empty file produces no records and no errors."""
        path = tmp_path / "test.jsonl"
        path.write_text("")
        records, errors = parse_raw_records(path)
        assert records == []
        assert errors == []


# ---------------------------------------------------------------------------
# Unit tests for validate_issue
# ---------------------------------------------------------------------------


class TestValidateIssue:
    """Test individual issue record validation."""

    def test_valid_issue(self) -> None:
        """A well-formed issue produces no errors."""
        assert validate_issue(_issue(), lineno=1) == []

    def test_missing_required_field(self) -> None:
        """Detect missing required fields."""
        record = _issue()
        del record["title"]
        errors = validate_issue(record, lineno=1)
        assert len(errors) == 1
        assert "missing required field 'title'" in errors[0]["message"]

    def test_invalid_status(self) -> None:
        """Detect invalid status values."""
        errors = validate_issue(_issue(status="bogus"), lineno=1)
        assert len(errors) == 1
        assert "invalid status" in errors[0]["message"]

    def test_invalid_issue_type(self) -> None:
        """Detect invalid issue_type values."""
        errors = validate_issue(_issue(issue_type="unicorn"), lineno=1)
        assert len(errors) == 1
        assert "invalid issue_type" in errors[0]["message"]

    def test_legacy_draft_issue_type_accepted(self) -> None:
        """Legacy issue_type='draft' is accepted (migrated on load)."""
        errors = validate_issue(_issue(issue_type="draft"), lineno=1)
        assert errors == []

    def test_legacy_subtask_issue_type_accepted(self) -> None:
        """Legacy issue_type='subtask' is accepted (migrated on load)."""
        errors = validate_issue(_issue(issue_type="subtask"), lineno=1)
        assert errors == []

    def test_priority_out_of_range(self) -> None:
        """Detect priority values outside 0-4."""
        errors = validate_issue(_issue(priority=99), lineno=1)
        assert len(errors) == 1
        assert "invalid priority" in errors[0]["message"]

    def test_invalid_timestamp(self) -> None:
        """Detect invalid ISO 8601 timestamps."""
        errors = validate_issue(
            _issue(created_at="not-a-timestamp"),
            lineno=1,
        )
        assert len(errors) == 1
        assert "invalid timestamp" in errors[0]["message"]


# ---------------------------------------------------------------------------
# Unit tests for validate_references
# ---------------------------------------------------------------------------


class TestValidateReferences:
    """Test referential integrity checks."""

    def test_dangling_parent(self) -> None:
        """Detect parent pointing to non-existent issue."""
        records = [_issue(issue_id="child", parent="test-nonexistent")]
        errors = _errors(validate_references(records))
        assert len(errors) == 1
        assert "non-existent parent" in errors[0]["message"]

    def test_valid_parent(self) -> None:
        """Valid parent reference produces no errors."""
        records = [
            _issue(issue_id="parent"),
            _issue(issue_id="child", parent="test-parent"),
        ]
        errors = _errors(validate_references(records))
        assert len(errors) == 0

    def test_dangling_dependency(self) -> None:
        """Detect dependency pointing to non-existent issue."""
        records = [
            _issue(issue_id="a"),
            _dep(issue_id="test-a", depends_on_id="test-missing"),
        ]
        errors = _errors(validate_references(records))
        assert any("non-existent" in e["message"] for e in errors)

    def test_circular_dependency(self) -> None:
        """Detect circular dependency chains."""
        records = [
            _issue(issue_id="a"),
            _issue(issue_id="b"),
            _issue(issue_id="c"),
            _dep(issue_id="test-a", depends_on_id="test-b"),
            _dep(issue_id="test-b", depends_on_id="test-c"),
            _dep(issue_id="test-c", depends_on_id="test-a"),
        ]
        errors = _errors(validate_references(records))
        assert any("Circular dependency" in e["message"] for e in errors)

    def test_event_nonexistent_issue_is_warning(self) -> None:
        """Event referencing non-existent issue is a warning, not error."""
        records = [_event(issue_id="test-gone")]
        results = validate_references(records)
        assert len(_errors(results)) == 0
        assert len(_warnings(results)) == 1

    def test_removed_deps_not_flagged(self) -> None:
        """Removed dependencies should not trigger dangling errors."""
        records = [
            _issue(issue_id="a"),
            _dep(
                issue_id="test-a",
                depends_on_id="test-gone",
                op="remove",
            ),
        ]
        errors = _errors(validate_references(records))
        assert len(errors) == 0


# ---------------------------------------------------------------------------
# Integration: validate_jsonl (full pipeline)
# ---------------------------------------------------------------------------


class TestValidateJsonl:
    """Test the top-level validate_jsonl function."""

    def test_valid_data(self, tmp_path: Path) -> None:
        """Valid data returns no errors."""
        path = tmp_path / "issues.jsonl"
        _write_jsonl(path, [_issue(issue_id="a"), _issue(issue_id="b")])
        errors = validate_jsonl(path)
        assert _errors(errors) == []

    def test_multiple_problems(self, tmp_path: Path) -> None:
        """Multiple problems are all reported."""
        path = tmp_path / "issues.jsonl"
        _write_jsonl(
            path,
            [
                _issue(status="bogus"),
                _issue(issue_id="child", parent="test-gone"),
            ],
        )
        errors = _errors(validate_jsonl(path))
        assert len(errors) >= 2


# ---------------------------------------------------------------------------
# Integration: dcat doctor uses validation
# ---------------------------------------------------------------------------


class TestDoctorValidation:
    """Test that doctor includes data integrity checks."""

    def test_doctor_passes_valid_data(self, dogcats_dir: Path) -> None:
        """Doctor passes when JSONL data is valid."""
        _write_jsonl(dogcats_dir / "issues.jsonl", [_issue()])
        result = runner.invoke(
            app,
            ["doctor", "--dogcats-dir", str(dogcats_dir)],
        )
        assert "Data integrity" in result.stdout
        assert "✓" in result.stdout

    def test_doctor_reports_invalid_data(self, dogcats_dir: Path) -> None:
        """Doctor reports data integrity errors."""
        _write_jsonl(
            dogcats_dir / "issues.jsonl",
            [_issue(status="bogus")],
        )
        result = runner.invoke(
            app,
            ["doctor", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 1
        assert "invalid status" in result.stdout

    def test_doctor_json_includes_validation(
        self,
        dogcats_dir: Path,
    ) -> None:
        """Doctor --json includes validation details."""
        _write_jsonl(
            dogcats_dir / "issues.jsonl",
            [_issue(status="bogus")],
        )
        result = runner.invoke(
            app,
            ["doctor", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        data = json.loads(result.stdout)
        assert "validation_details" in data
        assert len(data["validation_details"]) >= 1


# ---------------------------------------------------------------------------
# Regression: validate real repo data
# ---------------------------------------------------------------------------


class TestValidateRepoData:
    """Validate the actual repo issues.jsonl as a regression test."""

    def test_repo_issues_jsonl_is_valid(self) -> None:
        """The repo's own issues.jsonl passes validation."""
        repo_jsonl = (
            Path(__file__).resolve().parent.parent / ".dogcats" / "issues.jsonl"
        )
        if not repo_jsonl.exists():
            pytest.skip("No .dogcats/issues.jsonl in repo root")
        errors = _errors(validate_jsonl(repo_jsonl))
        assert errors == [], f"Validation errors in repo issues.jsonl: {errors}"


# ---------------------------------------------------------------------------
# Concurrent edit detection (post-merge)
# ---------------------------------------------------------------------------


def _install_merge_driver(repo: GitRepo) -> None:
    """Configure the dcat-jsonl merge driver in a git repo."""
    repo.git("config", "merge.dcat-jsonl.driver", MERGE_DRIVER_CMD)
    attrs = repo.path / ".gitattributes"
    attrs.write_text(".dogcats/*.jsonl merge=dcat-jsonl\n")
    repo.commit_all("Add merge driver config")


class TestDetectConcurrentEdits:
    """Test post-merge concurrent edit detection."""

    def test_detects_same_issue_edits(self, git_repo: GitRepo) -> None:
        """Detect when both branches modify the same issue."""
        repo = git_repo
        _install_merge_driver(repo)

        # Seed issue
        s = repo.storage()
        s.create(Issue(id="shared", namespace="test", title="Original"))
        repo.commit_all("Seed")

        # Branch A: change title
        repo.create_branch("branch-a")
        s = repo.storage()
        s.update("test-shared", {"title": "Title from A"})
        repo.commit_all("Update on A")

        # Branch B: change title differently
        repo.switch_branch("main")
        repo.create_branch("branch-b")
        s = repo.storage()
        s.update("test-shared", {"title": "Title from B"})
        repo.commit_all("Update on B")

        # Merge
        repo.switch_branch("main")
        repo.merge("branch-a")
        repo.merge("branch-b")

        # Detect
        warnings = detect_concurrent_edits(
            cwd=repo.path,
            storage_rel=".dogcats/issues.jsonl",
        )
        assert len(warnings) == 1
        assert warnings[0]["issue_id"] == "test-shared"
        assert "title" in warnings[0]["fields"]

    def test_no_warnings_for_different_issues(
        self,
        git_repo: GitRepo,
    ) -> None:
        """No warnings when branches modify different issues."""
        repo = git_repo
        _install_merge_driver(repo)

        # Seed
        s = repo.storage()
        s.create(Issue(id="a", namespace="test", title="Issue A"))
        s.create(Issue(id="b", namespace="test", title="Issue B"))
        repo.commit_all("Seed")

        # Branch A modifies issue A
        repo.create_branch("branch-a")
        s = repo.storage()
        s.update("test-a", {"title": "Updated A"})
        repo.commit_all("Update A")

        # Branch B modifies issue B
        repo.switch_branch("main")
        repo.create_branch("branch-b")
        s = repo.storage()
        s.update("test-b", {"title": "Updated B"})
        repo.commit_all("Update B")

        # Merge
        repo.switch_branch("main")
        repo.merge("branch-a")
        repo.merge("branch-b")

        warnings = detect_concurrent_edits(
            cwd=repo.path,
            storage_rel=".dogcats/issues.jsonl",
        )
        assert len(warnings) == 0

    def test_no_merge_returns_empty(self, git_repo: GitRepo) -> None:
        """No merge commit in history returns empty list."""
        repo = git_repo
        warnings = detect_concurrent_edits(
            cwd=repo.path,
            storage_rel=".dogcats/issues.jsonl",
        )
        assert warnings == []


# ---------------------------------------------------------------------------
# Integration: dcat doctor --post-merge
# ---------------------------------------------------------------------------


class TestDoctorPostMerge:
    """Test that doctor --post-merge detects concurrent edits via CLI."""

    def test_post_merge_no_merge_history(self, dogcats_dir: Path) -> None:
        """Doctor --post-merge with no merge history runs without error."""
        _write_jsonl(dogcats_dir / "issues.jsonl", [_issue()])
        result = runner.invoke(
            app,
            ["doctor", "--post-merge", "--dogcats-dir", str(dogcats_dir)],
        )
        # Should still pass — no merge means no warnings
        assert "Data integrity" in result.stdout

    def test_post_merge_detects_edits(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Doctor --post-merge reports concurrent edits after a merge."""
        repo = git_repo
        monkeypatch.chdir(repo.path)
        _install_merge_driver(repo)

        # Seed issue
        s = repo.storage()
        s.create(Issue(id="shared", namespace="test", title="Original"))
        repo.commit_all("Seed")

        # Branch A: change title
        repo.create_branch("branch-a")
        s = repo.storage()
        s.update("test-shared", {"title": "Title from A"})
        repo.commit_all("Update on A")

        # Branch B: change title differently
        repo.switch_branch("main")
        repo.create_branch("branch-b")
        s = repo.storage()
        s.update("test-shared", {"title": "Title from B"})
        repo.commit_all("Update on B")

        # Merge
        repo.switch_branch("main")
        repo.merge("branch-a")
        repo.merge("branch-b")

        result = runner.invoke(
            app,
            [
                "doctor",
                "--post-merge",
                "--dogcats-dir",
                str(repo.dogcats_dir),
            ],
        )
        assert "Concurrent edits detected" in result.stdout
        assert "test-shared" in result.stdout

    def test_post_merge_json_includes_concurrent_edits(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Doctor --post-merge --json includes concurrent_edits field."""
        repo = git_repo
        monkeypatch.chdir(repo.path)
        _install_merge_driver(repo)

        # Seed issue
        s = repo.storage()
        s.create(Issue(id="shared", namespace="test", title="Original"))
        repo.commit_all("Seed")

        # Branch A
        repo.create_branch("branch-a")
        s = repo.storage()
        s.update("test-shared", {"title": "Title from A"})
        repo.commit_all("Update on A")

        # Branch B
        repo.switch_branch("main")
        repo.create_branch("branch-b")
        s = repo.storage()
        s.update("test-shared", {"title": "Title from B"})
        repo.commit_all("Update on B")

        # Merge
        repo.switch_branch("main")
        repo.merge("branch-a")
        repo.merge("branch-b")

        result = runner.invoke(
            app,
            [
                "doctor",
                "--post-merge",
                "--json",
                "--dogcats-dir",
                str(repo.dogcats_dir),
            ],
        )
        data = json.loads(result.stdout)
        assert "concurrent_edits" in data
        assert len(data["concurrent_edits"]) == 1
        assert data["concurrent_edits"][0]["issue_id"] == "test-shared"
