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
    validate_inbox_jsonl,
    validate_issue_record,
    validate_jsonl,
    validate_proposal_record,
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


def _proposal(
    proposal_id: str = "abc",
    namespace: str = "test",
    **kwargs: Any,
) -> dict[str, Any]:
    """Build a minimal valid proposal record."""
    defaults: dict[str, Any] = {
        "record_type": "proposal",
        "id": proposal_id,
        "namespace": namespace,
        "title": "Test Proposal",
        "status": "open",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
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
        assert validate_issue_record(_issue(), lineno=1) == []

    def test_missing_required_field(self) -> None:
        """Detect missing required fields."""
        record = _issue()
        del record["title"]
        errors = validate_issue_record(record, lineno=1)
        assert len(errors) == 1
        assert "missing required field 'title'" in errors[0]["message"]

    def test_invalid_status(self) -> None:
        """Detect invalid status values."""
        errors = validate_issue_record(_issue(status="bogus"), lineno=1)
        assert len(errors) == 1
        assert "invalid status" in errors[0]["message"]

    def test_invalid_issue_type(self) -> None:
        """Detect invalid issue_type values."""
        errors = validate_issue_record(_issue(issue_type="unicorn"), lineno=1)
        assert len(errors) == 1
        assert "invalid issue_type" in errors[0]["message"]

    def test_legacy_draft_issue_type_accepted(self) -> None:
        """Legacy issue_type='draft' is accepted (migrated on load)."""
        errors = validate_issue_record(_issue(issue_type="draft"), lineno=1)
        assert errors == []

    def test_legacy_subtask_issue_type_accepted(self) -> None:
        """Legacy issue_type='subtask' is accepted (migrated on load)."""
        errors = validate_issue_record(_issue(issue_type="subtask"), lineno=1)
        assert errors == []

    def test_priority_out_of_range(self) -> None:
        """Detect priority values outside 0-4."""
        errors = validate_issue_record(_issue(priority=99), lineno=1)
        assert len(errors) == 1
        assert "invalid priority" in errors[0]["message"]

    def test_invalid_timestamp(self) -> None:
        """Detect invalid ISO 8601 timestamps."""
        errors = validate_issue_record(
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

    def test_unloadable_ref_emits_integrity_warning(
        self,
        git_repo: GitRepo,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When ``git show ref:path`` fails, surface a warning instead of [].

        The previous behaviour was to treat a failed load identically to
        ``no issues at this ref``, which made detect_concurrent_edits
        report a clean merge while real concurrent edits went unflagged.
        (dogcat-9wj2)
        """
        repo = git_repo
        _install_merge_driver(repo)

        # Build a real merge so detect_concurrent_edits gets past the
        # ``no merge_commit`` early-return.
        s = repo.storage()
        s.create(Issue(id="shared", namespace="test", title="Original"))
        repo.commit_all("Seed")
        repo.create_branch("branch-a")
        s = repo.storage()
        s.update("test-shared", {"title": "Title from A"})
        repo.commit_all("Update on A")
        repo.switch_branch("main")
        repo.create_branch("branch-b")
        s = repo.storage()
        s.update("test-shared", {"title": "Title from B"})
        repo.commit_all("Update on B")
        repo.switch_branch("main")
        repo.merge("branch-a")
        repo.merge("branch-b")

        # Force show_file to return None for the base ref so the
        # integrity guard triggers. Patch the symbol on the dogcat.git
        # module since _load_issues_at_ref imports the module locally.
        import dogcat.git as git_helpers

        real_show_file = git_helpers.show_file
        merge_commit = git_helpers.latest_merge_commit(cwd=repo.path)
        assert merge_commit is not None
        parents = git_helpers.merge_parents(merge_commit, cwd=repo.path)
        assert parents is not None
        base = git_helpers.merge_base(parents[0], parents[1], cwd=repo.path)
        assert base is not None
        bad_ref = f"{base}:.dogcats/issues.jsonl"

        def fake_show_file(git_ref: str, **kwargs: Any) -> bytes | None:
            if git_ref == bad_ref:
                return None
            return real_show_file(git_ref, **kwargs)

        monkeypatch.setattr(git_helpers, "show_file", fake_show_file)

        warnings = detect_concurrent_edits(
            cwd=repo.path,
            storage_rel=".dogcats/issues.jsonl",
        )
        assert warnings, "expected an integrity warning when a ref fails to load"
        assert any(w.get("level") == "warning" for w in warnings)
        assert any("could not read" in w.get("message", "") for w in warnings)
        # The failed ref must be reported so the user knows what to investigate.
        all_failed = [entry for w in warnings for entry in w.get("failed_refs", [])]
        assert any(entry["role"] == "base" for entry in all_failed)

    def test_detects_field_level_loss_different_fields(self, git_repo: GitRepo) -> None:
        """Detect when branches edit different fields on the same issue.

        This is the field-level loss case: A edits title, B edits priority,
        B's timestamp is later so B's entire record wins via LWW, losing A's
        title change. The detection should surface both field changes.
        """
        repo = git_repo
        _install_merge_driver(repo)

        # Seed issue
        s = repo.storage()
        s.create(Issue(id="shared", namespace="test", title="Original", priority=2))
        repo.commit_all("Seed")

        # Branch A: change title only
        repo.create_branch("branch-a")
        s = repo.storage()
        s.update("test-shared", {"title": "Title from A"})
        repo.commit_all("Update title on A")

        # Branch B: change priority only (with later timestamp)
        repo.switch_branch("main")
        repo.create_branch("branch-b")
        s = repo.storage()
        s.update("test-shared", {"priority": 3})
        repo.commit_all("Update priority on B")

        # Merge
        repo.switch_branch("main")
        repo.merge("branch-a")
        repo.merge("branch-b")

        # Detect concurrent edits
        warnings = detect_concurrent_edits(
            cwd=repo.path,
            storage_rel=".dogcats/issues.jsonl",
        )

        # Both fields must be surfaced — the whole point of field-level detection
        # is that the user can see what each branch tried to change.
        assert len(warnings) == 1
        assert warnings[0]["issue_id"] == "test-shared"
        fields = warnings[0]["fields"]
        assert "title" in fields, f"title not in detected fields: {fields}"
        assert "priority" in fields, f"priority not in detected fields: {fields}"


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
        """Doctor --post-merge surfaces field names of concurrent edits.

        Stresses the user-facing case from dogcat-46xd: branches edit
        DIFFERENT fields, so LWW silently drops one — doctor's CLI output
        must name both affected fields so the user can recover.
        """
        repo = git_repo
        monkeypatch.chdir(repo.path)
        _install_merge_driver(repo)

        # Seed issue
        s = repo.storage()
        s.create(Issue(id="shared", namespace="test", title="Original", priority=2))
        repo.commit_all("Seed")

        # Branch A: change title only
        repo.create_branch("branch-a")
        s = repo.storage()
        s.update("test-shared", {"title": "Title from A"})
        repo.commit_all("Update title on A")

        # Branch B: change priority only (later timestamp wins entire record)
        repo.switch_branch("main")
        repo.create_branch("branch-b")
        s = repo.storage()
        s.update("test-shared", {"priority": 3})
        repo.commit_all("Update priority on B")

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
        # Both affected field names must appear in the CLI output so the
        # user can see what each branch tried to change before LWW collapsed it.
        assert "title:" in result.stdout, (
            f"'title:' not found in doctor output:\n{result.stdout}"
        )
        assert "priority:" in result.stdout, (
            f"'priority:' not found in doctor output:\n{result.stdout}"
        )

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


# ---------------------------------------------------------------------------
# Unit tests for validate_proposal_record / validate_inbox_jsonl
# ---------------------------------------------------------------------------


class TestValidateProposalRecord:
    """Direct tests for the proposal validator."""

    def test_valid_proposal(self) -> None:
        """A well-formed proposal produces no errors."""
        assert validate_proposal_record(_proposal(), lineno=1) == []

    def test_missing_required_field(self) -> None:
        """Detect missing required fields (id, namespace, title, status)."""
        record = _proposal()
        del record["title"]
        errors = validate_proposal_record(record, lineno=1)
        assert len(errors) == 1
        assert "missing required field 'title'" in errors[0]["message"]

    def test_invalid_status(self) -> None:
        """Detect invalid proposal status values."""
        errors = validate_proposal_record(_proposal(status="bogus"), lineno=1)
        assert len(errors) == 1
        assert "invalid status 'bogus'" in errors[0]["message"]

    def test_tombstone_status_accepted(self) -> None:
        """Proposal status 'tombstone' is a valid value."""
        assert validate_proposal_record(_proposal(status="tombstone"), lineno=1) == []

    def test_invalid_timestamp(self) -> None:
        """Detect invalid ISO 8601 timestamps on proposals."""
        errors = validate_proposal_record(
            _proposal(closed_at="not-a-timestamp"), lineno=1
        )
        assert len(errors) == 1
        assert "invalid timestamp" in errors[0]["message"]

    def test_lineno_appears_in_message(self) -> None:
        """Errors include the line number for diagnostics."""
        errors = validate_proposal_record(_proposal(status="bogus"), lineno=42)
        assert "Line 42" in errors[0]["message"]


class TestValidateInboxJsonl:
    """Tests for the file-level inbox validator."""

    def test_valid_inbox_file(self, tmp_path: Path) -> None:
        """A file of valid proposals returns no errors."""
        path = tmp_path / "inbox.jsonl"
        _write_jsonl(path, [_proposal(proposal_id="a"), _proposal(proposal_id="b")])
        assert validate_inbox_jsonl(path) == []

    def test_invalid_proposal_surfaces_error(self, tmp_path: Path) -> None:
        """An invalid proposal record yields its error in file-level output."""
        path = tmp_path / "inbox.jsonl"
        _write_jsonl(path, [_proposal(status="bogus")])
        errors = validate_inbox_jsonl(path)
        messages = [e["message"] for e in errors]
        assert any("invalid status 'bogus'" in m for m in messages)

    def test_non_proposal_records_ignored(self, tmp_path: Path) -> None:
        """Issue records in inbox.jsonl are ignored (only proposals validated)."""
        path = tmp_path / "inbox.jsonl"
        # An issue record with an invalid status that would fail the issue
        # validator, but inbox validation must skip it entirely.
        _write_jsonl(path, [_issue(status="bogus")])
        assert validate_inbox_jsonl(path) == []
