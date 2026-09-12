"""Tests for ``--since`` on recently-closed and recently-added."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from dogcat.cli import app
from dogcat.event_log import EventLog, EventRecord
from dogcat.idgen import IDGenerator
from dogcat.models import Issue
from dogcat.storage import JSONLStorage

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()


@pytest.fixture
def dogcats_dir(tmp_path: Path) -> Path:
    path = tmp_path / ".dogcats"
    result = runner.invoke(app, ["init", "--dogcats-dir", str(path)])
    assert result.exit_code == 0
    return path


def _create_at(dogcats_dir: Path, title: str, when: datetime) -> str:
    storage = JSONLStorage(str(dogcats_dir / "issues.jsonl"))
    idgen = IDGenerator(existing_ids=storage.get_issue_ids(), namespace="dc")
    issue = Issue(
        id=idgen.generate_issue_id(title, timestamp=when, namespace="dc"),
        title=title,
        namespace="dc",
        created_at=when,
        updated_at=when,
    )
    return storage.create(issue).full_id


def _close_at(dogcats_dir: Path, issue_id: str, title: str, when: datetime) -> None:
    EventLog(dogcats_dir).append(
        EventRecord(
            event_type="closed",
            issue_id=issue_id,
            timestamp=when.isoformat(),
            title=title,
            changes={"status": {"old": "open", "new": "closed"}},
        )
    )


def _day(days_ago: int, hour: int = 12) -> datetime:
    base = datetime.now().astimezone() - timedelta(days=days_ago)
    return base.replace(hour=hour, minute=0, second=0, microsecond=0)


def _date(days_ago: int) -> str:
    return _day(days_ago).strftime("%Y-%m-%d")


class TestRecentlyAddedSince:
    """--since on recently-added filters created_at."""

    def test_date_is_inclusive(self, dogcats_dir: Path) -> None:
        """An issue created at 00:00 on the --since day is included."""
        _create_at(dogcats_dir, "Day before", _day(3, hour=23))
        _create_at(dogcats_dir, "At midnight", _day(2, hour=0))
        _create_at(dogcats_dir, "Day after", _day(1))

        result = runner.invoke(
            app,
            ["recently-added", "--since", _date(2), "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Day before" not in result.stdout
        assert "At midnight" in result.stdout
        assert "Day after" in result.stdout
        assert "Recently Added (2)" in result.stdout

    def test_since_lifts_default_limit(self, dogcats_dir: Path) -> None:
        """Without --since the view caps at 10; with it every match shows."""
        for n in range(12):
            _create_at(dogcats_dir, f"Issue {n}", _day(1) + timedelta(minutes=n))

        capped = runner.invoke(
            app, ["recently-added", "--json", "--dogcats-dir", str(dogcats_dir)]
        )
        assert len(json.loads(capped.stdout)) == 10

        result = runner.invoke(
            app,
            [
                "recently-added",
                "--since",
                _date(1),
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert len(json.loads(result.stdout)) == 12

    def test_explicit_limit_still_applies(self, dogcats_dir: Path) -> None:
        """A positional count caps the --since result."""
        for n in range(5):
            _create_at(dogcats_dir, f"Issue {n}", _day(1) + timedelta(minutes=n))

        result = runner.invoke(
            app,
            [
                "recently-added",
                "2",
                "--since",
                _date(1),
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert len(json.loads(result.stdout)) == 2

    def test_bad_date_rejected(self, dogcats_dir: Path) -> None:
        """A non-date value exits non-zero and names the format."""
        result = runner.invoke(
            app,
            [
                "recently-added",
                "--since",
                "yesterday",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code != 0
        assert "YYYY-MM-DD" in result.output


class TestRecentlyClosedSince:
    """--since on recently-closed filters the close event timestamp."""

    def test_filters_on_close_time_inclusive(self, dogcats_dir: Path) -> None:
        """The close event's timestamp decides, not created_at."""
        old = _create_at(dogcats_dir, "Closed long ago", _day(10))
        _close_at(dogcats_dir, old, "Closed long ago", _day(5, hour=23))
        edge = _create_at(dogcats_dir, "Closed at midnight", _day(10))
        _close_at(dogcats_dir, edge, "Closed at midnight", _day(4, hour=0))
        fresh = _create_at(dogcats_dir, "Closed yesterday", _day(10))
        _close_at(dogcats_dir, fresh, "Closed yesterday", _day(1))

        result = runner.invoke(
            app,
            ["recently-closed", "--since", _date(4), "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Closed long ago" not in result.stdout
        assert "Closed at midnight" in result.stdout
        assert "Closed yesterday" in result.stdout
        assert "Recently Closed (2)" in result.stdout

    def test_since_lifts_default_limit(self, dogcats_dir: Path) -> None:
        """Without --since the view caps at 10; with it every match shows."""
        for n in range(12):
            issue_id = _create_at(dogcats_dir, f"Issue {n}", _day(2))
            _close_at(
                dogcats_dir, issue_id, f"Issue {n}", _day(1) + timedelta(minutes=n)
            )

        capped = runner.invoke(
            app, ["recently-closed", "--json", "--dogcats-dir", str(dogcats_dir)]
        )
        assert len(json.loads(capped.stdout)) == 10

        result = runner.invoke(
            app,
            [
                "recently-closed",
                "--since",
                _date(1),
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert len(json.loads(result.stdout)) == 12

    def test_no_match_message(self, dogcats_dir: Path) -> None:
        """An empty range prints the same message as an empty store."""
        issue_id = _create_at(dogcats_dir, "Old", _day(10))
        _close_at(dogcats_dir, issue_id, "Old", _day(9))

        result = runner.invoke(
            app,
            ["recently-closed", "--since", _date(1), "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No recently closed issues" in result.stdout
