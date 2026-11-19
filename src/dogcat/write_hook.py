"""Optional user-global hook that vets records before dcat writes them.

``pre_write_hook`` in the global config (``~/.config/dogcat/config.toml``)
names a shell command. Before any record is appended to ``issues.jsonl`` or
``inbox.jsonl`` the command runs with the JSONL lines about to be written on
stdin. Exit 0 lets the write through; anything else aborts it and nothing
reaches disk. The hook's stderr reaches the user so it can say why it
refused; its stdout is discarded. This can enforce user-defined validation
or policy, for example secret scanning::

    pre_write_hook = "gitleaks stdin --no-banner --redact"

The hook is read from the global config only, never from a store's
``config.toml``: a store is often a checked-out repo, and a command in a
file someone else committed would run on every ``dcat create``.

The hook fails closed. A command that cannot start, times out or crashes
rejects the write, so configured validation cannot silently stop running.
"""

from __future__ import annotations

import contextlib
import os
import selectors
import signal
import subprocess
import time
from typing import TYPE_CHECKING

from dogcat.global_config import load_pre_write_hook_strict

if TYPE_CHECKING:
    from pathlib import Path

# Bound a hung hook so it cannot wedge every write.
HOOK_TIMEOUT_SECS = 30.0
HOOK_STDERR_LIMIT = 4096

# Set in the hook's environment so one command can tell the stores apart.
HOOK_TARGET_ENV_VAR = "DCAT_WRITE_TARGET"


class WriteHookRejectedError(ValueError):
    """The ``pre_write_hook`` refused the write, or could not be run.

    A ``ValueError`` so the CLI commands' existing ``except ValueError``
    branches print it as an ordinary error and exit 1.
    """


def _exchange(
    process: subprocess.Popen[bytes], payload: bytes, stderr: bytearray
) -> None:
    """Feed stdin and drain stderr, keeping one extra byte to detect truncation."""
    assert process.stdin is not None  # noqa: S101  # Popen uses PIPE below
    assert process.stderr is not None  # noqa: S101  # Popen uses PIPE below
    deadline = time.monotonic() + HOOK_TIMEOUT_SECS
    remaining = memoryview(payload)
    with selectors.DefaultSelector() as selector:
        selector.register(process.stderr, selectors.EVENT_READ)
        if remaining:
            os.set_blocking(process.stdin.fileno(), False)
            selector.register(process.stdin, selectors.EVENT_WRITE)
        else:
            process.stdin.close()
        while selector.get_map():
            timeout = deadline - time.monotonic()
            if timeout <= 0:
                raise subprocess.TimeoutExpired(process.args, HOOK_TIMEOUT_SECS)
            for key, event in selector.select(timeout):
                if event == selectors.EVENT_READ:
                    chunk = os.read(key.fd, 65536)
                    if chunk:
                        stderr.extend(chunk[: HOOK_STDERR_LIMIT + 1 - len(stderr)])
                    else:
                        selector.unregister(key.fd)
                else:
                    try:
                        count = os.write(key.fd, remaining[:65536])
                        remaining = remaining[count:]
                    except BrokenPipeError:
                        remaining = remaining[:0]
                    if not remaining:
                        selector.unregister(key.fd)
                        process.stdin.close()
        process.wait(timeout=max(0, deadline - time.monotonic()))


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
            stderr=subprocess.PIPE,
            start_new_session=True,
            env=env,
        )
    except (OSError, ValueError):
        msg = "pre_write_hook could not start"
        raise WriteHookRejectedError(msg) from None
    stderr = bytearray()
    with process:
        try:
            _exchange(process, payload, stderr)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            msg = f"pre_write_hook timed out after {HOOK_TIMEOUT_SECS:g}s"
        else:
            if process.returncode == 0:
                return
            msg = f"pre_write_hook rejected the write (exit {process.returncode})"
    detail = stderr[:HOOK_STDERR_LIMIT].decode("utf-8", errors="replace").rstrip()
    if len(stderr) > HOOK_STDERR_LIMIT:
        detail += " [stderr truncated]"
    if detail:
        msg += f": {detail}"
    raise WriteHookRejectedError(msg)
