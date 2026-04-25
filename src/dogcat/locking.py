"""Shared advisory file lock used across storage, inbox, and event log."""

from __future__ import annotations

import fcntl
import os
import time
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

# Default time we are willing to wait for the lock before giving up.
# A stale dcat process holding the lock would otherwise block every future
# write forever; bounding the wait turns the silent hang into a clear error.
DEFAULT_LOCK_TIMEOUT_SECS: float = 30.0
LOCK_TIMEOUT_ENV_VAR = "DCAT_LOCK_TIMEOUT_SECS"

_RETRY_INTERVAL_SECS = 0.05


def _resolve_timeout() -> float:
    """Pick the lock timeout, honoring an env override when set."""
    raw = os.environ.get(LOCK_TIMEOUT_ENV_VAR)
    if not raw:
        return DEFAULT_LOCK_TIMEOUT_SECS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_LOCK_TIMEOUT_SECS
    return value if value > 0 else DEFAULT_LOCK_TIMEOUT_SECS


@contextmanager
def advisory_file_lock(lock_path: Path) -> Generator[None, None, None]:
    """Acquire an advisory ``fcntl.LOCK_EX`` lock on ``lock_path``.

    The lock file is created on demand. ``OSError`` while opening the
    file is wrapped in a ``RuntimeError`` with the path and a remediation
    hint so callers see a clear error instead of a raw traceback when the
    directory is missing or unwritable.

    The lock is acquired with a non-blocking retry loop bounded by
    :data:`DEFAULT_LOCK_TIMEOUT_SECS` (override via the
    ``DCAT_LOCK_TIMEOUT_SECS`` environment variable). On timeout we raise
    ``RuntimeError`` naming the lock path so a stale holder can be
    investigated instead of blocking writers indefinitely.
    """
    try:
        lock_fd = lock_path.open("w")
    except OSError as e:
        msg = (
            f"Failed to open lock file at '{lock_path}': {e}. "
            f"Check that the directory exists and is writable."
        )
        raise RuntimeError(msg) from e
    try:
        timeout = _resolve_timeout()
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    msg = (
                        f"Timed out after {timeout:.1f}s waiting for advisory "
                        f"lock at '{lock_path}'. Another dcat process may be "
                        f"holding it; investigate and remove the lock file if "
                        f"the holder is gone."
                    )
                    raise RuntimeError(msg) from None
                time.sleep(_RETRY_INTERVAL_SECS)
        yield
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()
