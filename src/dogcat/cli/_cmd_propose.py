"""Propose command for sending proposals to a target repo's inbox."""

from __future__ import annotations

from pathlib import Path

import orjson
import typer

from ._completions import complete_namespaces
from ._helpers import find_dogcats_dir, get_default_operator
from ._json_state import echo_error, is_json_output


def _resolve_target_dogcats(to: str) -> str:
    """Resolve --to path to a .dogcats directory.

    If the path already ends with .dogcats, use it directly.
    Otherwise, append .dogcats to the path.
    """
    target = Path(to)
    if target.name == ".dogcats" and target.is_dir():
        return str(target)
    candidate = target / ".dogcats"
    if candidate.is_dir():
        return str(candidate)
    if target.is_dir():
        msg = f"No .dogcats directory found in {to}"
        raise ValueError(msg)
    msg = f"Target directory does not exist: {to}"
    raise ValueError(msg)


def register(app: typer.Typer) -> None:
    """Register the propose command."""

    @app.command()
    def propose(
        title: str = typer.Argument(
            ...,
            help="Proposal title",
        ),
        description: str | None = typer.Option(
            None,
            "--description",
            "-d",
            help="Proposal description",
        ),
        by: str | None = typer.Option(
            None,
            "--by",
            help="Who is proposing (default: auto-detected)",
        ),
        to: str | None = typer.Option(
            None,
            "--to",
            help="Target repo root or .dogcats directory",
        ),
        namespace: str | None = typer.Option(
            None,
            "--namespace",
            "-n",
            help="Namespace for the proposal",
            autocompletion=complete_namespaces,
        ),
        json_output: bool = typer.Option(
            False,
            "--json",
            help="Output as JSON",
        ),
    ) -> None:
        """Send a proposal to a repo's inbox (fire-and-forget).

        Creates a proposal in the target repo's .dogcats/inbox.jsonl.
        If --to is not specified, uses the current repo's inbox.
        """
        from dogcat.config import load_config
        from dogcat.idgen import IDGenerator
        from dogcat.inbox import InboxStorage
        from dogcat.models import Proposal

        is_json_output(json_output)

        proposed_by = by if by is not None else get_default_operator()

        # Resolve source repo path
        try:
            source_repo = str(Path.cwd())
        except OSError:
            source_repo = None

        # Resolve target .dogcats directory
        try:
            if to is not None:
                target_dir = _resolve_target_dogcats(to)
            else:
                target_dir = find_dogcats_dir()
        except (ValueError, SystemExit) as e:
            echo_error(str(e))
            raise typer.Exit(1) from None

        # Resolve namespace
        ns: str
        if namespace is not None:
            ns = namespace
        else:
            try:
                config = load_config(target_dir)
                ns = str(config.get("namespace", "dc"))
            except Exception:
                ns = "dc"

        # Generate ID
        try:
            inbox = InboxStorage(dogcats_dir=target_dir)
        except (ValueError, RuntimeError) as e:
            echo_error(str(e))
            raise typer.Exit(1) from None

        id_gen = IDGenerator(
            existing_ids=inbox.get_proposal_ids(),
            prefix=f"{ns}-inbox",
        )
        proposal_id = id_gen.generate_proposal_id(
            title,
            namespace=f"{ns}-inbox",
        )

        proposal = Proposal(
            id=proposal_id,
            title=title,
            namespace=ns,
            description=description,
            proposed_by=proposed_by,
            source_repo=source_repo,
        )

        try:
            inbox.create(proposal)
        except (ValueError, RuntimeError) as e:
            echo_error(str(e))
            raise typer.Exit(1) from None

        if is_json_output(json_output):
            from dogcat.models import proposal_to_dict

            typer.echo(orjson.dumps(proposal_to_dict(proposal)).decode())
        else:
            typer.echo(
                f"✓ Proposed {proposal.full_id}: {proposal.title}",
            )
