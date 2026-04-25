"""Tests for snooze/unsnooze/snoozed CLI commands."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from typer.testing import CliRunner

from dogcat.cli import app

runner = CliRunner()


def _init_and_create(tmp_path: Path, title: str = "Test issue") -> tuple[str, str]:
    """Initialize dogcats and create an issue, return (dogcats_dir, issue_id)."""
    dogcats_dir = str(tmp_path / ".dogcats")
    runner.invoke(app, ["init", "--dogcats-dir", dogcats_dir])
    result = runner.invoke(app, ["create", title, "--dogcats-dir", dogcats_dir])
    issue_id = result.stdout.split(": ")[0].split()[-1]
    return dogcats_dir, issue_id


class TestSnooze:
    """Test snooze command."""

    def test_snooze_with_days(self, tmp_path: Path) -> None:
        """Test snoozing an issue for N days."""
        dogcats_dir, issue_id = _init_and_create(tmp_path)
        result = runner.invoke(
            app, ["snooze", issue_id, "7d", "--dogcats-dir", dogcats_dir]
        )
        assert result.exit_code == 0
        assert "Snoozed" in result.stdout
        assert issue_id in result.stdout

    def test_snooze_with_weeks(self, tmp_path: Path) -> None:
        """Test snoozing an issue for N weeks."""
        dogcats_dir, issue_id = _init_and_create(tmp_path)
        result = runner.invoke(
            app, ["snooze", issue_id, "2w", "--dogcats-dir", dogcats_dir]
        )
        assert result.exit_code == 0
        assert "Snoozed" in result.stdout

    def test_snooze_with_months(self, tmp_path: Path) -> None:
        """Test snoozing an issue for N months."""
        dogcats_dir, issue_id = _init_and_create(tmp_path)
        result = runner.invoke(
            app, ["snooze", issue_id, "1m", "--dogcats-dir", dogcats_dir]
        )
        assert result.exit_code == 0
        assert "Snoozed" in result.stdout

    def test_snooze_with_iso_date(self, tmp_path: Path) -> None:
        """Test snoozing an issue until an ISO date."""
        dogcats_dir, issue_id = _init_and_create(tmp_path)
        future = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")
        result = runner.invoke(
            app, ["snooze", issue_id, future, "--dogcats-dir", dogcats_dir]
        )
        assert result.exit_code == 0
        assert "Snoozed" in result.stdout

    def test_snooze_invalid_duration(self, tmp_path: Path) -> None:
        """Test snooze with invalid duration string."""
        dogcats_dir, issue_id = _init_and_create(tmp_path)
        result = runner.invoke(
            app, ["snooze", issue_id, "xyz", "--dogcats-dir", dogcats_dir]
        )
        assert result.exit_code != 0
        output = result.stdout + (result.stderr or "")
        assert "Invalid duration" in output

    def test_snooze_preserves_status(self, tmp_path: Path) -> None:
        """Test that snoozing does not change the issue's status."""
        dogcats_dir, issue_id = _init_and_create(tmp_path)
        runner.invoke(
            app,
            [
                "update",
                issue_id,
                "--status",
                "in_progress",
                "--dogcats-dir",
                dogcats_dir,
            ],
        )
        runner.invoke(app, ["snooze", issue_id, "7d", "--dogcats-dir", dogcats_dir])
        result = runner.invoke(
            app, ["show", issue_id, "--json", "--dogcats-dir", dogcats_dir]
        )
        import json

        data = json.loads(result.stdout)
        assert data["status"] == "in_progress"
        assert data["snoozed_until"] is not None

    def test_snooze_json_output(self, tmp_path: Path) -> None:
        """Test snooze with --json output."""
        dogcats_dir, issue_id = _init_and_create(tmp_path)
        result = runner.invoke(
            app, ["snooze", issue_id, "7d", "--json", "--dogcats-dir", dogcats_dir]
        )
        assert result.exit_code == 0
        import json

        data = json.loads(result.stdout)
        assert data["snoozed_until"] is not None


class TestUnsnooze:
    """Test unsnooze command."""

    def test_unsnooze(self, tmp_path: Path) -> None:
        """Test unsnoozing an issue."""
        dogcats_dir, issue_id = _init_and_create(tmp_path)
        runner.invoke(app, ["snooze", issue_id, "7d", "--dogcats-dir", dogcats_dir])
        result = runner.invoke(
            app, ["unsnooze", issue_id, "--dogcats-dir", dogcats_dir]
        )
        assert result.exit_code == 0
        assert "Unsnoozed" in result.stdout

    def test_unsnooze_not_snoozed(self, tmp_path: Path) -> None:
        """Test unsnoozing an issue that is not snoozed."""
        dogcats_dir, issue_id = _init_and_create(tmp_path)
        result = runner.invoke(
            app, ["unsnooze", issue_id, "--dogcats-dir", dogcats_dir]
        )
        assert result.exit_code != 0
        output = result.stdout + (result.stderr or "")
        assert "not snoozed" in output

    def test_unsnooze_clears_snoozed_until(self, tmp_path: Path) -> None:
        """Test that unsnoozed clears the snoozed_until field."""
        dogcats_dir, issue_id = _init_and_create(tmp_path)
        runner.invoke(app, ["snooze", issue_id, "7d", "--dogcats-dir", dogcats_dir])
        runner.invoke(app, ["unsnooze", issue_id, "--dogcats-dir", dogcats_dir])
        result = runner.invoke(
            app, ["show", issue_id, "--json", "--dogcats-dir", dogcats_dir]
        )
        import json

        data = json.loads(result.stdout)
        assert data["snoozed_until"] is None


class TestSnoozedList:
    """Test snoozed command (listing snoozed issues)."""

    def test_snoozed_empty(self, tmp_path: Path) -> None:
        """Test snoozed list when nothing is snoozed."""
        dogcats_dir = str(tmp_path / ".dogcats")
        runner.invoke(app, ["init", "--dogcats-dir", dogcats_dir])
        result = runner.invoke(app, ["snoozed", "--dogcats-dir", dogcats_dir])
        assert result.exit_code == 0
        assert "No snoozed issues" in result.stdout

    def test_snoozed_shows_snoozed_issues(self, tmp_path: Path) -> None:
        """Test that snoozed list shows snoozed issues."""
        dogcats_dir, issue_id = _init_and_create(tmp_path)
        runner.invoke(app, ["snooze", issue_id, "7d", "--dogcats-dir", dogcats_dir])
        result = runner.invoke(app, ["snoozed", "--dogcats-dir", dogcats_dir])
        assert result.exit_code == 0
        assert "Snoozed (1)" in result.stdout
        assert "Test issue" in result.stdout

    def test_snoozed_json_output(self, tmp_path: Path) -> None:
        """Test snoozed list with --json."""
        dogcats_dir, issue_id = _init_and_create(tmp_path)
        runner.invoke(app, ["snooze", issue_id, "7d", "--dogcats-dir", dogcats_dir])
        result = runner.invoke(app, ["snoozed", "--json", "--dogcats-dir", dogcats_dir])
        assert result.exit_code == 0
        import json

        data = json.loads(result.stdout)
        assert len(data) == 1
        assert data[0]["snoozed_until"] is not None


class TestSnoozeFiltering:
    """Test that snoozed issues are filtered from list and ready."""

    def test_snoozed_hidden_from_list(self, tmp_path: Path) -> None:
        """Test that snoozed issues are hidden from default list."""
        dogcats_dir, issue_id = _init_and_create(tmp_path)
        runner.invoke(app, ["snooze", issue_id, "7d", "--dogcats-dir", dogcats_dir])
        result = runner.invoke(app, ["list", "--dogcats-dir", dogcats_dir])
        assert "Test issue" not in result.stdout

    def test_snoozed_visible_with_include_snoozed(self, tmp_path: Path) -> None:
        """Test that snoozed issues appear with --include-snoozed."""
        dogcats_dir, issue_id = _init_and_create(tmp_path)
        runner.invoke(app, ["snooze", issue_id, "7d", "--dogcats-dir", dogcats_dir])
        result = runner.invoke(
            app, ["list", "--include-snoozed", "--dogcats-dir", dogcats_dir]
        )
        assert "Test issue" in result.stdout

    def test_snoozed_visible_with_all(self, tmp_path: Path) -> None:
        """Test that snoozed issues appear with --all."""
        dogcats_dir, issue_id = _init_and_create(tmp_path)
        runner.invoke(app, ["snooze", issue_id, "7d", "--dogcats-dir", dogcats_dir])
        result = runner.invoke(app, ["list", "--all", "--dogcats-dir", dogcats_dir])
        assert "Test issue" in result.stdout

    def test_snoozed_hidden_from_ready(self, tmp_path: Path) -> None:
        """Test that snoozed issues are hidden from ready."""
        dogcats_dir, issue_id = _init_and_create(tmp_path)
        runner.invoke(app, ["snooze", issue_id, "7d", "--dogcats-dir", dogcats_dir])
        result = runner.invoke(app, ["ready", "--dogcats-dir", dogcats_dir])
        assert "Test issue" not in result.stdout

    def test_snoozed_visible_in_ready_with_include_snoozed(
        self, tmp_path: Path
    ) -> None:
        """Test that snoozed issues appear in ready with --include-snoozed."""
        dogcats_dir, issue_id = _init_and_create(tmp_path)
        runner.invoke(app, ["snooze", issue_id, "7d", "--dogcats-dir", dogcats_dir])
        result = runner.invoke(
            app, ["ready", "--include-snoozed", "--dogcats-dir", dogcats_dir]
        )
        assert "Test issue" in result.stdout

    def test_expired_snooze_visible_in_list(self, tmp_path: Path) -> None:
        """Test that expired snoozes show up in list again."""
        dogcats_dir, issue_id = _init_and_create(tmp_path)
        # Snooze with a date in the past
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        runner.invoke(
            app,
            [
                "update",
                issue_id,
                "--snooze-until",
                past,
                "--dogcats-dir",
                dogcats_dir,
            ],
        )
        result = runner.invoke(app, ["list", "--dogcats-dir", dogcats_dir])
        assert "Test issue" in result.stdout


class TestSnoozeViaUpdate:
    """Test snooze/unsnooze via the update command."""

    def test_update_snooze_until(self, tmp_path: Path) -> None:
        """Test --snooze-until via update command."""
        dogcats_dir, issue_id = _init_and_create(tmp_path)
        result = runner.invoke(
            app,
            [
                "update",
                issue_id,
                "--snooze-until",
                "7d",
                "--dogcats-dir",
                dogcats_dir,
            ],
        )
        assert result.exit_code == 0

        # Verify it's snoozed
        show = runner.invoke(
            app, ["show", issue_id, "--json", "--dogcats-dir", dogcats_dir]
        )
        import json

        data = json.loads(show.stdout)
        assert data["snoozed_until"] is not None

    def test_update_unsnooze(self, tmp_path: Path) -> None:
        """Test --unsnooze via update command."""
        dogcats_dir, issue_id = _init_and_create(tmp_path)
        runner.invoke(app, ["snooze", issue_id, "7d", "--dogcats-dir", dogcats_dir])
        result = runner.invoke(
            app,
            ["update", issue_id, "--unsnooze", "--dogcats-dir", dogcats_dir],
        )
        assert result.exit_code == 0

        show = runner.invoke(
            app, ["show", issue_id, "--json", "--dogcats-dir", dogcats_dir]
        )
        import json

        data = json.loads(show.stdout)
        assert data["snoozed_until"] is None


class TestParseDuration:
    """Test the parse_duration helper."""

    def test_days(self) -> None:
        """Test parsing day durations."""
        from dogcat.cli._helpers import parse_duration

        result = parse_duration("7d")
        expected_min = datetime.now().astimezone() + timedelta(days=6, hours=23)
        assert result > expected_min

    def test_weeks(self) -> None:
        """Test parsing week durations."""
        from dogcat.cli._helpers import parse_duration

        result = parse_duration("2w")
        expected_min = datetime.now().astimezone() + timedelta(
            weeks=1, days=6, hours=23
        )
        assert result > expected_min

    def test_months(self) -> None:
        """Test parsing month durations."""
        from dogcat.cli._helpers import parse_duration

        result = parse_duration("1m")
        expected_min = datetime.now().astimezone() + timedelta(days=29, hours=23)
        assert result > expected_min

    def test_iso_date(self) -> None:
        """Test parsing ISO8601 date strings."""
        from dogcat.cli._helpers import parse_duration

        result = parse_duration("2099-01-15")
        assert result.year == 2099
        assert result.month == 1
        assert result.day == 15

    def test_invalid(self) -> None:
        """Test that invalid duration strings raise ValueError."""
        import pytest

        from dogcat.cli._helpers import parse_duration

        with pytest.raises(ValueError, match="Invalid duration"):
            parse_duration("banana")

    def test_zero_duration(self) -> None:
        """'0d' yields a duration equal to (or within microseconds of) now."""
        from dogcat.cli._helpers import parse_duration

        before = datetime.now().astimezone()
        result = parse_duration("0d")
        after = datetime.now().astimezone()
        assert before <= result <= after

    def test_decimal_amount_rejected(self) -> None:
        """'1.5d' is rejected — the regex requires integer amounts."""
        import pytest

        from dogcat.cli._helpers import parse_duration

        with pytest.raises(ValueError, match="Invalid duration"):
            parse_duration("1.5d")

    def test_empty_string_rejected(self) -> None:
        """Empty string is rejected with a clear ValueError."""
        import pytest

        from dogcat.cli._helpers import parse_duration

        with pytest.raises(ValueError, match="Invalid duration"):
            parse_duration("")

    def test_large_relative_duration(self) -> None:
        """Large relative durations (e.g. '999d') parse without overflow."""
        from dogcat.cli._helpers import parse_duration

        result = parse_duration("999d")
        expected_min = datetime.now().astimezone() + timedelta(days=998, hours=23)
        assert result > expected_min

    def test_overflow_duration_rejected(self) -> None:
        """A multi-trillion-day duration is rejected with a clear error.

        Regression for dogcat-dfn9: ``999999999999d`` used to throw
        OverflowError inside timedelta with a meaningless message.
        """
        import pytest

        from dogcat.cli._helpers import parse_duration

        with pytest.raises(ValueError, match="too far in the future"):
            parse_duration("999999999999d")

    def test_far_future_iso_date_caps_relative(self) -> None:
        """Relative durations above the 100y cap are rejected."""
        import pytest

        from dogcat.cli._helpers import parse_duration

        # 100 years is fine — verify the threshold.
        parse_duration(f"{365 * 100}d")
        with pytest.raises(ValueError, match="too far in the future"):
            parse_duration(f"{365 * 100 + 1}d")

    def test_iso_z_suffix_accepted(self) -> None:
        """``2026-04-25T00:00:00Z`` parses correctly (regression for dogcat-3x9q).

        ``datetime.fromisoformat`` only accepts uppercase ``Z``; the
        previous implementation lowercased the input first, so the help
        text claiming ISO8601 support was wrong for the most common
        ``Z``-terminated form.
        """
        from dogcat.cli._helpers import parse_duration

        result = parse_duration("2026-04-25T00:00:00Z")
        assert result.year == 2026
        assert result.month == 4
        assert result.day == 25
        assert result.tzinfo is not None

    def test_iso_with_timezone(self) -> None:
        """ISO8601 with explicit timezone offset preserves the offset."""
        from dogcat.cli._helpers import parse_duration

        result = parse_duration("2099-06-15T12:00:00+05:30")
        assert result.year == 2099
        assert result.month == 6
        assert result.day == 15
        assert result.utcoffset() == timedelta(hours=5, minutes=30)

    def test_past_date_accepted(self) -> None:
        """Past ISO date is parsed without error — caller decides if it makes sense."""
        from dogcat.cli._helpers import parse_duration

        result = parse_duration("2020-01-01")
        assert result.year == 2020
        assert result < datetime.now().astimezone()
