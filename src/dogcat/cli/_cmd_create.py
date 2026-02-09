"""Create commands for dogcat CLI."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import orjson
import typer

from dogcat.config import get_issue_prefix
from dogcat.constants import DEFAULT_PRIORITY, DEFAULT_TYPE, parse_labels
from dogcat.idgen import IDGenerator
from dogcat.models import Issue, IssueType, Status

from ._helpers import (
    _ARG_HELP,
    _make_alias,
    _parse_args_for_create,
    _parse_priority_value,
    get_default_operator,
    get_storage,
)


def register(app: typer.Typer) -> None:
    """Register create and new commands."""

    @app.command()
    def create(
        arg1: str | None = typer.Argument(
            None,
            help=_ARG_HELP,
        ),
        arg2: str | None = typer.Argument(
            None,
            help=_ARG_HELP,
        ),
        arg3: str | None = typer.Argument(
            None,
            help=_ARG_HELP,
        ),
        title_opt: str | None = typer.Option(
            None,
            "--title",
            help="Issue title (alternative to positional argument)",
        ),
        description: str | None = typer.Option(
            None,
            "--description",
            "-d",
            help="Issue description",
        ),
        priority: int | None = typer.Option(
            None,
            "--priority",
            "-p",
            help="Priority (0-4, p0-p4, or critical/high/medium/low/minimal)",
            parser=_parse_priority_value,
            metavar="PRIORITY",
        ),
        issue_type: str | None = typer.Option(None, "--type", "-t", help="Issue type"),
        status: str | None = typer.Option(
            None,
            "--status",
            "-s",
            help="Initial status (open, in_progress, blocked, deferred)",
        ),
        owner: str | None = typer.Option(None, "--owner", "-o", help="Issue owner"),
        labels: str | None = typer.Option(
            None,
            "--labels",
            "-l",
            help="Labels (comma or space separated)",
        ),
        acceptance: str | None = typer.Option(
            None,
            "--acceptance",
            "-a",
            help="Acceptance criteria",
        ),
        notes: str | None = typer.Option(
            None,
            "--notes",
            "-n",
            help="Notes for the issue",
        ),
        depends_on: str | None = typer.Option(
            None,
            "--depends-on",
            help="Issue ID this depends on (this issue is blocked by the other)",
        ),
        blocks: str | None = typer.Option(
            None,
            "--blocks",
            help="Issue ID this blocks (the other issue is blocked by this one)",
        ),
        parent: str | None = typer.Option(
            None,
            "--parent",
            help="Parent issue ID (makes this a subtask)",
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        created_by: str | None = typer.Option(
            None,
            "--created-by",
            help="Who is creating this",
        ),
        design: str | None = typer.Option(None, "--design", help="Design notes"),
        external_ref: str | None = typer.Option(
            None,
            "--external-ref",
            help="External reference URL or ID",
        ),
        duplicate_of: str | None = typer.Option(
            None,
            "--duplicate-of",
            help="Original issue ID if duplicate",
        ),
        manual: bool = typer.Option(
            False,
            "--manual",
            help="Mark issue as manual (not for agents)",
        ),
        editor: bool = typer.Option(
            False,
            "--editor",
            "-e",
            help="Open the Textual editor after creating the issue",
        ),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Create a new issue.

        Supports shorthand notation: use single characters (0-4 for priority,
        b/f/e/s for bug/feature/epic/story) before or after the title.

        If the title starts with --, use -- to stop option parsing:
            dcat create -- "--flag is not a flag"

        Examples:
            dcat create "Fix login bug"           # Default priority 2, type task
            dcat create --title "Fix login bug"   # Same, using --title flag
            dcat create "Fix login bug" 1         # Priority 1
            dcat create 1 "Fix login bug"         # Priority 1 (shorthand first)
            dcat create "Add feature" f           # Type feature
            dcat create b "Fix crash"             # Type bug (shorthand first)
            dcat create 0 b "Critical bug"        # Priority 0, type bug
            dcat create b 1 "Important bug"       # Type bug, priority 1
            dcat create "Fix login bug" -p 1      # Priority 1 (explicit flag)
            dcat create "Fix login bug" -p p1     # Priority 1 (pINT notation)
            dcat create "Add feature" -t feature  # Type feature (explicit flag)
            dcat create -- "--flag is not a flag"  # Title starting with dashes
        """
        try:
            # Parse arguments to extract title and shorthands
            title, shorthand_priority, shorthand_type = _parse_args_for_create(
                [arg1, arg2, arg3],
            )

            # --title flag overrides positional title if no positional title given
            if not title and title_opt:
                title = title_opt
            elif title and title_opt:
                typer.echo(
                    "Error: Cannot use both positional title and --title flag",
                    err=True,
                )
                raise typer.Exit(1)

            # Validate that shorthands and explicit options aren't used together
            if shorthand_priority is not None and priority is not None:
                typer.echo(
                    "Error: Cannot use both priority shorthand (0-4) and "
                    "--priority flag together",
                    err=True,
                )
                raise typer.Exit(1)
            if shorthand_type is not None and issue_type is not None:
                typer.echo(
                    "Error: Cannot use both type shorthand (b/f/e/s/q) and "
                    "--type flag together",
                    err=True,
                )
                raise typer.Exit(1)

            if not title:
                typer.echo("Error: Title is required", err=True)
                raise typer.Exit(1)

            storage = get_storage(dogcats_dir)

            # Get namespace from config
            namespace = get_issue_prefix(dogcats_dir)
            idgen = IDGenerator(existing_ids=storage.get_issue_ids(), prefix=namespace)

            # Generate ID hash
            timestamp = datetime.now().astimezone()
            issue_id = idgen.generate_issue_id(
                title,
                timestamp=timestamp,
                namespace=namespace,
            )

            # Parse labels
            issue_labels = parse_labels(labels) if labels else []

            # Determine final priority and type (explicit options override shorthand)
            final_priority = (
                priority
                if priority is not None
                else (
                    shorthand_priority
                    if shorthand_priority is not None
                    else DEFAULT_PRIORITY
                )
            )
            final_type = (
                issue_type
                if issue_type is not None
                else (shorthand_type if shorthand_type is not None else DEFAULT_TYPE)
            )

            # Determine initial status
            initial_status = Status(status) if status else Status.OPEN

            # Build metadata
            issue_metadata: dict[str, Any] = {}
            if manual:
                issue_metadata["manual"] = True

            # Set default operator for owner and created_by if not provided
            default_operator = get_default_operator()
            final_owner = owner if owner is not None else default_operator
            final_created_by = (
                created_by if created_by is not None else default_operator
            )

            # Validate dependency targets exist BEFORE creating
            # the issue (atomic operation)
            if depends_on:
                resolved_depends_on = storage.resolve_id(depends_on)
                if resolved_depends_on is None:
                    typer.echo(f"Error: Issue {depends_on} not found", err=True)
                    raise typer.Exit(1)
            if blocks:
                resolved_blocks = storage.resolve_id(blocks)
                if resolved_blocks is None:
                    typer.echo(f"Error: Issue {blocks} not found", err=True)
                    raise typer.Exit(1)

            # Resolve duplicate_of if provided
            if duplicate_of:
                resolved_dup = storage.resolve_id(duplicate_of)
                if resolved_dup is None:
                    typer.echo(f"Error: Issue {duplicate_of} not found", err=True)
                    raise typer.Exit(1)
                duplicate_of = resolved_dup

            # Resolve parent if provided
            if parent:
                resolved_parent = storage.resolve_id(parent)
                if resolved_parent is None:
                    typer.echo(f"Error: Parent issue {parent} not found", err=True)
                    raise typer.Exit(1)
                parent = resolved_parent

            # Create issue
            issue = Issue(
                id=issue_id,
                title=title,
                namespace=namespace,
                description=description,
                status=initial_status,
                priority=final_priority,
                issue_type=IssueType(final_type),
                owner=final_owner,
                parent=parent,
                labels=issue_labels,
                external_ref=external_ref,
                design=design,
                acceptance=acceptance,
                notes=notes,
                duplicate_of=duplicate_of,
                created_by=final_created_by,
                metadata=issue_metadata,
            )

            storage.create(issue)

            # Add dependencies if specified
            if depends_on:
                storage.add_dependency(
                    issue.full_id,
                    depends_on,
                    "blocks",
                    created_by=created_by,
                )
            if blocks:
                storage.add_dependency(
                    blocks,
                    issue.full_id,
                    "blocks",
                    created_by=created_by,
                )

            if json_output:
                from dogcat.models import issue_to_dict

                typer.echo(orjson.dumps(issue_to_dict(issue)).decode())
            else:
                typer.echo(
                    f"✓ Created {issue.full_id}: {title} "
                    f"[{final_type}, pri {final_priority}]",
                )

            if editor:
                from dogcat.edit import edit_issue

                updated = edit_issue(issue.full_id, storage)
                if updated is not None:
                    typer.echo(f"✓ Updated {updated.full_id}: {updated.title}")
                else:
                    typer.echo("Edit cancelled")

        except ValueError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)
        except typer.Exit:
            raise  # Re-raise without duplicate error message
        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)

    app.command(name="c", hidden=True)(
        _make_alias(
            create,
            doc=(
                "Create a new issue (alias for 'create' command).\n\n"
                "Supports shorthand notation: use single characters "
                "(0-4 for priority,\n"
                "b/f/e/s for bug/feature/epic/story) before or after the title.\n\n"
                "Examples:\n"
                '    dcat c "Fix login bug"           # Default priority 2, type task\n'
                '    dcat c "Fix login bug" 1         # Priority 1\n'
                '    dcat c 0 b "Critical bug"        # Priority 0, type bug'
            ),
            exclude_params=frozenset({"editor"}),
            param_defaults={"editor": False},
        ),
    )

    app.command(name="add", hidden=True)(
        _make_alias(
            create,
            doc="Create a new issue (alias for 'create' command).",
            exclude_params=frozenset({"editor"}),
            param_defaults={"editor": False},
        ),
    )

    @app.command(name="new")
    def new_issue_cmd(
        arg1: str | None = typer.Argument(None, help=_ARG_HELP),
        arg2: str | None = typer.Argument(None, help=_ARG_HELP),
        arg3: str | None = typer.Argument(None, help=_ARG_HELP),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """Open an interactive Textual form to create a new issue.

        Supports shorthand notation: use single characters (0-4 for priority,
        b/f/e/s for bug/feature/epic/story) before or after the title.

        Examples:
            dcat new                           # Empty form
            dcat new "Fix login bug"           # Pre-filled title
            dcat new "Fix login bug" 1         # Pre-filled title + priority 1
            dcat new b "Fix crash"             # Pre-filled type bug + title
            dcat new 0 b "Critical bug"        # Priority 0 + type bug + title
        """
        try:
            title = ""
            priority_sh: int | None = None
            type_sh: str | None = None

            if arg1 is not None:
                title, priority_sh, type_sh = _parse_args_for_create([arg1, arg2, arg3])

            storage = get_storage(dogcats_dir)
            namespace = get_issue_prefix(dogcats_dir)
            owner = get_default_operator()

            from dogcat.edit import new_issue

            created = new_issue(
                storage,
                namespace,
                owner=owner,
                title=title,
                priority=priority_sh,
                issue_type=type_sh,
            )
            if created is not None:
                if json_output:
                    from dogcat.models import issue_to_dict

                    typer.echo(orjson.dumps(issue_to_dict(created)).decode())
                else:
                    typer.echo(
                        f"✓ Created {created.full_id}: {created.title} "
                        f"[{created.issue_type.value}, pri {created.priority}]",
                    )
            else:
                typer.echo("Create cancelled")

        except ValueError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)
        except typer.Exit:
            raise
        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)

    app.command(name="n", hidden=True)(
        _make_alias(
            new_issue_cmd,
            doc="Open a Textual form to create a new issue (alias for 'new').",
        ),
    )
