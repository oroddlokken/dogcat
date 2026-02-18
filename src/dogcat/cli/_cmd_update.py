"""Update command for dogcat CLI."""

from __future__ import annotations

from typing import Any

import orjson
import typer

from dogcat.constants import parse_labels

from ._completions import (
    complete_issue_ids,
    complete_labels,
    complete_namespaces,
    complete_owners,
    complete_priorities,
    complete_statuses,
    complete_types,
)
from ._helpers import _parse_priority_value, get_default_operator, get_storage
from ._json_state import echo_error, is_json_output


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
            help="New status (draft, open, in_progress, in_review, blocked, deferred)",
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
            help="New issue type (task, bug, feature, story, chore, epic, question)",
            autocompletion=complete_types,
        ),
        description: str | None = typer.Option(
            None,
            "--description",
            "-d",
            help="New description",
        ),
        body: str | None = typer.Option(
            None,
            "--body",
            help="New description (alias for --description)",
            hidden=True,
        ),
        owner: str | None = typer.Option(
            None,
            "--owner",
            "-o",
            help="New owner",
            autocompletion=complete_owners,
        ),
        acceptance: str | None = typer.Option(
            None,
            "--acceptance",
            "--acceptance-criteria",
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
            help="Parent issue ID (makes this a child issue)",
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
        remove_depends_on: str | None = typer.Option(
            None,
            "--remove-depends-on",
            help="Remove a dependency this issue has on another",
            autocompletion=complete_issue_ids,
        ),
        remove_blocks: str | None = typer.Option(
            None,
            "--remove-blocks",
            help="Remove a blocks relationship from this issue to another",
            autocompletion=complete_issue_ids,
        ),
        namespace: str | None = typer.Option(
            None,
            "--namespace",
            help="Move issue to a different namespace (cascades to all references)",
            autocompletion=complete_namespaces,
        ),
        all_namespaces: bool = typer.Option(  # noqa: ARG001
            False,
            "--all-namespaces",
            "--all-ns",
            "-A",
            hidden=True,
        ),
        manual: bool | None = typer.Option(
            None,
            "--manual/--no-manual",
            help="Mark/unmark issue as manual (not for agents)",
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        updated_by: str | None = typer.Option(
            None,
            "--by",
            help="Who is updating this",
        ),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Update an issue."""
        try:
            # Merge --body into --description (hidden alias)
            if body is not None:
                if description is not None:
                    echo_error("Cannot use both --description and --body together")
                    raise typer.Exit(1)
                description = body

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
                        echo_error(f"Issue {duplicate_of} not found")
                        raise typer.Exit(1)
                    updates["duplicate_of"] = resolved_dup
            if parent is not None:
                if parent == "":
                    updates["parent"] = None
                else:
                    resolved_parent = storage.resolve_id(parent)
                    if resolved_parent is None:
                        echo_error(f"Parent issue {parent} not found")
                        raise typer.Exit(1)
                    updates["parent"] = resolved_parent
            if labels is not None:
                updates["labels"] = parse_labels(labels)
            if manual is not None:
                # Get current issue to preserve existing metadata
                current = storage.get(issue_id)
                if current is None:
                    echo_error(f"Issue {issue_id} not found")
                    raise typer.Exit(1)
                new_metadata = dict(current.metadata) if current.metadata else {}
                if manual:
                    new_metadata["manual"] = True
                    new_metadata.pop("no_agent", None)  # migrate old key
                else:
                    new_metadata.pop("manual", None)
                    new_metadata.pop("no_agent", None)  # migrate old key
                updates["metadata"] = new_metadata

            if (
                not updates
                and not namespace
                and not depends_on
                and not blocks
                and not remove_depends_on
                and not remove_blocks
            ):
                echo_error("No updates provided")
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
                    echo_error(f"Issue {issue_id} not found")
                    raise typer.Exit(1)

            # Change namespace if specified (must happen after regular
            # updates since it re-keys the issue and cascades references)
            if namespace is not None:
                issue = storage.change_namespace(
                    issue.full_id,
                    namespace,
                    updated_by=final_updated_by,
                )

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

            # Remove dependencies if specified
            if remove_depends_on:
                resolved_target = storage.resolve_id(remove_depends_on)
                if resolved_target is None:
                    echo_error(f"Issue {remove_depends_on} not found")
                    raise typer.Exit(1)
                # Check the dependency exists before removing
                deps = storage.get_dependencies(issue.full_id)
                if not any(d.depends_on_id == resolved_target for d in deps):
                    echo_error(f"{issue.full_id} does not depend on {resolved_target}")
                    raise typer.Exit(1)
                storage.remove_dependency(issue.full_id, resolved_target)

            if remove_blocks:
                resolved_target = storage.resolve_id(remove_blocks)
                if resolved_target is None:
                    echo_error(f"Issue {remove_blocks} not found")
                    raise typer.Exit(1)
                # Check the dependency exists before removing (reversed direction)
                deps = storage.get_dependencies(resolved_target)
                if not any(d.depends_on_id == issue.full_id for d in deps):
                    echo_error(f"{issue.full_id} does not block {resolved_target}")
                    raise typer.Exit(1)
                storage.remove_dependency(resolved_target, issue.full_id)

            if is_json_output(json_output):
                from dogcat.models import issue_to_dict

                typer.echo(orjson.dumps(issue_to_dict(issue)).decode())
            else:
                typer.echo(f"✓ Updated {issue.full_id}: {issue.title}")

        except ValueError as e:
            echo_error(str(e))
            raise typer.Exit(1)
        except typer.Exit:
            raise
        except Exception as e:
            echo_error(str(e))
            raise typer.Exit(1)
