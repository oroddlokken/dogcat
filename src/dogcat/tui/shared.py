"""Shared design system for dogcat TUI components."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from rich.text import Text
from textual.css.query import NoMatches
from textual.widgets import Select

from dogcat.constants import PRIORITY_COLORS, STATUS_COLORS, TYPE_COLORS
from dogcat.models import is_manual_issue
from dogcat.status_display import resolve_status_glyph

if TYPE_CHECKING:
    from dogcat.models import Issue

SHARED_CSS = """
#title-bar {
    height: auto;
    max-height: 3;
    padding: 0 2;
    margin: 1 0;
}

#id-display {
    width: auto;
    min-width: 12;
    padding: 0 2;
    content-align: left middle;
    height: 3;
    color: $text-muted;
}

.field-label {
    margin-top: 1;
    color: $text-muted;
}

.field-row {
    height: auto;
    max-height: 5;
    margin-bottom: 1;
}

.field-row > Select {
    width: 1fr;
}

.info-row {
    height: auto;
    max-height: 5;
}

.info-row > Input {
    width: 1fr;
}

.info-row > Select {
    width: 1fr;
}

.deps-row {
    height: auto;
    max-height: 5;
    margin-top: 1;
}

.deps-row > Input {
    width: 1fr;
}

.deps-row > Select {
    width: 1fr;
}

.collapsible-textarea {
    height: auto;
    min-height: 5;
    max-height: 8;
}
"""


def make_issue_label(
    issue: Issue,
    blocked_ids: set[str] | None = None,
) -> Text:
    """Build a Rich Text label for an issue.

    Matches the CLI ``dcat list`` format:
    ``emoji [priority] id: title [type] [labels] [manual]``
    """
    type_color = TYPE_COLORS.get(issue.issue_type.value, "white")
    priority_color = PRIORITY_COLORS.get(issue.priority, "white")

    # Shared glyph rule (blocked override, exempting advanced statuses).
    status_emoji, color_key = resolve_status_glyph(issue, blocked_ids)
    status_color = STATUS_COLORS.get(color_key, "white")

    label = Text()
    label.append(f"{status_emoji} ", style=f"bold {status_color}")
    label.append(f"[{issue.priority}]", style=f"bold {priority_color}")
    label.append(f" {issue.full_id}: {issue.title}")
    label.append(f" [{issue.issue_type.value}]", style=type_color)
    if issue.labels:
        label.append(f" [{', '.join(issue.labels)}]", style="cyan")
    if is_manual_issue(issue.metadata):
        label.append(" [manual]", style="yellow")
    return label


class MountSafeSelect(Select[Any]):
    """Select that tolerates losing its children while Mount is in flight.

    `Select._on_mount` pushes the constructor's `value` through
    `SelectCurrent.update`, which queries `#label`. Textual guards the
    `SelectCurrent` lookup one level up but not that query or the
    `SelectOverlay` lookup beside it, so a panel swap that removes the
    subtree mid-mount raises NoMatches into the app (dogcat-5obm).
    """

    def _watch_value(self, value: Any) -> None:
        try:
            super()._watch_value(value)
        except NoMatches:
            self._value = value
            if self.is_mounted:
                # The children may be mid-compose rather than gone; retry so a
                # surviving select still shows its label.
                self.call_after_refresh(self._reapply_value, value)

    def _reapply_value(self, value: Any) -> None:
        """Re-run the value watcher once the DOM has settled."""
        with contextlib.suppress(NoMatches):
            super()._watch_value(value)
