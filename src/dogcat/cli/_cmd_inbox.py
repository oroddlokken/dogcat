"""Inbox command group for managing received proposals."""

from __future__ import annotations

from typing import TYPE_CHECKING

import orjson
import typer

from dogcat.constants import STATUS_COLORS

from ._completions import (
    complete_labels,
    complete_namespaces,
    complete_priorities,
    complete_proposal_ids,
    complete_types,
)
from ._helpers import SortedGroup, find_dogcats_dir, get_default_operator
from ._json_state import echo_error, is_json_output

if TYPE_CHECKING:
    from dogcat.inbox import InboxStorage
    from dogcat.models import Proposal


def _get_inbox(dogcats_dir: str) -> InboxStorage:
    """Get an InboxStorage instance, resolving the directory."""
    from pathlib import Path

    from dogcat.inbox import InboxStorage

    if not Path(dogcats_dir).is_dir():
        dogcats_dir = find_dogcats_dir()
    return InboxStorage(dogcats_dir=dogcats_dir)


def _get_remote_inbox(dogcats_dir: str) -> tuple[InboxStorage, str] | None:
    """Get a remote InboxStorage if inbox_remote is configured.

    Returns:
        Tuple of (InboxStorage, remote_path) or None if not configured.
    """
    from pathlib import Path

    from dogcat.config import load_config
    from dogcat.inbox import InboxStorage

    if not Path(dogcats_dir).is_dir():
        dogcats_dir = find_dogcats_dir()

    config = load_config(dogcats_dir)
    remote_path = config.get("inbox_remote")
    if not remote_path:
        return None

    remote_dogcats = Path(remote_path).expanduser()
    if not remote_dogcats.is_dir():
        return None

    # Look for .dogcats subdir if the path doesn't end with it
    if remote_dogcats.name != ".dogcats":
        candidate = remote_dogcats / ".dogcats"
        if candidate.is_dir():
            remote_dogcats = candidate

    try:
        return InboxStorage(dogcats_dir=str(remote_dogcats)), str(remote_path)
    except (ValueError, RuntimeError):
        return None


def _format_proposal_brief(proposal: Proposal) -> str:
    """Format a proposal for brief list display."""
    emoji = proposal.get_status_emoji()
    return f"{emoji} {proposal.full_id}: {proposal.title}"


def _format_proposal_full(proposal: Proposal) -> str:
    """Format a proposal for detailed display."""

    def _styled(label: str) -> str:
        return typer.style(label, bold=True)

    status_color = STATUS_COLORS.get(proposal.status.value, "white")
    styled_status = typer.style(proposal.status.value, fg=status_color)
    dt_fmt = "%Y-%m-%d %H:%M:%S"

    lines = [
        f"{_styled('ID:')} {proposal.full_id}",
        f"{_styled('Title:')} {proposal.title}",
        "",
        f"{_styled('Status:')} {styled_status}",
    ]

    if proposal.proposed_by:
        lines.append(f"{_styled('Proposed by:')} {proposal.proposed_by}")
    if proposal.source_repo:
        lines.append(f"{_styled('Source repo:')} {proposal.source_repo}")
    lines.append(
        f"{_styled('Created:')} {proposal.created_at.strftime(dt_fmt)}",
    )
    if proposal.closed_at:
        closed_line = f"{_styled('Closed:')} {proposal.closed_at.strftime(dt_fmt)}"
        if proposal.close_reason:
            closed_line += f" ({proposal.close_reason})"
        lines.append(closed_line)
    if proposal.closed_by:
        lines.append(f"{_styled('Closed by:')} {proposal.closed_by}")
    if proposal.resolved_issue:
        lines.append(
            f"{_styled('Resolved issue:')} {proposal.resolved_issue}",
        )
    if proposal.description:
        lines.append(f"\n{_styled('Description:')}\n{proposal.description}")

    return "\n".join(lines)


inbox_app = typer.Typer(
    help="Manage inbox proposals.",
    no_args_is_help=True,
    cls=SortedGroup,
)


def register(app: typer.Typer) -> None:
    """Register the inbox command group."""
    app.add_typer(inbox_app, name="inbox")

    @inbox_app.command("list")
    def inbox_list(
        show_all: bool = typer.Option(
            False,
            "--all",
            "-a",
            help="Include closed and tombstoned proposals",
        ),
        namespace: str | None = typer.Option(
            None,
            "--namespace",
            "-n",
            help="Filter by namespace",
            autocompletion=complete_namespaces,
        ),
        all_namespaces: bool = typer.Option(
            False,
            "--all-namespaces",
            "--all-ns",
            "-A",
            help="Show proposals from all namespaces",
        ),
        json_output: bool = typer.Option(
            False,
            "--json",
            help="Output as JSON",
        ),
        dogcats_dir: str = typer.Option(
            ".dogcats",
            help="Path to .dogcats directory",
        ),
    ) -> None:
        """List inbox proposals."""
        from dogcat.config import get_issue_prefix, get_namespace_filter
        from dogcat.models import ProposalStatus, proposal_to_dict

        is_json_output(json_output)

        try:
            inbox = _get_inbox(dogcats_dir)

        except (ValueError, RuntimeError) as e:
            echo_error(str(e))
            raise typer.Exit(1) from None

        proposals = inbox.list(
            include_tombstones=show_all,
            namespace=namespace,
        )

        # Namespace filtering
        if not all_namespaces and not namespace:
            try:
                actual_dir = dogcats_dir
                from pathlib import Path

                if not Path(dogcats_dir).is_dir():
                    actual_dir = find_dogcats_dir()
                ns_filter = get_namespace_filter(actual_dir, None)
                if ns_filter is not None:
                    proposals = [p for p in proposals if ns_filter(p.namespace)]
            except Exception:
                import logging

                logging.getLogger(__name__).warning(
                    "Namespace filtering failed; showing unfiltered results",
                    exc_info=True,
                )

        if not show_all:
            proposals = [
                p
                for p in proposals
                if p.status not in (ProposalStatus.CLOSED, ProposalStatus.TOMBSTONE)
            ]

        # Load remote proposals if inbox_remote is configured
        remote_proposals: list[Proposal] = []
        remote_path: str | None = None
        try:
            actual_dir = dogcats_dir
            from pathlib import Path

            if not Path(dogcats_dir).is_dir():
                actual_dir = find_dogcats_dir()
            result = _get_remote_inbox(actual_dir)
            if result is not None:
                remote_inbox, remote_path = result
                current_ns = namespace or get_issue_prefix(actual_dir)
                remote_proposals = remote_inbox.list(
                    include_tombstones=show_all,
                    namespace=current_ns if not all_namespaces else None,
                )
                if not show_all:
                    remote_proposals = [
                        p
                        for p in remote_proposals
                        if p.status
                        not in (ProposalStatus.CLOSED, ProposalStatus.TOMBSTONE)
                    ]
        except Exception:
            import logging

            logging.getLogger(__name__).debug(
                "Remote inbox loading failed",
                exc_info=True,
            )

        if is_json_output(json_output):
            local_data = [{**proposal_to_dict(p), "source": "local"} for p in proposals]
            remote_data = [
                {**proposal_to_dict(p), "source": "remote"} for p in remote_proposals
            ]
            typer.echo(orjson.dumps(local_data + remote_data).decode())
        elif not proposals and not remote_proposals:
            typer.echo("No proposals in inbox.")
        else:
            if proposals:
                for proposal in proposals:
                    typer.echo(_format_proposal_brief(proposal))
            if remote_proposals:
                if proposals:
                    typer.echo()
                typer.echo(
                    typer.style(
                        f"Remote proposals ({remote_path}):",
                        bold=True,
                    ),
                )
                for proposal in remote_proposals:
                    typer.echo(f"  {_format_proposal_brief(proposal)}")

    @inbox_app.command("show")
    def inbox_show(
        proposal_id: str = typer.Argument(
            ...,
            help="Proposal ID",
            autocompletion=complete_proposal_ids,
        ),
        json_output: bool = typer.Option(
            False,
            "--json",
            help="Output as JSON",
        ),
        dogcats_dir: str = typer.Option(
            ".dogcats",
            help="Path to .dogcats directory",
        ),
    ) -> None:
        """Show details of a specific proposal."""
        from dogcat.models import proposal_to_dict

        is_json_output(json_output)

        try:
            inbox = _get_inbox(dogcats_dir)

        except (ValueError, RuntimeError) as e:
            echo_error(str(e))
            raise typer.Exit(1) from None

        try:
            proposal = inbox.get(proposal_id)
        except ValueError as e:
            echo_error(str(e))
            raise typer.Exit(1) from None

        if proposal is None:
            # Fall back to remote inbox
            remote = _get_remote_inbox(dogcats_dir)
            if remote is not None:
                remote_inbox, _ = remote
                proposal = remote_inbox.get(proposal_id)

        if proposal is None:
            echo_error(f"Proposal {proposal_id} not found")
            raise typer.Exit(1)

        if is_json_output(json_output):
            typer.echo(
                orjson.dumps(proposal_to_dict(proposal)).decode(),
            )
        else:
            typer.echo(_format_proposal_full(proposal))

    def _close_one(
        inbox: InboxStorage,
        proposal_id: str,
        reason: str | None,
        closed_by: str | None,
        resolved_issue: str | None,
        json_output: bool,
    ) -> bool:
        """Close a single proposal. Returns True if an error occurred."""
        from dogcat.models import proposal_to_dict

        try:
            proposal = inbox.close(
                proposal_id,
                reason=reason,
                closed_by=closed_by,
                resolved_issue=resolved_issue,
            )

            if is_json_output(json_output):
                typer.echo(
                    orjson.dumps(proposal_to_dict(proposal)).decode(),
                )
            else:
                typer.echo(
                    f"✓ Closed {proposal.full_id}: {proposal.title}",
                )
        except (ValueError, Exception) as e:
            echo_error(f"closing {proposal_id}: {e}")
            return True
        return False

    @inbox_app.command("close")
    def inbox_close(
        proposal_ids: list[str] = typer.Argument(  # noqa: B008
            ...,
            help="Proposal ID(s) to close",
            autocompletion=complete_proposal_ids,
        ),
        reason: str | None = typer.Option(
            None,
            "--reason",
            "-r",
            help="Reason for closing",
        ),
        issue: str | None = typer.Option(
            None,
            "--issue",
            "-i",
            help="Issue ID created from this proposal (stored as string)",
        ),
        by: str | None = typer.Option(
            None,
            "--by",
            help="Who is closing this",
        ),
        json_output: bool = typer.Option(
            False,
            "--json",
            help="Output as JSON",
        ),
        dogcats_dir: str = typer.Option(
            ".dogcats",
            help="Path to .dogcats directory",
        ),
    ) -> None:
        """Close one or more inbox proposals."""
        is_json_output(json_output)
        closed_by = by if by is not None else get_default_operator()

        try:
            inbox = _get_inbox(dogcats_dir)

        except (ValueError, RuntimeError) as e:
            echo_error(str(e))
            raise typer.Exit(1) from None

        has_errors = False

        for proposal_id in proposal_ids:
            has_errors = (
                _close_one(
                    inbox,
                    proposal_id,
                    reason,
                    closed_by,
                    issue,
                    json_output,
                )
                or has_errors
            )

        if has_errors:
            raise typer.Exit(1)

    def _delete_one(
        inbox: InboxStorage,
        proposal_id: str,
        deleted_by: str | None,
        json_output: bool,
    ) -> bool:
        """Delete a single proposal. Returns True if an error occurred."""
        from dogcat.models import proposal_to_dict

        try:
            proposal = inbox.delete(proposal_id, deleted_by=deleted_by)

            if is_json_output(json_output):
                typer.echo(
                    orjson.dumps(proposal_to_dict(proposal)).decode(),
                )
            else:
                typer.echo(
                    f"✓ Deleted {proposal.full_id}: {proposal.title}",
                )
        except (ValueError, Exception) as e:
            echo_error(f"deleting {proposal_id}: {e}")
            return True
        return False

    @inbox_app.command("delete")
    def inbox_delete(
        proposal_ids: list[str] = typer.Argument(  # noqa: B008
            ...,
            help="Proposal ID(s) to delete",
            autocompletion=complete_proposal_ids,
        ),
        by: str | None = typer.Option(
            None,
            "--by",
            help="Who is deleting this",
        ),
        json_output: bool = typer.Option(
            False,
            "--json",
            help="Output as JSON",
        ),
        dogcats_dir: str = typer.Option(
            ".dogcats",
            help="Path to .dogcats directory",
        ),
    ) -> None:
        """Delete one or more inbox proposals (creates tombstone)."""
        is_json_output(json_output)
        deleted_by = by if by is not None else get_default_operator()

        try:
            inbox = _get_inbox(dogcats_dir)

        except (ValueError, RuntimeError) as e:
            echo_error(str(e))
            raise typer.Exit(1) from None

        has_errors = False

        for proposal_id in proposal_ids:
            has_errors = (
                _delete_one(
                    inbox,
                    proposal_id,
                    deleted_by,
                    json_output,
                )
                or has_errors
            )

        if has_errors:
            raise typer.Exit(1)

    @inbox_app.command("accept")
    def inbox_accept(
        proposal_id: str = typer.Argument(
            ...,
            help="Proposal ID to accept (from remote inbox)",
            autocompletion=complete_proposal_ids,
        ),
        priority: int | None = typer.Option(
            None,
            "--priority",
            "-p",
            help="Priority for the new issue (0-4)",
            autocompletion=complete_priorities,
        ),
        issue_type: str | None = typer.Option(
            None,
            "--type",
            "-t",
            help="Issue type (task, bug, feature, etc.)",
            autocompletion=complete_types,
        ),
        labels: str | None = typer.Option(
            None,
            "--labels",
            "--label",
            "-l",
            help="Labels (comma or space separated)",
            autocompletion=complete_labels,
        ),
        json_output: bool = typer.Option(
            False,
            "--json",
            help="Output as JSON",
        ),
        dogcats_dir: str = typer.Option(
            ".dogcats",
            help="Path to .dogcats directory",
        ),
    ) -> None:
        """Accept a remote proposal and create a local issue from it."""
        from datetime import datetime
        from pathlib import Path

        from dogcat.config import get_issue_prefix
        from dogcat.constants import DEFAULT_PRIORITY, DEFAULT_TYPE, parse_labels
        from dogcat.idgen import IDGenerator
        from dogcat.models import Issue, IssueType, Status, issue_to_dict

        is_json_output(json_output)
        operator = get_default_operator()

        # Resolve local .dogcats dir
        actual_dir = dogcats_dir
        if not Path(dogcats_dir).is_dir():
            actual_dir = find_dogcats_dir()

        # Get remote inbox
        remote_result = _get_remote_inbox(actual_dir)
        if remote_result is None:
            echo_error(
                "No remote inbox configured. "
                "Set inbox_remote with: dcat config set inbox_remote <path> --local",
            )
            raise typer.Exit(1)

        remote_inbox, _remote_path = remote_result

        # Find the proposal
        try:
            proposal = remote_inbox.get(proposal_id)
        except ValueError as e:
            echo_error(str(e))
            raise typer.Exit(1) from None

        if proposal is None:
            echo_error(f"Proposal {proposal_id} not found in remote inbox")
            raise typer.Exit(1)

        # Create a local issue from the proposal
        try:
            from ._helpers import get_storage

            storage = get_storage(actual_dir)
            namespace = get_issue_prefix(actual_dir)
            idgen = IDGenerator(existing_ids=storage.get_issue_ids(), prefix=namespace)

            timestamp = datetime.now().astimezone()
            issue_id = idgen.generate_issue_id(
                proposal.title,
                timestamp=timestamp,
                namespace=namespace,
            )

            issue_labels = parse_labels(labels) if labels else []
            final_priority = priority if priority is not None else DEFAULT_PRIORITY
            final_type = issue_type if issue_type is not None else DEFAULT_TYPE

            issue = Issue(
                id=issue_id,
                title=proposal.title,
                namespace=namespace,
                description=proposal.description,
                status=Status.OPEN,
                priority=final_priority,
                issue_type=IssueType(final_type),
                owner=operator,
                labels=issue_labels,
                created_by=operator,
            )

            storage.create(issue)

            # Close the remote proposal with a link to the new issue
            remote_inbox.close(
                proposal.full_id,
                reason="Accepted as issue",
                closed_by=operator,
                resolved_issue=issue.full_id,
            )

            if is_json_output(json_output):
                typer.echo(orjson.dumps(issue_to_dict(issue)).decode())
            else:
                typer.echo(
                    f"✓ Created {issue.full_id} from proposal {proposal.full_id}",
                )

        except (ValueError, RuntimeError) as e:
            echo_error(str(e))
            raise typer.Exit(1) from None

    def _reject_one(
        remote_inbox: InboxStorage,
        proposal_id: str,
        reason: str | None,
        closed_by: str | None,
        json_output: bool,
    ) -> bool:
        """Reject a single remote proposal. Returns True if an error occurred."""
        from dogcat.models import proposal_to_dict

        try:
            proposal = remote_inbox.close(
                proposal_id,
                reason=reason or "Rejected",
                closed_by=closed_by,
            )
            if is_json_output(json_output):
                typer.echo(
                    orjson.dumps(proposal_to_dict(proposal)).decode(),
                )
            else:
                typer.echo(
                    f"✓ Rejected {proposal.full_id}: {proposal.title}",
                )
        except (ValueError, RuntimeError) as e:
            echo_error(f"rejecting {proposal_id}: {e}")
            return True
        return False

    @inbox_app.command("reject")
    def inbox_reject(
        proposal_ids: list[str] = typer.Argument(  # noqa: B008
            ...,
            help="Proposal ID(s) to reject (from remote inbox)",
            autocompletion=complete_proposal_ids,
        ),
        reason: str | None = typer.Option(
            None,
            "--reason",
            "-r",
            help="Reason for rejecting",
        ),
        json_output: bool = typer.Option(
            False,
            "--json",
            help="Output as JSON",
        ),
        dogcats_dir: str = typer.Option(
            ".dogcats",
            help="Path to .dogcats directory",
        ),
    ) -> None:
        """Reject one or more remote proposals (closes them in remote inbox)."""
        from pathlib import Path

        is_json_output(json_output)
        operator = get_default_operator()

        # Resolve local .dogcats dir
        actual_dir = dogcats_dir
        if not Path(dogcats_dir).is_dir():
            actual_dir = find_dogcats_dir()

        # Get remote inbox
        remote_result = _get_remote_inbox(actual_dir)
        if remote_result is None:
            echo_error(
                "No remote inbox configured. "
                "Set inbox_remote with: dcat config set inbox_remote <path> --local",
            )
            raise typer.Exit(1)

        remote_inbox, _remote_path = remote_result
        has_errors = False

        for pid in proposal_ids:
            has_errors = (
                _reject_one(remote_inbox, pid, reason, operator, json_output)
                or has_errors
            )

        if has_errors:
            raise typer.Exit(1)
