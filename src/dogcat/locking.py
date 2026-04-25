"""Shared advisory file lock used across storage, inbox, and event log."""

from __future__ import annotations

import fcntl
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path


@contextmanager
def advisory_file_lock(lock_path: Path) -> Generator[None, None, None]:
    """Acquire an advisory ``fcntl.LOCK_EX`` lock on ``lock_path``.

    The lock file is created on demand. ``OSError`` while opening the
    file is wrapped in a ``RuntimeError`` with the path and a remediation
    hint so callers see a clear error instead of a raw traceback when the
    directory is missing or unwritable.
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
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()
