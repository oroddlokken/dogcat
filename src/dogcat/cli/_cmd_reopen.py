"""Reopen command for dogcat CLI."""

from __future__ import annotations

import orjson
import typer

from ._completions import complete_closed_issue_ids
from ._helpers import apply_to_each, get_default_operator, get_storage, with_ns_shim
from ._json_state import is_json, set_json


def register(app: typer.Typer) -> None:
    """Register reopen command."""

    @app.command()
    @with_ns_shim
    def reopen(
        issue_ids: list[str] = typer.Argument(  # noqa: B008
            ...,
            help="Issue ID(s) to reopen",
            autocompletion=complete_closed_issue_ids,
        ),
        reason: str | None = typer.Option(
            None,
            "--reason",
            "-r",
            help="Reason for reopening",
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        reopened_by: str | None = typer.Option(
            None,
            "--by",
            help="Who is reopening this",
        ),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Reopen one or more closed issues."""
        set_json(json_output)
        storage = get_storage(dogcats_dir)
        final_reopened_by = (
            reopened_by if reopened_by is not None else get_default_operator()
        )

        def _reopen(issue_id: str) -> None:
            issue = storage.reopen(
                issue_id, reason=reason, reopened_by=final_reopened_by
            )
            if is_json():
                from dogcat.models import issue_to_dict

                typer.echo(orjson.dumps(issue_to_dict(issue)).decode())
            else:
                typer.echo(f"✓ Reopened {issue.full_id}: {issue.title}")

        if apply_to_each(issue_ids, _reopen, verb="reopening"):
            raise typer.Exit(1)
