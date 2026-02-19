"""Stale issue detection command for dogcat CLI."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import orjson
import typer

from ._completions import (
    complete_durations,
    complete_labels,
    complete_namespaces,
    complete_owners,
    complete_priorities,
    complete_types,
)
from ._formatting import (
    format_issue_brief,
    format_issue_table,
    format_issue_tree,
)
from ._helpers import apply_common_filters, get_storage
from ._json_state import echo_error, is_json_output


def _parse_duration_arg(value: str) -> timedelta:
    """Parse a shorthand duration string like '7d', '3h', or '1d12h'.

    Returns:
        timedelta representing the duration.

    Raises:
        ValueError: If the format is invalid.
    """
    match = re.fullmatch(r"(?:(\d+)d)?(?:(\d+)h)?", value)
    if not match or (match.group(1) is None and match.group(2) is None):
        msg = f"Invalid duration '{value}'. Use format like 7d, 3h, or 1d12h."
        raise ValueError(msg)
    days = int(match.group(1)) if match.group(1) else 0
    hours = int(match.group(2)) if match.group(2) else 0
    return timedelta(days=days, hours=hours)


def register(app: typer.Typer) -> None:
    """Register stale command."""

    @app.command()
    def stale(
        duration_arg: str | None = typer.Argument(
            None,
            help="Duration shorthand (e.g. 7d, 3h, 1d12h)",
            autocompletion=complete_durations,
        ),
        days: int | None = typer.Option(
            None,
            "--days",
            help="Filter by N days of inactivity",
        ),
        hours: int | None = typer.Option(
            None,
            "--hours",
            help="Filter by N hours of inactivity",
        ),
        limit: int | None = typer.Option(None, "--limit", help="Limit results"),
        issue_type: str | None = typer.Option(
            None,
            "--type",
            "-t",
            help="Filter by type",
            autocompletion=complete_types,
        ),
        priority: int | None = typer.Option(
            None,
            "--priority",
            "-p",
            help="Filter by priority",
            autocompletion=complete_priorities,
        ),
        label: str | None = typer.Option(
            None,
            "--label",
            "-l",
            help="Filter by label",
            autocompletion=complete_labels,
        ),
        owner: str | None = typer.Option(
            None,
            "--owner",
            "-o",
            help="Filter by owner",
            autocompletion=complete_owners,
        ),
        namespace: str | None = typer.Option(
            None,
            "--namespace",
            help="Filter by namespace",
            autocompletion=complete_namespaces,
        ),
        all_namespaces: bool = typer.Option(
            False,
            "--all-namespaces",
            "--all-ns",
            "-A",
            help="Show issues from all namespaces",
        ),
        agent_only: bool = typer.Option(
            False,
            "--agent-only",
            help="Only show issues available for agents",
        ),
        tree: bool = typer.Option(False, "--tree", help="Display as tree"),
        table: bool = typer.Option(False, "--table", help="Display in columns"),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Show issues with no recent activity.

        Lists issues that have had no updates within a given time period.
        Default threshold is 7 days. Only considers active issues (not
        closed or deleted).

        Examples:
            dcat stale              # issues with no activity in 7 days
            dcat stale --days 14    # issues with no activity in 14 days
            dcat stale --hours 48   # issues with no activity in 48 hours
            dcat stale 7d           # shorthand for --days 7
            dcat stale 3h           # shorthand for --hours 3
            dcat stale 1d12h        # 1 day and 12 hours
        """
        try:
            # Determine threshold
            if duration_arg and (days is not None or hours is not None):
                echo_error("Cannot use positional duration with --days/--hours")
                raise typer.Exit(1)

            if duration_arg:
                try:
                    threshold = _parse_duration_arg(duration_arg)
                except ValueError as e:
                    echo_error(str(e))
                    raise typer.Exit(1)
            elif days is not None or hours is not None:
                threshold = timedelta(
                    days=days or 0,
                    hours=hours or 0,
                )
            else:
                threshold = timedelta(days=7)

            now = datetime.now(timezone.utc)
            cutoff = now - threshold

            storage = get_storage(dogcats_dir)
            issues = storage.list()

            # Only consider active issues
            active_statuses = {
                "draft",
                "open",
                "in_progress",
                "in_review",
                "blocked",
                "deferred",
            }
            issues = [i for i in issues if i.status.value in active_statuses]

            # Filter to stale issues (updated_at before cutoff)
            issues = [
                i for i in issues if i.updated_at.astimezone(timezone.utc) < cutoff
            ]

            issues = apply_common_filters(
                issues,
                issue_type=issue_type,
                priority=priority,
                label=label,
                owner=owner,
                namespace=namespace,
                all_namespaces=all_namespaces,
                agent_only=agent_only,
                dogcats_dir=str(storage.dogcats_dir),
                storage=storage,
            )

            issues.sort(key=lambda i: (i.priority, i.updated_at))

            if limit:
                issues = issues[:limit]

            if is_json_output(json_output):
                from dogcat.models import issue_to_dict

                output = [issue_to_dict(issue) for issue in issues]
                typer.echo(orjson.dumps(output).decode())
            elif not issues:
                typer.echo("No stale issues")
            else:
                typer.echo(f"Stale ({len(issues)}):")
                if tree:
                    typer.echo(format_issue_tree(issues))
                elif table:
                    typer.echo(format_issue_table(issues))
                else:
                    for issue in issues:
                        age = _format_age(now, issue.updated_at)
                        age_str = typer.style(
                            f"[{age}]",
                            fg="bright_black",
                        )
                        typer.echo(f"{format_issue_brief(issue)} {age_str}")

        except typer.Exit:
            raise
        except Exception as e:
            echo_error(str(e))
            raise typer.Exit(1)


def _format_age(now: datetime, updated_at: datetime) -> str:
    """Format the age of an issue as a human-readable string."""
    delta = now - updated_at.astimezone(timezone.utc)
    total_hours = int(delta.total_seconds() // 3600)
    if total_hours < 24:
        return f"{total_hours}h ago"
    total_days = delta.days
    if total_days == 1:
        return "1 day ago"
    return f"{total_days} days ago"
