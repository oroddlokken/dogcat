"""Shared design system for dogcat TUI components."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text

from dogcat.constants import PRIORITY_COLORS, STATUS_COLORS, TYPE_COLORS

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

    # Override status icon/color for dependency-blocked issues
    if blocked_ids and issue.full_id in blocked_ids:
        status_emoji = "\u25a0"  # ■
        status_color = STATUS_COLORS.get("blocked", "white")
    else:
        status_emoji = issue.get_status_emoji()
        status_color = STATUS_COLORS.get(issue.status.value, "white")

    label = Text()
    label.append(f"{status_emoji} ", style=f"bold {status_color}")
    label.append(f"[{issue.priority}]", style=f"bold {priority_color}")
    label.append(f" {issue.full_id}: {issue.title}")
    label.append(f" [{issue.issue_type.value}]", style=type_color)
    if issue.labels:
        label.append(f" [{', '.join(issue.labels)}]", style="cyan")
    if issue.metadata.get("manual") or issue.metadata.get("no_agent"):
        label.append(" [manual]", style="yellow")
    return label
