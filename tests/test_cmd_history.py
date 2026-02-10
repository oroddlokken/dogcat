"""Tests for dcat history CLI command."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

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
    """Create an issue and return its full ID."""
    args = ["create", title, "--dogcats-dir", str(dogcats_dir)]
    for key, value in kwargs.items():
        args.extend([f"--{key}", value])
    result = runner.invoke(app, args)
    assert result.exit_code == 0
    # Extract issue ID from output (e.g., "✓ Created dc-xxxx: Title")
    for word in result.stdout.split():
        if word.startswith("dc-") or (len(word) > 3 and "-" in word):
            return word.rstrip(":")
    msg = f"Could not find issue ID in output: {result.stdout}"
    raise ValueError(msg)


class TestHistory:
    """Tests for history."""

    def test_history_no_events(self, tmp_path: Path) -> None:
        """Test history no events."""
        dogcats_dir = _init_repo(tmp_path)
        result = runner.invoke(app, ["history", "--dogcats-dir", str(dogcats_dir)])
        assert result.exit_code == 0
        assert "No history found" in result.stdout

    def test_history_shows_created_event(self, tmp_path: Path) -> None:
        """Test history shows created event."""
        dogcats_dir = _init_repo(tmp_path)
        _create_issue(dogcats_dir, "Test bug")
        result = runner.invoke(app, ["history", "--dogcats-dir", str(dogcats_dir)])
        assert result.exit_code == 0
        assert "Created" in result.stdout
        assert "Test bug" in result.stdout

    def test_history_shows_update_event(self, tmp_path: Path) -> None:
        """Test history shows update event."""
        dogcats_dir = _init_repo(tmp_path)
        issue_id = _create_issue(dogcats_dir, "Test issue")
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
        result = runner.invoke(app, ["history", "--dogcats-dir", str(dogcats_dir)])
        assert result.exit_code == 0
        assert "Updated" in result.stdout
        assert "status" in result.stdout

    def test_history_filter_by_issue(self, tmp_path: Path) -> None:
        """Test history filter by issue."""
        dogcats_dir = _init_repo(tmp_path)
        id1 = _create_issue(dogcats_dir, "Issue one")
        _create_issue(dogcats_dir, "Issue two")

        result = runner.invoke(
            app,
            ["history", "--issue", id1, "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert id1 in result.stdout
        # Should not contain events for issue two
        assert "Issue two" not in result.stdout

    def test_history_limit(self, tmp_path: Path) -> None:
        """Test history limit."""
        dogcats_dir = _init_repo(tmp_path)
        # Create multiple events
        for i in range(5):
            _create_issue(dogcats_dir, f"Issue {i}")

        result = runner.invoke(
            app,
            ["history", "--limit", "2", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        # Should only show 2 events (count issue lines starting with +)
        assert result.stdout.count("Issue") == 2

    def test_history_json_output(self, tmp_path: Path) -> None:
        """Test history json output."""
        dogcats_dir = _init_repo(tmp_path)
        _create_issue(dogcats_dir, "JSON test")

        result = runner.invoke(
            app,
            ["history", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["event_type"] == "created"

    def test_history_close_event(self, tmp_path: Path) -> None:
        """Test history close event."""
        dogcats_dir = _init_repo(tmp_path)
        issue_id = _create_issue(dogcats_dir, "To close")
        runner.invoke(
            app,
            ["close", issue_id, "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(app, ["history", "--dogcats-dir", str(dogcats_dir)])
        assert result.exit_code == 0
        assert "Closed" in result.stdout


class TestHistoryAlias:
    """Tests for history alias."""

    def test_h_alias_works(self, tmp_path: Path) -> None:
        """Test h alias works."""
        dogcats_dir = _init_repo(tmp_path)
        _create_issue(dogcats_dir, "Alias test")

        result = runner.invoke(app, ["h", "--dogcats-dir", str(dogcats_dir)])
        assert result.exit_code == 0
        assert "Created" in result.stdout

    def test_h_alias_with_options(self, tmp_path: Path) -> None:
        """Test h alias with options."""
        dogcats_dir = _init_repo(tmp_path)
        _create_issue(dogcats_dir, "Alias options")

        result = runner.invoke(
            app,
            ["h", "--limit", "1", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert result.stdout.count("Created") == 1
