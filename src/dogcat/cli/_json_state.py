"""Global JSON output state for dogcat CLI."""

from __future__ import annotations

import sys

import orjson
import typer

_global_json: bool = False


def set_json(value: bool) -> None:
    """Set JSON output mode for the current invocation.

    Called once by the global Typer callback (with the global ``--json``
    flag) and once by each subcommand body (with its local ``--json``).
    Setting ``True`` enables JSON for any later ``echo_error`` /
    ``is_json()`` calls; setting ``False`` from the global callback
    resets state between in-process invocations (e.g. CliRunner tests).

    Subcommands typically pass ``json_output``; if both global and local
    are ``False`` the state stays ``False``. The order of calls is
    callback → subcommand body, so a subcommand cannot downgrade the
    global flag back to off (the body's ``False`` would only run after a
    global ``True``, but the body sees ``json_output=False`` only when
    the user did not pass ``--json`` to the subcommand — which is fine).
    """
    global _global_json  # noqa: PLW0603
    if value:
        _global_json = True


def reset_json() -> None:
    """Reset JSON state to off (called by the global callback)."""
    global _global_json  # noqa: PLW0603
    _global_json = False


def is_json() -> bool:
    """Return True if JSON output is currently enabled."""
    return _global_json


def echo_error(message: str) -> None:
    """Output an error message, formatted as JSON if in JSON mode.

    In JSON mode, outputs ``{"error": "..."}`` to stderr.
    In plain mode, outputs ``Error: ...`` to stderr.
    """
    if _global_json:
        sys.stderr.write(orjson.dumps({"error": message}).decode() + "\n")
    else:
        typer.echo(f"Error: {message}", err=True)
