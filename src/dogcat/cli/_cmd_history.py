"""History command for dogcat CLI."""

from __future__ import annotations

import orjson
import typer

from dogcat.config import extract_prefix, get_namespace_filter

from ._completions import complete_issue_ids
from ._formatting import format_event, get_event_legend
from ._helpers import get_storage
from ._json_state import echo_error, is_json_output


def register(app: typer.Typer) -> None:
    """Register history commands."""

    @app.command()
    def history(
        limit_arg: int | None = typer.Argument(None, help="Number of events to show"),
        all_namespaces: bool = typer.Option(
            False,
            "--all-namespaces",
            "--all-ns",
            "-A",
            help="Show events from all namespaces",
        ),
        issue: str | None = typer.Option(
            None,
            "--issue",
            "-i",
            help="Filter events for a specific issue",
            autocompletion=complete_issue_ids,
        ),
        limit: int | None = typer.Option(
            None,
            "--limit",
            help="Number of events to show",
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        verbose: bool = typer.Option(
            False,
            "--verbose",
            "-v",
            help="Show full content of long-form fields",
        ),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Show change history as a chronological timeline."""
        try:
            from dogcat.event_log import EventLog, _serialize

            final_limit = limit_arg or limit or 20
            storage = get_storage(dogcats_dir)
            event_log = EventLog(storage.dogcats_dir)

            # Resolve partial issue ID if provided
            resolved_issue = None
            if issue:
                resolved_issue = storage.resolve_id(issue)
                if resolved_issue is None:
                    echo_error(f"Issue {issue} not found")
                    raise typer.Exit(1)

            events = event_log.read(issue_id=resolved_issue, limit=final_limit)

            # Apply namespace filter (skip if --all-namespaces)
            if not all_namespaces:
                actual_dogcats_dir = str(storage.dogcats_dir)
                ns_filter = get_namespace_filter(actual_dogcats_dir)
                if ns_filter is not None:
                    events = [
                        e for e in events if ns_filter(extract_prefix(e.issue_id) or "")
                    ]

            events.reverse()  # Display oldest-first (chronological)

            # Fill in missing titles from storage
            for event in events:
                if not event.title:
                    issue_obj = storage.get(event.issue_id)
                    if issue_obj:
                        event.title = issue_obj.title

            if is_json_output(json_output):
                output = [_serialize(e) for e in events]
                typer.echo(orjson.dumps(output).decode())
            elif not events:
                typer.echo("No history found")
            else:
                for event in events:
                    typer.echo(format_event(event, verbose=verbose))
                typer.echo(get_event_legend())

        except typer.Exit:
            raise
        except Exception as e:
            echo_error(str(e))
            raise typer.Exit(1) from e

    @app.command(name="h", hidden=True)
    def history_alias(
        limit_arg: int | None = typer.Argument(None, help="Number of events to show"),
        all_namespaces: bool = typer.Option(
            False,
            "--all-namespaces",
            "--all-ns",
            "-A",
            help="Show events from all namespaces",
        ),
        issue: str | None = typer.Option(
            None,
            "--issue",
            "-i",
            help="Filter events for a specific issue",
            autocompletion=complete_issue_ids,
        ),
        limit: int | None = typer.Option(
            None,
            "--limit",
            help="Number of events to show",
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        verbose: bool = typer.Option(
            False,
            "--verbose",
            "-v",
            help="Show full content of long-form fields",
        ),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Alias for history."""
        history(
            limit_arg=limit_arg,
            all_namespaces=all_namespaces,
            issue=issue,
            limit=limit,
            json_output=json_output,
            verbose=verbose,
            dogcats_dir=dogcats_dir,
        )
