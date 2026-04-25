"""Shared atomic file primitives for JSONL append-only stores.

Both :class:`dogcat.storage.JSONLStorage` and :class:`dogcat.inbox.InboxStorage`
use the same durability pattern: write to a tempfile in the same directory,
fsync, then ``replace()`` the target. Centralising it here means a single
place to harden (e.g. directory-fsync after rename) and a single place to
test.

Locking is left to callers: each store has its own
:meth:`_file_lock` context, and the lifetimes / re-entrancy rules differ
(e.g. ``JSONLStorage`` re-uses the lock from ``_append`` into
``_save_locked``).
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path
from typing import IO, TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


def atomic_rewrite_jsonl(
    target: Path,
    dogcats_dir: Path,
    write_fn: Callable[[IO[bytes]], int],
) -> int:
    """Rewrite ``target`` atomically via a tempfile in ``dogcats_dir``.

    ``write_fn`` receives an open binary file handle, writes records to it,
    and returns the number of lines written. After fsync, the tempfile is
    renamed onto ``target``. On any failure the tempfile is unlinked.
    """
    # Capture the existing mode of ``target`` BEFORE we write, so the
    # tempfile rename doesn't silently demote a 0644-shared file to
    # 0600 (NamedTemporaryFile's default mode). Without this, a shared
    # .dogcats becomes inaccessible to everyone except the writer
    # after the first compaction. (dogcat-1cfd)
    target_mode: int | None = None
    try:
        if target.exists():
            target_mode = target.stat().st_mode & 0o7777
    except OSError:
        target_mode = None

    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=dogcats_dir,
        delete=False,
        suffix=".jsonl",
    ) as tmp_file:
        tmp_path = Path(tmp_file.name)
        try:
            line_count = write_fn(tmp_file)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        except Exception as e:
            tmp_path.unlink(missing_ok=True)
            msg = f"Failed to write to temporary file: {e}"
            raise RuntimeError(msg) from e

    if target_mode is not None:
        # Best-effort — proceed with the rename even if the chmod
        # fails; the alternative is failing the whole save.
        with contextlib.suppress(OSError):
            tmp_path.chmod(target_mode)

    try:
        tmp_path.replace(target)
    except OSError as e:
        tmp_path.unlink(missing_ok=True)
        msg = f"Failed to write {target.name}: {e}"
        raise RuntimeError(msg) from e

    return line_count


def append_jsonl_payload(target: Path, payload: bytes) -> None:
    r"""Append ``payload`` to ``target`` with a trailing-newline guard.

    If ``target`` exists and its last byte is not ``\n`` (e.g. from a
    prior truncated write), a newline is prepended to ``payload`` so the
    next record starts on its own line and doesn't concatenate with the
    corrupt tail.
    """
    try:
        if target.exists() and target.stat().st_size > 0:
            with target.open("rb") as check:
                check.seek(-1, 2)
                if check.read(1) != b"\n":
                    payload = b"\n" + payload

        with target.open("ab") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
    except OSError as e:
        msg = f"Failed to append to {target.name}: {e}"
        raise RuntimeError(msg) from e
