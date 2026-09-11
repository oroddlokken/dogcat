"""Tests for the shared blocked-status glyph resolution (dogcat-4gj6)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from dogcat.cli import app
from dogcat.constants import STATUS_SYMBOLS
from dogcat.models import Issue, Status
from dogcat.status_display import is_blocked_display, resolve_status_glyph

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()


def _issue(status: Status) -> Issue:
    return Issue(id="a", namespace="t", title="T", status=status)


class TestResolveStatusGlyph:
    """The blocked override applies unless the status is display-exempt."""

    def test_blocked_open_issue_gets_blocked_glyph(self) -> None:
        """An open, dependency-blocked issue shows the blocked glyph + color."""
        issue = _issue(Status.OPEN)
        symbol, color_key = resolve_status_glyph(issue, {"t-a"})
        assert color_key == "blocked"
        assert symbol == "■"
        assert is_blocked_display(issue, {"t-a"}) is True

    @pytest.mark.parametrize(
        "status",
        [Status.IN_REVIEW, Status.DEFERRED, Status.CLOSED],
    )
    def test_advanced_statuses_are_exempt_from_blocked_override(
        self, status: Status
    ) -> None:
        """in_review / deferred / closed keep their natural glyph even if blocked."""
        issue = _issue(status)
        symbol, color_key = resolve_status_glyph(issue, {"t-a"})
        assert color_key == status.value
        assert symbol == issue.get_status_emoji()
        assert is_blocked_display(issue, {"t-a"}) is False

    def test_unblocked_issue_uses_natural_glyph(self) -> None:
        """An issue not in blocked_ids always uses its natural glyph."""
        issue = _issue(Status.OPEN)
        symbol, color_key = resolve_status_glyph(issue, {"t-other"})
        assert color_key == Status.OPEN.value
        assert symbol == issue.get_status_emoji()

    def test_none_blocked_ids_uses_natural_glyph(self) -> None:
        """A None/empty blocked set never triggers the blocked override."""
        issue = _issue(Status.OPEN)
        assert is_blocked_display(issue, None) is False
        _, color_key = resolve_status_glyph(issue, None)
        assert color_key == Status.OPEN.value


class TestRenderersAgree:
    """All three renderers resolve the same glyph for the same issue."""

    def test_cli_table_and_tui_agree_on_blocked_open_issue(self) -> None:
        """dcat-list brief, the Rich table row, and the TUI label all match."""
        from dogcat.cli._formatting import _row_status
        from dogcat.tui.shared import make_issue_label

        issue = _issue(Status.OPEN)
        blocked = {"t-a"}
        expected_symbol, _ = resolve_status_glyph(issue, blocked)

        # Rich table row.
        row_emoji, _color = _row_status(issue, blocked, dimmed=False)
        assert row_emoji == expected_symbol

        # TUI Rich Text label starts with the glyph.
        label = make_issue_label(issue, blocked)
        assert label.plain.startswith(expected_symbol)


class TestInProgressIsExempt:
    """An issue you have started is not blocked, whatever its deps say (dogcat-132j)."""

    def test_in_progress_keeps_its_own_glyph(self) -> None:
        """in_progress survives the blocked override the way in_review does."""
        issue = _issue(Status.IN_PROGRESS)
        symbol, color_key = resolve_status_glyph(issue, {"t-a"})
        assert color_key == Status.IN_PROGRESS.value
        assert symbol == STATUS_SYMBOLS["in_progress"]
        assert is_blocked_display(issue, {"t-a"}) is False


def _glyph_for(stdout: str, full_id: str) -> str:
    """Return the leading status glyph of the output line naming ``full_id``."""
    for line in stdout.splitlines():
        if full_id in line:
            return line.strip()[0]
    message = f"{full_id} missing from output:\n{stdout}"
    raise AssertionError(message)


def _create(dogcats_dir: Path, title: str, *extra: str) -> str:
    """Create an issue and return its full ``namespace-id``."""
    result = runner.invoke(
        app,
        ["create", title, "--dogcats-dir", str(dogcats_dir), "--json", *extra],
    )
    assert result.exit_code == 0, result.stdout
    record = json.loads(result.stdout.strip().splitlines()[-1])
    return f"{record['namespace']}-{record['id']}"


class TestListAndPrAgree:
    """``dcat list`` and ``dcat pr`` resolve one glyph per issue (dogcat-132j)."""

    def _blocked_pair(self, dogcats_dir: Path, status: str) -> tuple[str, str]:
        """Build a blocker plus a dependent issue at ``status``; return both ids."""
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])
        blocker = _create(dogcats_dir, "Blocker")
        dependent = _create(dogcats_dir, "Label", "--depends-on", blocker)
        result = runner.invoke(
            app,
            [
                "update",
                dependent,
                "--status",
                status,
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0, result.stdout
        return blocker, dependent

    def test_in_progress_blocked_issue_reads_the_same_on_both(
        self, tmp_path: Path
    ) -> None:
        """Both surfaces show the in-progress glyph, not the blocked one."""
        dogcats_dir = tmp_path / ".dogcats"
        blocker, dependent = self._blocked_pair(dogcats_dir, "in_progress")

        listed = runner.invoke(app, ["list", "--dogcats-dir", str(dogcats_dir)])
        pr = runner.invoke(app, ["pr", "--dogcats-dir", str(dogcats_dir)])
        assert listed.exit_code == 0, listed.stdout
        assert pr.exit_code == 0, pr.stdout

        assert _glyph_for(listed.stdout, dependent) == STATUS_SYMBOLS["in_progress"]
        assert _glyph_for(pr.stdout, dependent) == STATUS_SYMBOLS["in_progress"]
        # The dependency is still visible in list, just not as the status.
        assert f"[blocked by: {blocker}]" in listed.stdout

    def test_open_blocked_issue_still_shows_the_blocked_glyph(
        self, tmp_path: Path
    ) -> None:
        """The override survives for the statuses it was written for."""
        dogcats_dir = tmp_path / ".dogcats"
        _blocker, dependent = self._blocked_pair(dogcats_dir, "open")

        listed = runner.invoke(app, ["list", "--dogcats-dir", str(dogcats_dir)])
        assert _glyph_for(listed.stdout, dependent) == STATUS_SYMBOLS["blocked"]
