"""Global JSON output state for dogcat CLI."""

from __future__ import annotations

import sys

import orjson
import typer

_global_json: bool = False


def set_json_flag(value: bool) -> None:
    """Set the global JSON output flag."""
    global _global_json  # noqa: PLW0603
    _global_json = value


def is_json_output(local_flag: bool = False) -> bool:
    """Check if JSON output is enabled (global or local flag).

    Also syncs the local flag to global state so that ``echo_error``
    outputs JSON when the per-command ``--json`` flag is used.
    """
    global _global_json  # noqa: PLW0603
    if local_flag and not _global_json:
        _global_json = True
    return local_flag or _global_json


def echo_error(message: str) -> None:
    """Output an error message, formatted as JSON if in JSON mode.

    In JSON mode, outputs ``{"error": "..."}`` to stderr.
    In plain mode, outputs ``Error: ...`` to stderr.
    """
    if _global_json:
        sys.stderr.write(orjson.dumps({"error": message}).decode() + "\n")
    else:
        typer.echo(f"Error: {message}", err=True)
