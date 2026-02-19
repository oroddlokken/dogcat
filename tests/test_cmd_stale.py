"""Tests for the stale command."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from dogcat.cli import app
from dogcat.cli._cmd_stale import _format_age, _parse_duration_arg

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()


class TestParseDurationArg:
    """Test duration argument parsing."""

    def test_days_only(self) -> None:
        """Parse days-only duration."""
        assert _parse_duration_arg("7d") == timedelta(days=7)

    def test_hours_only(self) -> None:
        """Parse hours-only duration."""
        assert _parse_duration_arg("3h") == timedelta(hours=3)

    def test_days_and_hours(self) -> None:
        """Parse combined days and hours duration."""
        assert _parse_duration_arg("1d12h") == timedelta(days=1, hours=12)

    def test_invalid_format(self) -> None:
        """Reject invalid duration format."""
        import pytest

        with pytest.raises(ValueError, match="Invalid duration"):
            _parse_duration_arg("abc")

    def test_empty_string(self) -> None:
        """Reject empty string."""
        import pytest

        with pytest.raises(ValueError, match="Invalid duration"):
            _parse_duration_arg("")


class TestFormatAge:
    """Test age formatting."""

    def test_hours(self) -> None:
        """Format age in hours."""
        now = datetime.now(timezone.utc)
        updated = now - timedelta(hours=5)
        assert _format_age(now, updated) == "5h ago"

    def test_one_day(self) -> None:
        """Format age as singular day."""
        now = datetime.now(timezone.utc)
        updated = now - timedelta(days=1, hours=1)
        assert _format_age(now, updated) == "1 day ago"

    def test_multiple_days(self) -> None:
        """Format age as plural days."""
        now = datetime.now(timezone.utc)
        updated = now - timedelta(days=10)
        assert _format_age(now, updated) == "10 days ago"


class TestStaleCommand:
    """Test the stale CLI command."""

    def test_stale_no_issues(self, tmp_path: Path) -> None:
        """Test stale with no issues."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(app, ["stale", "--dogcats-dir", str(dogcats_dir)])
        assert result.exit_code == 0
        assert "No stale issues" in result.stdout

    def test_stale_no_stale_issues(self, tmp_path: Path) -> None:
        """Test stale when all issues are recent."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])
        runner.invoke(
            app,
            ["create", "Fresh issue", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(app, ["stale", "--dogcats-dir", str(dogcats_dir)])
        assert result.exit_code == 0
        assert "No stale issues" in result.stdout

    def test_stale_finds_old_issues(self, tmp_path: Path) -> None:
        """Test that stale finds issues with old updated_at."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        # Create an issue
        create_result = runner.invoke(
            app,
            [
                "create",
                "Old issue",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        data = json.loads(create_result.stdout)
        issue_id = f"{data['namespace']}-{data['id']}"

        # Manually backdate the updated_at in the JSONL file
        _backdate_issue(dogcats_dir, issue_id, days=10)

        result = runner.invoke(app, ["stale", "--dogcats-dir", str(dogcats_dir)])
        assert result.exit_code == 0
        assert "Stale (1):" in result.stdout
        assert "Old issue" in result.stdout

    def test_stale_excludes_closed(self, tmp_path: Path) -> None:
        """Test that stale excludes closed issues."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        create_result = runner.invoke(
            app,
            [
                "create",
                "Closed issue",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        data = json.loads(create_result.stdout)
        issue_id = f"{data['namespace']}-{data['id']}"

        # Close the issue then backdate it
        runner.invoke(
            app,
            ["close", issue_id, "--dogcats-dir", str(dogcats_dir)],
        )
        _backdate_issue(dogcats_dir, issue_id, days=10)

        result = runner.invoke(app, ["stale", "--dogcats-dir", str(dogcats_dir)])
        assert result.exit_code == 0
        assert "No stale issues" in result.stdout

    def test_stale_with_days_option(self, tmp_path: Path) -> None:
        """Test stale with --days option."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        create_result = runner.invoke(
            app,
            [
                "create",
                "Old issue",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        data = json.loads(create_result.stdout)
        issue_id = f"{data['namespace']}-{data['id']}"
        _backdate_issue(dogcats_dir, issue_id, days=5)

        # 3 days should find it
        result = runner.invoke(
            app,
            ["stale", "--days", "3", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Old issue" in result.stdout

        # 10 days should not find it
        result = runner.invoke(
            app,
            ["stale", "--days", "10", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No stale issues" in result.stdout

    def test_stale_with_hours_option(self, tmp_path: Path) -> None:
        """Test stale with --hours option."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        create_result = runner.invoke(
            app,
            [
                "create",
                "Recent issue",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        data = json.loads(create_result.stdout)
        issue_id = f"{data['namespace']}-{data['id']}"
        _backdate_issue(dogcats_dir, issue_id, hours=5)

        # 3 hours should find it
        result = runner.invoke(
            app,
            ["stale", "--hours", "3", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Recent issue" in result.stdout

    def test_stale_with_duration_shorthand(self, tmp_path: Path) -> None:
        """Test stale with positional duration shorthand."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        create_result = runner.invoke(
            app,
            [
                "create",
                "Old issue",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        data = json.loads(create_result.stdout)
        issue_id = f"{data['namespace']}-{data['id']}"
        _backdate_issue(dogcats_dir, issue_id, days=5)

        result = runner.invoke(
            app,
            ["stale", "3d", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Old issue" in result.stdout

    def test_stale_duration_and_option_conflict(self, tmp_path: Path) -> None:
        """Test that positional duration + --days/--hours is an error."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            [
                "stale",
                "7d",
                "--days",
                "3",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 1

    def test_stale_json_output(self, tmp_path: Path) -> None:
        """Test stale with --json flag."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        create_result = runner.invoke(
            app,
            [
                "create",
                "Old issue",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        data = json.loads(create_result.stdout)
        issue_id = f"{data['namespace']}-{data['id']}"
        _backdate_issue(dogcats_dir, issue_id, days=10)

        result = runner.invoke(
            app,
            ["stale", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert len(output) == 1
        assert output[0]["title"] == "Old issue"

    def test_stale_with_type_filter(self, tmp_path: Path) -> None:
        """Test stale with --type filter."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        # Create a bug and a task
        create_bug = runner.invoke(
            app,
            [
                "create",
                "Old bug",
                "--type",
                "bug",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        bug_data = json.loads(create_bug.stdout)
        bug_id = f"{bug_data['namespace']}-{bug_data['id']}"

        create_task = runner.invoke(
            app,
            [
                "create",
                "Old task",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        task_data = json.loads(create_task.stdout)
        task_id = f"{task_data['namespace']}-{task_data['id']}"

        _backdate_issue(dogcats_dir, bug_id, days=10)
        _backdate_issue(dogcats_dir, task_id, days=10)

        result = runner.invoke(
            app,
            [
                "stale",
                "--type",
                "bug",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Old bug" in result.stdout
        assert "Old task" not in result.stdout

    def test_stale_limit(self, tmp_path: Path) -> None:
        """Test stale with --limit."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        for i in range(3):
            create_result = runner.invoke(
                app,
                [
                    "create",
                    f"Old issue {i}",
                    "--json",
                    "--dogcats-dir",
                    str(dogcats_dir),
                ],
            )
            data = json.loads(create_result.stdout)
            issue_id = f"{data['namespace']}-{data['id']}"
            _backdate_issue(dogcats_dir, issue_id, days=10)

        result = runner.invoke(
            app,
            [
                "stale",
                "--limit",
                "2",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert len(output) == 2

    def test_stale_combined_days_and_hours(self, tmp_path: Path) -> None:
        """Test stale with both --days and --hours combined."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        create_result = runner.invoke(
            app,
            [
                "create",
                "Medium old issue",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        data = json.loads(create_result.stdout)
        issue_id = f"{data['namespace']}-{data['id']}"
        # Backdate by 36 hours (1 day 12 hours)
        _backdate_issue(dogcats_dir, issue_id, hours=36)

        # --days 1 --hours 0 = 24h, should find it (36h > 24h)
        result = runner.invoke(
            app,
            [
                "stale",
                "--days",
                "1",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Medium old issue" in result.stdout

        # --days 2 = 48h, should NOT find it (36h < 48h)
        result = runner.invoke(
            app,
            [
                "stale",
                "--days",
                "2",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "No stale issues" in result.stdout

    def test_stale_shows_age(self, tmp_path: Path) -> None:
        """Test that stale output includes age info."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        create_result = runner.invoke(
            app,
            [
                "create",
                "Old issue",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        data = json.loads(create_result.stdout)
        issue_id = f"{data['namespace']}-{data['id']}"
        _backdate_issue(dogcats_dir, issue_id, days=10)

        result = runner.invoke(app, ["stale", "--dogcats-dir", str(dogcats_dir)])
        assert result.exit_code == 0
        assert "days ago" in result.stdout


def _backdate_issue(
    dogcats_dir: Path,
    issue_id: str,
    *,
    days: int = 0,
    hours: int = 0,
) -> None:
    """Backdate an issue's updated_at by rewriting the JSONL file."""
    import orjson

    jsonl_path = dogcats_dir / "issues.jsonl"
    lines = jsonl_path.read_bytes().splitlines()
    new_lines: list[bytes] = []
    old_time = (
        datetime.now(timezone.utc) - timedelta(days=days, hours=hours)
    ).isoformat()

    for line in lines:
        if not line.strip():
            new_lines.append(line)
            continue
        record = orjson.loads(line)
        record_type = record.get("record_type", "issue")
        if record_type == "issue":
            full_id = f"{record.get('namespace', 'dc')}-{record['id']}"
            if full_id == issue_id:
                record["updated_at"] = old_time
        new_lines.append(orjson.dumps(record))

    jsonl_path.write_bytes(b"\n".join(new_lines) + b"\n")
