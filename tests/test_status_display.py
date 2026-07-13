"""Tests for the shared blocked-status glyph resolution (dogcat-4gj6)."""

from __future__ import annotations

import pytest

from dogcat.models import Issue, Status
from dogcat.status_display import is_blocked_display, resolve_status_glyph


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
