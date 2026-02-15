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

from ._completions import (
    complete_issue_ids,
    complete_labels,
    complete_priorities,
    complete_statuses,
    complete_types,
)
from ._helpers import (
    _ARG_HELP,
    _ARG_HELP_SHORTHAND,
    _make_alias,
    _parse_args_for_create,
    _parse_priority_value,
    get_default_operator,
    get_storage,
)
from ._json_state import echo_error, is_json_output

_CREATE_DOC = """\
Create a new issue.

Use --type and --priority flags to set type and priority.

If the title starts with --, use -- to stop option parsing:
    dcat create -- "--flag is not a flag"

Examples:
    dcat create "Fix login bug"           # Default priority 2, type task
    dcat create --title "Fix login bug"   # Same, using --title flag
    dcat create "Fix login bug" -p 1      # Priority 1 (explicit flag)
    dcat create "Fix login bug" -p p1     # Priority 1 (pINT notation)
    dcat create "Add feature" -t feature  # Type feature (explicit flag)
    dcat create -- "--flag is not a flag"  # Title starting with dashes\
"""

_C_DOC = """\
Create a new issue (quick create).

Supports shorthand notation: use single characters (0-4 for priority,
b/f/e/s for bug/feature/epic/story, d for draft status) before or after the title.

Examples:
    dcat c "Fix login bug"           # Default priority 2, type task
    dcat c "Fix login bug" 1         # Priority 1
    dcat c 0 b "Critical bug"        # Priority 0, type bug
    dcat c d "Initial thoughts"      # Draft status
    dcat c e 0 d "Design v2"        # Epic, priority 0, draft status\
"""


def register(app: typer.Typer) -> None:
    """Register create and new commands."""

    def _create_impl(
        arg1: str | None = typer.Argument(
            None,
            help=_ARG_HELP_SHORTHAND,
        ),
        arg2: str | None = typer.Argument(
            None,
            help=_ARG_HELP_SHORTHAND,
        ),
        arg3: str | None = typer.Argument(
            None,
            help=_ARG_HELP_SHORTHAND,
        ),
        arg4: str | None = typer.Argument(
            None,
            help=_ARG_HELP_SHORTHAND,
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
            autocompletion=complete_priorities,
        ),
        issue_type: str | None = typer.Option(
            None,
            "--type",
            "-t",
            help="Issue type (task, bug, feature, story, chore, epic, question)",
            autocompletion=complete_types,
        ),
        status: str | None = typer.Option(
            None,
            "--status",
            "-s",
            help="Initial status (draft, open, in_progress, blocked, deferred)",
            autocompletion=complete_statuses,
        ),
        owner: str | None = typer.Option(None, "--owner", "-o", help="Issue owner"),
        labels: str | None = typer.Option(
            None,
            "--labels",
            "-l",
            help="Labels (comma or space separated)",
            autocompletion=complete_labels,
        ),
        acceptance: str | None = typer.Option(
            None,
            "--acceptance",
            "--acceptance-criteria",
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
            autocompletion=complete_issue_ids,
        ),
        blocks: str | None = typer.Option(
            None,
            "--blocks",
            help="Issue ID this blocks (the other issue is blocked by this one)",
            autocompletion=complete_issue_ids,
        ),
        parent: str | None = typer.Option(
            None,
            "--parent",
            help="Parent issue ID (makes this a child issue)",
            autocompletion=complete_issue_ids,
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        created_by: str | None = typer.Option(
            None,
            "--by",
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
            autocompletion=complete_issue_ids,
        ),
        manual: bool = typer.Option(
            False,
            "--manual",
            help="Mark issue as manual (not for agents)",
        ),
        allow_shorthands: bool = typer.Option(False, hidden=True),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Create a new issue (implementation)."""
        try:
            # Parse arguments to extract title and shorthands
            title, shorthand_priority, shorthand_type, shorthand_status = (
                _parse_args_for_create(
                    [arg1, arg2, arg3, arg4],
                    allow_shorthands=allow_shorthands,
                )
            )

            # --title flag overrides positional title if no positional title given
            if not title and title_opt:
                title = title_opt
            elif title and title_opt:
                echo_error("Cannot use both positional title and --title flag")
                raise typer.Exit(1)

            # Validate that shorthands and explicit options aren't used together
            if shorthand_priority is not None and priority is not None:
                echo_error(
                    "Cannot use both priority shorthand (0-4) and "
                    "--priority flag together"
                )
                raise typer.Exit(1)
            if shorthand_type is not None and issue_type is not None:
                echo_error(
                    "Cannot use both type shorthand (b/f/e/s/q) and "
                    "--type flag together"
                )
                raise typer.Exit(1)
            if shorthand_status is not None and status is not None:
                echo_error(
                    "Cannot use both status shorthand (d) and --status flag together"
                )
                raise typer.Exit(1)

            if not title:
                echo_error("Title is required")
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
            if status:
                initial_status = Status(status)
            elif shorthand_status:
                initial_status = Status(shorthand_status)
            else:
                initial_status = Status.OPEN

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
                    echo_error(f"Issue {depends_on} not found")
                    raise typer.Exit(1)
            if blocks:
                resolved_blocks = storage.resolve_id(blocks)
                if resolved_blocks is None:
                    echo_error(f"Issue {blocks} not found")
                    raise typer.Exit(1)

            # Resolve duplicate_of if provided
            if duplicate_of:
                resolved_dup = storage.resolve_id(duplicate_of)
                if resolved_dup is None:
                    echo_error(f"Issue {duplicate_of} not found")
                    raise typer.Exit(1)
                duplicate_of = resolved_dup

            # Resolve parent if provided
            if parent:
                resolved_parent = storage.resolve_id(parent)
                if resolved_parent is None:
                    echo_error(f"Parent issue {parent} not found")
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

            if is_json_output(json_output):
                from dogcat.models import issue_to_dict

                typer.echo(orjson.dumps(issue_to_dict(issue)).decode())
            else:
                typer.echo(
                    f"✓ Created {issue.full_id}: {title} "
                    f"[{final_type}, pri {final_priority}]",
                )

        except ValueError as e:
            echo_error(str(e))
            raise typer.Exit(1)
        except typer.Exit:
            raise  # Re-raise without duplicate error message
        except Exception as e:
            echo_error(str(e))
            raise typer.Exit(1)

    app.command(name="create")(
        _make_alias(
            _create_impl,
            doc=_CREATE_DOC,
            exclude_params=frozenset(
                {"arg2", "arg3", "arg4", "allow_shorthands"},
            ),
            param_defaults={
                "arg2": None,
                "arg3": None,
                "arg4": None,
                "allow_shorthands": False,
            },
            param_help={"arg1": _ARG_HELP},
        ),
    )

    app.command(name="c", hidden=False)(
        _make_alias(
            _create_impl,
            doc=_C_DOC,
            exclude_params=frozenset({"allow_shorthands"}),
            param_defaults={"allow_shorthands": True},
        ),
    )

    app.command(name="add", hidden=True)(
        _make_alias(
            _create_impl,
            doc="Create a new issue (alias for 'create' command).",
            exclude_params=frozenset(
                {"arg2", "arg3", "arg4", "allow_shorthands"},
            ),
            param_defaults={
                "arg2": None,
                "arg3": None,
                "arg4": None,
                "allow_shorthands": False,
            },
            param_help={"arg1": _ARG_HELP},
        ),
    )

    @app.command(name="new")
    def new_issue_cmd(
        arg1: str | None = typer.Argument(None, help=_ARG_HELP_SHORTHAND),
        arg2: str | None = typer.Argument(None, help=_ARG_HELP_SHORTHAND),
        arg3: str | None = typer.Argument(None, help=_ARG_HELP_SHORTHAND),
        arg4: str | None = typer.Argument(None, help=_ARG_HELP_SHORTHAND),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """Open an interactive Textual form to create a new issue.

        Supports shorthand notation: use single characters (0-4 for priority,
        b/f/e/s for bug/feature/epic/story, d for draft status) before or after
        the title.

        Examples:
            dcat new                           # Empty form
            dcat new "Fix login bug"           # Pre-filled title
            dcat new "Fix login bug" 1         # Pre-filled title + priority 1
            dcat new b "Fix crash"             # Pre-filled type bug + title
            dcat new 0 b "Critical bug"        # Priority 0 + type bug + title
            dcat new d "Initial thoughts"      # Draft status + title
        """
        try:
            title = ""
            priority_sh: int | None = None
            type_sh: str | None = None
            status_sh: str | None = None

            if arg1 is not None:
                title, priority_sh, type_sh, status_sh = _parse_args_for_create(
                    [arg1, arg2, arg3, arg4],
                )

            storage = get_storage(dogcats_dir)
            namespace = get_issue_prefix(dogcats_dir)
            owner = get_default_operator()

            from dogcat.tui.editor import new_issue

            created = new_issue(
                storage,
                namespace,
                owner=owner,
                title=title,
                priority=priority_sh,
                issue_type=type_sh,
                status=status_sh,
            )
            if created is not None:
                if is_json_output(json_output):
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
            echo_error(str(e))
            raise typer.Exit(1)
        except typer.Exit:
            raise
        except Exception as e:
            echo_error(str(e))
            raise typer.Exit(1)

    app.command(name="n", hidden=True)(
        _make_alias(
            new_issue_cmd,
            doc="Open a Textual form to create a new issue (alias for 'new').",
        ),
    )
