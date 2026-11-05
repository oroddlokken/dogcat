"""Optional user-global hook that vets records before dcat writes them.

``pre_write_hook`` in the global config (``~/.config/dogcat/config.toml``)
names a shell command. Before any record is appended to ``issues.jsonl`` or
``inbox.jsonl`` the command runs with the JSONL lines about to be written on
stdin. Exit 0 lets the write through; anything else aborts it and nothing
reaches disk. This can enforce user-defined validation or policy, for example
secret scanning::

    pre_write_hook = "gitleaks stdin --no-banner --redact"

The hook is read from the global config only, never from a store's
``config.toml``: a store is often a checked-out repo, and a command in a
file someone else committed would run on every ``dcat create``.

The hook fails closed. A command that cannot start, times out or crashes
rejects the write, so configured validation cannot silently stop running.
"""

from __future__ import annotations

import os
import signal
import subprocess
from typing import TYPE_CHECKING

from dogcat.global_config import load_pre_write_hook_strict

if TYPE_CHECKING:
    from pathlib import Path

# Bound a hung hook so it cannot wedge every write.
HOOK_TIMEOUT_SECS = 30.0

# Set in the hook's environment so one command can tell the stores apart.
HOOK_TARGET_ENV_VAR = "DCAT_WRITE_TARGET"


class WriteHookRejectedError(ValueError):
    """The ``pre_write_hook`` refused the write, or could not be run.

    A ``ValueError`` so the CLI commands' existing ``except ValueError``
    branches print it as an ordinary error and exit 1.
    """


def run_pre_write_hook(payload: bytes, target: Path) -> None:
    """Run the configured ``pre_write_hook`` over ``payload``.

    Args:
        payload: The serialized JSONL lines about to be appended.
        target: The file they are about to be appended to.

    Raises:
        WriteHookRejectedError: The hook exited non-zero, timed out or
            could not be started.
    """
    try:
        command = load_pre_write_hook_strict()
    except ValueError as exc:
        msg = f"Invalid global config: {exc}"
        raise WriteHookRejectedError(msg) from None
    if not command:
        return
    if os.name != "posix":
        msg = "pre_write_hook requires POSIX process groups"
        raise WriteHookRejectedError(msg)

    env = {**os.environ, HOOK_TARGET_ENV_VAR: str(target.absolute())}
    try:
        process = subprocess.Popen(  # noqa: S602  # user's own global config
            command,
            shell=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=env,
        )
    except (OSError, ValueError):
        msg = "pre_write_hook could not start"
        raise WriteHookRejectedError(msg) from None
    try:
        process.communicate(input=payload, timeout=HOOK_TIMEOUT_SECS)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        finally:
            process.communicate()
        msg = f"pre_write_hook timed out after {HOOK_TIMEOUT_SECS:g}s"
        raise WriteHookRejectedError(msg) from None

    if process.returncode != 0:
        msg = f"pre_write_hook rejected the write (exit {process.returncode})"
        raise WriteHookRejectedError(msg)
