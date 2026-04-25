"""Display and formatting functions for dogcat CLI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import typer

from dogcat.constants import (
    EVENT_SYMBOLS,
    PRIORITY_COLORS,
    STATUS_COLORS,
    STATUS_SYMBOLS,
    TYPE_COLORS,
)
from dogcat.models import Status

if TYPE_CHECKING:
    from rich.table import Table

    from dogcat.event_log import EventRecord
    from dogcat.models import Issue, Proposal


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


def format_proposal_brief(proposal: Proposal) -> str:
    """Format a proposal for brief display.

    Returns:
        Formatted string like: ● dc-inbox-4kzj: My proposal [inbox]
    """
    symbol = typer.style("●", fg="bright_cyan")
    full_id = typer.style(proposal.full_id, fg="bright_cyan")
    label = typer.style("[inbox]", fg="bright_black")
    return f"{symbol} {full_id}: {proposal.title} {label}"


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

    # Use blocked symbol if issue has open dependencies, but let advanced
    # statuses (in_review, deferred, closed) take precedence over blocked display
    _blocked_override_exempt = {Status.IN_REVIEW, Status.DEFERRED, Status.CLOSED}
    if (
        blocked_ids
        and issue.full_id in blocked_ids
        and issue.status not in _blocked_override_exempt
    ):
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
    snoozed_str = ""
    if issue.snoozed_until is not None:
        from datetime import datetime as dt

        now = dt.now().astimezone()
        if issue.snoozed_until > now:
            until_date = issue.snoozed_until.strftime("%Y-%m-%d")
            snoozed_color = "bright_black" if is_closed else "bright_magenta"
            snoozed_str = " " + typer.style(
                f"[snoozed until {until_date}]", fg=snoozed_color
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

    suffixes = parent_str + labels_str + snoozed_str + manual_str
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

    if issue.snoozed_until is not None:
        from datetime import datetime as dt

        now = dt.now().astimezone()
        snooze_date = issue.snoozed_until.strftime("%Y-%m-%d %H:%M")
        if issue.snoozed_until > now:
            styled_snooze = typer.style(snooze_date, fg="bright_magenta")
            lines.append(f"{key('Snoozed until:')} {styled_snooze}")
        else:
            styled_snooze = typer.style(f"{snooze_date} (expired)", fg="bright_black")
            lines.append(f"{key('Snoozed until:')} {styled_snooze}")

    dt_fmt = "%Y-%m-%d %H:%M:%S"
    lines.append(f"{key('Created:')} {issue.created_at.strftime(dt_fmt)}")
    if issue.closed_at:
        closed_line = f"{key('Closed:')} {issue.closed_at.strftime(dt_fmt)}"
        if issue.closed_reason:
            closed_line += f" ({issue.closed_reason})"
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
        for i, comment in enumerate(issue.comments):
            if i > 0:
                lines.append("")
            ts = comment.created_at.strftime(dt_fmt)
            lines.append(f"  [{comment.id}] {comment.author} ({ts})")
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
    preview_subtasks: dict[str, list[Issue]] | None = None,
) -> str:
    """Format issues as a tree based on parent-child relationships.

    Args:
        issues: List of issues to format
        _indent: Current indentation level (unused, kept for compatibility)
        blocked_ids: Set of issue IDs that are blocked by dependencies
        blocked_by_map: Mapping of issue ID to list of blocking issue IDs
        hidden_counts: Deferred parent full_id -> count of hidden descendants
        deferred_blocker_map: Issue full_id -> list of deferred blocker IDs
        preview_subtasks: Deferred parent full_id -> list of preview child issues

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
        has_previews = (
            preview_subtasks is not None and issue.full_id in preview_subtasks
        )
        return format_issue_brief(
            issue,
            blocked_ids,
            blocked_by_map,
            hidden_subtask_count=(
                None
                if has_previews
                else (hidden_counts.get(issue.full_id) if hidden_counts else None)
            ),
            deferred_blockers=(
                deferred_blocker_map.get(issue.full_id)
                if deferred_blocker_map
                else None
            ),
        )

    def _preview_lines(issue_id: str, depth: int) -> list[str]:
        """Render preview subtask lines for a deferred parent."""
        if not preview_subtasks or issue_id not in preview_subtasks:
            return []
        lines: list[str] = []
        previews = preview_subtasks[issue_id]
        indent_str = "  " * depth
        for preview in previews:
            formatted = format_issue_brief(
                preview,
                blocked_ids,
                blocked_by_map,
            )
            lines.append(f"{indent_str}{formatted}")
        total = hidden_counts.get(issue_id, 0) if hidden_counts else 0
        remaining = total - len(previews)
        if remaining > 0:
            summary = typer.style(
                f"[...and {remaining} more hidden subtasks]",
                fg="yellow",
            )
            lines.append(f"{indent_str}{summary}")
        return lines

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
            # Add preview subtasks for deferred parents
            lines.extend(_preview_lines(issue.full_id, depth + 1))
            # Recursively format children
            lines.extend(format_recursive(issue.full_id, depth + 1))

        return lines

    # Format root issues and their children
    lines: list[str] = []
    for issue in roots:
        formatted = _brief(issue)
        lines.append(formatted)
        # Add preview subtasks for deferred parents
        lines.extend(_preview_lines(issue.full_id, 1))
        lines.extend(format_recursive(issue.full_id, 1))

    return "\n".join(lines)


# Static column configuration for the issue table. Each entry is
# (header, kwargs-for-Table.add_column). Conditional columns (Ext Ref,
# Blocked By) are appended in `_build_issue_table`.
_ISSUE_TABLE_BASE_COLUMNS: tuple[tuple[str, dict[str, Any]], ...] = (
    ("", {"width": 2, "no_wrap": True}),  # Status emoji
    ("ID", {"no_wrap": True}),
    ("Parent", {"no_wrap": True}),
    ("Type", {"no_wrap": True}),
    ("Pri", {"width": 3, "no_wrap": True}),
    ("Title", {"overflow": "fold"}),  # Wrap long titles
    ("Labels", {"no_wrap": False}),
)
# Status values where the open-blocker symbol must NOT replace the natural emoji.
_BLOCKED_DISPLAY_EXEMPT = {Status.IN_REVIEW, Status.DEFERRED, Status.CLOSED}


def _build_issue_table(*, has_ext_ref: bool, has_blocked: bool) -> Table:
    """Create the Rich table shell with the right set of columns."""
    from rich import box
    from rich.table import Table

    table = Table(
        show_header=True,
        header_style="bold",
        box=box.ROUNDED,
        pad_edge=False,
        show_edge=False,
    )
    for header, kwargs in _ISSUE_TABLE_BASE_COLUMNS:
        table.add_column(header, **kwargs)
    if has_ext_ref:
        table.add_column("Ext Ref", no_wrap=True)
    if has_blocked:
        table.add_column("Blocked By", no_wrap=False)
    return table


def _row_status(
    issue: Issue, blocked_ids: set[str] | None, *, dimmed: bool
) -> tuple[str, str]:
    """Pick the status emoji and color for an issue row."""
    if (
        blocked_ids
        and issue.full_id in blocked_ids
        and issue.status not in _BLOCKED_DISPLAY_EXEMPT
    ):
        emoji, status_color = "■", STATUS_COLORS.get("blocked", "white")
    else:
        emoji = issue.get_status_emoji()
        status_color = STATUS_COLORS.get(issue.status.value, "white")
    if dimmed:
        status_color = "bright_black"
    return emoji, status_color


def _hidden_subtask_suffix(
    issue: Issue,
    hidden_counts: dict[str, int] | None,
    preview_subtasks: dict[str, list[Issue]] | None,
) -> str:
    """Suffix shown on deferred parents that have hidden descendants."""
    has_previews = preview_subtasks is not None and issue.full_id in preview_subtasks
    if has_previews or not hidden_counts or issue.full_id not in hidden_counts:
        return ""
    return f" [yellow]\\[{hidden_counts[issue.full_id]} hidden subtasks][/]"


def _blocked_by_cell(
    issue: Issue,
    blocked_by_map: dict[str, list[str]] | None,
    deferred_blocker_map: dict[str, list[str]] | None,
) -> str:
    """Render the contents of the 'Blocked By' column for one issue."""
    blockers = (
        ", ".join(blocked_by_map[issue.full_id])
        if blocked_by_map and issue.full_id in blocked_by_map
        else ""
    )
    deferred_suffix = (
        f"[bright_black]{', '.join(deferred_blocker_map[issue.full_id])} (deferred)[/]"
        if deferred_blocker_map and issue.full_id in deferred_blocker_map
        else ""
    )
    if blockers and deferred_suffix:
        return f"[red]{blockers}[/] {deferred_suffix}"
    if blockers:
        return f"[red]{blockers}[/]"
    return deferred_suffix


def _add_issue_row(
    table: Table,
    issue: Issue,
    *,
    dimmed: bool = False,
    blocked_ids: set[str] | None = None,
    blocked_by_map: dict[str, list[str]] | None = None,
    hidden_counts: dict[str, int] | None = None,
    deferred_blocker_map: dict[str, list[str]] | None = None,
    preview_subtasks: dict[str, list[Issue]] | None = None,
    has_ext_ref: bool = False,
    has_blocked: bool = False,
) -> None:
    """Add a single issue as a row to the table."""
    from rich.markup import escape

    emoji, status_color = _row_status(issue, blocked_ids, dimmed=dimmed)
    priority_color = (
        "bright_black"
        if dimmed
        else f"bold {PRIORITY_COLORS.get(issue.priority, 'white')}"
    )
    issue_type = issue.issue_type.value
    type_color = "bright_black" if dimmed else TYPE_COLORS.get(issue_type, "white")

    parent_id = ""
    if issue.parent:
        parent_id = (
            issue.parent.split("-", 1)[-1] if "-" in issue.parent else issue.parent
        )

    labels_str = ", ".join(escape(lbl) for lbl in issue.labels) if issue.labels else ""
    manual_str = (
        " [yellow]\\[manual][/]"
        if issue.metadata.get("manual") or issue.metadata.get("no_agent")
        else ""
    )
    hidden_suffix = _hidden_subtask_suffix(issue, hidden_counts, preview_subtasks)

    title_text = escape(issue.title)
    if dimmed:
        title_text = f"[bright_black]{title_text}[/]"

    row: list[str] = [
        f"[{status_color}]{emoji}[/]",
        f"[bright_black]{issue.id}[/]" if dimmed else issue.id,
        f"[bright_black]{parent_id}[/]" if dimmed else parent_id,
        f"[{type_color}]{issue_type}[/]",
        f"[{priority_color}]{issue.priority}[/]",
        f"{title_text}{manual_str}{hidden_suffix}",
        f"[cyan]{labels_str}[/]" if labels_str else "",
    ]
    if has_ext_ref:
        ref = escape(issue.external_ref) if issue.external_ref else ""
        row.append(f"[bright_black]{ref}[/]" if ref else "")
    if has_blocked:
        row.append(_blocked_by_cell(issue, blocked_by_map, deferred_blocker_map))
    table.add_row(*row)


def _add_summary_row(
    table: Table, remaining: int, *, has_ext_ref: bool, has_blocked: bool
) -> None:
    """Add a summary row counting hidden subtasks beyond the previews shown."""
    num_cols_before_title = 5  # emoji, ID, Parent, Type, Pri
    num_cols_after_title = 1 + int(has_ext_ref) + int(has_blocked)  # Labels + extras
    row = [""] * num_cols_before_title
    row.append(f"[yellow]\\[...and {remaining} more hidden subtasks][/]")
    row.extend([""] * num_cols_after_title)
    table.add_row(*row)


def format_issue_table(
    issues: list[Issue],
    blocked_ids: set[str] | None = None,
    blocked_by_map: dict[str, list[str]] | None = None,
    hidden_counts: dict[str, int] | None = None,
    deferred_blocker_map: dict[str, list[str]] | None = None,
    preview_subtasks: dict[str, list[Issue]] | None = None,
) -> str:
    """Format issues as an aligned table with columns using Rich.

    Args:
        issues: List of issues to format
        blocked_ids: Set of issue IDs that are blocked by dependencies
        blocked_by_map: Mapping of issue ID to list of blocking issue IDs
        hidden_counts: Deferred parent full_id -> count of hidden descendants
        deferred_blocker_map: Issue full_id -> list of deferred blocker IDs
        preview_subtasks: Deferred parent full_id -> list of preview child issues

    Returns:
        Formatted table string (rendered by Rich)
    """
    from io import StringIO

    from rich.console import Console

    if not issues:
        return ""

    has_ext_ref = any(issue.external_ref for issue in issues)
    has_blocked = bool(
        blocked_ids and any(issue.full_id in blocked_ids for issue in issues),
    )

    table = _build_issue_table(has_ext_ref=has_ext_ref, has_blocked=has_blocked)

    def _add(issue: Issue, *, dimmed: bool = False) -> None:
        _add_issue_row(
            table,
            issue,
            dimmed=dimmed,
            blocked_ids=blocked_ids,
            blocked_by_map=blocked_by_map,
            hidden_counts=hidden_counts,
            deferred_blocker_map=deferred_blocker_map,
            preview_subtasks=preview_subtasks,
            has_ext_ref=has_ext_ref,
            has_blocked=has_blocked,
        )

    for issue in issues:
        _add(issue)
        if preview_subtasks and issue.full_id in preview_subtasks:
            previews = preview_subtasks[issue.full_id]
            for preview in previews:
                _add(preview, dimmed=True)
            total = hidden_counts.get(issue.full_id, 0) if hidden_counts else 0
            remaining = total - len(previews)
            if remaining > 0:
                _add_summary_row(
                    table,
                    remaining,
                    has_ext_ref=has_ext_ref,
                    has_blocked=has_blocked,
                )

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

    # Derive current status and show its symbol (skip when redundant with event symbol)
    current_status: str | None = None
    if "status" in event.changes:
        current_status = event.changes["status"].get("new")
    elif event.event_type == "created":
        current_status = "open"

    if current_status and STATUS_SYMBOLS.get(current_status, "") != symbol:
        status_sym = STATUS_SYMBOLS.get(current_status, "")
        status_color = STATUS_COLORS.get(current_status, "white")
        styled_status = typer.style(status_sym, fg=status_color, bold=True)
        styled_symbol = f"{styled_symbol} {styled_status}"

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

    # Long-form fields: show summary instead of full content unless verbose
    _long_fields = {"description", "notes", "acceptance", "design"}

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
        field_styled = typer.style(field_name, fg="cyan")
        if not verbose and field_name in _long_fields:
            if old is not None and new is not None:
                # Both exist: show "(edited)" instead of "changed -> changed"
                edited = typer.style("(edited)", fg="yellow")
                change_parts.append(f"{field_styled}: {edited}")
            elif new is not None:
                added = typer.style("(added)", fg="green")
                change_parts.append(f"{field_styled}: {added}")
            else:
                removed = typer.style("(removed)", fg="red")
                change_parts.append(f"{field_styled}: {removed}")
        elif old is None:
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
    event_items = "+ Created  ~ Updated  \u2713 Closed  \u2717 Deleted"
    status_items = "  ".join(
        f"{sym} {name.replace('_', ' ').title()}"
        for name, sym in STATUS_SYMBOLS.items()
        if name != "tombstone"
    )
    return f"\nEvent: {event_items}\nStatus: {status_items}"
