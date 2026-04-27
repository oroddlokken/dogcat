"""Workflow and status commands for dogcat CLI."""

from __future__ import annotations

import orjson
import typer

from dogcat.config import extract_prefix, get_namespace_filter
from dogcat.constants import TERMINAL_STATUSES
from dogcat.models import Status, is_manual_issue

from ._completions import (
    complete_issue_ids,
    complete_labels,
    complete_namespaces,
    complete_owners,
    complete_priorities,
    complete_snooze_durations,
    complete_types,
)
from ._formatting import (
    format_issue_brief,
    format_issue_table,
    format_issue_tree,
    format_proposal_brief,
)
from ._helpers import (
    _make_alias,
    apply_common_filters,
    check_agent_manual_exclusive,
    check_comments_exclusive,
    get_default_operator,
    get_storage,
    load_open_inbox_proposals,
    parse_duration,
    resolve_limit,
    with_ns_shim,
)
from ._json_state import echo_error, is_json, set_json


def register(app: typer.Typer) -> None:
    """Register workflow/status commands."""

    @app.command()
    def ready(
        limit_arg: int | None = typer.Argument(None, help="Limit results"),
        limit: int | None = typer.Option(None, "--limit", help="Limit results"),
        issue_type: str | None = typer.Option(
            None,
            "--type",
            "-t",
            help="Filter by type",
            autocompletion=complete_types,
        ),
        exclude_type: list[str] = typer.Option(  # noqa: B008
            [],
            "--exclude-type",
            help="Exclude issues of this type (repeatable)",
            autocompletion=complete_types,
        ),
        priority: int | None = typer.Option(
            None,
            "--priority",
            "-p",
            help="Filter by priority",
            autocompletion=complete_priorities,
        ),
        label: str | None = typer.Option(
            None,
            "--label",
            "-l",
            help="Filter by label",
            autocompletion=complete_labels,
        ),
        owner: str | None = typer.Option(
            None,
            "--owner",
            "-o",
            help="Filter by owner",
            autocompletion=complete_owners,
        ),
        parent: str | None = typer.Option(
            None,
            "--parent",
            help="Filter by parent issue ID",
            autocompletion=complete_issue_ids,
        ),
        no_parent: bool = typer.Option(
            False,
            "--no-parent",
            help="Show only top-level issues (no parent)",
        ),
        namespace: str | None = typer.Option(
            None,
            "--namespace",
            help="Filter by namespace",
            autocompletion=complete_namespaces,
        ),
        all_namespaces: bool = typer.Option(
            False,
            "--all-namespaces",
            "--all-ns",
            "-A",
            help="Show issues from all namespaces",
        ),
        agent_only: bool = typer.Option(
            False,
            "--agent-only",
            help="Only show issues available for agents",
        ),
        manual: bool = typer.Option(
            False,
            "--manual",
            help="Only show issues marked as manual",
        ),
        has_comments: bool = typer.Option(
            False,
            "--has-comments",
            help="Only show issues that have at least one comment",
        ),
        without_comments: bool = typer.Option(
            False,
            "--without-comments",
            help="Only show issues that have no comments",
        ),
        include_snoozed: bool = typer.Option(
            False,
            "--include-snoozed",
            help="Include snoozed issues in results",
        ),
        tree: bool = typer.Option(False, "--tree", help="Display as tree"),
        table: bool = typer.Option(False, "--table", help="Display in columns"),
        include_inbox: bool = typer.Option(
            False,
            "--include-inbox",
            help="Show pending inbox proposals alongside ready issues",
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Show issues ready to work (no blocking dependencies)."""
        set_json(json_output)
        try:
            from dogcat.deps import get_ready_work

            final_limit = resolve_limit(limit_arg, limit)
            storage = get_storage(dogcats_dir)
            ready_issues = get_ready_work(storage, include_snoozed=include_snoozed)

            ready_issues = apply_common_filters(
                ready_issues,
                issue_type=issue_type,
                exclude_types=exclude_type,
                priority=priority,
                label=label,
                owner=owner,
                parent=parent,
                no_parent=no_parent,
                namespace=namespace,
                all_namespaces=all_namespaces,
                agent_only=agent_only,
                manual_only=manual,
                has_comments=has_comments,
                without_comments=without_comments,
                dogcats_dir=str(storage.dogcats_dir),
                storage=storage,
            )

            if final_limit is not None:
                ready_issues = ready_issues[:final_limit]

            if is_json():
                from dogcat.models import issue_to_dict

                output = [issue_to_dict(issue) for issue in ready_issues]
                typer.echo(orjson.dumps(output).decode())
            elif not ready_issues:
                typer.echo("No ready work")
            else:
                typer.echo(f"Ready ({len(ready_issues)}):")
                if tree:
                    typer.echo(format_issue_tree(ready_issues))
                elif table:
                    typer.echo(format_issue_table(ready_issues))
                else:
                    for issue in ready_issues:
                        typer.echo(format_issue_brief(issue))

            # Append inbox proposals if requested
            if include_inbox and not is_json():
                _show_inbox_in_ready(
                    str(storage.dogcats_dir), namespace, all_namespaces
                )

        except typer.Exit:
            raise
        except Exception as e:
            echo_error(str(e))
            raise typer.Exit(1)

    def _show_inbox_in_ready(
        dogcats_dir: str,
        namespace: str | None,
        all_namespaces: bool,
    ) -> None:
        """Show open inbox proposals in ready output."""
        proposals = load_open_inbox_proposals(
            dogcats_dir,
            namespace,
            all_namespaces=all_namespaces,
        )
        if proposals:
            typer.echo(f"\nInbox ({len(proposals)}):")
            for proposal in proposals:
                typer.echo(format_proposal_brief(proposal))

    @app.command()
    def blocked(
        limit_arg: int | None = typer.Argument(None, help="Limit results"),
        limit: int | None = typer.Option(None, "--limit", help="Limit results"),
        issue_type: str | None = typer.Option(
            None,
            "--type",
            "-t",
            help="Filter by type",
            autocompletion=complete_types,
        ),
        exclude_type: list[str] = typer.Option(  # noqa: B008
            [],
            "--exclude-type",
            help="Exclude issues of this type (repeatable)",
            autocompletion=complete_types,
        ),
        priority: int | None = typer.Option(
            None,
            "--priority",
            "-p",
            help="Filter by priority",
            autocompletion=complete_priorities,
        ),
        label: str | None = typer.Option(
            None,
            "--label",
            "-l",
            help="Filter by label",
            autocompletion=complete_labels,
        ),
        owner: str | None = typer.Option(
            None,
            "--owner",
            "-o",
            help="Filter by owner",
            autocompletion=complete_owners,
        ),
        parent: str | None = typer.Option(
            None,
            "--parent",
            help="Filter by parent issue ID",
            autocompletion=complete_issue_ids,
        ),
        no_parent: bool = typer.Option(
            False,
            "--no-parent",
            help="Show only top-level issues (no parent)",
        ),
        namespace: str | None = typer.Option(
            None,
            "--namespace",
            help="Filter by namespace",
            autocompletion=complete_namespaces,
        ),
        all_namespaces: bool = typer.Option(
            False,
            "--all-namespaces",
            "--all-ns",
            "-A",
            help="Show issues from all namespaces",
        ),
        agent_only: bool = typer.Option(
            False,
            "--agent-only",
            help="Only show issues available for agents",
        ),
        manual: bool = typer.Option(
            False,
            "--manual",
            help="Only show issues marked as manual",
        ),
        has_comments: bool = typer.Option(
            False,
            "--has-comments",
            help="Only show issues that have at least one comment",
        ),
        without_comments: bool = typer.Option(
            False,
            "--without-comments",
            help="Only show issues that have no comments",
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Show all blocked issues."""
        set_json(json_output)
        try:
            from dogcat.deps import get_blocked_issues

            final_limit = resolve_limit(limit_arg, limit)
            storage = get_storage(dogcats_dir)
            blocked_issues = get_blocked_issues(storage)

            # Filter underlying issues, keep blocked entries that match
            blocked_issue_ids = {bi.issue_id for bi in blocked_issues}
            underlying = [storage.get(bid) for bid in blocked_issue_ids]
            underlying = [i for i in underlying if i is not None]
            filtered = apply_common_filters(
                underlying,
                issue_type=issue_type,
                exclude_types=exclude_type,
                priority=priority,
                label=label,
                owner=owner,
                parent=parent,
                no_parent=no_parent,
                namespace=namespace,
                all_namespaces=all_namespaces,
                agent_only=agent_only,
                manual_only=manual,
                has_comments=has_comments,
                without_comments=without_comments,
                dogcats_dir=str(storage.dogcats_dir),
                storage=storage,
            )
            filtered_ids = {i.full_id for i in filtered}
            blocked_issues = [
                bi for bi in blocked_issues if bi.issue_id in filtered_ids
            ]

            if final_limit is not None:
                blocked_issues = blocked_issues[:final_limit]

            if is_json():
                output = [
                    {
                        "issue_id": bi.issue_id,
                        "blocking_ids": bi.blocking_ids,
                        "reason": bi.reason,
                    }
                    for bi in blocked_issues
                ]
                typer.echo(orjson.dumps(output).decode())
            elif not blocked_issues:
                typer.echo("No blocked issues")
            else:
                typer.echo(f"Blocked ({len(blocked_issues)}):")
                for bi in blocked_issues:
                    issue = storage.get(bi.issue_id)
                    if issue:
                        typer.echo(format_issue_brief(issue))
                    else:
                        typer.echo(f"  {bi.issue_id}")
                    for blocker_id in bi.blocking_ids:
                        blocker = storage.get(blocker_id)
                        if blocker:
                            typer.echo(
                                typer.style("    blocked by ", fg="bright_black")
                                + format_issue_brief(blocker),
                            )
                        else:
                            typer.echo(
                                typer.style(
                                    f"    blocked by {blocker_id}",
                                    fg="bright_black",
                                ),
                            )

        except typer.Exit:
            raise
        except Exception as e:
            echo_error(str(e))
            raise typer.Exit(1)

    @app.command("in-progress")
    def in_progress(
        limit_arg: int | None = typer.Argument(None, help="Limit results"),
        limit: int | None = typer.Option(None, "--limit", help="Limit results"),
        issue_type: str | None = typer.Option(
            None,
            "--type",
            "-t",
            help="Filter by type",
            autocompletion=complete_types,
        ),
        exclude_type: list[str] = typer.Option(  # noqa: B008
            [],
            "--exclude-type",
            help="Exclude issues of this type (repeatable)",
            autocompletion=complete_types,
        ),
        priority: int | None = typer.Option(
            None,
            "--priority",
            "-p",
            help="Filter by priority",
            autocompletion=complete_priorities,
        ),
        label: str | None = typer.Option(
            None,
            "--label",
            "-l",
            help="Filter by label",
            autocompletion=complete_labels,
        ),
        owner: str | None = typer.Option(
            None,
            "--owner",
            "-o",
            help="Filter by owner",
            autocompletion=complete_owners,
        ),
        parent: str | None = typer.Option(
            None,
            "--parent",
            help="Filter by parent issue ID",
            autocompletion=complete_issue_ids,
        ),
        no_parent: bool = typer.Option(
            False,
            "--no-parent",
            help="Show only top-level issues (no parent)",
        ),
        namespace: str | None = typer.Option(
            None,
            "--namespace",
            help="Filter by namespace",
            autocompletion=complete_namespaces,
        ),
        all_namespaces: bool = typer.Option(
            False,
            "--all-namespaces",
            "--all-ns",
            "-A",
            help="Show issues from all namespaces",
        ),
        agent_only: bool = typer.Option(
            False,
            "--agent-only",
            help="Only show issues available for agents",
        ),
        manual: bool = typer.Option(
            False,
            "--manual",
            help="Only show issues marked as manual",
        ),
        has_comments: bool = typer.Option(
            False,
            "--has-comments",
            help="Only show issues that have at least one comment",
        ),
        without_comments: bool = typer.Option(
            False,
            "--without-comments",
            help="Only show issues that have no comments",
        ),
        tree: bool = typer.Option(False, "--tree", help="Display as tree"),
        table: bool = typer.Option(False, "--table", help="Display in columns"),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Show issues currently in progress."""
        set_json(json_output)
        _list_by_status(
            status="in_progress",
            heading="In Progress",
            empty_msg="No in-progress issues",
            limit_arg=limit_arg,
            limit=limit,
            issue_type=issue_type,
            exclude_types=exclude_type,
            priority=priority,
            label=label,
            owner=owner,
            parent=parent,
            no_parent=no_parent,
            namespace=namespace,
            all_namespaces=all_namespaces,
            agent_only=agent_only,
            manual_only=manual,
            has_comments=has_comments,
            without_comments=without_comments,
            tree=tree,
            table=table,
            dogcats_dir=dogcats_dir,
            auto_tree=True,
        )

    @app.command("open")
    def open_issues(
        limit_arg: int | None = typer.Argument(None, help="Limit results"),
        limit: int | None = typer.Option(None, "--limit", help="Limit results"),
        issue_type: str | None = typer.Option(
            None,
            "--type",
            "-t",
            help="Filter by type",
            autocompletion=complete_types,
        ),
        exclude_type: list[str] = typer.Option(  # noqa: B008
            [],
            "--exclude-type",
            help="Exclude issues of this type (repeatable)",
            autocompletion=complete_types,
        ),
        priority: int | None = typer.Option(
            None,
            "--priority",
            "-p",
            help="Filter by priority",
            autocompletion=complete_priorities,
        ),
        label: str | None = typer.Option(
            None,
            "--label",
            "-l",
            help="Filter by label",
            autocompletion=complete_labels,
        ),
        owner: str | None = typer.Option(
            None,
            "--owner",
            "-o",
            help="Filter by owner",
            autocompletion=complete_owners,
        ),
        parent: str | None = typer.Option(
            None,
            "--parent",
            help="Filter by parent issue ID",
            autocompletion=complete_issue_ids,
        ),
        no_parent: bool = typer.Option(
            False,
            "--no-parent",
            help="Show only top-level issues (no parent)",
        ),
        namespace: str | None = typer.Option(
            None,
            "--namespace",
            help="Filter by namespace",
            autocompletion=complete_namespaces,
        ),
        all_namespaces: bool = typer.Option(
            False,
            "--all-namespaces",
            "--all-ns",
            "-A",
            help="Show issues from all namespaces",
        ),
        agent_only: bool = typer.Option(
            False,
            "--agent-only",
            help="Only show issues available for agents",
        ),
        manual: bool = typer.Option(
            False,
            "--manual",
            help="Only show issues marked as manual",
        ),
        has_comments: bool = typer.Option(
            False,
            "--has-comments",
            help="Only show issues that have at least one comment",
        ),
        without_comments: bool = typer.Option(
            False,
            "--without-comments",
            help="Only show issues that have no comments",
        ),
        tree: bool = typer.Option(False, "--tree", help="Display as tree"),
        table: bool = typer.Option(False, "--table", help="Display in columns"),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Show all open issues."""
        set_json(json_output)
        _list_by_status(
            status="open",
            heading="Open",
            empty_msg="No open issues",
            limit_arg=limit_arg,
            limit=limit,
            issue_type=issue_type,
            exclude_types=exclude_type,
            priority=priority,
            label=label,
            owner=owner,
            parent=parent,
            no_parent=no_parent,
            namespace=namespace,
            all_namespaces=all_namespaces,
            agent_only=agent_only,
            manual_only=manual,
            has_comments=has_comments,
            without_comments=without_comments,
            tree=tree,
            table=table,
            dogcats_dir=dogcats_dir,
            auto_tree=True,
        )

    @app.command("in-review")
    def in_review(
        limit_arg: int | None = typer.Argument(None, help="Limit results"),
        limit: int | None = typer.Option(None, "--limit", help="Limit results"),
        issue_type: str | None = typer.Option(
            None,
            "--type",
            "-t",
            help="Filter by type",
            autocompletion=complete_types,
        ),
        exclude_type: list[str] = typer.Option(  # noqa: B008
            [],
            "--exclude-type",
            help="Exclude issues of this type (repeatable)",
            autocompletion=complete_types,
        ),
        priority: int | None = typer.Option(
            None,
            "--priority",
            "-p",
            help="Filter by priority",
            autocompletion=complete_priorities,
        ),
        label: str | None = typer.Option(
            None,
            "--label",
            "-l",
            help="Filter by label",
            autocompletion=complete_labels,
        ),
        owner: str | None = typer.Option(
            None,
            "--owner",
            "-o",
            help="Filter by owner",
            autocompletion=complete_owners,
        ),
        parent: str | None = typer.Option(
            None,
            "--parent",
            help="Filter by parent issue ID",
            autocompletion=complete_issue_ids,
        ),
        no_parent: bool = typer.Option(
            False,
            "--no-parent",
            help="Show only top-level issues (no parent)",
        ),
        namespace: str | None = typer.Option(
            None,
            "--namespace",
            help="Filter by namespace",
            autocompletion=complete_namespaces,
        ),
        all_namespaces: bool = typer.Option(
            False,
            "--all-namespaces",
            "--all-ns",
            "-A",
            help="Show issues from all namespaces",
        ),
        agent_only: bool = typer.Option(
            False,
            "--agent-only",
            help="Only show issues available for agents",
        ),
        manual: bool = typer.Option(
            False,
            "--manual",
            help="Only show issues marked as manual",
        ),
        has_comments: bool = typer.Option(
            False,
            "--has-comments",
            help="Only show issues that have at least one comment",
        ),
        without_comments: bool = typer.Option(
            False,
            "--without-comments",
            help="Only show issues that have no comments",
        ),
        tree: bool = typer.Option(False, "--tree", help="Display as tree"),
        table: bool = typer.Option(False, "--table", help="Display in columns"),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Show issues currently in review."""
        set_json(json_output)
        _list_by_status(
            status="in_review",
            heading="In Review",
            empty_msg="No in-review issues",
            limit_arg=limit_arg,
            limit=limit,
            issue_type=issue_type,
            exclude_types=exclude_type,
            priority=priority,
            label=label,
            owner=owner,
            parent=parent,
            no_parent=no_parent,
            namespace=namespace,
            all_namespaces=all_namespaces,
            agent_only=agent_only,
            manual_only=manual,
            has_comments=has_comments,
            without_comments=without_comments,
            tree=tree,
            table=table,
            dogcats_dir=dogcats_dir,
            auto_tree=True,
        )

    def _set_status(
        issue_id: str,
        status: str,
        label: str,
        json_output: bool,
        operator: str | None,
        dogcats_dir: str,
    ) -> None:
        """Set an issue's status."""
        set_json(json_output)
        try:
            storage = get_storage(dogcats_dir)
            final_operator = (
                operator if operator is not None else get_default_operator()
            )
            issue = storage.update(
                issue_id,
                {"status": status, "updated_by": final_operator},
            )

            if is_json():
                from dogcat.models import issue_to_dict

                typer.echo(orjson.dumps(issue_to_dict(issue)).decode())
            else:
                typer.echo(f"✓ {label} {issue.full_id}: {issue.title}")

        except ValueError as e:
            echo_error(str(e))
            raise typer.Exit(1)
        except typer.Exit:
            raise
        except Exception as e:
            echo_error(str(e))
            raise typer.Exit(1)

    def _list_by_status(
        *,
        status: str,
        heading: str,
        empty_msg: str,
        limit_arg: int | None,
        limit: int | None,
        issue_type: str | None,
        exclude_types: list[str] | None,
        priority: int | None,
        label: str | None,
        owner: str | None,
        parent: str | None,
        no_parent: bool = False,
        namespace: str | None,
        all_namespaces: bool,
        agent_only: bool,
        manual_only: bool,
        has_comments: bool,
        without_comments: bool,
        tree: bool,
        table: bool,
        dogcats_dir: str,
        auto_tree: bool = False,
    ) -> None:
        """List issues filtered by a single status.

        ``auto_tree=True`` flips the renderer into tree mode whenever any
        result has a parent, matching the historical behavior of the public
        list-style commands (``open``, ``in_progress``, ``in_review``,
        ``deferred``). The hidden shorthand commands keep the literal
        ``--tree`` flag semantics by leaving ``auto_tree=False``.
        """
        try:
            final_limit = resolve_limit(limit_arg, limit)
            storage = get_storage(dogcats_dir)
            issues = storage.list({"status": status})
            issues.sort(key=lambda i: i.priority)

            issues = apply_common_filters(
                issues,
                issue_type=issue_type,
                exclude_types=exclude_types,
                priority=priority,
                label=label,
                owner=owner,
                parent=parent,
                no_parent=no_parent,
                namespace=namespace,
                all_namespaces=all_namespaces,
                agent_only=agent_only,
                manual_only=manual_only,
                has_comments=has_comments,
                without_comments=without_comments,
                dogcats_dir=str(storage.dogcats_dir),
                storage=storage,
            )

            if final_limit is not None:
                issues = issues[:final_limit]

            if is_json():
                from dogcat.models import issue_to_dict

                output = [issue_to_dict(issue) for issue in issues]
                typer.echo(orjson.dumps(output).decode())
            elif not issues:
                typer.echo(empty_msg)
            else:
                typer.echo(f"{heading} ({len(issues)}):")
                if tree or (auto_tree and any(i.parent for i in issues)):
                    typer.echo(format_issue_tree(issues))
                elif table:
                    typer.echo(format_issue_table(issues))
                else:
                    for issue in issues:
                        typer.echo(format_issue_brief(issue))

        except typer.Exit:
            raise
        except Exception as e:
            echo_error(str(e))
            raise typer.Exit(1)

    @app.command(name="ir", hidden=True)
    def in_review_shortcut(
        limit_arg: int | None = typer.Argument(None, help="Limit results"),
        limit: int | None = typer.Option(None, "--limit", help="Limit results"),
        issue_type: str | None = typer.Option(
            None,
            "--type",
            "-t",
            help="Filter by type",
            autocompletion=complete_types,
        ),
        exclude_type: list[str] = typer.Option(  # noqa: B008
            [],
            "--exclude-type",
            help="Exclude issues of this type (repeatable)",
            autocompletion=complete_types,
        ),
        priority: int | None = typer.Option(
            None,
            "--priority",
            "-p",
            help="Filter by priority",
            autocompletion=complete_priorities,
        ),
        label: str | None = typer.Option(
            None,
            "--label",
            "-l",
            help="Filter by label",
            autocompletion=complete_labels,
        ),
        owner: str | None = typer.Option(
            None,
            "--owner",
            "-o",
            help="Filter by owner",
            autocompletion=complete_owners,
        ),
        parent: str | None = typer.Option(
            None,
            "--parent",
            help="Filter by parent issue ID",
            autocompletion=complete_issue_ids,
        ),
        no_parent: bool = typer.Option(
            False,
            "--no-parent",
            help="Show only top-level issues (no parent)",
        ),
        namespace: str | None = typer.Option(
            None,
            "--namespace",
            help="Filter by namespace",
            autocompletion=complete_namespaces,
        ),
        all_namespaces: bool = typer.Option(
            False,
            "--all-namespaces",
            "--all-ns",
            "-A",
            help="Show issues from all namespaces",
        ),
        agent_only: bool = typer.Option(
            False,
            "--agent-only",
            help="Only show issues available for agents",
        ),
        manual: bool = typer.Option(
            False,
            "--manual",
            help="Only show issues marked as manual",
        ),
        has_comments: bool = typer.Option(
            False,
            "--has-comments",
            help="Only show issues that have at least one comment",
        ),
        without_comments: bool = typer.Option(
            False,
            "--without-comments",
            help="Only show issues that have no comments",
        ),
        tree: bool = typer.Option(False, "--tree", help="Display as tree"),
        table: bool = typer.Option(False, "--table", help="Display in columns"),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """List issues with in-review status."""
        set_json(json_output)
        _list_by_status(
            status="in_review",
            heading="In Review",
            empty_msg="No in-review issues",
            limit_arg=limit_arg,
            limit=limit,
            issue_type=issue_type,
            exclude_types=exclude_type,
            priority=priority,
            label=label,
            owner=owner,
            parent=parent,
            no_parent=no_parent,
            namespace=namespace,
            all_namespaces=all_namespaces,
            agent_only=agent_only,
            manual_only=manual,
            has_comments=has_comments,
            without_comments=without_comments,
            tree=tree,
            table=table,
            dogcats_dir=dogcats_dir,
        )

    @app.command(name="ip", hidden=True)
    def in_progress_shortcut(
        limit_arg: int | None = typer.Argument(None, help="Limit results"),
        limit: int | None = typer.Option(None, "--limit", help="Limit results"),
        issue_type: str | None = typer.Option(
            None,
            "--type",
            "-t",
            help="Filter by type",
            autocompletion=complete_types,
        ),
        exclude_type: list[str] = typer.Option(  # noqa: B008
            [],
            "--exclude-type",
            help="Exclude issues of this type (repeatable)",
            autocompletion=complete_types,
        ),
        priority: int | None = typer.Option(
            None,
            "--priority",
            "-p",
            help="Filter by priority",
            autocompletion=complete_priorities,
        ),
        label: str | None = typer.Option(
            None,
            "--label",
            "-l",
            help="Filter by label",
            autocompletion=complete_labels,
        ),
        owner: str | None = typer.Option(
            None,
            "--owner",
            "-o",
            help="Filter by owner",
            autocompletion=complete_owners,
        ),
        parent: str | None = typer.Option(
            None,
            "--parent",
            help="Filter by parent issue ID",
            autocompletion=complete_issue_ids,
        ),
        no_parent: bool = typer.Option(
            False,
            "--no-parent",
            help="Show only top-level issues (no parent)",
        ),
        namespace: str | None = typer.Option(
            None,
            "--namespace",
            help="Filter by namespace",
            autocompletion=complete_namespaces,
        ),
        all_namespaces: bool = typer.Option(
            False,
            "--all-namespaces",
            "--all-ns",
            "-A",
            help="Show issues from all namespaces",
        ),
        agent_only: bool = typer.Option(
            False,
            "--agent-only",
            help="Only show issues available for agents",
        ),
        manual: bool = typer.Option(
            False,
            "--manual",
            help="Only show issues marked as manual",
        ),
        has_comments: bool = typer.Option(
            False,
            "--has-comments",
            help="Only show issues that have at least one comment",
        ),
        without_comments: bool = typer.Option(
            False,
            "--without-comments",
            help="Only show issues that have no comments",
        ),
        tree: bool = typer.Option(False, "--tree", help="Display as tree"),
        table: bool = typer.Option(False, "--table", help="Display in columns"),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """List issues with in-progress status."""
        set_json(json_output)
        _list_by_status(
            status="in_progress",
            heading="In Progress",
            empty_msg="No in-progress issues",
            limit_arg=limit_arg,
            limit=limit,
            issue_type=issue_type,
            exclude_types=exclude_type,
            priority=priority,
            label=label,
            owner=owner,
            parent=parent,
            no_parent=no_parent,
            namespace=namespace,
            all_namespaces=all_namespaces,
            agent_only=agent_only,
            manual_only=manual,
            has_comments=has_comments,
            without_comments=without_comments,
            tree=tree,
            table=table,
            dogcats_dir=dogcats_dir,
        )

    @app.command("deferred")
    def deferred(
        limit_arg: int | None = typer.Argument(None, help="Limit results"),
        limit: int | None = typer.Option(None, "--limit", help="Limit results"),
        issue_type: str | None = typer.Option(
            None,
            "--type",
            "-t",
            help="Filter by type",
            autocompletion=complete_types,
        ),
        exclude_type: list[str] = typer.Option(  # noqa: B008
            [],
            "--exclude-type",
            help="Exclude issues of this type (repeatable)",
            autocompletion=complete_types,
        ),
        priority: int | None = typer.Option(
            None,
            "--priority",
            "-p",
            help="Filter by priority",
            autocompletion=complete_priorities,
        ),
        label: str | None = typer.Option(
            None,
            "--label",
            "-l",
            help="Filter by label",
            autocompletion=complete_labels,
        ),
        owner: str | None = typer.Option(
            None,
            "--owner",
            "-o",
            help="Filter by owner",
            autocompletion=complete_owners,
        ),
        parent: str | None = typer.Option(
            None,
            "--parent",
            help="Filter by parent issue ID",
            autocompletion=complete_issue_ids,
        ),
        no_parent: bool = typer.Option(
            False,
            "--no-parent",
            help="Show only top-level issues (no parent)",
        ),
        namespace: str | None = typer.Option(
            None,
            "--namespace",
            help="Filter by namespace",
            autocompletion=complete_namespaces,
        ),
        all_namespaces: bool = typer.Option(
            False,
            "--all-namespaces",
            "--all-ns",
            "-A",
            help="Show issues from all namespaces",
        ),
        agent_only: bool = typer.Option(
            False,
            "--agent-only",
            help="Only show issues available for agents",
        ),
        manual: bool = typer.Option(
            False,
            "--manual",
            help="Only show issues marked as manual",
        ),
        has_comments: bool = typer.Option(
            False,
            "--has-comments",
            help="Only show issues that have at least one comment",
        ),
        without_comments: bool = typer.Option(
            False,
            "--without-comments",
            help="Only show issues that have no comments",
        ),
        tree: bool = typer.Option(False, "--tree", help="Display as tree"),
        table: bool = typer.Option(False, "--table", help="Display in columns"),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Show issues currently deferred."""
        set_json(json_output)
        _list_by_status(
            status="deferred",
            heading="Deferred",
            empty_msg="No deferred issues",
            limit_arg=limit_arg,
            limit=limit,
            issue_type=issue_type,
            exclude_types=exclude_type,
            priority=priority,
            label=label,
            owner=owner,
            parent=parent,
            no_parent=no_parent,
            namespace=namespace,
            all_namespaces=all_namespaces,
            agent_only=agent_only,
            manual_only=manual,
            has_comments=has_comments,
            without_comments=without_comments,
            tree=tree,
            table=table,
            dogcats_dir=dogcats_dir,
        )

    @app.command(name="defer", hidden=True)
    @with_ns_shim
    def defer_shortcut(
        issue_id: str = typer.Argument(
            ...,
            help="Issue ID",
            autocompletion=complete_issue_ids,
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        operator: str | None = typer.Option(
            None,
            "--by",
            help="Who is making this change",
        ),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Set an issue's status to deferred."""
        _set_status(
            issue_id,
            "deferred",
            "Deferred",
            json_output,
            operator,
            dogcats_dir,
        )

    @app.command("manual")
    def manual_list(
        limit_arg: int | None = typer.Argument(None, help="Limit results"),
        limit: int | None = typer.Option(None, "--limit", help="Limit results"),
        issue_type: str | None = typer.Option(
            None,
            "--type",
            "-t",
            help="Filter by type",
            autocompletion=complete_types,
        ),
        exclude_type: list[str] = typer.Option(  # noqa: B008
            [],
            "--exclude-type",
            help="Exclude issues of this type (repeatable)",
            autocompletion=complete_types,
        ),
        priority: int | None = typer.Option(
            None,
            "--priority",
            "-p",
            help="Filter by priority",
            autocompletion=complete_priorities,
        ),
        label: str | None = typer.Option(
            None,
            "--label",
            "-l",
            help="Filter by label",
            autocompletion=complete_labels,
        ),
        owner: str | None = typer.Option(
            None,
            "--owner",
            "-o",
            help="Filter by owner",
            autocompletion=complete_owners,
        ),
        parent: str | None = typer.Option(
            None,
            "--parent",
            help="Filter by parent issue ID",
            autocompletion=complete_issue_ids,
        ),
        no_parent: bool = typer.Option(
            False,
            "--no-parent",
            help="Show only top-level issues (no parent)",
        ),
        namespace: str | None = typer.Option(
            None,
            "--namespace",
            help="Filter by namespace",
            autocompletion=complete_namespaces,
        ),
        all_namespaces: bool = typer.Option(
            False,
            "--all-namespaces",
            "--all-ns",
            "-A",
            help="Show issues from all namespaces",
        ),
        tree: bool = typer.Option(False, "--tree", help="Display as tree"),
        table: bool = typer.Option(False, "--table", help="Display in columns"),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Show issues marked as manual."""
        set_json(json_output)
        try:
            final_limit = resolve_limit(limit_arg, limit)
            storage = get_storage(dogcats_dir)
            issues = storage.list()
            issues = [
                i
                for i in issues
                if is_manual_issue(i.metadata)
                and i.status.value not in TERMINAL_STATUSES
            ]
            issues = apply_common_filters(
                issues,
                issue_type=issue_type,
                exclude_types=exclude_type,
                priority=priority,
                label=label,
                owner=owner,
                parent=parent,
                no_parent=no_parent,
                namespace=namespace,
                all_namespaces=all_namespaces,
                dogcats_dir=str(storage.dogcats_dir),
                storage=storage,
            )
            issues.sort(key=lambda i: i.priority)
            if final_limit is not None:
                issues = issues[:final_limit]

            if is_json():
                from dogcat.models import issue_to_dict

                output = [issue_to_dict(issue) for issue in issues]
                typer.echo(orjson.dumps(output).decode())
            elif not issues:
                typer.echo("No manual issues")
            else:
                typer.echo(f"Manual ({len(issues)}):")
                if tree:
                    typer.echo(format_issue_tree(issues))
                elif table:
                    typer.echo(format_issue_table(issues))
                else:
                    for issue in issues:
                        typer.echo(format_issue_brief(issue))

        except typer.Exit:
            raise
        except Exception as e:
            echo_error(str(e))
            raise typer.Exit(1)

    @app.command(name="mark-manual", hidden=True)
    @with_ns_shim
    def mark_manual_shortcut(
        issue_id: str = typer.Argument(
            ...,
            help="Issue ID",
            autocompletion=complete_issue_ids,
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        operator: str | None = typer.Option(
            None,
            "--by",
            help="Who is making this change",
        ),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Mark an issue as manual (not for agents)."""
        try:
            set_json(json_output)
            storage = get_storage(dogcats_dir)
            final_operator = (
                operator if operator is not None else get_default_operator()
            )
            current = storage.get(issue_id)
            if current is None:
                echo_error(f"Issue {issue_id} not found")
                raise typer.Exit(1)
            from dogcat.models import set_manual_flag

            issue = storage.update(
                issue_id,
                {
                    "metadata": set_manual_flag(current.metadata or {}, manual=True),
                    "operator": final_operator,
                },
            )

            if is_json():
                from dogcat.models import issue_to_dict

                typer.echo(orjson.dumps(issue_to_dict(issue)).decode())
            else:
                typer.echo(f"✓ Marked manual {issue.full_id}: {issue.title}")

        except ValueError as e:
            echo_error(str(e))
            raise typer.Exit(1)
        except typer.Exit:
            raise
        except Exception as e:
            echo_error(str(e))
            raise typer.Exit(1)

    @app.command("recently-closed")
    def recently_closed(
        limit_arg: int | None = typer.Argument(None, help="Number of issues to show"),
        limit: int | None = typer.Option(
            None, "--limit", help="Number of issues to show"
        ),
        all_namespaces: bool = typer.Option(
            False,
            "--all-namespaces",
            "--all-ns",
            "-A",
            help="Show issues from all namespaces",
        ),
        agent_only: bool = typer.Option(
            False,
            "--agent-only",
            help="Only show issues available for agents",
        ),
        manual: bool = typer.Option(
            False,
            "--manual",
            help="Only show issues marked as manual",
        ),
        has_comments: bool = typer.Option(
            False,
            "--has-comments",
            help="Only show issues that have at least one comment",
        ),
        without_comments: bool = typer.Option(
            False,
            "--without-comments",
            help="Only show issues that have no comments",
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Show recently closed issues (oldest first).

        Displays the last N closed issues in chronological order.
        """
        set_json(json_output)
        try:
            from dogcat.event_log import EventLog, _serialize

            from ._formatting import format_event, get_event_legend

            check_agent_manual_exclusive(agent_only=agent_only, manual_only=manual)
            check_comments_exclusive(
                has_comments=has_comments, without_comments=without_comments
            )

            storage = get_storage(dogcats_dir)
            final_limit = resolve_limit(limit_arg, limit, default=10)
            event_log = EventLog(storage.dogcats_dir)
            events = [e for e in event_log.read() if e.event_type == "closed"]

            # Apply namespace filter (skip if --all-namespaces)
            if not all_namespaces:
                actual_dogcats_dir = str(storage.dogcats_dir)
                ns_filter = get_namespace_filter(actual_dogcats_dir)
                if ns_filter is not None:
                    events = [
                        e for e in events if ns_filter(extract_prefix(e.issue_id) or "")
                    ]

            if agent_only or manual:

                def _is_manual(event_issue_id: str) -> bool:
                    issue_obj = storage.get(event_issue_id)
                    if issue_obj is None:
                        return False
                    return is_manual_issue(issue_obj.metadata)

                if agent_only:
                    events = [e for e in events if not _is_manual(e.issue_id)]
                else:
                    events = [e for e in events if _is_manual(e.issue_id)]

            if has_comments or without_comments:

                def _has_comments(event_issue_id: str) -> bool:
                    issue_obj = storage.get(event_issue_id)
                    return bool(issue_obj and issue_obj.comments)

                if has_comments:
                    events = [e for e in events if _has_comments(e.issue_id)]
                else:
                    events = [e for e in events if not _has_comments(e.issue_id)]

            events = events[:final_limit]
            events.reverse()  # Display oldest-first

            # Fill in missing titles from storage
            for event in events:
                if not event.title:
                    issue_obj = storage.get(event.issue_id)
                    if issue_obj:
                        event.title = issue_obj.title

            if is_json():
                output = [_serialize(e) for e in events]
                typer.echo(orjson.dumps(output).decode())
            elif not events:
                typer.echo("No recently closed issues")
            else:
                typer.echo(f"Recently Closed ({len(events)}):")
                for event in events:
                    typer.echo(format_event(event))
                typer.echo(get_event_legend())

        except typer.Exit:
            raise
        except Exception as e:
            echo_error(str(e))
            raise typer.Exit(1)

    @app.command("recently-added")
    def recently_added(
        limit_arg: int | None = typer.Argument(None, help="Number of issues to show"),
        limit: int | None = typer.Option(
            None, "--limit", help="Number of issues to show"
        ),
        all_namespaces: bool = typer.Option(
            False,
            "--all-namespaces",
            "--all-ns",
            "-A",
            help="Show issues from all namespaces",
        ),
        agent_only: bool = typer.Option(
            False,
            "--agent-only",
            help="Only show issues available for agents",
        ),
        manual: bool = typer.Option(
            False,
            "--manual",
            help="Only show issues marked as manual",
        ),
        has_comments: bool = typer.Option(
            False,
            "--has-comments",
            help="Only show issues that have at least one comment",
        ),
        without_comments: bool = typer.Option(
            False,
            "--without-comments",
            help="Only show issues that have no comments",
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Show recently created issues in chronological order (oldest first).

        Displays the last N issues sorted by created_at date,
        with the oldest of the recent issues at the top.
        """
        set_json(json_output)
        try:
            storage = get_storage(dogcats_dir)
            issues = [
                i for i in storage.list() if i.status.value not in TERMINAL_STATUSES
            ]

            issues = apply_common_filters(
                issues,
                agent_only=agent_only,
                manual_only=manual,
                has_comments=has_comments,
                without_comments=without_comments,
                all_namespaces=all_namespaces,
                dogcats_dir=str(storage.dogcats_dir),
                storage=storage,
            )

            final_limit = resolve_limit(limit_arg, limit, default=10)
            # Sort descending to select the N most recent, then reverse for display
            issues.sort(key=lambda i: i.created_at, reverse=True)

            # Take first N (most recent), then reverse for oldest-first display
            recent = issues[:final_limit]
            recent.reverse()

            if is_json():
                from dogcat.models import issue_to_dict

                output = [issue_to_dict(issue) for issue in recent]
                typer.echo(orjson.dumps(output).decode())
            else:
                if not recent:
                    typer.echo("No recently added issues")
                else:
                    typer.echo(f"Recently Added ({len(recent)}):")
                    for issue in recent:
                        created_str = typer.style(
                            f"[{issue.created_at.strftime('%Y-%m-%d %H:%M')}]",
                            fg="bright_black",
                        )
                        typer.echo(f"{format_issue_brief(issue)} {created_str}")

        except typer.Exit:
            raise
        except Exception as e:
            echo_error(str(e))
            raise typer.Exit(1)

    app.command(name="rc", hidden=True)(
        _make_alias(recently_closed, doc="Alias for recently-closed."),
    )

    app.command(name="o", hidden=True)(
        _make_alias(open_issues, doc="Alias for open."),
    )

    app.command(name="b", hidden=True)(
        _make_alias(blocked, doc="Alias for blocked."),
    )

    app.command(name="d", hidden=True)(
        _make_alias(deferred, doc="Alias for deferred."),
    )

    app.command(name="ra", hidden=True)(
        _make_alias(recently_added, doc="Alias for recently-added."),
    )

    @app.command(name="pr")
    def progress_review(
        exclude_type: list[str] = typer.Option(  # noqa: B008
            [],
            "--exclude-type",
            help="Exclude issues of this type (repeatable)",
            autocompletion=complete_types,
        ),
        no_parent: bool = typer.Option(
            False,
            "--no-parent",
            help="Show only top-level issues (no parent)",
        ),
        agent_only: bool = typer.Option(
            False,
            "--agent-only",
            help="Only show issues available for agents",
        ),
        manual: bool = typer.Option(
            False,
            "--manual",
            help="Only show issues marked as manual",
        ),
        has_comments: bool = typer.Option(
            False,
            "--has-comments",
            help="Only show issues that have at least one comment",
        ),
        without_comments: bool = typer.Option(
            False,
            "--without-comments",
            help="Only show issues that have no comments",
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Show in-progress and in-review issues together."""
        set_json(json_output)
        try:
            storage = get_storage(dogcats_dir)
            ip_issues = apply_common_filters(
                storage.list({"status": Status.IN_PROGRESS.value}),
                exclude_types=exclude_type,
                no_parent=no_parent,
                agent_only=agent_only,
                manual_only=manual,
                has_comments=has_comments,
                without_comments=without_comments,
                storage=storage,
            )
            ir_issues = apply_common_filters(
                storage.list({"status": Status.IN_REVIEW.value}),
                exclude_types=exclude_type,
                no_parent=no_parent,
                agent_only=agent_only,
                manual_only=manual,
                has_comments=has_comments,
                without_comments=without_comments,
                storage=storage,
            )

            ip_issues.sort(key=lambda i: i.priority)
            ir_issues.sort(key=lambda i: i.priority)

            if is_json():
                from dogcat.models import issue_to_dict

                output = {
                    "in_progress": [issue_to_dict(issue) for issue in ip_issues],
                    "in_review": [issue_to_dict(issue) for issue in ir_issues],
                }
                typer.echo(orjson.dumps(output).decode())
            else:
                typer.echo(f"In Progress ({len(ip_issues)}):")
                if not ip_issues:
                    typer.echo("  No in-progress issues")
                else:
                    ip_has_parent = any(i.parent for i in ip_issues)
                    if ip_has_parent:
                        tree = format_issue_tree(ip_issues)
                        for line in tree.splitlines():
                            typer.echo(f"  {line}")
                    else:
                        for issue in ip_issues:
                            typer.echo(f"  {format_issue_brief(issue)}")

                typer.echo()
                typer.echo(f"In Review ({len(ir_issues)}):")
                if not ir_issues:
                    typer.echo("  No in-review issues")
                else:
                    ir_has_parent = any(i.parent for i in ir_issues)
                    if ir_has_parent:
                        tree = format_issue_tree(ir_issues)
                        for line in tree.splitlines():
                            typer.echo(f"  {line}")
                    else:
                        for issue in ir_issues:
                            typer.echo(f"  {format_issue_brief(issue)}")

        except typer.Exit:
            raise
        except Exception as e:
            echo_error(str(e))
            raise typer.Exit(1)

    @app.command()
    @with_ns_shim
    def snooze(
        issue_id: str = typer.Argument(
            ...,
            help="Issue ID to snooze",
            autocompletion=complete_issue_ids,
        ),
        duration: str = typer.Argument(
            ...,
            help="Duration (e.g. 7d, 2w, 1m) or ISO8601 date",
            autocompletion=complete_snooze_durations,
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        operator: str | None = typer.Option(
            None,
            "--by",
            help="Who is making this change",
        ),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Snooze an issue for a duration (hide from list/ready)."""
        set_json(json_output)
        try:
            snooze_until = parse_duration(duration)
            storage = get_storage(dogcats_dir)
            final_operator = (
                operator if operator is not None else get_default_operator()
            )
            issue = storage.update(
                issue_id,
                {"snoozed_until": snooze_until, "updated_by": final_operator},
            )

            if is_json():
                from dogcat.models import issue_to_dict

                typer.echo(orjson.dumps(issue_to_dict(issue)).decode())
            else:
                until_str = snooze_until.strftime("%Y-%m-%d")
                typer.echo(f"Snoozed {issue.full_id}: {issue.title} until {until_str}")

        except ValueError as e:
            echo_error(str(e))
            raise typer.Exit(1)
        except typer.Exit:
            raise
        except Exception as e:
            echo_error(str(e))
            raise typer.Exit(1)

    @app.command()
    @with_ns_shim
    def unsnooze(
        issue_id: str = typer.Argument(
            ...,
            help="Issue ID to unsnooze",
            autocompletion=complete_issue_ids,
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        operator: str | None = typer.Option(
            None,
            "--by",
            help="Who is making this change",
        ),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Remove snooze from an issue (make it visible again)."""
        set_json(json_output)
        try:
            storage = get_storage(dogcats_dir)
            existing = storage.get(storage.resolve_id(issue_id) or issue_id)
            if existing is None:
                echo_error(f"Issue {issue_id} not found")
                raise typer.Exit(1)
            if existing.snoozed_until is None:
                echo_error(f"Issue {existing.full_id} is not snoozed")
                raise typer.Exit(1)

            final_operator = (
                operator if operator is not None else get_default_operator()
            )
            issue = storage.update(
                issue_id,
                {"snoozed_until": None, "updated_by": final_operator},
            )

            if is_json():
                from dogcat.models import issue_to_dict

                typer.echo(orjson.dumps(issue_to_dict(issue)).decode())
            else:
                typer.echo(f"Unsnoozed {issue.full_id}: {issue.title}")

        except typer.Exit:
            raise
        except Exception as e:
            echo_error(str(e))
            raise typer.Exit(1)

    @app.command("snoozed")
    def snoozed_list(
        limit_arg: int | None = typer.Argument(None, help="Limit results"),
        limit: int | None = typer.Option(None, "--limit", help="Limit results"),
        issue_type: str | None = typer.Option(
            None,
            "--type",
            "-t",
            help="Filter by type",
            autocompletion=complete_types,
        ),
        exclude_type: list[str] = typer.Option(  # noqa: B008
            [],
            "--exclude-type",
            help="Exclude issues of this type (repeatable)",
            autocompletion=complete_types,
        ),
        priority: int | None = typer.Option(
            None,
            "--priority",
            "-p",
            help="Filter by priority",
            autocompletion=complete_priorities,
        ),
        label: str | None = typer.Option(
            None,
            "--label",
            "-l",
            help="Filter by label",
            autocompletion=complete_labels,
        ),
        owner: str | None = typer.Option(
            None,
            "--owner",
            "-o",
            help="Filter by owner",
            autocompletion=complete_owners,
        ),
        parent: str | None = typer.Option(
            None,
            "--parent",
            help="Filter by parent issue ID",
            autocompletion=complete_issue_ids,
        ),
        no_parent: bool = typer.Option(
            False,
            "--no-parent",
            help="Show only top-level issues (no parent)",
        ),
        namespace: str | None = typer.Option(
            None,
            "--namespace",
            help="Filter by namespace",
            autocompletion=complete_namespaces,
        ),
        all_namespaces: bool = typer.Option(
            False,
            "--all-namespaces",
            "--all-ns",
            "-A",
            help="Show issues from all namespaces",
        ),
        agent_only: bool = typer.Option(
            False,
            "--agent-only",
            help="Only show issues available for agents",
        ),
        manual: bool = typer.Option(
            False,
            "--manual",
            help="Only show issues marked as manual",
        ),
        has_comments: bool = typer.Option(
            False,
            "--has-comments",
            help="Only show issues that have at least one comment",
        ),
        without_comments: bool = typer.Option(
            False,
            "--without-comments",
            help="Only show issues that have no comments",
        ),
        tree: bool = typer.Option(False, "--tree", help="Display as tree"),
        table: bool = typer.Option(False, "--table", help="Display in columns"),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Show currently snoozed issues."""
        set_json(json_output)
        try:
            from datetime import datetime as dt

            final_limit = resolve_limit(limit_arg, limit)
            storage = get_storage(dogcats_dir)
            now = dt.now().astimezone()

            # Get all non-closed issues that are currently snoozed
            all_issues = storage.list()
            issues = [
                i
                for i in all_issues
                if i.snoozed_until is not None
                and i.snoozed_until > now
                and i.status.value not in TERMINAL_STATUSES
            ]

            issues = apply_common_filters(
                issues,
                issue_type=issue_type,
                exclude_types=exclude_type,
                priority=priority,
                label=label,
                owner=owner,
                parent=parent,
                no_parent=no_parent,
                namespace=namespace,
                all_namespaces=all_namespaces,
                agent_only=agent_only,
                manual_only=manual,
                has_comments=has_comments,
                without_comments=without_comments,
                dogcats_dir=str(storage.dogcats_dir),
                storage=storage,
            )
            issues.sort(key=lambda i: (i.snoozed_until or now, i.priority))
            if final_limit is not None:
                issues = issues[:final_limit]

            if is_json():
                from dogcat.models import issue_to_dict

                output = [issue_to_dict(issue) for issue in issues]
                typer.echo(orjson.dumps(output).decode())
            elif not issues:
                typer.echo("No snoozed issues")
            else:
                typer.echo(f"Snoozed ({len(issues)}):")
                if tree:
                    typer.echo(format_issue_tree(issues))
                elif table:
                    typer.echo(format_issue_table(issues))
                else:
                    for issue in issues:
                        typer.echo(format_issue_brief(issue))

        except typer.Exit:
            raise
        except Exception as e:
            echo_error(str(e))
            raise typer.Exit(1)
