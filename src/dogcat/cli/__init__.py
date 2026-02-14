"""Dogcat CLI commands for issue tracking."""

from __future__ import annotations

import typer

from ._helpers import SortedGroup

app = typer.Typer(
    help="dogcat - lightweight, file-based issue tracking "
    "and memory upgrade for AI agents (and humans!)",
    no_args_is_help=True,
    cls=SortedGroup,
)


@app.callback(invoke_without_command=True)
def _global_options(
    ctx: typer.Context,
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output as JSON for all commands",
    ),
) -> None:
    from ._json_state import set_json_flag

    set_json_flag(json_output)
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit(0)


from . import (  # noqa: E402
    _cmd_archive,
    _cmd_close,
    _cmd_config,
    _cmd_create,
    _cmd_demo,
    _cmd_dep,
    _cmd_diff,
    _cmd_docs,
    _cmd_features,
    _cmd_history,
    _cmd_init,
    _cmd_maintenance,
    _cmd_read,
    _cmd_reopen,
    _cmd_tui,
    _cmd_update,
    _cmd_workflow,
)

for _mod in (
    _cmd_archive,
    _cmd_close,
    _cmd_config,
    _cmd_create,
    _cmd_demo,
    _cmd_dep,
    _cmd_diff,
    _cmd_docs,
    _cmd_features,
    _cmd_history,
    _cmd_init,
    _cmd_maintenance,
    _cmd_read,
    _cmd_reopen,
    _cmd_tui,
    _cmd_update,
    _cmd_workflow,
):
    _mod.register(app)


def main() -> None:
    """Run the Dogcat CLI application."""
    app()


# Backward-compat re-exports (used by tests and app.py)
from ._formatting import format_issue_brief as format_issue_brief  # noqa: E402
from ._helpers import find_dogcats_dir as find_dogcats_dir  # noqa: E402
from ._helpers import get_default_operator as get_default_operator  # noqa: E402
from ._helpers import get_storage as get_storage  # noqa: E402
