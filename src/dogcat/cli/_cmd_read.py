"""Read/display commands for dogcat CLI."""

from __future__ import annotations

from datetime import timezone
from typing import TYPE_CHECKING, Any

import orjson
import typer

from dogcat.config import get_namespace_filter
from dogcat.constants import parse_labels

from ._completions import (
    complete_issue_ids,
    complete_labels,
    complete_priorities,
    complete_statuses,
    complete_types,
)
from ._formatting import (
    format_issue_brief,
    format_issue_full,
    format_issue_table,
    format_issue_tree,
    get_legend,
)
from ._helpers import _make_alias, get_storage

if TYPE_CHECKING:
    from dogcat.models import Issue
    from dogcat.storage import JSONLStorage


def _collect_descendants(storage: JSONLStorage, parent_id: str) -> set[str]:
    """Recursively collect all descendant issue IDs of a parent.

    Args:
        storage: The storage instance
        parent_id: The parent issue ID

    Returns:
        Set of all descendant issue full_ids
    """
    descendants: set[str] = set()
    try:
        children = storage.get_children(parent_id)
    except ValueError:
        return descendants
    for child in children:
        descendants.add(child.full_id)
        descendants |= _collect_descendants(storage, child.full_id)
    return descendants


def _collapse_deferred_subtrees(
    issues: list[Issue],
    storage: JSONLStorage,
) -> tuple[list[Issue], dict[str, int], dict[str, list[str]]]:
    """Collapse children of deferred parents and annotate blocked externals.

    Args:
        issues: The list of issues to process
        storage: The storage instance

    Returns:
        Tuple of (filtered issues, hidden_counts, deferred_blocker_map)
        - filtered issues: children of deferred parents removed
        - hidden_counts: deferred parent full_id -> count of hidden descendants
        - deferred_blocker_map: issue full_id -> list of deferred blocker IDs
    """
    from dogcat.models import Status

    visible_ids = {i.full_id for i in issues}

    # Find deferred parents in the visible set
    deferred_parents = {i.full_id for i in issues if i.status == Status.DEFERRED}

    # Collect all descendants of deferred parents
    all_deferred_descendants: set[str] = set()
    # Map: descendant_id -> deferred ancestor id(s)
    descendant_to_deferred: dict[str, set[str]] = {}
    hidden_counts: dict[str, int] = {}

    for dp_id in deferred_parents:
        descendants = _collect_descendants(storage, dp_id)
        visible_descendants = descendants & visible_ids
        if visible_descendants:
            hidden_counts[dp_id] = len(visible_descendants)
            all_deferred_descendants |= visible_descendants
            for desc_id in descendants:
                descendant_to_deferred.setdefault(desc_id, set()).add(dp_id)

    # Build deferred blocker map for non-child issues that depend on
    # a deferred issue or a child-of-deferred issue
    deferred_or_descendant_ids = deferred_parents | all_deferred_descendants
    deferred_blocker_map: dict[str, list[str]] = {}

    for issue in issues:
        if issue.full_id in deferred_or_descendant_ids:
            continue
        try:
            deps = storage.get_dependencies(issue.full_id)
        except ValueError:
            continue
        deferred_blockers: list[str] = []
        for dep in deps:
            dep_id = dep.depends_on_id
            if dep_id in deferred_parents:
                deferred_blockers.append(dep_id)
            elif dep_id in descendant_to_deferred:
                # Attribute to the deferred ancestor
                deferred_blockers.extend(descendant_to_deferred[dep_id])
        if deferred_blockers:
            # Deduplicate while preserving order
            seen: set[str] = set()
            unique: list[str] = []
            for b in deferred_blockers:
                if b not in seen:
                    seen.add(b)
                    unique.append(b)
            deferred_blocker_map[issue.full_id] = unique

    # Filter out descendants of deferred parents
    filtered = [i for i in issues if i.full_id not in all_deferred_descendants]

    return filtered, hidden_counts, deferred_blocker_map


def register(app: typer.Typer) -> None:
    """Register read/display commands."""

    @app.command("list")
    def list_issues(
        status: str | None = typer.Option(
            None,
            "--status",
            "-s",
            help="Filter by status",
            autocompletion=complete_statuses,
        ),
        priority: int | None = typer.Option(
            None,
            "--priority",
            "-p",
            help="Filter by priority",
            autocompletion=complete_priorities,
        ),
        issue_type: str | None = typer.Option(
            None,
            "--type",
            "-t",
            help="Filter by type",
            autocompletion=complete_types,
        ),
        label: str | None = typer.Option(
            None,
            "--label",
            "-l",
            help="Filter by label (comma or space separated)",
            autocompletion=complete_labels,
        ),
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
        namespace: str | None = typer.Option(
            None,
            "--namespace",
            "-ns",
            help="Filter by namespace",
        ),
        agent_only: bool = typer.Option(
            False,
            "--agent-only",
            help="Only show issues available for agents",
        ),
        tree: bool = typer.Option(
            False,
            "--tree",
            help="Display issues as a tree based on parent-child relationships",
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
            # Validate mutually exclusive options early
            if tree and table:
                typer.echo("Error: --tree and --table are mutually exclusive", err=True)
                raise typer.Exit(1)

            storage = get_storage(dogcats_dir)

            # Build filters
            filters: dict[str, Any] = {}
            if status:
                filters["status"] = status
            elif closed:
                filters["status"] = "closed"
            # Note: open_issues is handled after storage.list
            # to filter multiple statuses

            if priority is not None:
                filters["priority"] = priority
            if issue_type:
                filters["type"] = issue_type
            if label:
                labels_filter = parse_labels(label)
                filters["label"] = labels_filter
            if owner:
                filters["owner"] = owner

            issues = storage.list(filters or None)

            # Apply namespace filtering
            actual_dogcats_dir = str(storage.dogcats_dir)
            ns_filter = get_namespace_filter(actual_dogcats_dir, namespace)
            if ns_filter is not None:
                issues = [i for i in issues if ns_filter(i.namespace)]

            # Exclude closed/tombstone issues by default (unless explicitly requested)
            # Also include closed issues when date filters are used
            closed_excluded_by_default = (
                not status
                and not closed
                and not all_issues
                and not (closed_after or closed_before)
            )
            if closed_excluded_by_default:
                issues = [
                    i for i in issues if i.status.value not in ("closed", "tombstone")
                ]

            # Handle --open filter for multiple statuses
            if open_issues:
                issues = [
                    i for i in issues if i.status.value in ("open", "in_progress")
                ]

            # Filter out manual issues if requested
            if agent_only:
                issues = [
                    i
                    for i in issues
                    if not (i.metadata.get("manual") or i.metadata.get("no_agent"))
                ]

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
                                    after_dt = after_dt.replace(tzinfo=timezone.utc)
                                if issue.closed_at < after_dt:
                                    should_include = False

                            if closed_before and should_include:
                                before_dt = dt.fromisoformat(closed_before)
                                # Make timezone-naive dates UTC-aware for comparison
                                if before_dt.tzinfo is None:
                                    before_dt = before_dt.replace(tzinfo=timezone.utc)
                                if issue.closed_at > before_dt:
                                    should_include = False

                            if should_include:
                                filtered_issues.append(issue)

                    issues = filtered_issues
                except ValueError as e:
                    typer.echo(f"Error parsing date: {e}", err=True)
                    raise typer.Exit(1)

            # In tree mode, re-include closed parents of visible children
            # so the hierarchy is preserved (closed parents show with ✓ icon)
            if tree and closed_excluded_by_default:
                visible_ids = {i.full_id for i in issues}
                checked: set[str] = set()
                while True:
                    missing_parent_ids = {
                        i.parent
                        for i in issues
                        if i.parent
                        and i.parent not in visible_ids
                        and i.parent not in checked
                    }
                    if not missing_parent_ids:
                        break
                    for parent_id in missing_parent_ids:
                        checked.add(parent_id)
                        parent_issue = storage.get(parent_id)
                        if parent_issue and not parent_issue.is_tombstone():
                            issues.append(parent_issue)
                            visible_ids.add(parent_issue.full_id)

            # Sort by priority (lower number = higher priority)
            issues = sorted(issues, key=lambda i: (i.priority, i.id))

            if json_output:
                if limit:
                    issues = issues[:limit]
                from dogcat.models import issue_to_dict

                output = [issue_to_dict(issue) for issue in issues]
                typer.echo(orjson.dumps(output).decode())
            else:
                # Collapse children of deferred parents
                issues, hidden_counts, deferred_blocker_map = (
                    _collapse_deferred_subtrees(issues, storage)
                )

                if limit:
                    issues = issues[:limit]

                # Get blocked issue IDs to show correct status symbol
                from dogcat.deps import get_blocked_issues

                blocked_issues = get_blocked_issues(storage)
                blocked_ids = {bi.issue_id for bi in blocked_issues}
                blocked_by_map = {bi.issue_id: bi.blocking_ids for bi in blocked_issues}

                if not issues:
                    typer.echo("No issues found")
                elif tree:
                    typer.echo(
                        format_issue_tree(
                            issues,
                            blocked_ids=blocked_ids,
                            blocked_by_map=blocked_by_map,
                            hidden_counts=hidden_counts,
                            deferred_blocker_map=deferred_blocker_map,
                        ),
                    )
                    typer.echo(get_legend())
                elif table:
                    typer.echo(
                        format_issue_table(
                            issues,
                            blocked_ids=blocked_ids,
                            blocked_by_map=blocked_by_map,
                            hidden_counts=hidden_counts,
                            deferred_blocker_map=deferred_blocker_map,
                        ),
                    )
                    typer.echo(get_legend())
                else:
                    for issue in issues:
                        typer.echo(
                            format_issue_brief(
                                issue,
                                blocked_ids=blocked_ids,
                                blocked_by_map=blocked_by_map,
                                hidden_subtask_count=hidden_counts.get(
                                    issue.full_id,
                                ),
                                deferred_blockers=deferred_blocker_map.get(
                                    issue.full_id,
                                ),
                            ),
                        )
                    typer.echo(get_legend())

        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)

    @app.command()
    def show(
        issue_id: str = typer.Argument(
            ...,
            help="Issue ID",
            autocompletion=complete_issue_ids,
        ),
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
                parent_title = None
                if issue.parent:
                    parent_issue = storage.get(issue.parent)
                    if parent_issue:
                        parent_title = parent_issue.title
                output_lines = format_issue_full(
                    issue,
                    parent_title=parent_title,
                ).split(
                    "\n",
                )

                # Add dependencies
                deps = storage.get_dependencies(issue_id)
                if deps:
                    output_lines.append("\nDependencies:")
                    for dep in deps:
                        output_lines.append(
                            f"  → {dep.depends_on_id} ({dep.dep_type.value})",
                        )

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
                            output_lines.append(
                                f"  ← {link.from_id} ({link.link_type})",
                            )

                # Add children
                children = storage.get_children(issue_id)
                if children:
                    from dogcat.deps import get_blocked_issues

                    blocked_issues = get_blocked_issues(storage)
                    blocked_by_map = {
                        bi.issue_id: bi.blocking_ids for bi in blocked_issues
                    }

                    output_lines.append("\nChildren:")
                    for child in children:
                        brief = format_issue_brief(child, blocked_by_map=blocked_by_map)
                        output_lines.append(f"  ↳ {brief}")

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
    def edit(
        issue_id: str | None = typer.Argument(
            None,
            help="Issue ID (opens picker if omitted)",
            autocompletion=complete_issue_ids,
        ),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Open an issue in the Textual editor for interactive editing."""
        try:
            storage = get_storage(dogcats_dir)

            if issue_id is None:
                from dogcat.tui.picker import pick_issue

                issue_id = pick_issue(storage)
                if issue_id is None:
                    typer.echo("No issue selected")
                    return

            issue = storage.get(issue_id)
            if issue is None:
                typer.echo(f"Error: Issue {issue_id} not found", err=True)
                raise typer.Exit(1)

            from dogcat.tui.editor import edit_issue

            updated = edit_issue(issue_id, storage)
            if updated is not None:
                typer.echo(f"✓ Updated {updated.full_id}: {updated.title}")
            else:
                typer.echo("Edit cancelled")

        except typer.Exit:
            raise
        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)

    @app.command(name="e", hidden=True)
    def edit_alias(
        issue_id: str | None = typer.Argument(
            None,
            help="Issue ID (opens picker if omitted)",
            autocompletion=complete_issue_ids,
        ),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Open an issue in the Textual editor (alias for 'edit' command)."""
        edit(issue_id=issue_id, dogcats_dir=dogcats_dir)

    app.command(name="l", hidden=True)(
        _make_alias(
            list_issues,
            doc="Alias for list --tree.",
            exclude_params=frozenset({"tree", "table"}),
            param_defaults={"tree": True, "table": False},
        ),
    )

    app.command(name="lt", hidden=True)(
        _make_alias(
            list_issues,
            doc="Alias for list --table.",
            exclude_params=frozenset({"tree", "table"}),
            param_defaults={"tree": False, "table": True},
        ),
    )
