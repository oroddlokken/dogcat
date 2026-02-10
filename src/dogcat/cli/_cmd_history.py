"""History command for dogcat CLI."""

from __future__ import annotations

import orjson
import typer

from ._completions import complete_issue_ids
from ._formatting import format_event, get_event_legend
from ._helpers import get_storage


def register(app: typer.Typer) -> None:
    """Register history commands."""

    @app.command()
    def history(
        issue: str | None = typer.Option(
            None,
            "--issue",
            "-i",
            help="Filter events for a specific issue",
            autocompletion=complete_issue_ids,
        ),
        limit: int = typer.Option(
            20,
            "--limit",
            "-n",
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

            storage = get_storage(dogcats_dir)
            event_log = EventLog(storage.dogcats_dir)

            # Resolve partial issue ID if provided
            resolved_issue = None
            if issue:
                resolved_issue = storage.resolve_id(issue)
                if resolved_issue is None:
                    typer.echo(f"Issue {issue} not found", err=True)
                    raise typer.Exit(1)

            events = event_log.read(issue_id=resolved_issue, limit=limit)

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
                typer.echo("No history found")
            else:
                for event in events:
                    typer.echo(format_event(event, verbose=verbose))
                typer.echo(get_event_legend())

        except typer.Exit:
            raise
        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1) from e

    @app.command(name="h", hidden=True)
    def history_alias(
        issue: str | None = typer.Option(
            None,
            "--issue",
            "-i",
            help="Filter events for a specific issue",
            autocompletion=complete_issue_ids,
        ),
        limit: int = typer.Option(
            20,
            "--limit",
            "-n",
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
            issue=issue,
            limit=limit,
            json_output=json_output,
            verbose=verbose,
            dogcats_dir=dogcats_dir,
        )
