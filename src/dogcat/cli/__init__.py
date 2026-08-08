"""Dogcat CLI commands for issue tracking."""

from __future__ import annotations

import os
from pathlib import Path

import typer

from ._helpers import SortedGroup

app = typer.Typer(
    help="dogcat - file-based issue tracking "
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
    repo: str | None = typer.Option(
        None,
        "-C",
        "--repo",
        metavar="PATH",
        help="Run as if dcat was started in PATH.",
    ),
) -> None:
    from ._json_state import reset_json, set_json

    reset_json()
    set_json(json_output)
    if repo is not None:
        target = Path(repo).expanduser()
        try:
            resolved = target.resolve(strict=True)
        except FileNotFoundError:
            typer.echo(f"Error: -C path does not exist: {target}", err=True)
            raise typer.Exit(1) from None
        if not resolved.is_dir():
            typer.echo(f"Error: -C path is not a directory: {resolved}", err=True)
            raise typer.Exit(1)
        os.chdir(resolved)
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit(0)


# Register each ``_cmd_*`` module independently so a single broken
# transitive (rich/textual ABI mismatch, watchdog wheel for the wrong
# Python ABI, etc.) doesn't collapse the whole CLI — including the
# diagnostic commands like ``dcat doctor`` users would reach for to
# investigate. Failures are logged with the module name and the rest
# of the CLI continues to work.
import importlib  # noqa: E402
import logging  # noqa: E402

_logger = logging.getLogger(__name__)

_COMMAND_MODULES: tuple[str, ...] = (
    "_cmd_admin",
    "_cmd_archive",
    "_cmd_cache",
    "_cmd_chart",
    "_cmd_close",
    "_cmd_comment",
    "_cmd_config",
    "_cmd_create",
    "_cmd_demo",
    "_cmd_dep",
    "_cmd_diff",
    "_cmd_docs",
    "_cmd_doctor",
    "_cmd_example_md",
    "_cmd_features",
    "_cmd_graph",
    "_cmd_history",
    "_cmd_inbox",
    "_cmd_init",
    "_cmd_label",
    "_cmd_propose",
    "_cmd_read",
    "_cmd_rename_namespace",
    "_cmd_reopen",
    "_cmd_search",
    "_cmd_stale",
    "_cmd_tui",
    "_cmd_update",
    "_cmd_web",
    "_cmd_workflow",
)


def _register_command_module(name: str) -> None:
    """Import and register one ``_cmd_<name>`` module — log + skip on failure."""
    try:
        mod = importlib.import_module(f".{name}", package=__name__)
        mod.register(app)
    except Exception as exc:  # noqa: BLE001
        _logger.warning(
            # No global -v exists (the root callback defines only --json and
            # -C/--repo), and %s above already carries the exception.
            "Failed to load CLI command module %r: %s. "
            "The rest of dcat still works; that module's commands are "
            "unavailable.",
            name,
            exc,
        )


for _name in _COMMAND_MODULES:
    _register_command_module(_name)


def main() -> None:
    """Run the Dogcat CLI application."""
    app()


# Backward-compat re-exports (used by tests and app.py)
from ._formatting import format_issue_brief as format_issue_brief  # noqa: E402
from ._helpers import find_dogcats_dir as find_dogcats_dir  # noqa: E402
from ._helpers import get_default_operator as get_default_operator  # noqa: E402
from ._helpers import get_storage as get_storage  # noqa: E402
