"""Close and delete commands for dogcat CLI."""

from __future__ import annotations

from typing import TYPE_CHECKING

import orjson
import typer

from dogcat.models import Status

from ._completions import complete_issue_ids
from ._helpers import apply_to_each, get_default_operator, get_storage, with_ns_shim
from ._json_state import is_json, set_json

if TYPE_CHECKING:
    from dogcat.storage import JSONLStorage


def register(app: typer.Typer) -> None:
    """Register close, delete, and remove commands."""

    def _check_epic_completion(
        storage: JSONLStorage,
        parent_ids: set[str],
    ) -> None:
        """Print a message if all children of a parent are now closed."""
        for parent_id in parent_ids:
            parent = storage.get(parent_id)
            if parent is None:
                continue
            siblings = storage.get_children(parent_id)
            if all(s.status in (Status.CLOSED, Status.TOMBSTONE) for s in siblings):
                typer.echo(
                    f"All children of {parent.issue_type.value} {parent.full_id}"
                    f" '{parent.title}' are now closed."
                    f" Close the {parent.issue_type.value} with:"
                    f" dcat close {parent.id}"
                )

    @app.command()
    @with_ns_shim
    def close(
        issue_ids: list[str] = typer.Argument(  # noqa: B008
            ...,
            help="Issue ID(s) to close",
            autocompletion=complete_issue_ids,
        ),
        reason: str | None = typer.Option(
            None,
            "--reason",
            "-r",
            help="Reason for closing",
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        closed_by: str | None = typer.Option(
            None,
            "--by",
            help="Who is closing this",
        ),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Close one or more issues."""
        set_json(json_output)
        storage = get_storage(dogcats_dir)
        final_closed_by = closed_by if closed_by is not None else get_default_operator()
        parent_ids: set[str] = set()

        def _close(issue_id: str) -> None:
            issue = storage.close(issue_id, reason=reason, closed_by=final_closed_by)
            if issue.parent:
                parent_ids.add(issue.parent)
            if is_json():
                from dogcat.models import issue_to_dict

                typer.echo(orjson.dumps(issue_to_dict(issue)).decode())
            else:
                typer.echo(f"✓ Closed {issue.full_id}: {issue.title}")

        with storage.batch():
            has_errors = apply_to_each(issue_ids, _close, verb="closing")

        if parent_ids and not is_json():
            _check_epic_completion(storage, parent_ids)

        if has_errors:
            raise typer.Exit(1)

    @app.command()
    @with_ns_shim
    def delete(
        issue_ids: list[str] = typer.Argument(  # noqa: B008
            ...,
            help="Issue ID(s) to delete",
            autocompletion=complete_issue_ids,
        ),
        reason: str | None = typer.Option(
            None,
            "--reason",
            "-r",
            help="Reason for deletion",
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        deleted_by: str | None = typer.Option(
            None,
            "--by",
            help="Who is deleting this",
        ),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Delete one or more issues (creates tombstone).

        This marks the issue(s) as deleted (tombstone status) rather than permanently
        removing them from the database. Issues will be hidden from normal lists
        but can still be viewed with --all flag.
        """
        set_json(json_output)
        storage = get_storage(dogcats_dir)
        final_deleted_by = (
            deleted_by if deleted_by is not None else get_default_operator()
        )

        def _delete(issue_id: str) -> None:
            deleted = storage.delete(
                issue_id, reason=reason, deleted_by=final_deleted_by
            )
            if is_json():
                from dogcat.models import issue_to_dict

                typer.echo(orjson.dumps(issue_to_dict(deleted)).decode())
            else:
                typer.echo(f"✓ Deleted {deleted.full_id}: {deleted.title}")

        with storage.batch():
            has_errors = apply_to_each(issue_ids, _delete, verb="deleting")
        if has_errors:
            raise typer.Exit(1)

    @app.command(name="remove", hidden=True)
    @with_ns_shim
    def remove(
        issue_id: str = typer.Argument(
            ...,
            help="Issue ID",
            autocompletion=complete_issue_ids,
        ),
        reason: str = typer.Option(None, "--reason", "-r", help="Reason for deletion"),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        deleted_by: str = typer.Option(
            None,
            "--by",
            help="Who is deleting this",
        ),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Delete an issue (alias for 'delete' command).

        This marks the issue as deleted (tombstone status) rather than permanently
        removing it from the database. The issue will be hidden from normal lists
        but can still be viewed with --all flag.
        """
        # Just call delete with the same parameters
        delete(
            issue_ids=[issue_id],
            reason=reason,
            json_output=json_output,
            deleted_by=deleted_by,
            dogcats_dir=dogcats_dir,
        )
