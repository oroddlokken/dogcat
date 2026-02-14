"""Display and formatting functions for dogcat CLI."""

from __future__ import annotations

from typing import TYPE_CHECKING

import typer

from dogcat.constants import EVENT_SYMBOLS, PRIORITY_COLORS, STATUS_COLORS, TYPE_COLORS

if TYPE_CHECKING:
    from dogcat.event_log import EventRecord
    from dogcat.models import Issue


def get_legend(hidden_count: int = 0, *, color: bool = True) -> str:
    """Get a legend explaining status symbols and colors.

    Args:
        hidden_count: Total number of issues hidden under deferred parents
        color: Whether to apply color styling to legend symbols and priorities

    Returns:
        Multi-line legend string
    """
    status_items = [
        ("✎", "draft", "Draft"),
        ("●", "open", "Open"),
        ("◐", "in_progress", "In Progress"),
        ("?", "in_review", "In Review"),
        ("■", "blocked", "Blocked"),
        ("◇", "deferred", "Deferred"),
        ("✓", "closed", "Closed"),
        ("☠", "tombstone", "Tombstone"),
    ]
    if color:
        styled_statuses = [
            f"{typer.style(symbol, fg=STATUS_COLORS.get(key, 'white'))} {label}"
            for symbol, key, label in status_items
        ]
    else:
        styled_statuses = [f"{symbol} {label}" for symbol, _, label in status_items]
    # Split into two lines for readability
    status_line1 = "  Status: " + "  ".join(styled_statuses[:6])
    status_line2 = "          " + "  ".join(styled_statuses[6:])

    priority_items = [
        (0, "Critical"),
        (1, "High"),
        (2, "Medium"),
        (3, "Low"),
        (4, "Minimal"),
    ]
    if color:
        styled_priorities = [
            typer.style(
                f"{pri} ({label})",
                fg=PRIORITY_COLORS.get(pri, "white"),
                bold=True,
            )
            for pri, label in priority_items
        ]
    else:
        styled_priorities = [f"{pri} ({label})" for pri, label in priority_items]
    priority_line = "  Priority: " + "  ".join(styled_priorities)

    legend_lines = [
        "",
        "Legend:",
        status_line1,
        status_line2,
        priority_line,
    ]
    if hidden_count > 0:
        s = "s" if hidden_count != 1 else ""
        legend_lines.append(
            f"  {hidden_count} issue{s} hidden under deferred parents"
            " — use --expand to show",
        )
    return "\n".join(legend_lines)


def format_issue_brief(
    issue: Issue,
    blocked_ids: set[str] | None = None,
    blocked_by_map: dict[str, list[str]] | None = None,
    hidden_subtask_count: int | None = None,
    deferred_blockers: list[str] | None = None,
) -> str:
    """Format issue for brief display with color coding.

    Args:
        issue: The issue to format
        blocked_ids: Set of issue IDs that are blocked by dependencies
        blocked_by_map: Mapping of issue ID to list of blocking issue IDs
        hidden_subtask_count: Number of hidden subtasks (for deferred parents)
        deferred_blockers: List of deferred issue IDs blocking this issue

    Returns:
        Formatted string with status emoji, priority, ID, title, and type
    """
    # Dim entire line for closed issues
    is_closed = issue.closed_at is not None

    # Use blocked symbol if issue has open dependencies
    if blocked_ids and issue.full_id in blocked_ids:
        status_emoji = "■"
        status_color = (
            "bright_black" if is_closed else STATUS_COLORS.get("blocked", "white")
        )
    else:
        status_emoji = issue.get_status_emoji()
        status_color = (
            "bright_black"
            if is_closed
            else STATUS_COLORS.get(issue.status.value, "white")
        )
    status_emoji = typer.style(status_emoji, fg=status_color)

    priority_color = (
        "bright_black" if is_closed else PRIORITY_COLORS.get(issue.priority, "white")
    )
    priority_str = typer.style(
        f"[{issue.priority}]",
        fg=priority_color,
        bold=not is_closed,
    )

    type_color = (
        "bright_black"
        if is_closed
        else TYPE_COLORS.get(issue.issue_type.value, "white")
    )
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
        label_color = "bright_black" if is_closed else "cyan"
        labels_str = " " + typer.style(f"[{', '.join(issue.labels)}]", fg=label_color)
    ext_ref_str = ""
    if issue.external_ref:
        ext_ref_str = " " + typer.style(
            f"[extref: {issue.external_ref}]",
            fg="bright_black",
        )
    manual_str = ""
    if issue.metadata.get("manual") or issue.metadata.get("no_agent"):
        manual_color = "bright_black" if is_closed else "yellow"
        manual_str = " " + typer.style("[manual]", fg=manual_color)
    blocked_by_str = ""
    if blocked_by_map and issue.full_id in blocked_by_map:
        blockers = ", ".join(blocked_by_map[issue.full_id])
        blocked_color = "bright_black" if is_closed else "red"
        blocked_by_str = " " + typer.style(
            f"[blocked by: {blockers}]",
            fg=blocked_color,
        )
    hidden_str = ""
    if hidden_subtask_count:
        hidden_str = " " + typer.style(
            f"[{hidden_subtask_count} hidden subtasks]",
            fg="yellow",
        )
    deferred_blocker_str = ""
    if deferred_blockers:
        ids = ", ".join(deferred_blockers)
        deferred_blocker_str = " " + typer.style(
            f"[blocked by deferred: {ids}]",
            fg="bright_black",
        )
    if is_closed:
        id_title = typer.style(f"{issue.full_id}: {issue.title}", fg="bright_black")
    else:
        id_title = f"{issue.full_id}: {issue.title}"
    base = f"{status_emoji} {priority_str} {id_title} {type_str}"

    suffixes = parent_str + labels_str + manual_str
    suffixes += blocked_by_str + hidden_str + deferred_blocker_str
    suffixes += ext_ref_str + closed_str
    return f"{base}{suffixes}"


def _styled_key(label: str) -> str:
    """Style a field label as bold cyan."""
    return typer.style(label, fg="cyan", bold=True)


def format_issue_full(issue: Issue, parent_title: str | None = None) -> str:
    """Format issue for full display."""
    key = _styled_key
    status_color = STATUS_COLORS.get(issue.status.value, "white")
    styled_status = typer.style(issue.status.value, fg=status_color)
    lines = [
        f"{key('ID:')} {issue.full_id}",
        f"{key('Title:')} {issue.title}",
        "",
        f"{key('Status:')} {styled_status}",
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
    if issue.external_ref:
        lines.append(f"{key('External ref:')} {issue.external_ref}")
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
    hidden_counts: dict[str, int] | None = None,
    deferred_blocker_map: dict[str, list[str]] | None = None,
) -> str:
    """Format issues as a tree based on parent-child relationships.

    Args:
        issues: List of issues to format
        _indent: Current indentation level (unused, kept for compatibility)
        blocked_ids: Set of issue IDs that are blocked by dependencies
        blocked_by_map: Mapping of issue ID to list of blocking issue IDs
        hidden_counts: Deferred parent full_id -> count of hidden descendants
        deferred_blocker_map: Issue full_id -> list of deferred blocker IDs

    Returns:
        Formatted tree string
    """
    hierarchy = build_hierarchy(issues)

    # Collect all issue IDs in the filtered set
    issue_ids = {issue.full_id for issue in issues}

    # Determine root issues: those with no parent, OR whose parent is not
    # in the filtered set (orphaned children).
    roots = sorted(
        [i for i in issues if i.parent is None or i.parent not in issue_ids],
        key=lambda i: (i.priority, i.full_id),
    )

    def _brief(issue: Issue) -> str:
        return format_issue_brief(
            issue,
            blocked_ids,
            blocked_by_map,
            hidden_subtask_count=(
                hidden_counts.get(issue.full_id) if hidden_counts else None
            ),
            deferred_blockers=(
                deferred_blocker_map.get(issue.full_id)
                if deferred_blocker_map
                else None
            ),
        )

    def format_recursive(parent_id: str | None, depth: int) -> list[str]:
        """Recursively format issues and their children."""
        lines: list[str] = []
        children = hierarchy.get(parent_id, [])
        # Sort children by priority for consistent output
        children = sorted(children, key=lambda i: (i.priority, i.full_id))

        for issue in children:
            indent_str = "  " * depth
            formatted = _brief(issue)
            lines.append(f"{indent_str}{formatted}")
            # Recursively format children
            lines.extend(format_recursive(issue.full_id, depth + 1))

        return lines

    # Format root issues and their children
    lines: list[str] = []
    for issue in roots:
        formatted = _brief(issue)
        lines.append(formatted)
        lines.extend(format_recursive(issue.full_id, 1))

    return "\n".join(lines)


def format_issue_table(
    issues: list[Issue],
    blocked_ids: set[str] | None = None,
    blocked_by_map: dict[str, list[str]] | None = None,
    hidden_counts: dict[str, int] | None = None,
    deferred_blocker_map: dict[str, list[str]] | None = None,
) -> str:
    """Format issues as an aligned table with columns using Rich.

    Args:
        issues: List of issues to format
        blocked_ids: Set of issue IDs that are blocked by dependencies
        blocked_by_map: Mapping of issue ID to list of blocking issue IDs
        hidden_counts: Deferred parent full_id -> count of hidden descendants
        deferred_blocker_map: Issue full_id -> list of deferred blocker IDs

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

    # Only add optional columns when relevant data exists
    has_ext_ref = any(issue.external_ref for issue in issues)
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
    if has_ext_ref:
        table.add_column("Ext Ref", no_wrap=True)
    if has_blocked:
        table.add_column("Blocked By", no_wrap=False)

    # Add rows
    for issue in issues:
        # Use blocked symbol if issue has open dependencies
        if blocked_ids and issue.full_id in blocked_ids:
            emoji = "■"
            status_color = STATUS_COLORS.get("blocked", "white")
        else:
            emoji = issue.get_status_emoji()
            status_color = STATUS_COLORS.get(issue.status.value, "white")
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

        # Add hidden subtask count suffix to title for deferred parents
        hidden_suffix = ""
        if hidden_counts and issue.full_id in hidden_counts:
            count = hidden_counts[issue.full_id]
            hidden_suffix = f" [yellow]\\[{count} hidden subtasks][/]"

        row = [
            f"[{status_color}]{emoji}[/]",
            issue.id,
            parent_id,
            f"[{type_color}]{issue_type}[/]",
            f"[{priority_color}]{issue.priority}[/]",
            f"{escape(issue.title)}{manual_str}{hidden_suffix}",
            f"[cyan]{labels_str}[/]" if labels_str else "",
        ]
        if has_ext_ref:
            ref = escape(issue.external_ref) if issue.external_ref else ""
            row.append(f"[bright_black]{ref}[/]" if ref else "")
        if has_blocked:
            blockers = ""
            if blocked_by_map and issue.full_id in blocked_by_map:
                blockers = ", ".join(blocked_by_map[issue.full_id])
            # Also include deferred blockers
            deferred_suffix = ""
            if deferred_blocker_map and issue.full_id in deferred_blocker_map:
                deferred_ids = ", ".join(deferred_blocker_map[issue.full_id])
                deferred_suffix = f"[bright_black]{deferred_ids} (deferred)[/]"
            if blockers and deferred_suffix:
                row.append(f"[red]{blockers}[/] {deferred_suffix}")
            elif blockers:
                row.append(f"[red]{blockers}[/]")
            elif deferred_suffix:
                row.append(deferred_suffix)
            else:
                row.append("")
        table.add_row(*row)

    # Render to string
    string_io = StringIO()
    console = Console(file=string_io, force_terminal=True, width=None)
    console.print(table)

    return string_io.getvalue().rstrip()


def format_event(event: EventRecord, *, verbose: bool = False) -> str:
    """Format an event record for terminal display.

    Args:
        event: The event record to format.
        verbose: If True, show full content of long-form fields instead of "changed".

    Returns:
        Formatted multi-line string with symbol, timestamp, issue ID, and changes.
    """
    symbol = EVENT_SYMBOLS.get(event.event_type, "?")

    # Color the symbol based on event type
    symbol_colors = {
        "created": "bright_green",
        "closed": "white",
        "updated": "yellow",
        "deleted": "red",
    }
    color = symbol_colors.get(event.event_type, "white")
    styled_symbol = typer.style(symbol, fg=color, bold=True)

    # Parse and format the timestamp
    from datetime import datetime

    try:
        ts = datetime.fromisoformat(event.timestamp)
        ts_str = ts.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        ts_str = event.timestamp

    ts_styled = typer.style(ts_str, fg="bright_black")

    # Show id: title, matching the pattern used by other commands
    title = event.title
    if not title and event.event_type == "created" and "title" in event.changes:
        title = event.changes["title"].get("new", "")
    issue_styled = typer.style(event.issue_id, fg="cyan")
    if title:
        issue_styled += f": {title}"

    header = f"{styled_symbol} {ts_styled}  {issue_styled}"

    # Long-form fields: show "changed" (red) instead of full content unless verbose
    _long_fields = {"description", "notes", "acceptance", "design"}
    _changed = typer.style("changed", fg="red")

    # Format field changes on the next line
    change_parts: list[str] = []
    if event.by:
        by_label = typer.style("by", fg="cyan")
        change_parts.append(f"{by_label}: {event.by}")
    for field_name, change in event.changes.items():
        if field_name == "title" and event.event_type == "created":
            continue  # Already shown in header
        old = change.get("old")
        new = change.get("new")
        if not verbose and field_name in _long_fields:
            old = _changed if old is not None else None
            new = _changed if new is not None else None
        field_styled = typer.style(field_name, fg="cyan")
        if old is None:
            change_parts.append(f"{field_styled}: {new}")
        else:
            change_parts.append(f"{field_styled}: {old} -> {new}")

    lines = [header]
    if change_parts:
        lines.append("    " + "  ".join(change_parts))

    return "\n".join(lines)


def get_event_legend() -> str:
    """Get a legend explaining event symbols.

    Returns:
        Legend string
    """
    return "\nLegend: + Created  ~ Updated  ✓ Closed  ✗ Deleted"
