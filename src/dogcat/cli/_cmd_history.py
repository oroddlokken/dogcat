"""History command for dogcat CLI."""

from __future__ import annotations

from typing import TYPE_CHECKING

import orjson
import typer

from dogcat.config import extract_prefix, get_namespace_filter

from ._completions import complete_issue_ids
from ._formatting import format_event, get_event_legend
from ._helpers import get_storage
from ._json_state import echo_error, is_json_output

if TYPE_CHECKING:
    from dogcat.event_log import EventRecord


def _merge_events(
    issue_events: list[EventRecord],
    inbox_events: list[EventRecord],
    limit: int,
) -> list[EventRecord]:
    """Merge two newest-first event lists into one newest-first list."""
    merged: list[EventRecord] = []
    i, j = 0, 0
    while len(merged) < limit and (i < len(issue_events) or j < len(inbox_events)):
        if i >= len(issue_events):
            merged.append(inbox_events[j])
            j += 1
        elif (
            j >= len(inbox_events)
            or issue_events[i].timestamp >= inbox_events[j].timestamp
        ):
            merged.append(issue_events[i])
            i += 1
        else:
            merged.append(inbox_events[j])
            j += 1
    return merged


def _load_inbox_titles(dogcats_dir: str) -> dict[str, str]:
    """Load proposal titles for filling in missing event titles."""
    try:
        from dogcat.inbox import InboxStorage

        inbox = InboxStorage(dogcats_dir=dogcats_dir)
        return {p.full_id: p.title for p in inbox.list(include_tombstones=True)}
    except (ValueError, RuntimeError):
        return {}


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
            help="Filter events for a specific issue or proposal",
            autocompletion=complete_issue_ids,
        ),
        include_inbox: bool = typer.Option(
            True,
            "--include-inbox/--no-inbox",
            help="Include inbox proposal events",
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
            from dogcat.event_log import EventLog, InboxEventLog, _serialize

            final_limit = limit_arg or limit or 20
            storage = get_storage(dogcats_dir)
            event_log = EventLog(storage.dogcats_dir)

            # Resolve partial issue ID if provided — try issues first, then inbox
            resolved_issue = None
            if issue:
                resolved_issue = storage.resolve_id(issue)
                if resolved_issue is None:
                    # Try resolving as inbox proposal
                    try:
                        from dogcat.inbox import InboxStorage

                        inbox = InboxStorage(
                            dogcats_dir=str(storage.dogcats_dir),
                        )
                        resolved_issue = inbox.resolve_id(issue)
                    except (ValueError, RuntimeError):
                        pass
                if resolved_issue is None:
                    echo_error(f"Issue or proposal {issue} not found")
                    raise typer.Exit(1)

            events = event_log.read(issue_id=resolved_issue, limit=final_limit)

            # Merge inbox events
            if include_inbox:
                try:
                    inbox_log = InboxEventLog(storage.dogcats_dir)
                    inbox_events = inbox_log.read(
                        issue_id=resolved_issue,
                        limit=final_limit,
                    )
                    events = _merge_events(events, inbox_events, final_limit)
                except (ValueError, RuntimeError):
                    pass  # No inbox file — skip silently

            # Apply namespace filter (skip if --all-namespaces)
            if not all_namespaces:
                actual_dogcats_dir = str(storage.dogcats_dir)
                ns_filter = get_namespace_filter(actual_dogcats_dir)
                if ns_filter is not None:
                    events = [
                        e for e in events if ns_filter(extract_prefix(e.issue_id) or "")
                    ]

            events.reverse()  # Display oldest-first (chronological)

            # Fill in missing titles from storage (issues) and inbox (proposals)
            inbox_cache: dict[str, str] | None = None
            for event in events:
                if not event.title:
                    issue_obj = storage.get(event.issue_id)
                    if issue_obj:
                        event.title = issue_obj.title
                    elif "inbox" in event.issue_id:
                        if inbox_cache is None:
                            inbox_cache = _load_inbox_titles(
                                str(storage.dogcats_dir),
                            )
                        event.title = inbox_cache.get(event.issue_id)

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
            help="Filter events for a specific issue or proposal",
            autocompletion=complete_issue_ids,
        ),
        include_inbox: bool = typer.Option(
            True,
            "--include-inbox/--no-inbox",
            help="Include inbox proposal events",
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
            include_inbox=include_inbox,
            limit=limit,
            json_output=json_output,
            verbose=verbose,
            dogcats_dir=dogcats_dir,
        )
