"""Workflow and status commands for dogcat CLI."""

from __future__ import annotations

import orjson
import typer

from ._completions import complete_issue_ids
from ._formatting import format_issue_brief, format_issue_tree
from ._helpers import get_default_operator, get_storage


def register(app: typer.Typer) -> None:
    """Register workflow/status commands."""

    @app.command()
    def ready(
        limit: int = typer.Option(None, "--limit", "-l", help="Limit results"),
        agent_only: bool = typer.Option(
            False,
            "--agent-only",
            help="Only show issues available for agents",
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Show issues ready to work (no blocking dependencies)."""
        try:
            from dogcat.deps import get_ready_work

            storage = get_storage(dogcats_dir)
            ready_issues = get_ready_work(storage)

            if agent_only:
                ready_issues = [
                    i
                    for i in ready_issues
                    if not (i.metadata.get("manual") or i.metadata.get("no_agent"))
                ]

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
                        issue = storage.get(bi.issue_id)
                        if issue:
                            typer.echo(format_issue_brief(issue))
                        else:
                            typer.echo(f"  {bi.issue_id}")
                        for blocker_id in bi.blocking_ids:
                            blocker = storage.get(blocker_id)
                            if blocker:
                                typer.echo(
                                    typer.style("    blocked by ", fg="bright_black")
                                    + format_issue_brief(blocker),
                                )
                            else:
                                typer.echo(
                                    typer.style(
                                        f"    blocked by {blocker_id}",
                                        fg="bright_black",
                                    ),
                                )

        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)

    @app.command("in-progress")
    def in_progress(
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Show issues currently in progress."""
        try:
            storage = get_storage(dogcats_dir)
            issues = storage.list({"status": "in_progress"})
            issues.sort(key=lambda i: i.priority)

            if json_output:
                from dogcat.models import issue_to_dict

                output = [issue_to_dict(issue) for issue in issues]
                typer.echo(orjson.dumps(output).decode())
            else:
                if not issues:
                    typer.echo("No in-progress issues")
                else:
                    has_parent = any(i.parent for i in issues)
                    if has_parent:
                        typer.echo(format_issue_tree(issues))
                    else:
                        for issue in issues:
                            typer.echo(format_issue_brief(issue))

        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)

    @app.command("in-review")
    def in_review(
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Show issues currently in review."""
        try:
            storage = get_storage(dogcats_dir)
            issues = storage.list({"status": "in_review"})
            issues.sort(key=lambda i: i.priority)

            if json_output:
                from dogcat.models import issue_to_dict

                output = [issue_to_dict(issue) for issue in issues]
                typer.echo(orjson.dumps(output).decode())
            else:
                if not issues:
                    typer.echo("No in-review issues")
                else:
                    has_parent = any(i.parent for i in issues)
                    if has_parent:
                        typer.echo(format_issue_tree(issues))
                    else:
                        for issue in issues:
                            typer.echo(format_issue_brief(issue))

        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)

    def _set_status(
        issue_id: str,
        status: str,
        label: str,
        json_output: bool,
        operator: str | None,
        dogcats_dir: str,
    ) -> None:
        """Set an issue's status."""
        try:
            storage = get_storage(dogcats_dir)
            final_operator = (
                operator if operator is not None else get_default_operator()
            )
            issue = storage.update(
                issue_id,
                {"status": status, "updated_by": final_operator},
            )

            if json_output:
                from dogcat.models import issue_to_dict

                typer.echo(orjson.dumps(issue_to_dict(issue)).decode())
            else:
                typer.echo(f"✓ {label} {issue.full_id}: {issue.title}")

        except ValueError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)
        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)

    @app.command(name="ir", hidden=True)
    def in_review_shortcut(
        issue_id: str = typer.Argument(
            ...,
            help="Issue ID",
            autocompletion=complete_issue_ids,
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        operator: str | None = typer.Option(
            None,
            "--operator",
            help="Who is making this change",
        ),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Set an issue's status to in-review."""
        _set_status(
            issue_id,
            "in_review",
            "In review",
            json_output,
            operator,
            dogcats_dir,
        )

    @app.command(name="ip", hidden=True)
    def in_progress_shortcut(
        issue_id: str = typer.Argument(
            ...,
            help="Issue ID",
            autocompletion=complete_issue_ids,
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        operator: str | None = typer.Option(
            None,
            "--operator",
            help="Who is making this change",
        ),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Set an issue's status to in-progress."""
        _set_status(
            issue_id,
            "in_progress",
            "In progress",
            json_output,
            operator,
            dogcats_dir,
        )

    @app.command("deferred")
    def deferred(
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Show issues currently deferred."""
        try:
            storage = get_storage(dogcats_dir)
            issues = storage.list({"status": "deferred"})
            issues.sort(key=lambda i: i.priority)

            if json_output:
                from dogcat.models import issue_to_dict

                output = [issue_to_dict(issue) for issue in issues]
                typer.echo(orjson.dumps(output).decode())
            else:
                if not issues:
                    typer.echo("No deferred issues")
                else:
                    for issue in issues:
                        typer.echo(format_issue_brief(issue))

        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)

    @app.command(name="defer", hidden=True)
    def defer_shortcut(
        issue_id: str = typer.Argument(
            ...,
            help="Issue ID",
            autocompletion=complete_issue_ids,
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        operator: str | None = typer.Option(
            None,
            "--operator",
            help="Who is making this change",
        ),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Set an issue's status to deferred."""
        _set_status(
            issue_id,
            "deferred",
            "Deferred",
            json_output,
            operator,
            dogcats_dir,
        )

    @app.command("manual")
    def manual_list(
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Show issues marked as manual."""
        try:
            storage = get_storage(dogcats_dir)
            issues = storage.list()
            issues = [
                i
                for i in issues
                if (i.metadata.get("manual") or i.metadata.get("no_agent"))
                and i.status.value not in ("closed", "tombstone")
            ]
            issues.sort(key=lambda i: i.priority)

            if json_output:
                from dogcat.models import issue_to_dict

                output = [issue_to_dict(issue) for issue in issues]
                typer.echo(orjson.dumps(output).decode())
            else:
                if not issues:
                    typer.echo("No manual issues")
                else:
                    for issue in issues:
                        typer.echo(format_issue_brief(issue))

        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)

    @app.command(name="mark-manual", hidden=True)
    def mark_manual_shortcut(
        issue_id: str = typer.Argument(
            ...,
            help="Issue ID",
            autocompletion=complete_issue_ids,
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        operator: str | None = typer.Option(
            None,
            "--operator",
            help="Who is making this change",
        ),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Mark an issue as manual (not for agents)."""
        try:
            storage = get_storage(dogcats_dir)
            final_operator = (
                operator if operator is not None else get_default_operator()
            )
            current = storage.get(issue_id)
            if current is None:
                typer.echo(f"Error: Issue {issue_id} not found", err=True)
                raise typer.Exit(1)
            new_metadata = dict(current.metadata) if current.metadata else {}
            new_metadata["manual"] = True
            new_metadata.pop("no_agent", None)
            issue = storage.update(
                issue_id,
                {"metadata": new_metadata, "operator": final_operator},
            )

            if json_output:
                from dogcat.models import issue_to_dict

                typer.echo(orjson.dumps(issue_to_dict(issue)).decode())
            else:
                typer.echo(f"✓ Marked manual {issue.full_id}: {issue.title}")

        except ValueError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)
        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)

    @app.command("recently-closed")
    def recently_closed(
        limit: int = typer.Option(10, "--limit", "-n", help="Number of issues to show"),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Show recently closed issues (newest first).

        Displays the last N closed issues, most recent at the top.
        """
        try:
            from dogcat.event_log import EventLog, _serialize

            from ._formatting import format_event, get_event_legend

            storage = get_storage(dogcats_dir)
            event_log = EventLog(storage.dogcats_dir)
            events = [e for e in event_log.read() if e.event_type == "closed"][:limit]

            # Fill in missing titles from storage
            for event in events:
                if not event.title:
                    issue_obj = storage.get(event.issue_id)
                    if issue_obj:
                        event.title = issue_obj.title

            if json_output:
                output = [_serialize(e) for e in events]
                typer.echo(orjson.dumps(output).decode())
            elif not events:
                typer.echo("No recently closed issues")
            else:
                for event in events:
                    typer.echo(format_event(event))
                typer.echo(get_event_legend())

        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)

    @app.command("recently-added")
    def recently_added(
        limit: int = typer.Option(10, "--limit", "-n", help="Number of issues to show"),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Show recently created issues in descending order (newest first).

        Displays the last N issues sorted by created_at date,
        with the most recently created issue at the top.
        """
        try:
            storage = get_storage(dogcats_dir)
            issues = [i for i in storage.list() if i.status.value != "closed"]

            # Sort by created_at descending (newest first)
            issues.sort(key=lambda i: i.created_at, reverse=True)

            # Take first N (most recent)
            recent = issues[:limit]

            if json_output:
                from dogcat.models import issue_to_dict

                output = [issue_to_dict(issue) for issue in recent]
                typer.echo(orjson.dumps(output).decode())
            else:
                if not recent:
                    typer.echo("No recently added issues")
                else:
                    for issue in recent:
                        created_str = typer.style(
                            f"[{issue.created_at.strftime('%Y-%m-%d %H:%M')}]",
                            fg="bright_black",
                        )
                        typer.echo(f"{format_issue_brief(issue)} {created_str}")

        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)

    @app.command(name="rc", hidden=True)
    def recently_closed_alias(
        limit: int = typer.Option(10, "--limit", "-n", help="Number of issues to show"),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Alias for recently-closed."""
        recently_closed(limit=limit, json_output=json_output, dogcats_dir=dogcats_dir)

    @app.command(name="b", hidden=True)
    def blocked_alias(
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Alias for blocked."""
        blocked(json_output=json_output, dogcats_dir=dogcats_dir)

    @app.command(name="d", hidden=True)
    def deferred_alias(
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Alias for deferred."""
        deferred(json_output=json_output, dogcats_dir=dogcats_dir)

    @app.command(name="ra", hidden=True)
    def recently_added_alias(
        limit: int = typer.Option(10, "--limit", "-n", help="Number of issues to show"),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Alias for recently-added."""
        recently_added(limit=limit, json_output=json_output, dogcats_dir=dogcats_dir)

    @app.command(name="pr", hidden=True)
    def progress_review(
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Show in-progress and in-review issues together."""
        try:
            storage = get_storage(dogcats_dir)
            ip_issues = storage.list({"status": "in_progress"})
            ip_issues.sort(key=lambda i: i.priority)
            ir_issues = storage.list({"status": "in_review"})
            ir_issues.sort(key=lambda i: i.priority)

            if json_output:
                from dogcat.models import issue_to_dict

                output = {
                    "in_progress": [issue_to_dict(issue) for issue in ip_issues],
                    "in_review": [issue_to_dict(issue) for issue in ir_issues],
                }
                typer.echo(orjson.dumps(output).decode())
            else:
                typer.echo("In Progress:")
                if not ip_issues:
                    typer.echo("  No in-progress issues")
                else:
                    ip_has_parent = any(i.parent for i in ip_issues)
                    if ip_has_parent:
                        tree = format_issue_tree(ip_issues)
                        for line in tree.splitlines():
                            typer.echo(f"  {line}")
                    else:
                        for issue in ip_issues:
                            typer.echo(f"  {format_issue_brief(issue)}")

                typer.echo()
                typer.echo("In Review:")
                if not ir_issues:
                    typer.echo("  No in-review issues")
                else:
                    ir_has_parent = any(i.parent for i in ir_issues)
                    if ir_has_parent:
                        tree = format_issue_tree(ir_issues)
                        for line in tree.splitlines():
                            typer.echo(f"  {line}")
                    else:
                        for issue in ir_issues:
                            typer.echo(f"  {format_issue_brief(issue)}")

        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)
