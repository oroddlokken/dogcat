"""Tests for chronological ordering in CLI commands.

Verifies that recently-closed, recently-added, rc, history, and diff
all display entries oldest-first (chronological order).
"""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

from conftest import _GIT_TEST_ENV
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
    for word in result.stdout.split():
        if word.startswith("dc-") or (len(word) > 3 and "-" in word):
            return word.rstrip(":")
    msg = f"Could not find issue ID in output: {result.stdout}"
    raise ValueError(msg)


def _init_git_workspace(tmp_path: Path) -> Path:
    """Create a temporary git repo with initialized .dogcats."""
    subprocess.run(
        ["git", "init", str(tmp_path)],
        check=True,
        capture_output=True,
        env=_GIT_TEST_ENV,
    )

    dogcats_dir = tmp_path / ".dogcats"
    result = runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])
    assert result.exit_code == 0

    subprocess.run(
        ["git", "-C", str(tmp_path), "add", ".dogcats/"],
        check=True,
        capture_output=True,
        env=_GIT_TEST_ENV,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-m", "init"],
        check=True,
        capture_output=True,
        env=_GIT_TEST_ENV,
    )

    return tmp_path


class TestHistoryOrder:
    """History command displays events oldest-first (chronological)."""

    def test_history_oldest_first(self, tmp_path: Path) -> None:
        """Events appear in chronological order (oldest at top)."""
        dogcats_dir = _init_repo(tmp_path)
        _create_issue(dogcats_dir, "First issue")

        _create_issue(dogcats_dir, "Second issue")

        _create_issue(dogcats_dir, "Third issue")

        result = runner.invoke(app, ["history", "--dogcats-dir", str(dogcats_dir)])
        assert result.exit_code == 0
        stdout = result.stdout
        pos_first = stdout.index("First issue")
        pos_second = stdout.index("Second issue")
        pos_third = stdout.index("Third issue")
        assert pos_first < pos_second < pos_third

    def test_history_json_oldest_first(self, tmp_path: Path) -> None:
        """JSON output is also oldest-first."""
        dogcats_dir = _init_repo(tmp_path)
        _create_issue(dogcats_dir, "First issue")

        _create_issue(dogcats_dir, "Second issue")

        result = runner.invoke(
            app,
            ["history", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data[0]["title"] == "First issue"
        assert data[1]["title"] == "Second issue"


class TestRecentlyClosedOrder:
    """Recently-closed command displays events oldest-first."""

    def test_recently_closed_oldest_first(self, tmp_path: Path) -> None:
        """Closed issues appear in chronological order (oldest at top)."""
        dogcats_dir = _init_repo(tmp_path)
        id1 = _create_issue(dogcats_dir, "Closed first")
        runner.invoke(app, ["close", id1, "--dogcats-dir", str(dogcats_dir)])

        id2 = _create_issue(dogcats_dir, "Closed second")
        runner.invoke(app, ["close", id2, "--dogcats-dir", str(dogcats_dir)])

        id3 = _create_issue(dogcats_dir, "Closed third")
        runner.invoke(app, ["close", id3, "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            ["recently-closed", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        stdout = result.stdout
        pos_first = stdout.index("Closed first")
        pos_second = stdout.index("Closed second")
        pos_third = stdout.index("Closed third")
        assert pos_first < pos_second < pos_third


class TestRecentlyAddedOrder:
    """Recently-added command displays issues oldest-first."""

    def test_recently_added_oldest_first(self, tmp_path: Path) -> None:
        """Issues appear in chronological order (oldest at top)."""
        dogcats_dir = _init_repo(tmp_path)
        _create_issue(dogcats_dir, "Added first")

        _create_issue(dogcats_dir, "Added second")

        _create_issue(dogcats_dir, "Added third")

        result = runner.invoke(
            app,
            ["recently-added", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        stdout = result.stdout
        pos_first = stdout.index("Added first")
        pos_second = stdout.index("Added second")
        pos_third = stdout.index("Added third")
        assert pos_first < pos_second < pos_third


class TestDiffOrder:
    """Diff command displays events oldest-first."""

    def test_diff_oldest_first(self, tmp_path: Path) -> None:
        """New issues in diff appear in chronological order (oldest at top)."""
        git_workspace = _init_git_workspace(tmp_path)
        dogcats_dir = git_workspace / ".dogcats"

        _create_issue(dogcats_dir, "Diff first")

        _create_issue(dogcats_dir, "Diff second")

        _create_issue(dogcats_dir, "Diff third")

        result = runner.invoke(
            app,
            ["diff", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        stdout = result.stdout
        pos_first = stdout.index("Diff first")
        pos_second = stdout.index("Diff second")
        pos_third = stdout.index("Diff third")
        assert pos_first < pos_second < pos_third

    def test_diff_json_oldest_first(self, tmp_path: Path) -> None:
        """JSON diff output is also oldest-first."""
        git_workspace = _init_git_workspace(tmp_path)
        dogcats_dir = git_workspace / ".dogcats"

        _create_issue(dogcats_dir, "JSON diff first")

        _create_issue(dogcats_dir, "JSON diff second")

        result = runner.invoke(
            app,
            ["diff", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        titles = [e["title"] for e in data]
        assert titles.index("JSON diff first") < titles.index("JSON diff second")
