"""Update command for dogcat CLI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import orjson
import typer

from dogcat.constants import parse_labels
from dogcat.models import UpdateRequest, set_manual_flag

from ._completions import (
    complete_issue_ids,
    complete_labels,
    complete_namespaces,
    complete_owners,
    complete_priorities,
    complete_snooze_durations,
    complete_statuses,
    complete_types,
)
from ._helpers import (
    _parse_priority_value,
    apply_to_each,
    get_default_operator,
    get_storage,
    parse_duration,
)
from ._json_state import echo_error, is_json, set_json

if TYPE_CHECKING:
    from dogcat.storage import JSONLStorage


def _apply_manual_metadata_update(
    storage: JSONLStorage,
    issue_id: str,
    issue_updates: dict[str, Any],
    *,
    manual: bool | None,
) -> dict[str, Any]:
    """Patch ``issue_updates['metadata']`` with the new manual flag, if set.

    Returns the same dict so the caller can keep chaining mutations.
    Raises ``ValueError`` if the issue is missing — same contract the
    inline code had.
    """
    if manual is None:
        return issue_updates
    current = storage.get(issue_id)
    if current is None:
        msg = f"Issue {issue_id} not found"
        raise ValueError(msg)
    issue_updates["metadata"] = set_manual_flag(current.metadata or {}, manual=manual)
    return issue_updates


def _remove_dep_with_check(
    storage: JSONLStorage,
    *,
    subject: str,
    target_partial_id: str,
    direction: str,
) -> None:
    """Remove a dependency between ``subject`` and the resolved target.

    ``direction='depends_on'`` removes ``subject -> target``; the message
    is ``"{subject} does not depend on {target}"``.

    ``direction='blocks'`` removes ``target -> subject``; the message is
    ``"{subject} does not block {target}"``.

    Raises ``ValueError`` if the target doesn't resolve or if the
    expected dependency isn't there. Centralizes the two near-identical
    blocks the CLI used to spell out inline.
    """
    resolved_target = storage.resolve_id(target_partial_id)
    if resolved_target is None:
        msg = f"Issue {target_partial_id} not found"
        raise ValueError(msg)
    if direction == "depends_on":
        deps = storage.get_dependencies(subject)
        if not any(d.depends_on_id == resolved_target for d in deps):
            msg = f"{subject} does not depend on {resolved_target}"
            raise ValueError(msg)
        storage.remove_dependency(subject, resolved_target)
        return
    # The "blocks" direction looks for the inverse edge: target -> subject.
    deps = storage.get_dependencies(resolved_target)
    if not any(d.depends_on_id == subject for d in deps):
        msg = f"{subject} does not block {resolved_target}"
        raise ValueError(msg)
    storage.remove_dependency(resolved_target, subject)


def register(app: typer.Typer) -> None:
    """Register update command."""

    @app.command()
    def update(
        issue_ids: list[str] = typer.Argument(  # noqa: B008
            ...,
            help="Issue ID(s) to update",
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
            "--label",
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
        snooze_until: str | None = typer.Option(
            None,
            "--snooze-until",
            "--snooze",
            help="Snooze until duration (e.g. 7d, 2w) or ISO8601 date",
            autocompletion=complete_snooze_durations,
        ),
        unsnooze: bool = typer.Option(
            False,
            "--unsnooze",
            help="Remove snooze from issue",
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        updated_by: str | None = typer.Option(
            None,
            "--by",
            help="Who is updating this",
        ),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Update one or more issues."""
        set_json(json_output)
        try:
            # Merge --body into --description (hidden alias)
            if body is not None:
                if description is not None:
                    echo_error("Cannot use both --description and --body together")
                    raise typer.Exit(1)
                description = body

            # Guard: single-issue options cannot be used with multiple IDs
            if len(issue_ids) > 1:
                provided_single = {
                    name
                    for name, val in {
                        "title": title,
                        "description": description,
                        "parent": parent,
                        "duplicate_of": duplicate_of,
                        "namespace": namespace,
                        "acceptance": acceptance,
                        "notes": notes,
                        "design": design,
                        "external_ref": external_ref,
                        "depends_on": depends_on,
                        "blocks": blocks,
                        "remove_depends_on": remove_depends_on,
                        "remove_blocks": remove_blocks,
                    }.items()
                    if val is not None
                }
                if provided_single:
                    opts = ", ".join(
                        f"--{n.replace('_', '-')}" for n in sorted(provided_single)
                    )
                    echo_error(f"Cannot use {opts} with multiple issue IDs")
                    raise typer.Exit(1)

            storage = get_storage(dogcats_dir)

            # Build a typed UpdateRequest instead of an untyped dict so unknown
            # field names are rejected at construction time.
            request = UpdateRequest()
            if title is not None:
                request.title = title
            if status is not None:
                request.status = status
            if priority is not None:
                request.priority = priority
            if issue_type is not None:
                request.issue_type = issue_type
            if description is not None:
                request.description = description
            if owner is not None:
                request.owner = owner
            if acceptance is not None:
                request.acceptance = acceptance
            if notes is not None:
                request.notes = notes
            if design is not None:
                request.design = design
            if external_ref is not None:
                request.external_ref = external_ref
            if duplicate_of is not None:
                if duplicate_of == "":
                    request.duplicate_of = None
                else:
                    from ._helpers import require_resolved_id

                    request.duplicate_of = require_resolved_id(
                        storage, duplicate_of, label="Duplicate target"
                    )
            if parent is not None:
                if parent == "":
                    request.parent = None
                else:
                    from ._helpers import require_resolved_id

                    request.parent = require_resolved_id(
                        storage, parent, label="Parent issue"
                    )
            if labels is not None:
                request.labels = parse_labels(labels)
            if snooze_until is not None:
                request.snoozed_until = parse_duration(snooze_until)
            if unsnooze:
                request.snoozed_until = None

            updates = request.to_dict()

            if (
                request.is_empty()
                and manual is None
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

            def _update(issue_id: str) -> None:
                issue_updates = _apply_manual_metadata_update(
                    storage, issue_id, dict(updates), manual=manual
                )

                if issue_updates:
                    issue_updates["updated_by"] = final_updated_by
                    issue = storage.update(issue_id, issue_updates)
                else:
                    issue = storage.get(issue_id)
                    if issue is None:
                        msg = f"Issue {issue_id} not found"
                        raise ValueError(msg)

                if namespace is not None:
                    issue = storage.change_namespace(
                        issue.full_id,
                        namespace,
                        updated_by=final_updated_by,
                    )

                if depends_on:
                    storage.add_dependency(
                        issue_id, depends_on, "blocks", created_by=final_updated_by
                    )
                if blocks:
                    storage.add_dependency(
                        blocks, issue.full_id, "blocks", created_by=final_updated_by
                    )

                if remove_depends_on:
                    _remove_dep_with_check(
                        storage,
                        subject=issue.full_id,
                        target_partial_id=remove_depends_on,
                        direction="depends_on",
                    )
                if remove_blocks:
                    _remove_dep_with_check(
                        storage,
                        subject=issue.full_id,
                        target_partial_id=remove_blocks,
                        direction="blocks",
                    )

                if is_json():
                    from dogcat.models import issue_to_dict

                    typer.echo(orjson.dumps(issue_to_dict(issue)).decode())
                else:
                    typer.echo(f"✓ Updated {issue.full_id}: {issue.title}")

            with storage.batch():
                has_errors = apply_to_each(issue_ids, _update, verb="updating")
            if has_errors:
                raise typer.Exit(1)

        except typer.Exit:
            raise
        except Exception as e:
            echo_error(str(e))
            raise typer.Exit(1)
