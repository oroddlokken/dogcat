"""Workflow and status commands for dogcat CLI."""

from __future__ import annotations

import orjson
import typer

from dogcat.config import extract_prefix, get_issue_prefix, get_namespace_filter

from ._completions import (
    complete_issue_ids,
    complete_labels,
    complete_namespaces,
    complete_owners,
    complete_priorities,
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
    get_default_operator,
    get_storage,
)
from ._json_state import echo_error, is_json_output


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
        try:
            from dogcat.deps import get_ready_work

            final_limit = limit_arg or limit
            storage = get_storage(dogcats_dir)
            ready_issues = get_ready_work(storage)

            ready_issues = apply_common_filters(
                ready_issues,
                issue_type=issue_type,
                priority=priority,
                label=label,
                owner=owner,
                parent=parent,
                namespace=namespace,
                all_namespaces=all_namespaces,
                agent_only=agent_only,
                dogcats_dir=str(storage.dogcats_dir),
                storage=storage,
            )

            if final_limit:
                ready_issues = ready_issues[:final_limit]

            if is_json_output(json_output):
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
            if include_inbox and not is_json_output(json_output):
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
        try:
            from dogcat.inbox import InboxStorage

            inbox = InboxStorage(dogcats_dir=dogcats_dir)
            proposals = [p for p in inbox.list() if not p.is_closed()]

            if not all_namespaces:
                ns_filter = get_namespace_filter(dogcats_dir, namespace)
                if ns_filter is not None:
                    proposals = [p for p in proposals if ns_filter(p.namespace)]
                else:
                    primary = get_issue_prefix(dogcats_dir)
                    proposals = [p for p in proposals if p.namespace == primary]

            if proposals:
                typer.echo(f"\nInbox ({len(proposals)}):")
                for proposal in proposals:
                    typer.echo(format_proposal_brief(proposal))
        except (ValueError, RuntimeError):
            pass  # No inbox file — silently skip

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
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Show all blocked issues."""
        try:
            from dogcat.deps import get_blocked_issues

            final_limit = limit_arg or limit
            storage = get_storage(dogcats_dir)
            blocked_issues = get_blocked_issues(storage)

            # Filter underlying issues, keep blocked entries that match
            blocked_issue_ids = {bi.issue_id for bi in blocked_issues}
            underlying = [storage.get(bid) for bid in blocked_issue_ids]
            underlying = [i for i in underlying if i is not None]
            filtered = apply_common_filters(
                underlying,
                issue_type=issue_type,
                priority=priority,
                label=label,
                owner=owner,
                parent=parent,
                namespace=namespace,
                all_namespaces=all_namespaces,
                agent_only=agent_only,
                dogcats_dir=str(storage.dogcats_dir),
                storage=storage,
            )
            filtered_ids = {i.full_id for i in filtered}
            blocked_issues = [
                bi for bi in blocked_issues if bi.issue_id in filtered_ids
            ]

            if final_limit:
                blocked_issues = blocked_issues[:final_limit]

            if is_json_output(json_output):
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
        tree: bool = typer.Option(False, "--tree", help="Display as tree"),
        table: bool = typer.Option(False, "--table", help="Display in columns"),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Show issues currently in progress."""
        try:
            final_limit = limit_arg or limit
            storage = get_storage(dogcats_dir)
            issues = storage.list({"status": "in_progress"})
            issues = apply_common_filters(
                issues,
                issue_type=issue_type,
                priority=priority,
                label=label,
                owner=owner,
                parent=parent,
                namespace=namespace,
                all_namespaces=all_namespaces,
                agent_only=agent_only,
                dogcats_dir=str(storage.dogcats_dir),
                storage=storage,
            )
            issues.sort(key=lambda i: i.priority)
            if final_limit:
                issues = issues[:final_limit]

            if is_json_output(json_output):
                from dogcat.models import issue_to_dict

                output = [issue_to_dict(issue) for issue in issues]
                typer.echo(orjson.dumps(output).decode())
            elif not issues:
                typer.echo("No in-progress issues")
            else:
                typer.echo(f"In Progress ({len(issues)}):")
                if tree or any(i.parent for i in issues):
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
        tree: bool = typer.Option(False, "--tree", help="Display as tree"),
        table: bool = typer.Option(False, "--table", help="Display in columns"),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Show all open issues."""
        try:
            final_limit = limit_arg or limit
            storage = get_storage(dogcats_dir)
            issues = storage.list({"status": "open"})
            issues = apply_common_filters(
                issues,
                issue_type=issue_type,
                priority=priority,
                label=label,
                owner=owner,
                parent=parent,
                namespace=namespace,
                all_namespaces=all_namespaces,
                agent_only=agent_only,
                dogcats_dir=str(storage.dogcats_dir),
                storage=storage,
            )
            issues.sort(key=lambda i: i.priority)
            if final_limit:
                issues = issues[:final_limit]

            if is_json_output(json_output):
                from dogcat.models import issue_to_dict

                output = [issue_to_dict(issue) for issue in issues]
                typer.echo(orjson.dumps(output).decode())
            elif not issues:
                typer.echo("No open issues")
            else:
                typer.echo(f"Open ({len(issues)}):")
                if tree or any(i.parent for i in issues):
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
        tree: bool = typer.Option(False, "--tree", help="Display as tree"),
        table: bool = typer.Option(False, "--table", help="Display in columns"),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Show issues currently in review."""
        try:
            final_limit = limit_arg or limit
            storage = get_storage(dogcats_dir)
            issues = storage.list({"status": "in_review"})
            issues = apply_common_filters(
                issues,
                issue_type=issue_type,
                priority=priority,
                label=label,
                owner=owner,
                parent=parent,
                namespace=namespace,
                all_namespaces=all_namespaces,
                agent_only=agent_only,
                dogcats_dir=str(storage.dogcats_dir),
                storage=storage,
            )
            issues.sort(key=lambda i: i.priority)
            if final_limit:
                issues = issues[:final_limit]

            if is_json_output(json_output):
                from dogcat.models import issue_to_dict

                output = [issue_to_dict(issue) for issue in issues]
                typer.echo(orjson.dumps(output).decode())
            elif not issues:
                typer.echo("No in-review issues")
            else:
                typer.echo(f"In Review ({len(issues)}):")
                if tree or any(i.parent for i in issues):
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

    def _set_status(
        issue_id: str,
        status: str,
        label: str,
        json_output: bool,
        operator: str | None,
        dogcats_dir: str,
    ) -> None:
        """Set an issue's status."""
        try:
            storage = get_storage(dogcats_dir)
            final_operator = (
                operator if operator is not None else get_default_operator()
            )
            issue = storage.update(
                issue_id,
                {"status": status, "updated_by": final_operator},
            )

            if is_json_output(json_output):
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
        priority: int | None,
        label: str | None,
        owner: str | None,
        parent: str | None,
        namespace: str | None,
        all_namespaces: bool,
        agent_only: bool,
        tree: bool,
        table: bool,
        json_output: bool,
        dogcats_dir: str,
    ) -> None:
        """List issues filtered by a single status."""
        try:
            final_limit = limit_arg or limit
            storage = get_storage(dogcats_dir)
            issues = storage.list({"status": status})
            issues.sort(key=lambda i: i.priority)

            issues = apply_common_filters(
                issues,
                issue_type=issue_type,
                priority=priority,
                label=label,
                owner=owner,
                parent=parent,
                namespace=namespace,
                all_namespaces=all_namespaces,
                agent_only=agent_only,
                dogcats_dir=str(storage.dogcats_dir),
                storage=storage,
            )

            if final_limit:
                issues = issues[:final_limit]

            if is_json_output(json_output):
                from dogcat.models import issue_to_dict

                output = [issue_to_dict(issue) for issue in issues]
                typer.echo(orjson.dumps(output).decode())
            elif not issues:
                typer.echo(empty_msg)
            else:
                typer.echo(f"{heading} ({len(issues)}):")
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
        tree: bool = typer.Option(False, "--tree", help="Display as tree"),
        table: bool = typer.Option(False, "--table", help="Display in columns"),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """List issues with in-review status."""
        _list_by_status(
            status="in_review",
            heading="In Review",
            empty_msg="No in-review issues",
            limit_arg=limit_arg,
            limit=limit,
            issue_type=issue_type,
            priority=priority,
            label=label,
            owner=owner,
            parent=parent,
            namespace=namespace,
            all_namespaces=all_namespaces,
            agent_only=agent_only,
            tree=tree,
            table=table,
            json_output=json_output,
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
        tree: bool = typer.Option(False, "--tree", help="Display as tree"),
        table: bool = typer.Option(False, "--table", help="Display in columns"),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """List issues with in-progress status."""
        _list_by_status(
            status="in_progress",
            heading="In Progress",
            empty_msg="No in-progress issues",
            limit_arg=limit_arg,
            limit=limit,
            issue_type=issue_type,
            priority=priority,
            label=label,
            owner=owner,
            parent=parent,
            namespace=namespace,
            all_namespaces=all_namespaces,
            agent_only=agent_only,
            tree=tree,
            table=table,
            json_output=json_output,
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
        tree: bool = typer.Option(False, "--tree", help="Display as tree"),
        table: bool = typer.Option(False, "--table", help="Display in columns"),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Show issues currently deferred."""
        try:
            final_limit = limit_arg or limit
            storage = get_storage(dogcats_dir)
            issues = storage.list({"status": "deferred"})
            issues = apply_common_filters(
                issues,
                issue_type=issue_type,
                priority=priority,
                label=label,
                owner=owner,
                parent=parent,
                namespace=namespace,
                all_namespaces=all_namespaces,
                agent_only=agent_only,
                dogcats_dir=str(storage.dogcats_dir),
                storage=storage,
            )
            issues.sort(key=lambda i: i.priority)
            if final_limit:
                issues = issues[:final_limit]

            if is_json_output(json_output):
                from dogcat.models import issue_to_dict

                output = [issue_to_dict(issue) for issue in issues]
                typer.echo(orjson.dumps(output).decode())
            elif not issues:
                typer.echo("No deferred issues")
            else:
                typer.echo(f"Deferred ({len(issues)}):")
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

    @app.command(name="defer", hidden=True)
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
        try:
            final_limit = limit_arg or limit
            storage = get_storage(dogcats_dir)
            issues = storage.list()
            issues = [
                i
                for i in issues
                if (i.metadata.get("manual") or i.metadata.get("no_agent"))
                and i.status.value not in ("closed", "tombstone")
            ]
            issues = apply_common_filters(
                issues,
                issue_type=issue_type,
                priority=priority,
                label=label,
                owner=owner,
                parent=parent,
                namespace=namespace,
                all_namespaces=all_namespaces,
                dogcats_dir=str(storage.dogcats_dir),
                storage=storage,
            )
            issues.sort(key=lambda i: i.priority)
            if final_limit:
                issues = issues[:final_limit]

            if is_json_output(json_output):
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
        """Mark an issue as manual (not for agents)."""
        try:
            is_json_output(json_output)  # sync local flag for echo_error
            storage = get_storage(dogcats_dir)
            final_operator = (
                operator if operator is not None else get_default_operator()
            )
            current = storage.get(issue_id)
            if current is None:
                echo_error(f"Issue {issue_id} not found")
                raise typer.Exit(1)
            new_metadata = dict(current.metadata) if current.metadata else {}
            new_metadata["manual"] = True
            new_metadata.pop("no_agent", None)
            issue = storage.update(
                issue_id,
                {"metadata": new_metadata, "operator": final_operator},
            )

            if is_json_output(json_output):
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
            None, "--limit", "-n", help="Number of issues to show"
        ),
        all_namespaces: bool = typer.Option(
            False,
            "--all-namespaces",
            "--all-ns",
            "-A",
            help="Show issues from all namespaces",
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Show recently closed issues (oldest first).

        Displays the last N closed issues in chronological order.
        """
        try:
            from dogcat.event_log import EventLog, _serialize

            from ._formatting import format_event, get_event_legend

            storage = get_storage(dogcats_dir)
            final_limit = limit_arg or limit or 10
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

            events = events[:final_limit]
            events.reverse()  # Display oldest-first

            # Fill in missing titles from storage
            for event in events:
                if not event.title:
                    issue_obj = storage.get(event.issue_id)
                    if issue_obj:
                        event.title = issue_obj.title

            if is_json_output(json_output):
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
            None, "--limit", "-n", help="Number of issues to show"
        ),
        all_namespaces: bool = typer.Option(
            False,
            "--all-namespaces",
            "--all-ns",
            "-A",
            help="Show issues from all namespaces",
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Show recently created issues in chronological order (oldest first).

        Displays the last N issues sorted by created_at date,
        with the oldest of the recent issues at the top.
        """
        try:
            storage = get_storage(dogcats_dir)
            issues = [
                i
                for i in storage.list()
                if i.status.value not in ("closed", "tombstone")
            ]

            # Apply namespace filter (skip if --all-namespaces)
            if not all_namespaces:
                actual_dogcats_dir = str(storage.dogcats_dir)
                ns_filter = get_namespace_filter(actual_dogcats_dir)
                if ns_filter is not None:
                    issues = [i for i in issues if ns_filter(i.namespace)]

            final_limit = limit_arg or limit or 10
            # Sort descending to select the N most recent, then reverse for display
            issues.sort(key=lambda i: i.created_at, reverse=True)

            # Take first N (most recent), then reverse for oldest-first display
            recent = issues[:final_limit]
            recent.reverse()

            if is_json_output(json_output):
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

    @app.command(name="rc", hidden=True)
    def recently_closed_alias(
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
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Alias for recently-closed."""
        recently_closed(
            limit_arg=limit_arg,
            limit=limit,
            all_namespaces=all_namespaces,
            json_output=json_output,
            dogcats_dir=dogcats_dir,
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

    @app.command(name="ra", hidden=True)
    def recently_added_alias(
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
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Alias for recently-added."""
        recently_added(
            limit_arg=limit_arg,
            limit=limit,
            all_namespaces=all_namespaces,
            json_output=json_output,
            dogcats_dir=dogcats_dir,
        )

    @app.command(name="pr")
    def progress_review(
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Show in-progress and in-review issues together."""
        try:
            storage = get_storage(dogcats_dir)
            ip_issues = storage.list({"status": "in_progress"})
            ip_issues.sort(key=lambda i: i.priority)
            ir_issues = storage.list({"status": "in_review"})
            ir_issues.sort(key=lambda i: i.priority)

            if is_json_output(json_output):
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
