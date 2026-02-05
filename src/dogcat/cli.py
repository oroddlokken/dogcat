"""Dogcat CLI commands for issue tracking."""

from __future__ import annotations

import getpass
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import orjson
import typer

from dogcat.config import get_issue_prefix, set_issue_prefix
from dogcat.constants import (
    ALL_SHORTHANDS,
    DEFAULT_PRIORITY,
    DEFAULT_TYPE,
    PRIORITY_COLORS,
    PRIORITY_SHORTHANDS,
    TYPE_COLORS,
    TYPE_SHORTHANDS,
)
from dogcat.idgen import IDGenerator
from dogcat.models import Issue, IssueType, Status
from dogcat.storage import JSONLStorage

app = typer.Typer(
    help="Dogcat - Python issue tracking for Git projects",
    no_args_is_help=True,
)


def get_default_operator() -> str:
    """Get the default operator (user identifier) for issue operations.

    Tries to get the git config user.email first, falls back to machine username.

    Returns:
        User email from git config, or machine username as fallback.
    """
    try:
        result = subprocess.run(
            ["git", "config", "user.email"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, OSError):
        # git not installed or other OS error
        pass

    return getpass.getuser()


def find_dogcats_dir(start_dir: str | None = None) -> str:
    """Find .dogcats directory by searching upward from start_dir.

    Similar to how git finds .git directories.

    Args:
        start_dir: Directory to start searching from (default: current directory)

    Returns:
        Path to .dogcats directory, or ".dogcats" if not found
    """
    current = Path.cwd() if start_dir is None else Path(start_dir).resolve()

    while True:
        candidate = current / ".dogcats"
        if candidate.is_dir():
            return str(candidate)

        parent = current.parent
        if parent == current:
            # Reached filesystem root, not found
            return ".dogcats"
        current = parent


def get_storage(
    dogcats_dir: str = ".dogcats",
    create_dir: bool = False,
) -> JSONLStorage:
    """Get or create storage instance.

    If dogcats_dir doesn't exist in current directory, searches upward
    to find it (similar to how git finds .git).

    Args:
        dogcats_dir: Path to .dogcats directory.
        create_dir: If True, create the directory if it doesn't exist.

    Returns:
        JSONLStorage instance
    """
    # If not creating and the path doesn't exist locally, search upward
    if not create_dir and not Path(dogcats_dir).is_dir():
        dogcats_dir = find_dogcats_dir()
    return JSONLStorage(f"{dogcats_dir}/issues.jsonl", create_dir=create_dir)


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
) -> str:
    """Format issue for brief display with color coding.

    Args:
        issue: The issue to format
        blocked_ids: Set of issue IDs that are blocked by dependencies

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

    parent_str = f" [parent: {issue.parent}]" if issue.parent else ""
    base = f"{status_emoji} {priority_str} {issue.full_id}: {issue.title} {type_str}"

    return f"{base}{parent_str}"


def format_issue_full(issue: Issue) -> str:
    """Format issue for full display."""
    lines = [
        f"ID: {issue.full_id}",
        f"Title: {issue.title}",
        f"Status: {issue.status.value}",
        f"Priority: {issue.priority}",
        f"Type: {issue.issue_type.value}",
    ]

    if issue.parent:
        lines.append(f"Parent: {issue.parent}")
    if issue.description:
        lines.append(f"Description: {issue.description}")
    if issue.owner:
        lines.append(f"Owner: {issue.owner}")
    if issue.labels:
        lines.append(f"Labels: {', '.join(issue.labels)}")
    if issue.duplicate_of:
        lines.append(f"Duplicate of: {issue.duplicate_of}")
    if issue.acceptance:
        lines.append(f"Acceptance: {issue.acceptance}")
    if issue.notes:
        lines.append(f"Notes: {issue.notes}")

    lines.append(f"Created: {issue.created_at.isoformat()}")
    if issue.closed_at:
        lines.append(f"Closed: {issue.closed_at.isoformat()}")

    if issue.comments:
        lines.append("\nComments:")
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
) -> str:
    """Format issues as a tree based on parent-child relationships.

    Args:
        issues: List of issues to format
        _indent: Current indentation level (unused, kept for compatibility)
        blocked_ids: Set of issue IDs that are blocked by dependencies

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
            formatted = format_issue_brief(issue, blocked_ids)
            lines.append(f"{indent_str}{formatted}")
            # Recursively format children
            lines.extend(format_recursive(issue.full_id, depth + 1))

        return lines

    lines = format_recursive(None, 0)
    return "\n".join(lines)


def format_issue_table(
    issues: list[Issue],
    blocked_ids: set[str] | None = None,
) -> str:
    """Format issues as an aligned table with columns using Rich.

    Args:
        issues: List of issues to format
        blocked_ids: Set of issue IDs that are blocked by dependencies

    Returns:
        Formatted table string (rendered by Rich)
    """
    from io import StringIO

    from rich import box
    from rich.console import Console
    from rich.table import Table

    if not issues:
        return ""

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

        table.add_row(
            emoji,
            issue.id,
            parent_id,
            f"[{type_color}]{issue_type}[/]",
            f"[{priority_color}]{issue.priority}[/]",
            issue.title,
        )

    # Render to string
    string_io = StringIO()
    console = Console(file=string_io, force_terminal=True, width=None)
    console.print(table)

    return string_io.getvalue().rstrip()


@app.command()
def init(
    prefix: str | None = typer.Option(
        None,
        "--prefix",
        "-p",
        help="Issue prefix (default: auto-detect from directory name)",
    ),
    dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
) -> None:
    """Initialize a new Dogcat repository.

    If --prefix is not specified, the prefix is auto-detected from the
    directory name (e.g., folder 'myproject' -> prefix 'myproject').
    """
    dogcats_path = Path(dogcats_dir)

    # Use storage with create_dir=True to initialize the directory
    get_storage(dogcats_dir, create_dir=True)

    # Create empty issues file if it doesn't exist
    issues_file = dogcats_path / "issues.jsonl"
    if not issues_file.exists():
        issues_file.touch()
        typer.echo(f"✓ Created {issues_file}")
    else:
        typer.echo(f"✓ {issues_file} already exists")

    # Determine and save the issue prefix
    if prefix is None:
        # Auto-detect from directory name
        project_dir = dogcats_path.resolve().parent
        prefix = project_dir.name
        # Sanitize: only allow alphanumeric and hyphens
        prefix = "".join(c if c.isalnum() or c == "-" else "-" for c in prefix.lower())
        prefix = prefix.strip("-")
        if not prefix:
            prefix = "dc"  # Fallback to default

    # Strip trailing hyphens (the hyphen is added during ID generation)
    prefix = prefix.rstrip("-")

    # Save prefix to config
    set_issue_prefix(dogcats_dir, prefix)
    typer.echo(f"✓ Set issue prefix: {prefix}")

    typer.echo(f"\n✓ Dogcat repository initialized in {dogcats_dir}")
    typer.echo(f"  Issues will be named: {prefix}-<hash> (e.g., {prefix}-a3f2)")


@app.command("import-beads")
def import_beads(
    beads_jsonl: str = typer.Argument(..., help="Path to beads issues.jsonl file"),
    dogcats_dir: str = typer.Option(
        ".dogcats",
        help="Output directory for dogcat (will be created)",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Import into existing project (merge issues, keep current prefix)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show import progress",
    ),
) -> None:
    """Import issues from beads format into dogcat.

    By default, requires a fresh project (no existing issues.jsonl).
    Use --force to import into an existing project (merges issues, skips duplicates).
    """
    try:
        from dogcat.migrate import migrate_from_beads

        # Check if dogcat project already exists
        dogcats_path = Path(dogcats_dir)
        issues_file = dogcats_path / "issues.jsonl"
        has_existing_project = issues_file.exists()
        has_existing_data = has_existing_project and issues_file.stat().st_size > 0

        if has_existing_data:
            if force:
                # Merge mode: import into existing project
                if verbose:
                    typer.echo("Importing into existing project (merge mode)...")
            else:
                typer.echo(
                    "Error: .dogcats/issues.jsonl already exists.\n"
                    "  Use --force to import into existing project (merge)",
                    err=True,
                )
                raise typer.Exit(1)

        # When --force is used on existing project, merge (even if empty)
        merge_mode = force and has_existing_project

        # Perform import
        migrated, failed, skipped = migrate_from_beads(
            beads_jsonl,
            dogcats_dir,
            verbose=verbose,
            merge=merge_mode,
        )

        # Only set prefix if this is a fresh import (not merging)
        if migrated > 0 and not merge_mode:
            storage = get_storage(dogcats_dir)
            all_issues = storage.list()
            if all_issues:
                # Sort by created_at descending to get newest
                sorted_issues = sorted(
                    all_issues,
                    key=lambda i: i.created_at,
                    reverse=True,
                )
                newest_issue = sorted_issues[0]
                detected_prefix = newest_issue.namespace
                if detected_prefix:
                    set_issue_prefix(dogcats_dir, detected_prefix)
                    typer.echo(f"✓ Set issue prefix: {detected_prefix}")

        typer.echo("\n✓ Import complete!")
        typer.echo(f"  Imported: {migrated} issues")
        if skipped > 0:
            typer.echo(f"  Skipped (already exist): {skipped} issues")
        if failed > 0:
            typer.echo(f"  Failed: {failed} issues")

    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


def _is_priority_shorthand(value: str) -> bool:
    """Check if a string is a priority shorthand (single char: 0-4)."""
    return len(value) == 1 and value in PRIORITY_SHORTHANDS


def _is_type_shorthand(value: str) -> bool:
    """Check if a string is a type shorthand (single char: b/f/e/s)."""
    return len(value) == 1 and value.lower() in TYPE_SHORTHANDS


def _is_shorthand(value: str) -> bool:
    """Check if a string is any shorthand (priority or type)."""
    return _is_priority_shorthand(value) or _is_type_shorthand(value)


def _is_invalid_single_char(value: str) -> bool:
    """Check if a value is a single char that's not a valid shorthand."""
    return len(value) == 1 and value.lower() not in ALL_SHORTHANDS


def _parse_args_for_create(
    args: list[str | None],
) -> tuple[str, int | None, str | None]:
    """Parse positional arguments to extract title, priority, and type shorthand.

    Returns:
        (title, priority_shorthand, type_shorthand)
    Raises: ValueError if arguments are ambiguous or invalid.
    """
    title_parts: list[str] = []
    priority_sh = None
    type_sh = None

    for arg in args:
        if arg is None:
            continue
        if _is_priority_shorthand(arg) and priority_sh is None:
            priority_sh = int(arg)
        elif _is_type_shorthand(arg) and type_sh is None:
            type_sh = TYPE_SHORTHANDS[arg.lower()]
        elif _is_invalid_single_char(arg):
            valid_types = ", ".join(sorted(TYPE_SHORTHANDS.keys()))
            msg = (
                f"Invalid shorthand '{arg}'. "
                f"Valid priority: 0-4, valid type: {valid_types}"
            )
            raise ValueError(
                msg,
            )
        else:
            title_parts.append(arg)

    title = " ".join(title_parts) if title_parts else ""

    # Validate: title must not be a single-char shorthand (ambiguous)
    # e.g., "dcat c b 0 b" would make second "b" the title, which is confusing
    if title and len(title) == 1 and _is_shorthand(title):
        msg = (
            f"Ambiguous arguments: '{title}' looks like a shorthand "
            "but was used as title. Use a longer title or explicit "
            "--type/--priority options."
        )
        raise ValueError(msg)

    return title, priority_sh, type_sh


@app.command()
def create(
    arg1: str = typer.Argument(
        ...,
        help="Title or shorthand (0-4 for priority, b/f/e/s for type)",
    ),
    arg2: str | None = typer.Argument(
        None,
        help="Title or shorthand (0-4 for priority, b/f/e/s for type)",
    ),
    arg3: str | None = typer.Argument(
        None,
        help="Title or shorthand (0-4 for priority, b/f/e/s for type)",
    ),
    description: str | None = typer.Option(
        None,
        "--description",
        "-d",
        help="Issue description",
    ),
    priority: int | None = typer.Option(
        None,
        "--priority",
        "-p",
        help="Priority (0-4, default 2)",
    ),
    issue_type: str | None = typer.Option(None, "--type", "-t", help="Issue type"),
    status: str | None = typer.Option(
        None,
        "--status",
        "-s",
        help="Initial status (open, in_progress, blocked, deferred)",
    ),
    owner: str | None = typer.Option(None, "--owner", "-o", help="Issue owner"),
    labels: str | None = typer.Option(
        None,
        "--labels",
        "-l",
        help="Comma-separated labels",
    ),
    acceptance: str | None = typer.Option(
        None,
        "--acceptance",
        "-a",
        help="Acceptance criteria",
    ),
    notes: str | None = typer.Option(
        None,
        "--notes",
        "-n",
        help="Notes for the issue",
    ),
    depends_on: str | None = typer.Option(
        None,
        "--depends-on",
        help="Issue ID this depends on (this issue is blocked by the other)",
    ),
    blocks: str | None = typer.Option(
        None,
        "--blocks",
        help="Issue ID this blocks (the other issue is blocked by this one)",
    ),
    parent: str | None = typer.Option(
        None,
        "--parent",
        help="Parent issue ID (makes this a subtask)",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    created_by: str | None = typer.Option(
        None,
        "--created-by",
        help="Who is creating this",
    ),
    skip_agent: bool = typer.Option(
        False,
        "--skip-agent",
        help="Mark issue to be skipped by agents",
    ),
    dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
) -> None:
    """Create a new issue.

    Supports shorthand notation: use single characters (0-4 for priority,
    b/f/e/s for bug/feature/epic/story) before or after the title.

    Examples:
        dcat create "Fix login bug"         # Default priority 2, type task
        dcat create "Fix login bug" 1       # Priority 1
        dcat create 1 "Fix login bug"       # Priority 1 (shorthand first)
        dcat create "Add feature" f         # Type feature
        dcat create b "Fix crash"           # Type bug (shorthand first)
        dcat create 0 b "Critical bug"      # Priority 0, type bug
        dcat create b 1 "Important bug"     # Type bug, priority 1
    """
    try:
        # Parse arguments to extract title and shorthands
        title, shorthand_priority, shorthand_type = _parse_args_for_create(
            [arg1, arg2, arg3],
        )

        # Validate that shorthands and explicit options aren't used together
        if shorthand_priority is not None and priority is not None:
            typer.echo(
                "Error: Cannot use both priority shorthand (0-4) and "
                "--priority flag together",
                err=True,
            )
            raise typer.Exit(1)
        if shorthand_type is not None and issue_type is not None:
            typer.echo(
                "Error: Cannot use both type shorthand (b/f/e/s/q) and "
                "--type flag together",
                err=True,
            )
            raise typer.Exit(1)

        if not title:
            typer.echo("Error: Title is required", err=True)
            raise typer.Exit(1)

        storage = get_storage(dogcats_dir)

        # Get namespace from config
        namespace = get_issue_prefix(dogcats_dir)
        idgen = IDGenerator(existing_ids=storage.get_issue_ids(), prefix=namespace)

        # Generate ID hash
        timestamp = datetime.now().astimezone()
        issue_id = idgen.generate_issue_id(
            title,
            timestamp=timestamp,
            namespace=namespace,
        )

        # Parse labels
        issue_labels = [lbl.strip() for lbl in labels.split(",")] if labels else []

        # Determine final priority and type (explicit options override shorthand)
        final_priority = (
            priority
            if priority is not None
            else (
                shorthand_priority
                if shorthand_priority is not None
                else DEFAULT_PRIORITY
            )
        )
        final_type = (
            issue_type
            if issue_type is not None
            else (shorthand_type if shorthand_type is not None else DEFAULT_TYPE)
        )

        # Determine initial status
        initial_status = Status(status) if status else Status.OPEN

        # Build metadata
        issue_metadata: dict[str, Any] = {}
        if skip_agent:
            issue_metadata["skip_agent"] = True

        # Set default operator for owner and created_by if not provided
        default_operator = get_default_operator()
        final_owner = owner if owner is not None else default_operator
        final_created_by = created_by if created_by is not None else default_operator

        # Validate dependency targets exist BEFORE creating the issue (atomic operation)
        if depends_on:
            resolved_depends_on = storage.resolve_id(depends_on)
            if resolved_depends_on is None:
                typer.echo(f"Error: Issue {depends_on} not found", err=True)
                raise typer.Exit(1)
        if blocks:
            resolved_blocks = storage.resolve_id(blocks)
            if resolved_blocks is None:
                typer.echo(f"Error: Issue {blocks} not found", err=True)
                raise typer.Exit(1)

        # Resolve parent if provided
        if parent:
            resolved_parent = storage.resolve_id(parent)
            if resolved_parent is None:
                typer.echo(f"Error: Parent issue {parent} not found", err=True)
                raise typer.Exit(1)
            parent = resolved_parent

        # Create issue
        issue = Issue(
            id=issue_id,
            title=title,
            namespace=namespace,
            description=description,
            status=initial_status,
            priority=final_priority,
            issue_type=IssueType(final_type),
            owner=final_owner,
            parent=parent,
            labels=issue_labels,
            acceptance=acceptance,
            notes=notes,
            created_by=final_created_by,
            metadata=issue_metadata,
        )

        storage.create(issue)

        # Add dependencies if specified
        if depends_on:
            storage.add_dependency(
                issue.full_id,
                depends_on,
                "blocks",
                created_by=created_by,
            )
        if blocks:
            storage.add_dependency(
                blocks,
                issue.full_id,
                "blocks",
                created_by=created_by,
            )

        if json_output:
            from dogcat.models import issue_to_dict

            typer.echo(orjson.dumps(issue_to_dict(issue)).decode())
        else:
            typer.echo(
                f"✓ Created {issue.full_id}: {title} "
                f"[{final_type}, pri {final_priority}]",
            )

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except typer.Exit:
        raise  # Re-raise without duplicate error message
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command(name="c")
def create_alias(
    arg1: str = typer.Argument(
        ...,
        help="Title or shorthand (0-4 for priority, b/f/e/s for type)",
    ),
    arg2: str = typer.Argument(
        None,
        help="Title or shorthand (0-4 for priority, b/f/e/s for type)",
    ),
    arg3: str = typer.Argument(
        None,
        help="Title or shorthand (0-4 for priority, b/f/e/s for type)",
    ),
    description: str = typer.Option(
        None,
        "--description",
        "-d",
        help="Issue description",
    ),
    priority: int = typer.Option(
        None,
        "--priority",
        "-p",
        help="Priority (0-4, default 2)",
    ),
    issue_type: str = typer.Option(None, "--type", "-t", help="Issue type"),
    status: str = typer.Option(
        None,
        "--status",
        "-s",
        help="Initial status (open, in_progress, blocked, deferred)",
    ),
    owner: str = typer.Option(None, "--owner", "-o", help="Issue owner"),
    labels: str = typer.Option(None, "--labels", "-l", help="Comma-separated labels"),
    acceptance: str = typer.Option(
        None,
        "--acceptance",
        "-a",
        help="Acceptance criteria",
    ),
    notes: str = typer.Option(
        None,
        "--notes",
        "-n",
        help="Notes for the issue",
    ),
    depends_on: str = typer.Option(
        None,
        "--depends-on",
        help="Issue ID this depends on (this issue is blocked by the other)",
    ),
    blocks: str = typer.Option(
        None,
        "--blocks",
        help="Issue ID this blocks (the other issue is blocked by this one)",
    ),
    parent: str = typer.Option(
        None,
        "--parent",
        help="Parent issue ID (makes this a subtask)",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    created_by: str = typer.Option(None, "--created-by", help="Who is creating this"),
    skip_agent: bool = typer.Option(
        False,
        "--skip-agent",
        help="Mark issue to be skipped by agents",
    ),
    dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
) -> None:
    """Create a new issue (alias for 'create' command).

    Supports shorthand notation: use single characters (0-4 for priority,
    b/f/e/s for bug/feature/epic/story) before or after the title.

    Examples:
        dcat c "Fix login bug"           # Default priority 2, type task
        dcat c "Fix login bug" 1         # Priority 1
        dcat c 0 b "Critical bug"        # Priority 0, type bug
    """
    create(
        arg1=arg1,
        arg2=arg2,
        arg3=arg3,
        description=description,
        priority=priority,
        issue_type=issue_type,
        status=status,
        owner=owner,
        labels=labels,
        acceptance=acceptance,
        notes=notes,
        depends_on=depends_on,
        blocks=blocks,
        parent=parent,
        json_output=json_output,
        created_by=created_by,
        skip_agent=skip_agent,
        dogcats_dir=dogcats_dir,
    )


@app.command("list")
def list_issues(
    status: str | None = typer.Option(None, "--status", "-s", help="Filter by status"),
    priority: int | None = typer.Option(
        None,
        "--priority",
        "-p",
        help="Filter by priority",
    ),
    issue_type: str | None = typer.Option(None, "--type", "-t", help="Filter by type"),
    label: str | None = typer.Option(None, "--label", "-l", help="Filter by label"),
    owner: str | None = typer.Option(None, "--owner", "-o", help="Filter by owner"),
    closed: bool = typer.Option(False, "--closed", help="Show only closed issues"),
    open_issues: bool = typer.Option(
        False,
        "--open",
        help="Show only open/in-progress issues",
    ),
    all_issues: bool = typer.Option(
        False,
        "--all",
        help="Include archived and deleted issues",
    ),
    closed_after: str | None = typer.Option(
        None,
        "--closed-after",
        help="Issues closed after date (ISO8601)",
    ),
    closed_before: str | None = typer.Option(
        None,
        "--closed-before",
        help="Issues closed before date (ISO8601)",
    ),
    limit: int | None = typer.Option(None, "--limit", help="Limit results"),
    exclude_skip_agent: bool = typer.Option(
        False,
        "--exclude-skip-agent",
        help="Exclude issues marked to be skipped by agents",
    ),
    tree: bool = typer.Option(
        False,
        "--tree",
        help="Display issues as a tree hierarchy based on parent-child relationships",
    ),
    table: bool = typer.Option(
        False,
        "--table",
        help="Display issues in aligned columns",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
) -> None:
    """List issues with optional filters."""
    try:
        storage = get_storage(dogcats_dir)

        # Build filters
        filters: dict[str, Any] = {}
        if status:
            filters["status"] = status
        elif closed:
            filters["status"] = "closed"
        # Note: open_issues is handled after storage.list to filter multiple statuses

        if priority is not None:
            filters["priority"] = priority
        if issue_type:
            filters["type"] = issue_type
        if label:
            filters["label"] = label
        if owner:
            filters["owner"] = owner

        issues = storage.list(filters if filters else None)

        # Exclude closed/tombstone issues by default (unless explicitly requested)
        # Also include closed issues when date filters are used
        if (
            not status
            and not closed
            and not all_issues
            and not (closed_after or closed_before)
        ):
            issues = [
                i for i in issues if i.status.value not in ("closed", "tombstone")
            ]

        # Handle --open filter for multiple statuses
        if open_issues:
            issues = [i for i in issues if i.status.value in ("open", "in_progress")]

        # Filter out skip_agent issues if requested
        if exclude_skip_agent:
            issues = [i for i in issues if not i.metadata.get("skip_agent")]

        # Apply date-based filtering for closed issues
        if closed_after or closed_before:
            try:
                from datetime import datetime as dt

                filtered_issues: list[Issue] = []
                for issue in issues:
                    if issue.closed_at:
                        should_include = True

                        if closed_after:
                            after_dt = dt.fromisoformat(closed_after)
                            # Make timezone-naive dates UTC-aware for comparison
                            if after_dt.tzinfo is None:
                                after_dt = after_dt.replace(tzinfo=UTC)
                            if issue.closed_at < after_dt:
                                should_include = False

                        if closed_before and should_include:
                            before_dt = dt.fromisoformat(closed_before)
                            # Make timezone-naive dates UTC-aware for comparison
                            if before_dt.tzinfo is None:
                                before_dt = before_dt.replace(tzinfo=UTC)
                            if issue.closed_at > before_dt:
                                should_include = False

                        if should_include:
                            filtered_issues.append(issue)

                issues = filtered_issues
            except ValueError as e:
                typer.echo(f"Error parsing date: {e}", err=True)
                raise typer.Exit(1)

        # Sort by priority (lower number = higher priority)
        issues = sorted(issues, key=lambda i: (i.priority, i.id))

        if limit:
            issues = issues[:limit]

        # Validate mutually exclusive options
        if tree and table:
            typer.echo("Error: --tree and --table are mutually exclusive", err=True)
            raise typer.Exit(1)

        if json_output:
            from dogcat.models import issue_to_dict

            output = [issue_to_dict(issue) for issue in issues]
            typer.echo(orjson.dumps(output).decode())
        else:
            # Get blocked issue IDs to show correct status symbol
            from dogcat.deps import get_blocked_issues

            blocked_issues = get_blocked_issues(storage)
            blocked_ids = {bi.issue_id for bi in blocked_issues}

            if not issues:
                typer.echo("No issues found")
            elif tree:
                typer.echo(format_issue_tree(issues, blocked_ids=blocked_ids))
                typer.echo(get_legend())
            elif table:
                typer.echo(format_issue_table(issues, blocked_ids=blocked_ids))
                typer.echo(get_legend())
            else:
                for issue in issues:
                    typer.echo(format_issue_brief(issue, blocked_ids=blocked_ids))
                typer.echo(get_legend())

    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def show(
    issue_id: str = typer.Argument(..., help="Issue ID"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
) -> None:
    """Show details of a specific issue."""
    try:
        storage = get_storage(dogcats_dir)
        issue = storage.get(issue_id)

        if issue is None:
            typer.echo(f"Issue {issue_id} not found", err=True)
            raise typer.Exit(1)

        if json_output:
            from dogcat.models import issue_to_dict

            typer.echo(orjson.dumps(issue_to_dict(issue)).decode())
        else:
            output_lines = format_issue_full(issue).split("\n")

            # Add dependencies
            deps = storage.get_dependencies(issue_id)
            if deps:
                output_lines.append("\nDependencies:")
                for dep in deps:
                    output_lines.append(f"  → {dep.depends_on_id} ({dep.type.value})")

            # Add links
            links = storage.get_links(issue_id)
            incoming = storage.get_incoming_links(issue_id)
            if links or incoming:
                output_lines.append("\nLinks:")
                if links:
                    for link in links:
                        output_lines.append(f"  → {link.to_id} ({link.link_type})")
                if incoming:
                    for link in incoming:
                        output_lines.append(f"  ← {link.from_id} ({link.link_type})")

            # Add children
            children = storage.get_children(issue_id)
            if children:
                output_lines.append("\nChildren:")
                for child in children:
                    output_lines.append(f"  ↳ {child.id}: {child.title}")

            # Add metadata if present
            if issue.metadata:
                output_lines.append("\nMetadata:")
                for key, value in issue.metadata.items():
                    output_lines.append(f"  {key}: {value}")

            typer.echo("\n".join(output_lines))

    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def update(
    issue_id: str = typer.Argument(..., help="Issue ID"),
    title: str | None = typer.Option(None, "--title", help="New title"),
    status: str | None = typer.Option(None, "--status", "-s", help="New status"),
    priority: int | None = typer.Option(None, "--priority", "-p", help="New priority"),
    issue_type: str | None = typer.Option(None, "--type", "-t", help="New issue type"),
    description: str | None = typer.Option(
        None,
        "--description",
        "-d",
        help="New description",
    ),
    owner: str | None = typer.Option(None, "--owner", "-o", help="New owner"),
    acceptance: str | None = typer.Option(
        None,
        "--acceptance",
        "-a",
        help="New acceptance criteria",
    ),
    notes: str | None = typer.Option(None, "--notes", "-n", help="New notes"),
    duplicate_of: str | None = typer.Option(
        None,
        "--duplicate-of",
        help="Original issue ID if duplicate",
    ),
    parent: str | None = typer.Option(
        None,
        "--parent",
        help="Parent issue ID (makes this a subtask)",
    ),
    skip_agent: bool | None = typer.Option(
        None,
        "--skip-agent/--no-skip-agent",
        help="Mark/unmark issue to be skipped by agents",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    updated_by: str | None = typer.Option(
        None,
        "--updated-by",
        help="Who is updating this",
    ),
    dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
) -> None:
    """Update an issue."""
    try:
        storage = get_storage(dogcats_dir)

        # Build updates dict
        updates: dict[str, Any] = {}
        if title is not None:
            updates["title"] = title
        if status is not None:
            updates["status"] = status
        if priority is not None:
            updates["priority"] = priority
        if issue_type is not None:
            updates["issue_type"] = issue_type
        if description is not None:
            updates["description"] = description
        if owner is not None:
            updates["owner"] = owner
        if acceptance is not None:
            updates["acceptance"] = acceptance
        if notes is not None:
            updates["notes"] = notes
        if duplicate_of is not None:
            if duplicate_of == "":
                updates["duplicate_of"] = None
            else:
                resolved_dup = storage.resolve_id(duplicate_of)
                if resolved_dup is None:
                    typer.echo(f"Error: Issue {duplicate_of} not found", err=True)
                    raise typer.Exit(1)
                updates["duplicate_of"] = resolved_dup
        if parent is not None:
            if parent == "":
                updates["parent"] = None
            else:
                resolved_parent = storage.resolve_id(parent)
                if resolved_parent is None:
                    typer.echo(f"Error: Parent issue {parent} not found", err=True)
                    raise typer.Exit(1)
                updates["parent"] = resolved_parent
        if skip_agent is not None:
            # Get current issue to preserve existing metadata
            current = storage.get(issue_id)
            if current is None:
                typer.echo(f"Issue {issue_id} not found", err=True)
                raise typer.Exit(1)
            new_metadata = dict(current.metadata) if current.metadata else {}
            if skip_agent:
                new_metadata["skip_agent"] = True
            else:
                new_metadata.pop("skip_agent", None)
            updates["metadata"] = new_metadata

        if not updates:
            typer.echo("No updates provided", err=True)
            raise typer.Exit(1)

        # Set updated_by to default operator if not provided
        updates["updated_by"] = (
            updated_by if updated_by is not None else get_default_operator()
        )

        issue = storage.update(issue_id, updates)

        if json_output:
            from dogcat.models import issue_to_dict

            typer.echo(orjson.dumps(issue_to_dict(issue)).decode())
        else:
            typer.echo(f"✓ Updated {issue_id}: {issue.title}")

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def close(
    issue_id: str = typer.Argument(..., help="Issue ID"),
    reason: str | None = typer.Option(
        None,
        "--reason",
        "-r",
        help="Reason for closing",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    closed_by: str | None = typer.Option(
        None,
        "--closed-by",
        help="Who is closing this",
    ),
    dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
) -> None:
    """Close an issue."""
    try:
        storage = get_storage(dogcats_dir)
        issue = storage.close(issue_id, reason=reason)

        # Set closed_by to default operator if not provided
        final_closed_by = closed_by if closed_by is not None else get_default_operator()
        storage.update(issue_id, {"closed_by": final_closed_by})

        if json_output:
            from dogcat.models import issue_to_dict

            typer.echo(orjson.dumps(issue_to_dict(issue)).decode())
        else:
            typer.echo(f"✓ Closed {issue_id}: {issue.title}")

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def delete(
    issue_id: str = typer.Argument(..., help="Issue ID"),
    reason: str | None = typer.Option(
        None,
        "--reason",
        "-r",
        help="Reason for deletion",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    deleted_by: str | None = typer.Option(
        None,
        "--deleted-by",
        help="Who is deleting this",
    ),
    dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
) -> None:
    """Delete an issue (creates tombstone).

    This marks the issue as deleted (tombstone status) rather than permanently
    removing it from the database. The issue will be hidden from normal lists
    but can still be viewed with --all flag.
    """
    try:
        storage = get_storage(dogcats_dir)

        # Perform deletion (creates tombstone)
        deleted_issue = storage.delete(issue_id, reason=reason)

        # Set deleted_by to default operator if not provided
        final_deleted_by = (
            deleted_by if deleted_by is not None else get_default_operator()
        )
        storage.update(issue_id, {"deleted_by": final_deleted_by})

        if json_output:
            from dogcat.models import issue_to_dict

            typer.echo(orjson.dumps(issue_to_dict(deleted_issue)).decode())
        else:
            typer.echo(f"✓ Deleted {issue_id}: {deleted_issue.title}")

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command(name="remove")
def remove_cmd(
    issue_id: str = typer.Argument(..., help="Issue ID"),
    reason: str = typer.Option(None, "--reason", "-r", help="Reason for deletion"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    deleted_by: str = typer.Option(None, "--deleted-by", help="Who is deleting this"),
    dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
) -> None:
    """Delete an issue (alias for 'delete' command).

    This marks the issue as deleted (tombstone status) rather than permanently
    removing it from the database. The issue will be hidden from normal lists
    but can still be viewed with --all flag.
    """
    # Just call delete with the same parameters
    delete(
        issue_id=issue_id,
        reason=reason,
        json_output=json_output,
        deleted_by=deleted_by,
        dogcats_dir=dogcats_dir,
    )


@app.command()
def demo(
    dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force creation even if dogcats exists (dangerous)",
    ),
) -> None:
    """Generate demo issues for testing and exploration.

    Creates ~50 sample issues including epics, features, tasks, bugs, stories,
    and questions with various priorities, parent-child relationships, dependencies,
    labels, external references (Jira-style), and comments.

    The demo simulates a realistic team environment with:
    - Product Owner, Project Manager, Tech Lead, and Developers
    - Multiple epics with features, stories, and tasks
    - Bugs with reproduction steps and discussion
    - Questions with decisions and rationale
    - Full metadata: created_by, updated_by, closed_by, deleted_by

    Safety: By default, refuses to run if .dogcats already exists. Use --force
    to override (will add to existing issues).
    """
    from dogcat.demo import generate_demo_issues

    dogcats_path = Path(dogcats_dir)

    # Safety check: refuse to run if dogcats exists (unless --force)
    if dogcats_path.exists() and not force:
        typer.echo(
            "Error: .dogcats directory already exists. This command is for new "
            "projects only.",
            err=True,
        )
        typer.echo(
            "Use --force to add demo issues to an existing project (not recommended).",
            err=True,
        )
        raise typer.Exit(1)

    try:
        storage = get_storage(dogcats_dir, create_dir=True)
        typer.echo("Creating demo issues...")

        created_issues = generate_demo_issues(storage)

        typer.echo(f"\n✓ Created {len(created_issues)} demo issues")
        typer.echo("  - 3 epics (Platform, UX, Performance)")
        typer.echo("  - Features, stories, tasks, bugs, chores, and questions")
        typer.echo("  - With parent-child relationships and dependencies")
        typer.echo("  - Labels, external refs (Jira-style), and comments")
        typer.echo("  - Full metadata: created_by, updated_by, closed_by, deleted_by")
        typer.echo("\nTry: dcat list --table")

    except Exception as e:
        typer.echo(f"Error creating demo issues: {e}", err=True)
        raise typer.Exit(1)


@app.command("dep")
def dependency(
    issue_id: str = typer.Argument(..., help="Issue ID"),
    subcommand: str = typer.Argument(..., help="add, remove, or list"),
    depends_on_id: str = typer.Option(
        None,
        "--depends-on",
        "-d",
        help="Issue ID it depends on",
    ),
    dep_type: str = typer.Option("blocks", "--type", "-t", help="Dependency type"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    by: str = typer.Option(None, "--by", help="Who is making this change"),
    dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
) -> None:
    """Manage issue dependencies."""
    try:
        storage = get_storage(dogcats_dir)

        if subcommand == "add":
            if not depends_on_id:
                typer.echo("Error: --depends-on required for add", err=True)
                raise typer.Exit(1)

            dep = storage.add_dependency(
                issue_id,
                depends_on_id,
                dep_type,
                created_by=by,
            )
            typer.echo(
                f"✓ Added dependency: {depends_on_id} {dep.type.value} {issue_id}",
            )

        elif subcommand == "remove":
            if not depends_on_id:
                typer.echo("Error: --depends-on required for remove", err=True)
                raise typer.Exit(1)

            storage.remove_dependency(issue_id, depends_on_id)
            typer.echo(f"✓ Removed dependency: {issue_id} {depends_on_id}")

        elif subcommand == "list":
            deps = storage.get_dependencies(issue_id)

            if json_output:

                output = [
                    {
                        "issue_id": dep.issue_id,
                        "depends_on_id": dep.depends_on_id,
                        "type": dep.type.value,
                    }
                    for dep in deps
                ]
                typer.echo(orjson.dumps(output).decode())
            else:
                if deps:
                    for dep in deps:
                        typer.echo(f"  → {dep.depends_on_id} ({dep.type.value})")
                else:
                    typer.echo("No dependencies")
        else:
            typer.echo(f"Unknown subcommand: {subcommand}", err=True)
            raise typer.Exit(1)

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command("link")
def link_command(
    issue_id: str = typer.Argument(..., help="Issue ID"),
    subcommand: str = typer.Argument(..., help="add, remove, or list"),
    related_id: str = typer.Option(
        None,
        "--related",
        "-r",
        help="Issue ID to link to",
    ),
    link_type: str = typer.Option("relates_to", "--type", "-t", help="Link type"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    by: str = typer.Option(None, "--by", help="Who is making this change"),
    dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
) -> None:
    """Manage issue links (general relationships)."""
    try:
        storage = get_storage(dogcats_dir)

        if subcommand == "add":
            if not related_id:
                typer.echo("Error: --related required for add", err=True)
                raise typer.Exit(1)

            link = storage.add_link(
                issue_id,
                related_id,
                link_type,
                created_by=by,
            )
            typer.echo(
                f"✓ Added link: {issue_id} {link.link_type} {related_id}",
            )

        elif subcommand == "remove":
            if not related_id:
                typer.echo("Error: --related required for remove", err=True)
                raise typer.Exit(1)

            storage.remove_link(issue_id, related_id)
            typer.echo(f"✓ Removed link: {issue_id} {related_id}")

        elif subcommand == "list":
            links = storage.get_links(issue_id)
            incoming = storage.get_incoming_links(issue_id)

            if json_output:
                output = {
                    "outgoing": [
                        {
                            "from_id": link.from_id,
                            "to_id": link.to_id,
                            "type": link.link_type,
                        }
                        for link in links
                    ],
                    "incoming": [
                        {
                            "from_id": link.from_id,
                            "to_id": link.to_id,
                            "type": link.link_type,
                        }
                        for link in incoming
                    ],
                }
                typer.echo(orjson.dumps(output).decode())
            else:
                if links or incoming:
                    if links:
                        typer.echo("Outgoing links:")
                        for link in links:
                            typer.echo(f"  → {link.to_id} ({link.link_type})")
                    if incoming:
                        typer.echo("Incoming links:")
                        for link in incoming:
                            typer.echo(f"  ← {link.from_id} ({link.link_type})")
                else:
                    typer.echo("No links")
        else:
            typer.echo(f"Unknown subcommand: {subcommand}", err=True)
            raise typer.Exit(1)

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def ready(
    limit: int = typer.Option(None, "--limit", "-l", help="Limit results"),
    exclude_skip_agent: bool = typer.Option(
        False,
        "--exclude-skip-agent",
        help="Exclude issues marked to be skipped by agents",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
) -> None:
    """Show issues ready to work (no blocking dependencies)."""
    try:
        from dogcat.deps import get_ready_work

        storage = get_storage(dogcats_dir)
        ready_issues = get_ready_work(storage)

        if exclude_skip_agent:
            ready_issues = [i for i in ready_issues if not i.metadata.get("skip_agent")]

        if limit:
            ready_issues = ready_issues[:limit]

        if json_output:
            from dogcat.models import issue_to_dict

            output = [issue_to_dict(issue) for issue in ready_issues]
            typer.echo(orjson.dumps(output).decode())
        else:
            if not ready_issues:
                typer.echo("No ready work")
            else:
                for issue in ready_issues:
                    typer.echo(format_issue_brief(issue))

    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def blocked(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
) -> None:
    """Show all blocked issues."""
    try:
        from dogcat.deps import get_blocked_issues

        storage = get_storage(dogcats_dir)
        blocked_issues = get_blocked_issues(storage)

        if json_output:
            output = [
                {
                    "issue_id": bi.issue_id,
                    "blocking_ids": bi.blocking_ids,
                    "reason": bi.reason,
                }
                for bi in blocked_issues
            ]
            typer.echo(orjson.dumps(output).decode())
        else:
            if not blocked_issues:
                typer.echo("No blocked issues")
            else:
                for bi in blocked_issues:
                    blocker_list = ", ".join(bi.blocking_ids)
                    typer.echo(f"  {bi.issue_id}: blocked by {blocker_list}")

    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command("recently-closed")
def recently_closed(
    limit: int = typer.Option(10, "--limit", "-n", help="Number of issues to show"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
) -> None:
    """Show recently closed issues in ascending order (oldest first).

    Displays the last N closed issues sorted by closed_at date,
    with the most recently closed issue at the bottom.
    """
    try:
        storage = get_storage(dogcats_dir)
        issues = storage.list()

        # Filter to closed issues with closed_at date
        closed_issues = [
            i for i in issues if i.status.value == "closed" and i.closed_at
        ]

        # Sort by closed_at ascending (oldest first, newest last)
        closed_issues.sort(key=lambda i: i.closed_at)  # type: ignore[arg-type]

        # Take last N (most recent)
        recent = closed_issues[-limit:] if len(closed_issues) > limit else closed_issues

        if json_output:
            from dogcat.models import issue_to_dict

            output = [issue_to_dict(issue) for issue in recent]
            typer.echo(orjson.dumps(output).decode())
        else:
            if not recent:
                typer.echo("No recently closed issues")
            else:
                for issue in recent:
                    closed_str = (
                        issue.closed_at.strftime("%Y-%m-%d %H:%M")
                        if issue.closed_at
                        else ""
                    )
                    typer.echo(f"✓ [{closed_str}] {issue.full_id}: {issue.title}")
                    # Extract close reason from notes if present
                    if issue.notes and "Closed: " in issue.notes:
                        # Find the last "Closed: " entry
                        parts = issue.notes.split("Closed: ")
                        if len(parts) > 1:
                            reason = parts[-1].split("\n")[0].strip()
                            if reason:
                                typer.echo(f"    {reason}")
                    typer.echo()  # Blank line between issues

    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def prune(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="Show what would be removed without actually removing",
    ),
    dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
) -> None:
    """Remove tombstoned (deleted) issues from storage permanently.

    This command permanently removes issues with tombstone status from the
    storage file. Use --dry-run to preview what would be removed.
    """
    try:
        storage = get_storage(dogcats_dir)
        issues = storage.list()

        # Find tombstoned issues
        tombstones = [i for i in issues if i.status.value == "tombstone"]

        if not tombstones:
            typer.echo("No tombstoned issues to prune")
            return

        if dry_run:
            typer.echo(f"Would remove {len(tombstones)} tombstoned issue(s):")
            for issue in tombstones:
                typer.echo(f"  ☠ {issue.full_id}: {issue.title}")
        else:
            # Remove tombstones from storage using public API
            pruned_ids = storage.prune_tombstones()
            typer.echo(f"✓ Pruned {len(pruned_ids)} tombstoned issue(s)")

    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def stream(
    by: str = typer.Option(None, "--by", help="Attribution name for events"),
    dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
) -> None:
    """Stream issue changes in real-time (JSONL format).

    Watches for changes to issues and outputs events as JSONL lines.
    Press Ctrl+C to stop streaming.
    """
    try:
        from dogcat.stream import StreamWatcher

        storage_path = f"{dogcats_dir}/issues.jsonl"
        watcher = StreamWatcher(storage_path=storage_path, by=by)

        typer.echo("Streaming events... (Press Ctrl+C to stop)", err=True)
        watcher.stream()
        typer.echo("", err=True)

    except KeyboardInterrupt:
        typer.echo("", err=True)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def label(
    issue_id: str = typer.Argument(..., help="Issue ID"),
    subcommand: str = typer.Argument(..., help="add, remove, or list"),
    label_name: str = typer.Option(None, "--label", "-l", help="Label to add/remove"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    by: str = typer.Option(None, "--by", help="Who is managing labels"),
    dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
) -> None:
    """Manage issue labels."""
    try:
        storage = get_storage(dogcats_dir)

        if subcommand == "add":
            if not label_name:
                typer.echo("Error: --label required for add", err=True)
                raise typer.Exit(1)

            issue = storage.get(issue_id)
            if issue is None:
                typer.echo(f"Issue {issue_id} not found", err=True)
                raise typer.Exit(1)

            if label_name not in issue.labels:
                issue.labels.append(label_name)
                updates: dict[str, Any] = {"labels": issue.labels}
                if by:
                    updates["updated_by"] = by
                storage.update(issue_id, updates)
                typer.echo(f"✓ Added label '{label_name}' to {issue_id}")
            else:
                typer.echo(f"Label '{label_name}' already on {issue_id}")

        elif subcommand == "remove":
            if not label_name:
                typer.echo("Error: --label required for remove", err=True)
                raise typer.Exit(1)

            issue = storage.get(issue_id)
            if issue is None:
                typer.echo(f"Issue {issue_id} not found", err=True)
                raise typer.Exit(1)

            if label_name in issue.labels:
                issue.labels.remove(label_name)
                updates: dict[str, Any] = {"labels": issue.labels}
                if by:
                    updates["updated_by"] = by
                storage.update(issue_id, updates)
                typer.echo(f"✓ Removed label '{label_name}' from {issue_id}")
            else:
                typer.echo(f"Label '{label_name}' not on {issue_id}")

        elif subcommand == "list":
            issue = storage.get(issue_id)
            if issue is None:
                typer.echo(f"Issue {issue_id} not found", err=True)
                raise typer.Exit(1)

            if json_output:
                typer.echo(orjson.dumps(issue.labels).decode())
            else:
                if issue.labels:
                    for lbl in issue.labels:
                        typer.echo(f"  {lbl}")
                else:
                    typer.echo("No labels")
        else:
            typer.echo(f"Unknown subcommand: {subcommand}", err=True)
            raise typer.Exit(1)

    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def doctor(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    fix: bool = typer.Option(False, "--fix", help="Automatically fix issues"),
    dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
) -> None:
    """Diagnose dogcat installation and configuration.

    Performs health checks and suggests fixes for common issues.
    """
    import shutil

    checks: dict[str, dict[str, Any]] = {}
    all_passed = True

    # Check 1: .dogcats directory exists
    dogcats_path = Path(dogcats_dir)
    checks["dogcats_dir"] = {
        "description": f"{dogcats_dir}/ directory exists",
        "passed": dogcats_path.exists(),
        "fix": f"Run 'dogcat init' to create {dogcats_dir}",
    }
    if not checks["dogcats_dir"]["passed"]:
        all_passed = False

    # Check 2: issues.jsonl exists and is valid
    issues_file = dogcats_path / "issues.jsonl"
    issues_valid = False
    if issues_file.exists():
        try:
            with issues_file.open() as f:
                for line in f:
                    if line.strip():
                        orjson.loads(line)
            issues_valid = True
        except (OSError, orjson.JSONDecodeError):
            pass

    checks["issues_jsonl"] = {
        "description": f"{dogcats_dir}/issues.jsonl is valid JSON",
        "passed": issues_file.exists() and issues_valid,
        "fix": "Restore from backup or run 'dogcat init' to reset",
    }
    if not checks["issues_jsonl"]["passed"]:
        all_passed = False

    # Check 3: Git repository detected (informational only, not required)
    git_dir = Path(".git")
    checks["git_repo"] = {
        "description": "In a Git repository (optional)",
        "passed": git_dir.exists(),
        "fix": "Run 'git init' if you want git integration",
        "optional": True,
    }
    # Note: git repo is optional, so we don't set all_passed = False

    # Check 4: dogcat binary is in PATH
    dogcat_in_path = bool(shutil.which("dogcat"))
    checks["dogcat_in_path"] = {
        "description": "dogcat command is available in PATH",
        "passed": dogcat_in_path,
        "fix": "Ensure dogcat is installed and dogcat is in your PATH",
    }
    if not checks["dogcat_in_path"]["passed"]:
        all_passed = False

    # Check 5: Issue ID uniqueness
    issue_ids_unique = True
    if issues_file.exists() and issues_valid:
        try:
            storage = get_storage(dogcats_dir)
            issue_ids = list(storage._issues.keys())
            if len(issue_ids) != len(set(issue_ids)):
                issue_ids_unique = False
        except Exception:
            issue_ids_unique = False

    checks["issue_ids"] = {
        "description": "All issue IDs are unique",
        "passed": issue_ids_unique,
        "fix": "Manually review and fix duplicate IDs in issues.jsonl",
    }
    if not checks["issue_ids"]["passed"]:
        all_passed = False

    # Check 6: Dependency integrity
    deps_ok = True
    dangling_deps: list[Any] = []
    if issues_file.exists() and issues_valid:
        try:
            storage = get_storage(dogcats_dir)
            for dep in storage._dependencies:
                if (
                    dep.issue_id not in storage._issues
                    or dep.depends_on_id not in storage._issues
                ):
                    deps_ok = False
                    dangling_deps.append(dep)
        except Exception:
            deps_ok = False

    # Fix dangling dependencies if requested
    if fix and not deps_ok and dangling_deps:
        try:
            storage = get_storage(dogcats_dir)
            for dep in dangling_deps:
                storage._dependencies.remove(dep)
            storage._save()
            deps_ok = True
            typer.echo(
                f"Fixed: Removed {len(dangling_deps)} dangling dependency reference(s)",
            )
        except Exception as e:
            typer.echo(f"Error fixing dependencies: {e}")

    checks["dependencies"] = {
        "description": "Dependency references are valid",
        "fail_description": "Found dangling dependency references",
        "passed": deps_ok,
        "fix": "Run 'dogcat doctor --fix' to clean up invalid dependencies",
    }
    if not checks["dependencies"]["passed"]:
        all_passed = False

    # Output results
    if json_output:
        output_data = {
            "status": "ok" if all_passed else "issues_found",
            "checks": {
                name: {
                    "passed": check["passed"],
                    "description": check["description"],
                    "fix": check["fix"] if not check["passed"] else None,
                }
                for name, check in checks.items()
            },
        }
        typer.echo(orjson.dumps(output_data, option=orjson.OPT_INDENT_2).decode())
    else:
        # Human-readable output
        typer.echo("\nDogcat Health Check\n" + "=" * 40)
        for check in checks.values():
            is_optional = check.get("optional", False)
            if check["passed"]:
                status = "✓"
            elif is_optional:
                status = "○"  # Optional check not met (info only)
            else:
                status = "✗"
            desc = (
                check.get("fail_description", check["description"])
                if not check["passed"]
                else check["description"]
            )
            typer.echo(f"{status} {desc}")
            if not check["passed"] and not is_optional:
                typer.echo(f"  Fix: {check['fix']}")
        typer.echo("=" * 40)
        if all_passed:
            typer.echo("\n✓ All checks passed!")
        else:
            typer.echo("\n✗ Some checks failed. See above for fixes.")

    raise typer.Exit(0 if all_passed else 1)


@app.command()
def export(
    format_type: str = typer.Option(
        "json",
        "--format",
        "-f",
        help="Export format: json or jsonl",
    ),
    dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
) -> None:
    """Export all issues, dependencies, and links to stdout in specified format.

    Supported formats:
    - json: table-printed JSON object with issues, dependencies, and links
    - jsonl: JSON Lines (one record per line)
    """
    try:
        storage = get_storage(dogcats_dir)
        issues = storage.list()

        from dogcat.models import issue_to_dict

        # Get all dependencies and links
        all_deps: list[dict[str, Any]] = []
        all_links: list[dict[str, Any]] = []
        for issue in issues:
            deps = storage.get_dependencies(issue.full_id)
            all_deps.extend(
                {
                    "issue_id": dep.issue_id,
                    "depends_on_id": dep.depends_on_id,
                    "type": dep.type.value,
                    "created_at": dep.created_at.isoformat(),
                    "created_by": dep.created_by,
                }
                for dep in deps
            )
            links = storage.get_links(issue.full_id)
            all_links.extend(
                {
                    "from_id": link.from_id,
                    "to_id": link.to_id,
                    "link_type": link.link_type,
                    "created_at": link.created_at.isoformat(),
                    "created_by": link.created_by,
                }
                for link in links
            )

        if format_type == "json":
            # table-printed JSON object with all data
            output = {
                "issues": [issue_to_dict(issue) for issue in issues],
                "dependencies": all_deps,
                "links": all_links,
            }
            typer.echo(orjson.dumps(output, option=orjson.OPT_INDENT_2).decode())
        elif format_type == "jsonl":
            # JSON Lines format - one record per line
            for issue in issues:
                issue_dict = issue_to_dict(issue)
                typer.echo(orjson.dumps(issue_dict).decode())
            for dep in all_deps:
                typer.echo(orjson.dumps(dep).decode())
            for link in all_links:
                typer.echo(orjson.dumps(link).decode())
        else:
            typer.echo(f"Error: Unknown format '{format_type}'", err=True)
            typer.echo("Supported formats: json, jsonl", err=True)
            raise typer.Exit(1)

    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def comment(
    issue_id: str = typer.Argument(..., help="Issue ID"),
    action: str = typer.Argument(..., help="Action: add, list, or delete"),
    text: str = typer.Option(None, "--text", "-t", help="Comment text (for add)"),
    comment_id: str = typer.Option(
        None,
        "--comment-id",
        "-c",
        help="Comment ID (for delete)",
    ),
    author: str = typer.Option(None, "--author", help="Comment author name"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
) -> None:
    """Manage issue comments.

    Actions:
    - add: Add a comment to an issue
    - list: List all comments for an issue
    - delete: Delete a comment
    """
    try:
        from dogcat.models import Comment

        storage = get_storage(dogcats_dir)
        issue = storage.get(issue_id)

        if not issue:
            typer.echo(f"Error: Issue {issue_id} not found", err=True)
            raise typer.Exit(1)

        if action == "add":
            if not text:
                typer.echo("Error: --text is required for add action", err=True)
                raise typer.Exit(1)

            # Generate comment ID
            comment_counter = len(issue.comments) + 1
            new_comment_id = f"{issue_id}-c{comment_counter}"

            new_comment = Comment(
                id=new_comment_id,
                issue_id=issue.full_id,
                author=author or get_default_operator(),
                text=text,
            )

            issue.comments.append(new_comment)
            storage.update(issue_id, {"comments": issue.comments})

            if json_output:
                from dogcat.models import issue_to_dict

                typer.echo(orjson.dumps(issue_to_dict(issue)).decode())
            else:
                typer.echo(f"✓ Added comment {new_comment_id}")

        elif action == "list":
            if json_output:
                output = [
                    {
                        "id": c.id,
                        "author": c.author,
                        "text": c.text,
                        "created_at": c.created_at.isoformat(),
                    }
                    for c in issue.comments
                ]
                typer.echo(orjson.dumps(output).decode())
            else:
                if not issue.comments:
                    typer.echo("No comments")
                else:
                    for comment in issue.comments:
                        ts = comment.created_at.isoformat()
                        typer.echo(f"[{comment.id}] {comment.author} ({ts})")
                        typer.echo(f"  {comment.text}")

        elif action == "delete":
            if not comment_id:
                typer.echo(
                    "Error: --comment-id is required for delete action",
                    err=True,
                )
                raise typer.Exit(1)

            comment_to_delete = None
            for c in issue.comments:
                if c.id == comment_id:
                    comment_to_delete = c
                    break

            if not comment_to_delete:
                typer.echo(f"Error: Comment {comment_id} not found", err=True)
                raise typer.Exit(1)

            issue.comments.remove(comment_to_delete)
            storage.update(issue_id, {"comments": issue.comments})

            typer.echo(f"✓ Deleted comment {comment_id}")

        else:
            typer.echo(f"Error: Unknown action '{action}'", err=True)
            typer.echo("Valid actions: add, list, delete", err=True)
            raise typer.Exit(1)

    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def info(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show valid issue types, statuses, and priorities.

    Displays all valid values for issue fields, useful for
    understanding what options are available.
    """
    from dogcat.constants import (
        PRIORITY_OPTIONS,
        STATUS_OPTIONS,
        TYPE_OPTIONS,
        TYPE_SHORTHANDS,
    )

    if json_output:
        output = {
            "types": [
                {"label": label, "value": value} for label, value in TYPE_OPTIONS
            ],
            "type_shorthands": TYPE_SHORTHANDS,
            "statuses": [
                {"label": label, "value": value} for label, value in STATUS_OPTIONS
            ],
            "priorities": [
                {"label": label, "value": value} for label, value in PRIORITY_OPTIONS
            ],
        }
        typer.echo(orjson.dumps(output, option=orjson.OPT_INDENT_2).decode())
    else:
        typer.echo("Issue Types:")
        for label, value in TYPE_OPTIONS:
            shorthand = next(
                (k for k, v in TYPE_SHORTHANDS.items() if v == value),
                None,
            )
            shorthand_str = f" (shorthand: {shorthand})" if shorthand else ""
            typer.echo(f"  {value:<10} - {label}{shorthand_str}")

        typer.echo("\nStatuses:")
        for label, value in STATUS_OPTIONS:
            typer.echo(f"  {value:<12} - {label}")

        typer.echo("\nPriorities:")
        for label, value in PRIORITY_OPTIONS:
            typer.echo(f"  {value}  - {label}")

        typer.echo("\nShorthands for create command:")
        shorthand_list = ", ".join(
            f"{k}={v}" for k, v in sorted(TYPE_SHORTHANDS.items())
        )
        typer.echo(f"  Type: {shorthand_list}")
        typer.echo("  Priority: 0-4 (0=Critical, 4=Minimal)")


@app.command()
def status(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
) -> None:
    """Show repository status: prefix and issue counts.

    Displays the configured issue prefix and counts of issues by status.

    Examples:
        dcat status         # Show prefix and counts
        dcat status --json  # Output as JSON
    """
    try:
        storage = get_storage(dogcats_dir)
        # Get the actual dogcats_dir from storage (in case it was found by search)
        actual_dogcats_dir = str(storage.dogcats_dir)
        prefix = get_issue_prefix(actual_dogcats_dir)

        # Count issues by status
        all_issues = storage.list()
        status_counts: dict[str, int] = {}
        for issue in all_issues:
            status_val = issue.status.value
            status_counts[status_val] = status_counts.get(status_val, 0) + 1

        total = len(all_issues)

        if json_output:
            output = {
                "prefix": prefix,
                "total": total,
                "by_status": status_counts,
            }
            typer.echo(orjson.dumps(output, option=orjson.OPT_INDENT_2).decode())
        else:
            typer.echo(f"Prefix: {prefix}")
            typer.echo(f"Total issues: {total}")
            if status_counts:
                typer.echo("\nBy status:")
                for status_val, count in sorted(status_counts.items()):
                    typer.echo(f"  {status_val:<12} {count}")

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from None


@app.command()
def search(
    query: str = typer.Argument(
        ...,
        help="Search query (searches title and description)",
    ),
    case_sensitive: bool = typer.Option(
        False,
        "--case-sensitive",
        "-c",
        help="Case-sensitive search",
    ),
    status: str = typer.Option(None, "--status", "-s", help="Filter by status"),
    issue_type: str = typer.Option(None, "--type", "-t", help="Filter by type"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
) -> None:
    """Search issues by title and description.

    Searches for the query string in issue titles and descriptions.
    By default, search is case-insensitive.

    Examples:
        dcat search "login"              # Find issues mentioning login
        dcat search "bug" --type bug     # Find bug issues mentioning bug
        dcat search "API" -c             # Case-sensitive search
    """
    import re

    try:
        storage = get_storage(dogcats_dir)
        issues = storage.list()

        # Apply status/type filters first
        if status:
            issues = [i for i in issues if i.status.value == status]
        if issue_type:
            issues = [i for i in issues if i.issue_type.value == issue_type]

        # Exclude closed/tombstone by default
        if not status:
            issues = [
                i for i in issues if i.status.value not in ("closed", "tombstone")
            ]

        # Search in title and description
        flags = 0 if case_sensitive else re.IGNORECASE
        pattern = re.compile(re.escape(query), flags)

        matches: list[Issue] = []
        for issue in issues:
            title_match = pattern.search(issue.title) if issue.title else None
            desc_match = (
                pattern.search(issue.description) if issue.description else None
            )
            if title_match or desc_match:
                matches.append(issue)

        # Sort by priority
        matches = sorted(matches, key=lambda i: (i.priority, i.id))

        if json_output:
            from dogcat.models import issue_to_dict

            output = [issue_to_dict(issue) for issue in matches]
            typer.echo(orjson.dumps(output).decode())
        else:
            if not matches:
                typer.echo(f"No issues found matching '{query}'")
            else:
                typer.echo(f"Found {len(matches)} issue(s) matching '{query}':\n")
                for issue in matches:
                    typer.echo(format_issue_brief(issue))

    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def archive(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview what would be archived without making changes",
    ),
    older_than: str = typer.Option(
        None,
        "--older-than",
        help="Only archive issues closed more than N days ago (e.g. 30d)",
    ),
    confirm: bool = typer.Option(
        False,
        "--confirm",
        help="Skip confirmation prompt",
    ),
    dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
) -> None:
    """Archive closed issues to reduce startup load.

    Moves closed issues from the main storage file to an archive file
    at .dogcats/archive/closed-<timestamp>.jsonl.

    Issues are NOT archived if:
    - They have any open (non-closed) child issues
    - They have dependencies or links pointing to issues NOT being archived

    Examples:
        dcat archive                      # Archive all closed issues
        dcat archive --dry-run            # Preview what would be archived
        dcat archive --older-than 30d     # Only archive if closed 30+ days ago
        dcat archive --confirm            # Skip confirmation prompt
    """
    import re
    import tempfile
    from datetime import timedelta

    # Validate --older-than format early
    days: int | None = None
    if older_than:
        match = re.match(r"^(\d+)d$", older_than)
        if not match:
            typer.echo(
                "Error: --older-than must be in format Nd (e.g. 30d)",
                err=True,
            )
            raise typer.Exit(1)
        days = int(match.group(1))

    try:
        storage = get_storage(dogcats_dir)
        actual_dogcats_dir = str(storage.dogcats_dir)

        # Get all closed issues (not tombstoned)
        all_issues = storage.list()
        closed_issues = [
            i for i in all_issues if i.status == Status.CLOSED and not i.is_tombstone()
        ]

        if not closed_issues:
            typer.echo("No closed issues to archive.")
            return

        # Apply age filter if specified
        if days is not None:
            cutoff = datetime.now(UTC) - timedelta(days=days)
            closed_issues = [
                i
                for i in closed_issues
                if i.closed_at and i.closed_at.astimezone(UTC) <= cutoff
            ]

            if not closed_issues:
                typer.echo(f"No closed issues older than {days} days to archive.")
                return

        # Build set of IDs we want to archive
        candidate_ids = {i.full_id for i in closed_issues}

        # Determine which issues can actually be archived
        archivable: list[Issue] = []
        skipped: list[tuple[Issue, str]] = []

        for issue in closed_issues:
            # Check for open children
            children = storage.get_children(issue.full_id)
            open_children = [c for c in children if c.status != Status.CLOSED]
            if open_children:
                skipped.append(
                    (
                        issue,
                        f"has {len(open_children)} open child(ren): "
                        + ", ".join(c.full_id for c in open_children[:3]),
                    ),
                )
                continue

            # Check dependencies pointing to non-archived issues
            deps = storage.get_dependencies(issue.full_id)
            bad_deps = [d for d in deps if d.depends_on_id not in candidate_ids]
            if bad_deps:
                skipped.append(
                    (
                        issue,
                        "depends on non-archived issue(s): "
                        + ", ".join(d.depends_on_id for d in bad_deps[:3]),
                    ),
                )
                continue

            # Check dependents (issues that depend on this one)
            dependents = storage.get_dependents(issue.full_id)
            bad_dependents = [d for d in dependents if d.issue_id not in candidate_ids]
            if bad_dependents:
                skipped.append(
                    (
                        issue,
                        "is depended on by non-archived issue(s): "
                        + ", ".join(d.issue_id for d in bad_dependents[:3]),
                    ),
                )
                continue

            # Check links from this issue to non-archived issues
            links = storage.get_links(issue.full_id)
            bad_links = [link for link in links if link.to_id not in candidate_ids]
            if bad_links:
                skipped.append(
                    (
                        issue,
                        "has links to non-archived issue(s): "
                        + ", ".join(link.to_id for link in bad_links[:3]),
                    ),
                )
                continue

            # Check incoming links from non-archived issues
            incoming_links = storage.get_incoming_links(issue.full_id)
            bad_incoming = [
                link for link in incoming_links if link.from_id not in candidate_ids
            ]
            if bad_incoming:
                skipped.append(
                    (
                        issue,
                        "has incoming links from non-archived issue(s): "
                        + ", ".join(link.from_id for link in bad_incoming[:3]),
                    ),
                )
                continue

            archivable.append(issue)

        # Update candidate_ids to only include actually archivable issues
        archivable_ids = {i.full_id for i in archivable}

        if not archivable:
            typer.echo("No issues can be archived.")
            if skipped:
                typer.echo("\nSkipped issues:")
                for issue, reason in skipped:
                    typer.echo(f"  {issue.full_id}: {reason}")
            return

        # Show summary
        typer.echo(f"\nWill archive {len(archivable)} issue(s):")
        for issue in archivable[:10]:
            typer.echo(f"  {issue.full_id}: {issue.title}")
        if len(archivable) > 10:
            typer.echo(f"  ... and {len(archivable) - 10} more")

        if skipped:
            typer.echo(f"\nSkipping {len(skipped)} issue(s):")
            for issue, reason in skipped[:5]:
                typer.echo(f"  {issue.full_id}: {reason}")
            if len(skipped) > 5:
                typer.echo(f"  ... and {len(skipped) - 5} more")

        if dry_run:
            typer.echo("\n(dry run - no changes made)")
            return

        # Confirm unless --confirm flag is passed
        if not confirm:
            typer.echo("")
            proceed = typer.confirm(
                f"Archive {len(archivable)} issue(s)?",
                default=False,
            )
            if not proceed:
                typer.echo("Aborted.")
                return

        # Create archive directory
        archive_dir = Path(actual_dogcats_dir) / "archive"
        archive_dir.mkdir(exist_ok=True)

        # Generate timestamp for archive file
        timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S")
        archive_filename = f"closed-{timestamp}.jsonl"
        archive_path = archive_dir / archive_filename

        # Collect dependencies and links that should be archived
        # (both sides are in archivable_ids)
        from dogcat.models import issue_to_dict

        archived_deps = [
            dep
            for dep in storage._dependencies
            if dep.issue_id in archivable_ids and dep.depends_on_id in archivable_ids
        ]
        archived_links = [
            link
            for link in storage._links
            if link.from_id in archivable_ids and link.to_id in archivable_ids
        ]

        # Write to archive file atomically
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=archive_dir,
            delete=False,
            suffix=".jsonl",
        ) as tmp_file:
            tmp_path = Path(tmp_file.name)

            try:
                # Write issues
                for issue in archivable:
                    data = issue_to_dict(issue)
                    tmp_file.write(orjson.dumps(data))
                    tmp_file.write(b"\n")

                # Write dependencies
                for dep in archived_deps:
                    dep_data = {
                        "issue_id": dep.issue_id,
                        "depends_on_id": dep.depends_on_id,
                        "type": dep.type.value,
                        "created_at": dep.created_at.isoformat(),
                        "created_by": dep.created_by,
                    }
                    tmp_file.write(orjson.dumps(dep_data))
                    tmp_file.write(b"\n")

                # Write links
                for link in archived_links:
                    link_data = {
                        "from_id": link.from_id,
                        "to_id": link.to_id,
                        "link_type": link.link_type,
                        "created_at": link.created_at.isoformat(),
                        "created_by": link.created_by,
                    }
                    tmp_file.write(orjson.dumps(link_data))
                    tmp_file.write(b"\n")

                tmp_file.flush()
            except Exception as e:
                tmp_path.unlink(missing_ok=True)
                msg = f"Failed to write archive file: {e}"
                raise RuntimeError(msg) from e

        # Atomic rename to final archive path
        try:
            tmp_path.replace(archive_path)
        except OSError as e:
            tmp_path.unlink(missing_ok=True)
            msg = f"Failed to create archive file: {e}"
            raise RuntimeError(msg) from e

        # Remove archived issues from storage
        for issue in archivable:
            del storage._issues[issue.full_id]

        # Remove archived dependencies
        storage._dependencies = [
            dep
            for dep in storage._dependencies
            if dep.issue_id not in archivable_ids
            or dep.depends_on_id not in archivable_ids
        ]

        # Remove archived links
        storage._links = [
            link
            for link in storage._links
            if link.from_id not in archivable_ids or link.to_id not in archivable_ids
        ]

        # Save the updated storage
        storage._save()

        typer.echo(f"\n✓ Archived {len(archivable)} issue(s) to {archive_path}")
        if archived_deps:
            typer.echo(f"  Including {len(archived_deps)} dependency record(s)")
        if archived_links:
            typer.echo(f"  Including {len(archived_links)} link record(s)")

    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def guide() -> None:
    """Show a human-friendly guide to using dcat.

    Displays a walkthrough of dcat's core features and workflows,
    written for humans rather than AI agents.
    """
    guide_text = """\
╔════════════════════════════════════════════════════════════════════════════╗
║                           DCAT USER GUIDE                                ║
╚════════════════════════════════════════════════════════════════════════════╝

  dcat is a lightweight, git-friendly issue tracker that lives inside
  your repository. Issues are stored in a single .dogcats/issues.jsonl
  file — no server, no database, no setup beyond "dcat init".

── Getting Started ─────────────────────────────────────────────────────────

  Initialize a repository (one-time):

    dcat init

  Create your first issue:

    dcat create "Fix login page styling"

  You can set type and priority at creation time:

    dcat create "Crash on empty input" --type bug --priority 1

  Shorthands also work — single letters for type, digits for priority:

    dcat create "Crash on empty input" b 1

  Available types: task (t), bug (b), feature (f), story (s),
                   chore (c), epic (e), question (q), draft (d)

  Priority scale: 0 = Critical, 1 = High, 2 = Medium (default),
                  3 = Low, 4 = Minimal

── Viewing Issues ──────────────────────────────────────────────────────────

  List all open issues:

    dcat list

  Show as a formatted table:

    dcat list --table

  View a specific issue in detail:

    dcat show <issue_id>

  Search issues by keyword:

    dcat search "login"

  See recently closed issues:

    dcat recently-closed

── Working on Issues ───────────────────────────────────────────────────────

  Issues move through these statuses:

    open → in_progress → in_review → closed

  Other statuses: blocked, deferred

  Update an issue's status:

    dcat update <id> --status in_progress

  Close an issue with a reason:

    dcat close <id> --reason "Fixed in commit abc123"

  To find issues that are ready to work on (no blockers):

    dcat ready

── Dependencies & Hierarchy ────────────────────────────────────────────────

  Issues can have parent-child relationships for organization:

    dcat create "Subtask" --parent <parent_id>

  Parent-child is purely organizational — children are NOT blocked by
  their parent. If a child genuinely needs its parent to finish first,
  add an explicit dependency:

    dcat dep <child_id> add --depends-on <parent_id>

  View dependencies for an issue:

    dcat dep <id> list

  See all blocked issues across the project:

    dcat blocked

── Filtering & Advanced Usage ──────────────────────────────────────────────

  Filter by type, priority, label, or status:

    dcat list --type bug
    dcat list --priority 0
    dcat list --label "backend"
    dcat list --status in_review

  Add labels to an issue:

    dcat label <id> add "backend"

  Add a comment:

    dcat comment <id> "Needs more investigation"

  Date-based queries for closed issues:

    dcat list --closed --closed-after 2025-01-01

  JSON output for scripting:

    dcat list --json

── Questions ────────────────────────────────────────────────────────────────

  "question" is a special issue type for tracking decisions and
  open questions — not tasks to work on:

    dcat create "Which auth provider should we use?" --type question

  Close with an answer:

    dcat close <id> --reason "Going with Auth0"

── Useful Commands ─────────────────────────────────────────────────────────

  dcat info        Show valid types, statuses, and priorities
  dcat status      Show project overview and counts
  dcat doctor      Run health checks on your issue data
  dcat export      Export all issues (for backup or migration)
  dcat prune       Permanently remove deleted issues

── Getting Help ────────────────────────────────────────────────────────────

  dcat --help              List all commands
  dcat <command> --help    Help for a specific command
  dcat prime               Show the machine-readable workflow guide
"""
    typer.echo(guide_text)


@app.command()
def prime() -> None:
    """Show dogcat workflow guide and best practices for AI agents.

    This command displays guidance for effective dogcat usage and workflows.
    """
    guide = """
╔════════════════════════════════════════════════════════════════════════════╗
║                         DOGCAT WORKFLOW GUIDE                              ║
╚════════════════════════════════════════════════════════════════════════════╝

## Quick Start for AI agents

1. Create an issue:
   $ dcat create "My first issue" --type bug --priority 1

2. List issues:
   $ dcat list
   $ dcat list --open
   $ dcat list --closed
   $ dcat list --table  # Formatted table

3. Update an issue:
   $ dcat update <issue_id> --status in_progress

4. Close an issue:
   $ dcat close <issue_id> --reason "Fixed"

## Essential Commands

### Finding Work
  dcat list              - Show all open issues
  dcat list --open       - Show only open/in-progress issues
  dcat list --closed     - Show only closed issues
  dcat list --table     - Show as formatted table
  dcat ready             - Show issues ready to work (no blockers)
  dcat recently-closed   - Show recently closed issues

### Creating & Updating
  dcat create <title>                       - Create a new issue
  dcat create <title> --status in_progress  - Create with status
  dcat create <title> --depends-on <id>     - Create with dependency
  dcat update <id>                          - Update an issue
  dcat close <id>                           - Mark issue as closed

### Managing Dependencies
  dcat dep <id> add --depends-on <other_id> - Add dependency
  dcat dep <id> list                        - Show dependencies
  dcat blocked                              - Show all blocked issues

### Maintenance Commands
  dcat prune             - Remove tombstoned issues permanently
  dcat prune --dry-run   - Preview what would be pruned
  dcat export            - Export all issues, deps, and links
  dcat stream            - Stream issue changes in real-time

## Parent-Child vs Dependencies

Parent-child relationships are **organizational** (grouping), not **blocking**.
Child issues appear in `dcat ready` even when their parent is still open.

Use this to decide:
- Can this child task be started independently? → Keep as parent-child only
- Must the parent complete first? → Add explicit dependency:
    dcat dep <child_id> add --depends-on <parent_id>

Example: A feature with subtasks - subtasks can often be worked in parallel,
so they should NOT depend on the parent. But if subtask B needs subtask A's
output, add a dependency between them.

## Tips & Tricks

- Use --json flag with any list command for programmatic output
- Use --operator flag to track who made changes
- Use --closed-after and --closed-before for date-based queries
- Use --all flag to include archived/tombstoned issues
- Use dcat info to see valid types, statuses, and priorities
- Use dcat search <query> to find issues by title/description

## Agent Integration

Use --skip-agent to mark issues that should be skipped by AI agents:
  dcat create "Manual review needed" --skip-agent

Use --exclude-skip-agent in list/ready to filter out these issues:
  dcat ready --exclude-skip-agent   # Show only agent-workable issues
  dcat list --exclude-skip-agent    # Hide skip-agent issues

## Status Workflow

Issues progress through these statuses:
  open -> in_progress -> in_review -> closed

Status meanings:
  open        - New issue, not yet started
  in_progress - Actively being worked on
  in_review   - Work complete, awaiting review/testing
  blocked     - Waiting on external dependency
  deferred    - Postponed for later
  closed      - Done

Update status:
  dcat update <id> --status in_review

## Common Workflows

### Starting Work on an Issue
$ dcat ready              # Check available work
$ dcat show <issue_id>    # View issue details (includes parent, children, dependencies)
$ dcat update <issue_id> --status in_progress

### Submitting for Review
$ dcat update <issue_id> --status in_review

### Creating Related Issues
$ dcat create "Blocker task"
$ dcat create "Dependent task" --depends-on <blocker_id>

### Closing Issues
$ dcat close <issue_id> --reason "Explanation"

### Tracking Dependencies
$ dcat dep <new_task> add --depends-on <blocker_id>
$ dcat blocked            # See what's blocked

## Questions

Questions (type: question, shorthand: q) are special issues used to track
questions that need answers, NOT tasks to work on. Use them to:
- Document technical questions that need research
- Track decisions that need to be made
- Record questions for team discussion

Close with answer:  dcat close <id> --reason "Use JWT tokens"

## Need Help?
  dcat --help            - Show all commands
  dcat <command> --help  - Get help for a specific command
"""
    typer.echo(guide)


def main() -> None:
    """Run the Dogcat CLI application."""
    app()


if __name__ == "__main__":
    main()
