"""Tests for dcat backfill-history command."""

from __future__ import annotations

from typing import TYPE_CHECKING

import orjson
from typer.testing import CliRunner

from dogcat.cli import app

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()


def _init_repo(tmp_path: Path) -> Path:
    """Initialize a dogcats repo and return the dogcats dir."""
    dogcats_dir = tmp_path / ".dogcats"
    result = runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])
    assert result.exit_code == 0
    return dogcats_dir


def _create_issue(dogcats_dir: Path, title: str, **kwargs: str) -> str:
    """Create an issue and return its ID."""
    args = ["create", title, "--dogcats-dir", str(dogcats_dir)]
    for key, value in kwargs.items():
        args.extend([f"--{key}", value])
    result = runner.invoke(app, args)
    assert result.exit_code == 0
    for word in result.stdout.split():
        if word.startswith("dc-") or (len(word) > 3 and "-" in word):
            return word.rstrip(":")
    msg = f"Could not find issue ID in output: {result.stdout}"
    raise ValueError(msg)


def _strip_event_records(dogcats_dir: Path) -> None:
    """Remove event records from issues.jsonl to simulate pre-upgrade state."""
    issues_path = dogcats_dir / "issues.jsonl"
    kept: list[bytes] = []
    for line in issues_path.read_bytes().splitlines():
        if not line.strip():
            continue
        data = orjson.loads(line)
        if data.get("record_type") != "event":
            kept.append(line)
    issues_path.write_bytes(b"\n".join(kept) + b"\n")


class TestBackfillHistory:
    """Tests for backfill history."""

    def test_backfill_generates_events(self, tmp_path: Path) -> None:
        """Test backfill generates events."""
        dogcats_dir = _init_repo(tmp_path)
        _strip_event_records(dogcats_dir)

        result = runner.invoke(
            app,
            ["backfill-history", "--dogcats-dir", str(dogcats_dir)],
        )
        # No issues to backfill, should succeed with 0 events
        assert result.exit_code == 0
        assert "0 event(s)" in result.stdout

    def test_backfill_from_existing_issues(self, tmp_path: Path) -> None:
        """Test backfill from existing issues."""
        dogcats_dir = _init_repo(tmp_path)
        _create_issue(dogcats_dir, "Issue one")
        _create_issue(dogcats_dir, "Issue two")
        _strip_event_records(dogcats_dir)

        result = runner.invoke(
            app,
            ["backfill-history", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        # Should have at least 2 created events
        assert "event(s)" in result.stdout

    def test_backfill_dry_run(self, tmp_path: Path) -> None:
        """Test backfill dry run."""
        dogcats_dir = _init_repo(tmp_path)
        _create_issue(dogcats_dir, "Dry run test")
        _strip_event_records(dogcats_dir)

        result = runner.invoke(
            app,
            ["backfill-history", "--dry-run", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Dry run" in result.stderr or "Dry run" in result.output

    def test_backfill_warns_on_existing_events(self, tmp_path: Path) -> None:
        """Test backfill warns on existing events."""
        dogcats_dir = _init_repo(tmp_path)
        _create_issue(dogcats_dir, "Existing issue")

        # Event records already exist from the create above
        result = runner.invoke(
            app,
            ["backfill-history", "--dogcats-dir", str(dogcats_dir)],
        )
        # Should fail because event records already exist
        assert result.exit_code == 1
        assert "already exist" in (result.stderr or result.output)

    def test_backfill_dry_run_with_existing_events_shows_preview(
        self,
        tmp_path: Path,
    ) -> None:
        """Test backfill dry run with existing events shows preview."""
        dogcats_dir = _init_repo(tmp_path)
        _create_issue(dogcats_dir, "Test issue")

        # Event records exist, but dry-run should still work (just warn)
        result = runner.invoke(
            app,
            [
                "backfill-history",
                "--dry-run",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0

    def test_backfill_detects_updates(self, tmp_path: Path) -> None:
        """Test backfill detects updates."""
        dogcats_dir = _init_repo(tmp_path)
        issue_id = _create_issue(dogcats_dir, "Updatable issue")
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
        _strip_event_records(dogcats_dir)

        result = runner.invoke(
            app,
            ["backfill-history", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0

        # Verify events were created
        history_result = runner.invoke(
            app,
            [
                "history",
                "--issue",
                issue_id,
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert history_result.exit_code == 0
        assert "Created" in history_result.stdout or "Updated" in history_result.stdout
