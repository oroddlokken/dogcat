"""Shared atomic file primitives for JSONL append-only stores.

Both :class:`dogcat.storage.JSONLStorage` and :class:`dogcat.inbox.InboxStorage`
need the same durability pattern: write to a tempfile in the same directory,
fsync, then ``replace()`` the target. Keeping it here gives one place to harden
it (e.g. adding a directory-fsync after the rename).

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
    from collections.abc import Callable, Iterator


def atomic_rewrite_jsonl(
    target: Path,
    dogcats_dir: Path,
    write_fn: Callable[[IO[bytes]], int],
) -> int:
    """Rewrite ``target`` atomically via a tempfile in ``dogcats_dir``.

    ``write_fn`` receives an open binary file handle, writes records to it,
    and returns the number of lines written. After fsync, the tempfile is
    renamed onto ``target``. On any failure the tempfile is unlinked.

    Raises:
        RuntimeError: Wrapping any ``OSError`` from the write, fsync or
            rename, with the original attached via ``from``. A caller that
            guards a save with ``except OSError`` catches nothing here.
    """
    # Capture the existing mode of ``target`` BEFORE we write, so the
    # tempfile rename doesn't silently demote a 0644-shared file to
    # 0600 (NamedTemporaryFile's default mode). Without this, a shared
    # .dogcats becomes inaccessible to everyone except the writer
    # after the first compaction.
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

    Raises:
        RuntimeError: Wrapping any ``OSError`` from the append or fsync, as
            in :func:`atomic_rewrite_jsonl` — ``except OSError`` around a
            call to this catches nothing.
    """
    try:
        # "a+b" rather than "ab" so the trailing-byte probe reuses this
        # handle instead of a second open(): Python seeks an append-mode
        # handle to EOF on open, so tell() is the size check, and O_APPEND
        # forces every write to EOF regardless of where the probe left the
        # read position.
        with target.open("a+b") as f:
            if f.tell() > 0:
                f.seek(-1, os.SEEK_END)
                if f.read(1) != b"\n":
                    f.write(b"\n")
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
    except OSError as e:
        msg = f"Failed to append to {target.name}: {e}"
        raise RuntimeError(msg) from e


_READ_CHUNK_SIZE = 1 << 20

# Per-line verdicts recorded by the classify pass and replayed by the two
# write passes. One byte per line, so the bookkeeping stays proportional to
# the line count rather than to the file's bytes.
_DROP = 0
_KEEP = 1
_ARCHIVE = 2


def _iter_lines(fh: IO[bytes]) -> Iterator[bytes]:
    r"""Yield lines from ``fh`` with ``bytes.splitlines(keepends=True)`` semantics.

    ``splitlines`` breaks on more separators than ``\n`` (``\r``, ``\v``,
    ``\f``, ``\x1c``-``\x1e``), so iterating the handle directly would
    partition a file differently than reading it whole. Holding back the last
    element of each chunk keeps a separator that straddles a chunk boundary —
    ``\r`` then ``\n`` — from splitting into two lines.

    Peak memory is one chunk plus the longest line, not the whole file.
    """
    chunk_size = _READ_CHUNK_SIZE
    carry = b""
    while True:
        chunk = fh.read(chunk_size)
        if not chunk:
            break
        parts = (carry + chunk).splitlines(keepends=True)
        carry = parts.pop() if parts else b""
        yield from parts
    if carry:
        yield carry


def _replay_verdicts(
    source: Path,
    verdicts: bytes,
    wanted: int,
    line_count: int,
) -> Callable[[IO[bytes]], int]:
    """Return a write_fn streaming ``source``'s ``wanted`` lines into a tempfile.

    ``verdicts`` pairs positionally with ``source``'s lines. ``strict=True``
    on the zip means a source that changed between the classify pass and this
    one raises rather than silently writing a truncated file.
    """

    def writer(f: IO[bytes]) -> int:
        with source.open("rb") as fh:
            for verdict, raw_line in zip(verdicts, _iter_lines(fh), strict=True):
                if verdict == wanted:
                    f.write(raw_line if raw_line.endswith(b"\n") else raw_line + b"\n")
        return line_count

    return writer


def split_and_rewrite_jsonl(
    source: Path,
    source_dir: Path,
    archive: Path,
    archive_dir: Path,
    classify: Callable[[bytes], bool],
) -> tuple[int, int]:
    """Partition ``source`` into archive vs keep, then atomically rewrite both.

    ``classify(stripped_line)`` returns True when a line belongs in the archive
    file, False when it stays in the source file, and is called once per line.
    Blank lines are dropped on both sides. Lines that fail to be classified
    (e.g. corrupt JSON whose classifier raises) are the caller's
    responsibility — they should classify such lines as "keep" so the source
    isn't quietly losing rows.

    The file is streamed three times — once to classify, once per output file
    to write — rather than held in memory as three copies. Callers already hold
    the store's file lock across the whole call, so the passes see one snapshot.

    Returns ``(archived_lines, remaining_lines)``. When nothing was classified
    as archive, the source is left untouched and ``(0, 0)`` is returned.
    """
    if not source.exists():
        return 0, 0

    verdicts = bytearray()
    archived_count = 0
    remaining_count = 0
    with source.open("rb") as fh:
        for raw_line in _iter_lines(fh):
            stripped = raw_line.strip()
            if not stripped:
                verdicts.append(_DROP)
            elif classify(stripped):
                verdicts.append(_ARCHIVE)
                archived_count += 1
            else:
                verdicts.append(_KEEP)
                remaining_count += 1

    if not archived_count:
        return 0, 0

    frozen = bytes(verdicts)
    atomic_rewrite_jsonl(
        archive,
        archive_dir,
        _replay_verdicts(source, frozen, _ARCHIVE, archived_count),
    )
    atomic_rewrite_jsonl(
        source,
        source_dir,
        _replay_verdicts(source, frozen, _KEEP, remaining_count),
    )

    return archived_count, remaining_count
