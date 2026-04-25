"""Close and delete commands for dogcat CLI."""

from __future__ import annotations

from typing import TYPE_CHECKING

import orjson
import typer

from dogcat.models import Status

from ._completions import complete_issue_ids
from ._helpers import get_default_operator, get_storage
from ._json_state import echo_error, is_json_output

if TYPE_CHECKING:
    from dogcat.storage import JSONLStorage


def register(app: typer.Typer) -> None:
    """Register close, delete, and remove commands."""

    def _close_one(
        storage: JSONLStorage,
        issue_id: str,
        reason: str | None,
        closed_by: str | None,
        json_output: bool,
    ) -> tuple[bool, str | None]:
        """Close a single issue. Returns (had_error, parent_id)."""
        try:
            issue = storage.close(
                issue_id,
                reason=reason,
                closed_by=closed_by,
            )

            if is_json_output(json_output):
                from dogcat.models import issue_to_dict

                typer.echo(orjson.dumps(issue_to_dict(issue)).decode())
            else:
                typer.echo(f"✓ Closed {issue.full_id}: {issue.title}")
        except (ValueError, Exception) as e:
            echo_error(f"closing {issue_id}: {e}")
            return True, None
        else:
            return False, issue.parent

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
        all_namespaces: bool = typer.Option(  # noqa: ARG001
            False,
            "--all-namespaces",
            "--all-ns",
            "-A",
            hidden=True,
        ),
        namespace: str | None = typer.Option(  # noqa: ARG001
            None,
            "--namespace",
            hidden=True,
        ),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Close one or more issues."""
        storage = get_storage(dogcats_dir)
        final_closed_by = closed_by if closed_by is not None else get_default_operator()
        has_errors = False
        parent_ids: set[str] = set()

        for issue_id in issue_ids:
            had_error, parent_id = _close_one(
                storage,
                issue_id,
                reason,
                final_closed_by,
                json_output,
            )
            has_errors = had_error or has_errors
            if parent_id:
                parent_ids.add(parent_id)

        if parent_ids and not is_json_output(json_output):
            _check_epic_completion(storage, parent_ids)

        if has_errors:
            raise typer.Exit(1)

    def _delete_one(
        storage: JSONLStorage,
        issue_id: str,
        reason: str | None,
        deleted_by: str | None,
        json_output: bool,
    ) -> bool:
        """Delete a single issue. Returns True if an error occurred."""
        try:
            deleted_issue = storage.delete(
                issue_id,
                reason=reason,
                deleted_by=deleted_by,
            )

            if is_json_output(json_output):
                from dogcat.models import issue_to_dict

                typer.echo(orjson.dumps(issue_to_dict(deleted_issue)).decode())
            else:
                typer.echo(f"✓ Deleted {deleted_issue.full_id}: {deleted_issue.title}")
        except (ValueError, Exception) as e:
            echo_error(f"deleting {issue_id}: {e}")
            return True
        return False

    @app.command()
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
        all_namespaces: bool = typer.Option(  # noqa: ARG001
            False,
            "--all-namespaces",
            "--all-ns",
            "-A",
            hidden=True,
        ),
        namespace: str | None = typer.Option(  # noqa: ARG001
            None,
            "--namespace",
            hidden=True,
        ),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Delete one or more issues (creates tombstone).

        This marks the issue(s) as deleted (tombstone status) rather than permanently
        removing them from the database. Issues will be hidden from normal lists
        but can still be viewed with --all flag.
        """
        storage = get_storage(dogcats_dir)
        final_deleted_by = (
            deleted_by if deleted_by is not None else get_default_operator()
        )
        has_errors = False

        for issue_id in issue_ids:
            has_errors = (
                _delete_one(
                    storage,
                    issue_id,
                    reason,
                    final_deleted_by,
                    json_output,
                )
                or has_errors
            )

        if has_errors:
            raise typer.Exit(1)

    @app.command(name="remove", hidden=True)
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
        all_namespaces: bool = typer.Option(  # noqa: ARG001
            False,
            "--all-namespaces",
            "--all-ns",
            "-A",
            hidden=True,
        ),
        namespace: str | None = typer.Option(  # noqa: ARG001
            None,
            "--namespace",
            hidden=True,
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
