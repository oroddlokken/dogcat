"""Reopen command for dogcat CLI."""

from __future__ import annotations

from typing import TYPE_CHECKING

import orjson
import typer

from ._completions import complete_issue_ids
from ._helpers import get_default_operator, get_storage
from ._json_state import echo_error, is_json_output

if TYPE_CHECKING:
    from dogcat.storage import JSONLStorage


def register(app: typer.Typer) -> None:
    """Register reopen command."""

    def _reopen_one(
        storage: JSONLStorage,
        issue_id: str,
        reason: str | None,
        reopened_by: str | None,
        json_output: bool,
    ) -> bool:
        """Reopen a single issue. Returns True if an error occurred."""
        try:
            issue = storage.reopen(
                issue_id,
                reason=reason,
                reopened_by=reopened_by,
            )

            if is_json_output(json_output):
                from dogcat.models import issue_to_dict

                typer.echo(orjson.dumps(issue_to_dict(issue)).decode())
            else:
                typer.echo(f"✓ Reopened {issue.full_id}: {issue.title}")
        except (ValueError, Exception) as e:
            echo_error(f"reopening {issue_id}: {e}")
            return True
        return False

    @app.command()
    def reopen(
        issue_ids: list[str] = typer.Argument(  # noqa: B008
            ...,
            help="Issue ID(s) to reopen",
            autocompletion=complete_issue_ids,
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
            "--reopened-by",
            help="Who is reopening this",
        ),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Reopen one or more closed issues."""
        storage = get_storage(dogcats_dir)
        final_reopened_by = (
            reopened_by if reopened_by is not None else get_default_operator()
        )
        has_errors = False

        for issue_id in issue_ids:
            has_errors = (
                _reopen_one(
                    storage,
                    issue_id,
                    reason,
                    final_reopened_by,
                    json_output,
                )
                or has_errors
            )

        if has_errors:
            raise typer.Exit(1)
