"""Display and formatting functions for dogcat CLI."""

from __future__ import annotations

from typing import TYPE_CHECKING

import typer

from dogcat.constants import PRIORITY_COLORS, TYPE_COLORS

if TYPE_CHECKING:
    from dogcat.models import Issue


def get_legend() -> str:
    """Get a legend explaining status symbols and colors.

    Returns:
        Multi-line legend string
    """
    legend_lines = [
        "",
        "Legend:",
        "  Status: ● Open  ◐ In Progress  ? In Review  ■ Blocked  ◇ Deferred",
        "          ✓ Closed  ☠ Tombstone",
        "  Priority: 0 (Critical) → 4 (Low)",
    ]
    return "\n".join(legend_lines)


def format_issue_brief(
    issue: Issue,
    blocked_ids: set[str] | None = None,
    blocked_by_map: dict[str, list[str]] | None = None,
) -> str:
    """Format issue for brief display with color coding.

    Args:
        issue: The issue to format
        blocked_ids: Set of issue IDs that are blocked by dependencies
        blocked_by_map: Mapping of issue ID to list of blocking issue IDs

    Returns:
        Formatted string with status emoji, priority, ID, title, and type
    """
    # Use blocked symbol if issue has open dependencies
    if blocked_ids and issue.full_id in blocked_ids:
        status_emoji = "■"
    else:
        status_emoji = issue.get_status_emoji()

    priority_color = PRIORITY_COLORS.get(issue.priority, "white")
    priority_str = typer.style(f"[{issue.priority}]", fg=priority_color, bold=True)

    type_color = TYPE_COLORS.get(issue.issue_type.value, "white")
    type_str = typer.style(f"[{issue.issue_type.value}]", fg=type_color)

    parent_str = (
        typer.style(f" [parent: {issue.parent}]", fg="bright_black")
        if issue.parent
        else ""
    )
    closed_str = ""
    if issue.closed_at:
        closed_ts = issue.closed_at.strftime("%Y-%m-%d %H:%M")
        closed_str = typer.style(f" [closed {closed_ts}]", fg="bright_black")
    labels_str = ""
    if issue.labels:
        labels_str = " " + typer.style(f"[{', '.join(issue.labels)}]", fg="cyan")
    manual_str = ""
    if issue.metadata.get("manual") or issue.metadata.get("no_agent"):
        manual_str = " " + typer.style("[manual]", fg="yellow")
    blocked_by_str = ""
    if blocked_by_map and issue.full_id in blocked_by_map:
        blockers = ", ".join(blocked_by_map[issue.full_id])
        blocked_by_str = " " + typer.style(f"[blocked by: {blockers}]", fg="red")
    base = f"{status_emoji} {priority_str} {issue.full_id}: {issue.title} {type_str}"

    return f"{base}{parent_str}{labels_str}{manual_str}{blocked_by_str}{closed_str}"


def _styled_key(label: str) -> str:
    """Style a field label as bold cyan."""
    return typer.style(label, fg="cyan", bold=True)


def format_issue_full(issue: Issue, parent_title: str | None = None) -> str:
    """Format issue for full display."""
    key = _styled_key
    lines = [
        f"{key('ID:')} {issue.full_id}",
        f"{key('Title:')} {issue.title}",
        "",
        f"{key('Status:')} {issue.status.value}",
        f"{key('Priority:')} {issue.priority}",
        f"{key('Type:')} {issue.issue_type.value}",
        "",
    ]

    if issue.parent:
        parent_line = f"{key('Parent:')} {issue.parent}"
        if parent_title:
            parent_line += f" ({parent_title})"
        lines.append(parent_line)
    if issue.owner:
        lines.append(f"{key('Owner:')} {issue.owner}")
    if issue.labels:
        lines.append(f"{key('Labels:')} {', '.join(issue.labels)}")
    if issue.duplicate_of:
        lines.append(f"{key('Duplicate of:')} {issue.duplicate_of}")

    dt_fmt = "%Y-%m-%d %H:%M:%S"
    lines.append(f"{key('Created:')} {issue.created_at.strftime(dt_fmt)}")
    if issue.closed_at:
        closed_line = f"{key('Closed:')} {issue.closed_at.strftime(dt_fmt)}"
        if issue.close_reason:
            closed_line += f" ({issue.close_reason})"
        lines.append(closed_line)

    if issue.description:
        lines.append(f"\n{key('Description:')}\n{issue.description}")

    if issue.notes:
        lines.append(f"\n{key('Notes:')}\n{issue.notes}")

    if issue.acceptance:
        lines.append(f"\n{key('Acceptance criteria:')}\n{issue.acceptance}")

    if issue.design:
        lines.append(f"\n{key('Design:')}\n{issue.design}")

    if issue.comments:
        lines.append(f"\n{key('Comments:')}")
        for comment in issue.comments:
            lines.append(f"  [{comment.id}] {comment.author}")
            lines.append(f"  {comment.text}")

    return "\n".join(lines)


def build_hierarchy(issues: list[Issue]) -> dict[str | None, list[Issue]]:
    """Build parent->children mapping from issue list.

    Args:
        issues: List of issues

    Returns:
        Dictionary mapping parent_id (or None for roots) to list of child issues
    """
    hierarchy: dict[str | None, list[Issue]] = {}
    for issue in issues:
        parent_id = issue.parent
        if parent_id not in hierarchy:
            hierarchy[parent_id] = []
        hierarchy[parent_id].append(issue)
    return hierarchy


def format_issue_tree(
    issues: list[Issue],
    _indent: int = 0,
    blocked_ids: set[str] | None = None,
    blocked_by_map: dict[str, list[str]] | None = None,
) -> str:
    """Format issues as a tree based on parent-child relationships.

    Args:
        issues: List of issues to format
        _indent: Current indentation level (unused, kept for compatibility)
        blocked_ids: Set of issue IDs that are blocked by dependencies
        blocked_by_map: Mapping of issue ID to list of blocking issue IDs

    Returns:
        Formatted tree string
    """
    hierarchy = build_hierarchy(issues)

    def format_recursive(parent_id: str | None, depth: int) -> list[str]:
        """Recursively format issues and their children."""
        lines: list[str] = []
        children = hierarchy.get(parent_id, [])
        # Sort children by priority for consistent output
        children = sorted(children, key=lambda i: (i.priority, i.full_id))

        for issue in children:
            indent_str = "  " * depth
            formatted = format_issue_brief(issue, blocked_ids, blocked_by_map)
            lines.append(f"{indent_str}{formatted}")
            # Recursively format children
            lines.extend(format_recursive(issue.full_id, depth + 1))

        return lines

    lines = format_recursive(None, 0)
    return "\n".join(lines)


def format_issue_table(
    issues: list[Issue],
    blocked_ids: set[str] | None = None,
    blocked_by_map: dict[str, list[str]] | None = None,
) -> str:
    """Format issues as an aligned table with columns using Rich.

    Args:
        issues: List of issues to format
        blocked_ids: Set of issue IDs that are blocked by dependencies
        blocked_by_map: Mapping of issue ID to list of blocking issue IDs

    Returns:
        Formatted table string (rendered by Rich)
    """
    from io import StringIO

    from rich import box
    from rich.console import Console
    from rich.markup import escape
    from rich.table import Table

    if not issues:
        return ""

    # Only add Blocked By column if there are blocked issues in the list
    has_blocked = blocked_ids and any(issue.full_id in blocked_ids for issue in issues)

    # Create Rich table with column dividers
    table = Table(
        show_header=True,
        header_style="bold",
        box=box.ROUNDED,
        pad_edge=False,
        show_edge=False,
    )

    # Add columns - title column wraps instead of truncating
    table.add_column("", width=2, no_wrap=True)  # Status emoji
    table.add_column("ID", no_wrap=True)
    table.add_column("Parent", no_wrap=True)
    table.add_column("Type", no_wrap=True)
    table.add_column("Pri", width=3, no_wrap=True)
    table.add_column("Title", overflow="fold")  # Wrap long titles
    table.add_column("Labels", no_wrap=False)
    if has_blocked:
        table.add_column("Blocked By", no_wrap=False)

    # Add rows
    for issue in issues:
        # Use blocked symbol if issue has open dependencies
        if blocked_ids and issue.full_id in blocked_ids:
            emoji = "■"
        else:
            emoji = issue.get_status_emoji()
        priority_color = f"bold {PRIORITY_COLORS.get(issue.priority, 'white')}"
        issue_type = issue.issue_type.value
        type_color = TYPE_COLORS.get(issue_type, "white")

        # Extract just the ID part from parent if it has a prefix
        parent_id = ""
        if issue.parent:
            parent_id = (
                issue.parent.split("-", 1)[-1] if "-" in issue.parent else issue.parent
            )

        labels_str = (
            ", ".join(escape(lbl) for lbl in issue.labels) if issue.labels else ""
        )
        manual_str = (
            " [yellow]\\[manual][/]"
            if issue.metadata.get("manual") or issue.metadata.get("no_agent")
            else ""
        )

        row = [
            emoji,
            issue.id,
            parent_id,
            f"[{type_color}]{issue_type}[/]",
            f"[{priority_color}]{issue.priority}[/]",
            f"{escape(issue.title)}{manual_str}",
            f"[cyan]{labels_str}[/]" if labels_str else "",
        ]
        if has_blocked:
            blockers = ""
            if blocked_by_map and issue.full_id in blocked_by_map:
                blockers = ", ".join(blocked_by_map[issue.full_id])
            row.append(f"[red]{blockers}[/]" if blockers else "")
        table.add_row(*row)

    # Render to string
    string_io = StringIO()
    console = Console(file=string_io, force_terminal=True, width=None)
    console.print(table)

    return string_io.getvalue().rstrip()
