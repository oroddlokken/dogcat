"""Update command for dogcat CLI."""

from __future__ import annotations

from typing import Any

import orjson
import typer

from dogcat.constants import parse_labels

from ._completions import (
    complete_issue_ids,
    complete_labels,
    complete_priorities,
    complete_statuses,
    complete_types,
)
from ._helpers import _parse_priority_value, get_default_operator, get_storage


def register(app: typer.Typer) -> None:
    """Register update command."""

    @app.command()
    def update(
        issue_id: str = typer.Argument(
            ...,
            help="Issue ID",
            autocompletion=complete_issue_ids,
        ),
        title: str | None = typer.Option(None, "--title", help="New title"),
        status: str | None = typer.Option(
            None,
            "--status",
            "-s",
            help="New status",
            autocompletion=complete_statuses,
        ),
        priority: int | None = typer.Option(
            None,
            "--priority",
            "-p",
            help="New priority (0-4 or p0-p4)",
            parser=_parse_priority_value,
            metavar="PRIORITY",
            autocompletion=complete_priorities,
        ),
        issue_type: str | None = typer.Option(
            None,
            "--type",
            "-t",
            help="New issue type",
            autocompletion=complete_types,
        ),
        description: str | None = typer.Option(
            None,
            "--description",
            "-d",
            help="New description",
        ),
        owner: str | None = typer.Option(None, "--owner", "-o", help="New owner"),
        acceptance: str | None = typer.Option(
            None,
            "--acceptance",
            "-a",
            help="New acceptance criteria",
        ),
        notes: str | None = typer.Option(None, "--notes", "-n", help="New notes"),
        duplicate_of: str | None = typer.Option(
            None,
            "--duplicate-of",
            help="Original issue ID if duplicate",
            autocompletion=complete_issue_ids,
        ),
        parent: str | None = typer.Option(
            None,
            "--parent",
            help="Parent issue ID (makes this a subtask)",
            autocompletion=complete_issue_ids,
        ),
        labels: str | None = typer.Option(
            None,
            "--labels",
            "-l",
            help="Labels, comma or space separated (replaces existing)",
            autocompletion=complete_labels,
        ),
        design: str | None = typer.Option(None, "--design", help="New design notes"),
        external_ref: str | None = typer.Option(
            None,
            "--external-ref",
            help="New external reference URL or ID",
        ),
        depends_on: str | None = typer.Option(
            None,
            "--depends-on",
            help="Issue ID this depends on (this issue is blocked by the other)",
            autocompletion=complete_issue_ids,
        ),
        blocks: str | None = typer.Option(
            None,
            "--blocks",
            help="Issue ID this blocks (the other issue is blocked by this one)",
            autocompletion=complete_issue_ids,
        ),
        manual: bool | None = typer.Option(
            None,
            "--manual/--no-manual",
            help="Mark/unmark issue as manual (not for agents)",
        ),
        editor: bool = typer.Option(
            False,
            "--editor",
            "-e",
            help="Open the Textual editor after updating the issue",
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        updated_by: str | None = typer.Option(
            None,
            "--updated-by",
            help="Who is updating this",
        ),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Update an issue."""
        try:
            storage = get_storage(dogcats_dir)

            # Build updates dict
            updates: dict[str, Any] = {}
            if title is not None:
                updates["title"] = title
            if status is not None:
                updates["status"] = status
            if priority is not None:
                updates["priority"] = priority
            if issue_type is not None:
                updates["issue_type"] = issue_type
            if description is not None:
                updates["description"] = description
            if owner is not None:
                updates["owner"] = owner
            if acceptance is not None:
                updates["acceptance"] = acceptance
            if notes is not None:
                updates["notes"] = notes
            if design is not None:
                updates["design"] = design
            if external_ref is not None:
                updates["external_ref"] = external_ref
            if duplicate_of is not None:
                if duplicate_of == "":
                    updates["duplicate_of"] = None
                else:
                    resolved_dup = storage.resolve_id(duplicate_of)
                    if resolved_dup is None:
                        typer.echo(f"Error: Issue {duplicate_of} not found", err=True)
                        raise typer.Exit(1)
                    updates["duplicate_of"] = resolved_dup
            if parent is not None:
                if parent == "":
                    updates["parent"] = None
                else:
                    resolved_parent = storage.resolve_id(parent)
                    if resolved_parent is None:
                        typer.echo(f"Error: Parent issue {parent} not found", err=True)
                        raise typer.Exit(1)
                    updates["parent"] = resolved_parent
            if labels is not None:
                updates["labels"] = parse_labels(labels)
            if manual is not None:
                # Get current issue to preserve existing metadata
                current = storage.get(issue_id)
                if current is None:
                    typer.echo(f"Issue {issue_id} not found", err=True)
                    raise typer.Exit(1)
                new_metadata = dict(current.metadata) if current.metadata else {}
                if manual:
                    new_metadata["manual"] = True
                    new_metadata.pop("no_agent", None)  # migrate old key
                else:
                    new_metadata.pop("manual", None)
                    new_metadata.pop("no_agent", None)  # migrate old key
                updates["metadata"] = new_metadata

            if not updates and not depends_on and not blocks and not editor:
                typer.echo("No updates provided", err=True)
                raise typer.Exit(1)

            # Set updated_by to default operator if not provided
            final_updated_by = (
                updated_by if updated_by is not None else get_default_operator()
            )

            if updates:
                updates["updated_by"] = final_updated_by
                issue = storage.update(issue_id, updates)
            else:
                issue = storage.get(issue_id)
                if issue is None:
                    typer.echo(f"Issue {issue_id} not found", err=True)
                    raise typer.Exit(1)

            # Add dependencies if specified
            if depends_on:
                storage.add_dependency(
                    issue_id,
                    depends_on,
                    "blocks",
                    created_by=final_updated_by,
                )
            if blocks:
                storage.add_dependency(
                    blocks,
                    issue.full_id,
                    "blocks",
                    created_by=final_updated_by,
                )

            if json_output:
                from dogcat.models import issue_to_dict

                typer.echo(orjson.dumps(issue_to_dict(issue)).decode())
            else:
                typer.echo(f"✓ Updated {issue.full_id}: {issue.title}")

            if editor:
                from dogcat.edit import edit_issue

                edited = edit_issue(issue.full_id, storage)
                if edited is not None:
                    typer.echo(f"✓ Updated {edited.full_id}: {edited.title}")
                else:
                    typer.echo("Edit cancelled")

        except ValueError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)
        except typer.Exit:
            raise
        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)
