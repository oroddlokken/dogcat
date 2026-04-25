"""Tests for the dcat repair-jsonl CLI command."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import orjson
from typer.testing import CliRunner

from dogcat.cli import app
from dogcat.models import Issue, issue_to_dict

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()


def _init(tmp_path: Path) -> Path:
    """Initialize a .dogcats directory and return its path."""
    dogcats_dir = tmp_path / ".dogcats"
    runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])
    return dogcats_dir


def _valid_issue_line(issue_id: str = "ok", title: str = "OK") -> str:
    """Return a serialized JSONL line for a valid issue."""
    return orjson.dumps(issue_to_dict(Issue(id=issue_id, title=title))).decode()


class TestRepairJsonl:
    """Tests for the repair-jsonl admin command."""

    def test_no_bad_lines_reports_clean(self, tmp_path: Path) -> None:
        """Reports a clean status when no malformed lines exist."""
        dogcats_dir = _init(tmp_path)
        result = runner.invoke(app, ["repair-jsonl", "--dogcats-dir", str(dogcats_dir)])
        assert result.exit_code == 0, result.stdout
        assert "No malformed JSONL lines found" in result.stdout

    def test_dry_run_reports_without_modifying(self, tmp_path: Path) -> None:
        """Dry-run lists bad lines but does not modify any file."""
        dogcats_dir = _init(tmp_path)
        issues_path = dogcats_dir / "issues.jsonl"
        valid = _valid_issue_line()
        issues_path.write_text(f"{valid}\nGARBAGE\n{valid}\n")

        result = runner.invoke(
            app,
            ["repair-jsonl", "--dry-run", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0, result.stdout
        assert "Would move" in result.stdout
        assert "line 2" in result.stdout
        assert not (issues_path.with_suffix(issues_path.suffix + ".bad")).exists()
        assert "GARBAGE" in issues_path.read_text()

    def test_repair_writes_sidecar_and_compacts(self, tmp_path: Path) -> None:
        """Repair moves bad lines to a sidecar and compacts the source file."""
        dogcats_dir = _init(tmp_path)
        issues_path = dogcats_dir / "issues.jsonl"
        valid_a = _valid_issue_line("aaa", "A")
        valid_b = _valid_issue_line("bbb", "B")
        issues_path.write_text(f"{valid_a}\nGARBAGE\n{valid_b}\n")

        result = runner.invoke(app, ["repair-jsonl", "--dogcats-dir", str(dogcats_dir)])
        assert result.exit_code == 0, result.stdout
        sidecar = issues_path.with_suffix(issues_path.suffix + ".bad")
        assert sidecar.exists()
        assert "GARBAGE" in sidecar.read_text()
        compacted = issues_path.read_text().splitlines()
        assert len(compacted) == 2
        assert "GARBAGE" not in issues_path.read_text()

    def test_repair_inbox_jsonl(self, tmp_path: Path) -> None:
        """Repair also moves bad lines out of inbox.jsonl."""
        dogcats_dir = _init(tmp_path)
        inbox_path = dogcats_dir / "inbox.jsonl"
        good = (
            '{"record_type": "proposal", "id": "aaaa", "namespace": "test", '
            '"title": "ok", "created_at": "2026-04-25T12:00:00+00:00", '
            '"updated_at": "2026-04-25T12:00:00+00:00", "status": "open"}'
        )
        inbox_path.write_text(f"{good}\nnot json\n{good}\n")

        result = runner.invoke(app, ["repair-jsonl", "--dogcats-dir", str(dogcats_dir)])
        assert result.exit_code == 0, result.stdout
        sidecar = inbox_path.with_suffix(inbox_path.suffix + ".bad")
        assert sidecar.exists()
        assert "not json" in sidecar.read_text()

    def test_json_output(self, tmp_path: Path) -> None:
        """Repair emits a JSON summary with --json."""
        dogcats_dir = _init(tmp_path)
        issues_path = dogcats_dir / "issues.jsonl"
        valid = _valid_issue_line()
        issues_path.write_text(f"{valid}\nGARBAGE\n")

        result = runner.invoke(
            app,
            [
                "repair-jsonl",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0, result.stdout
        data = json.loads(result.stdout)
        assert data["issues"]["bad_lines"] == 1
        assert data["issues"]["lineno"] == [2]
        assert data["issues"]["sidecar"] is not None

    def test_doctor_surfaces_bad_line_count(self, tmp_path: Path) -> None:
        """Doctor's issues_jsonl check fails and recommends repair-jsonl."""
        dogcats_dir = _init(tmp_path)
        issues_path = dogcats_dir / "issues.jsonl"
        valid = _valid_issue_line()
        issues_path.write_text(f"{valid}\nGARBAGE\n{valid}\n")

        result = runner.invoke(
            app, ["doctor", "--json", "--dogcats-dir", str(dogcats_dir)]
        )
        assert result.exit_code != 0, result.stdout
        data = json.loads(result.stdout)
        issues_check = data["checks"]["issues_jsonl"]
        assert issues_check["passed"] is False
        assert "repair-jsonl" in issues_check["fix"]
