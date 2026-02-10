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

from . import (  # noqa: E402
    _cmd_archive,
    _cmd_close,
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
    _cmd_tui,
    _cmd_update,
    _cmd_workflow,
)

for _mod in (
    _cmd_archive,
    _cmd_close,
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
