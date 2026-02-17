"""Inbox command group for managing received proposals."""

from __future__ import annotations

from typing import TYPE_CHECKING

import orjson
import typer

from dogcat.constants import STATUS_COLORS

from ._completions import complete_namespaces, complete_proposal_ids
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
        from dogcat.config import get_namespace_filter
        from dogcat.models import proposal_to_dict

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
            from dogcat.models import ProposalStatus

            proposals = [
                p
                for p in proposals
                if p.status not in (ProposalStatus.CLOSED, ProposalStatus.TOMBSTONE)
            ]

        if is_json_output(json_output):
            data = [proposal_to_dict(p) for p in proposals]
            typer.echo(orjson.dumps(data).decode())
        elif not proposals:
            typer.echo("No proposals in inbox.")
        else:
            for proposal in proposals:
                typer.echo(_format_proposal_brief(proposal))

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
            echo_error(f"Proposal {proposal_id} not found")
            raise typer.Exit(1)

        if is_json_output(json_output):
            typer.echo(
                orjson.dumps(proposal_to_dict(proposal)).decode(),
            )
        else:
            typer.echo(_format_proposal_full(proposal))

    @inbox_app.command("close")
    def inbox_close(
        proposal_id: str = typer.Argument(
            ...,
            help="Proposal ID to close",
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
        """Close an inbox proposal."""
        from dogcat.models import proposal_to_dict

        is_json_output(json_output)
        closed_by = by if by is not None else get_default_operator()

        try:
            inbox = _get_inbox(dogcats_dir)

        except (ValueError, RuntimeError) as e:
            echo_error(str(e))
            raise typer.Exit(1) from None

        try:
            proposal = inbox.close(
                proposal_id,
                reason=reason,
                closed_by=closed_by,
                resolved_issue=issue,
            )
        except ValueError as e:
            echo_error(str(e))
            raise typer.Exit(1) from None

        if is_json_output(json_output):
            typer.echo(
                orjson.dumps(proposal_to_dict(proposal)).decode(),
            )
        else:
            typer.echo(
                f"✓ Closed {proposal.full_id}: {proposal.title}",
            )

    @inbox_app.command("delete")
    def inbox_delete(
        proposal_id: str = typer.Argument(
            ...,
            help="Proposal ID to delete",
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
        """Delete an inbox proposal (creates tombstone)."""
        from dogcat.models import proposal_to_dict

        is_json_output(json_output)

        try:
            inbox = _get_inbox(dogcats_dir)

        except (ValueError, RuntimeError) as e:
            echo_error(str(e))
            raise typer.Exit(1) from None

        try:
            proposal = inbox.delete(proposal_id)
        except ValueError as e:
            echo_error(str(e))
            raise typer.Exit(1) from None

        if is_json_output(json_output):
            typer.echo(
                orjson.dumps(proposal_to_dict(proposal)).decode(),
            )
        else:
            typer.echo(
                f"✓ Deleted {proposal.full_id}: {proposal.title}",
            )
