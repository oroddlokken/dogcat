"""Direct tests for the atomic JSONL primitives in ``dogcat._jsonl_io``.

These primitives back every storage/inbox write. The failure paths are
the interesting part: tempfile cleanup on writer error, RuntimeError
wrapping on rename failure, the trailing-newline guard for ``append``,
and the (currently non-atomic) two-step ``split_and_rewrite_jsonl``
rewrite where a failure on the second leg can leave records in both
files. (dogcat-g6it)
"""

from __future__ import annotations

from pathlib import Path
from typing import IO, TYPE_CHECKING

import pytest

from dogcat._jsonl_io import (
    append_jsonl_payload,
    atomic_rewrite_jsonl,
    split_and_rewrite_jsonl,
)

if TYPE_CHECKING:
    from collections.abc import Callable


def _writer(lines: list[bytes]) -> Callable[[IO[bytes]], int]:
    def write_fn(f: IO[bytes]) -> int:
        for line in lines:
            f.write(line if line.endswith(b"\n") else line + b"\n")
        return len(lines)

    return write_fn


class TestAtomicRewriteJsonl:
    """Direct coverage for ``atomic_rewrite_jsonl`` failure paths."""

    def test_writes_lines_atomically(self, tmp_path: Path) -> None:
        """Successful write replaces the target with the written lines."""
        target = tmp_path / "issues.jsonl"
        count = atomic_rewrite_jsonl(target, tmp_path, _writer([b"a", b"b"]))
        assert count == 2
        assert target.read_text().splitlines() == ["a", "b"]

    def test_writer_failure_cleans_up_tempfile(self, tmp_path: Path) -> None:
        """write_fn raising leaves no tempfile and raises RuntimeError.

        Callers rely on a single exception type for IO failures.
        """
        target = tmp_path / "issues.jsonl"

        def boom(_f: IO[bytes]) -> int:
            msg = "writer exploded"
            raise ValueError(msg)

        with pytest.raises(RuntimeError, match=r"Failed to write to temporary file"):
            atomic_rewrite_jsonl(target, tmp_path, boom)

        assert not target.exists()
        # No leftover .jsonl tempfiles in the directory.
        assert list(tmp_path.glob("*.jsonl")) == []

    def test_replace_failure_cleans_up_and_wraps(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``tmp_path.replace`` raising leaves the original untouched.

        The tempfile must be unlinked and the OSError wrapped as
        RuntimeError to match the writer-failure contract.
        """
        target = tmp_path / "issues.jsonl"
        target.write_text("original\n")

        real_replace = Path.replace

        def fail_replace(self: Path, dst: str | Path) -> Path:
            if Path(dst) == target:
                msg = "disk full"
                raise OSError(msg)
            return real_replace(self, dst)

        monkeypatch.setattr(Path, "replace", fail_replace)

        with pytest.raises(RuntimeError, match=r"Failed to write issues\.jsonl"):
            atomic_rewrite_jsonl(target, tmp_path, _writer([b"new"]))

        # Original content untouched.
        assert target.read_text() == "original\n"
        # No tempfile left behind.
        leftover = [p for p in tmp_path.glob("*.jsonl") if p != target]
        assert leftover == []

    def test_preserves_target_mode_across_rename(self, tmp_path: Path) -> None:
        """Target's POSIX mode is preserved across the atomic rename."""
        target = tmp_path / "issues.jsonl"
        target.write_text("seed\n")
        target.chmod(0o644)
        atomic_rewrite_jsonl(target, tmp_path, _writer([b"a"]))
        assert (target.stat().st_mode & 0o777) == 0o644

    def test_chmod_failure_does_not_block_rewrite(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``chmod`` failure after fsync is best-effort and must not block.

        The rewrite must still complete so callers don't lose writes over
        a permissions hiccup.
        """
        target = tmp_path / "issues.jsonl"
        target.write_text("seed\n")
        target.chmod(0o644)

        real_chmod = Path.chmod

        def fail_chmod(self: Path, mode: int, *, follow_symlinks: bool = True) -> None:
            if self.suffix == ".jsonl" and self != target:
                msg = "simulated chmod failure"
                raise OSError(msg)
            return real_chmod(self, mode, follow_symlinks=follow_symlinks)

        monkeypatch.setattr(Path, "chmod", fail_chmod)

        atomic_rewrite_jsonl(target, tmp_path, _writer([b"after"]))
        assert target.read_text() == "after\n"


class TestAppendJsonlPayload:
    """Direct coverage for ``append_jsonl_payload``."""

    def test_appends_to_existing_file_with_newline(self, tmp_path: Path) -> None:
        """Normal append concatenates onto a newline-terminated file."""
        target = tmp_path / "log.jsonl"
        target.write_text("a\n")
        append_jsonl_payload(target, b"b\n")
        assert target.read_text() == "a\nb\n"

    def test_prepends_newline_when_last_byte_is_not_newline(
        self, tmp_path: Path
    ) -> None:
        """Truncated tails get a leading newline so records don't concatenate.

        Without this guard, a file that ended mid-line would silently
        merge the next record onto the corrupt tail.
        """
        target = tmp_path / "log.jsonl"
        target.write_bytes(b"prev_record_no_newline")
        append_jsonl_payload(target, b"new\n")
        # New record must start on its own line.
        text = target.read_text()
        assert text.endswith("\nnew\n")
        assert "no_newlinenew" not in text

    def test_creates_file_when_missing(self, tmp_path: Path) -> None:
        """Append to a missing file creates it with the payload."""
        target = tmp_path / "log.jsonl"
        append_jsonl_payload(target, b"a\n")
        assert target.read_text() == "a\n"

    def test_appends_to_existing_empty_file(self, tmp_path: Path) -> None:
        """A zero-byte file gets the payload with no leading newline.

        The single-handle probe reads the size from ``tell()``; a
        seek-back on an empty file would raise, so the guard has to skip
        it. (dogcat-47qk)
        """
        target = tmp_path / "log.jsonl"
        target.write_bytes(b"")
        append_jsonl_payload(target, b"a\n")
        assert target.read_bytes() == b"a\n"

    def test_repeated_appends_after_unterminated_tail(self, tmp_path: Path) -> None:
        """Only the first append after a corrupt tail inserts a newline.

        The second append sees a newline-terminated file and must not add
        a blank line. This is the case a ``tell()``-based probe breaks if
        it leaves the read position where the write lands. (dogcat-47qk)
        """
        target = tmp_path / "log.jsonl"
        target.write_bytes(b"truncated")
        append_jsonl_payload(target, b"one\n")
        append_jsonl_payload(target, b"two\n")
        assert target.read_bytes() == b"truncated\none\ntwo\n"

    def test_payload_without_trailing_newline_preserved(self, tmp_path: Path) -> None:
        """A payload that lacks a trailing newline is written verbatim.

        The guard fixes the file's tail, never the payload's.
        """
        target = tmp_path / "log.jsonl"
        target.write_bytes(b"a\n")
        append_jsonl_payload(target, b"b")
        assert target.read_bytes() == b"a\nb"

    def test_oserror_wrapped_as_runtimeerror(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Bare OSError must be wrapped so callers see one failure mode."""
        target = tmp_path / "log.jsonl"
        target.write_text("seed\n")

        real_open = Path.open

        def boom(self: Path, *args: object, **kwargs: object) -> object:
            if self == target and "a+b" in args:
                msg = "disk full"
                raise OSError(msg)
            return real_open(self, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(Path, "open", boom)

        with pytest.raises(RuntimeError, match=r"Failed to append to log\.jsonl"):
            append_jsonl_payload(target, b"x\n")

    def test_append_opens_the_file_once(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """One append opens the target once, not twice.

        Guards the regression back to a separate probe handle plus a
        separate append handle. (dogcat-47qk)
        """
        target = tmp_path / "log.jsonl"
        target.write_bytes(b"truncated")

        real_open = Path.open
        opens: list[object] = []

        def counting_open(self: Path, *args: object, **kwargs: object) -> object:
            if self == target:
                opens.append(args[0] if args else kwargs.get("mode"))
            return real_open(self, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(Path, "open", counting_open)
        append_jsonl_payload(target, b"x\n")

        assert opens == ["a+b"]
        assert target.read_bytes() == b"truncated\nx\n"

    def test_fsync_called_on_every_append(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The fsync is a deliberate durability choice — keep it.

        Trimming syscalls around the append must not trim the fsync
        itself. (dogcat-47qk)
        """
        import dogcat._jsonl_io as io_mod

        real_fsync = io_mod.os.fsync
        calls: list[int] = []

        def tracking_fsync(fd: int) -> None:
            calls.append(fd)
            real_fsync(fd)

        monkeypatch.setattr(io_mod.os, "fsync", tracking_fsync)

        target = tmp_path / "log.jsonl"
        append_jsonl_payload(target, b"a\n")
        append_jsonl_payload(target, b"b\n")
        assert len(calls) == 2


class TestSplitAndRewriteJsonl:
    """Direct coverage for ``split_and_rewrite_jsonl``."""

    def _classify_archive_marker(self, line: bytes) -> bool:
        return line.startswith(b"ARCHIVE:")

    def test_partition_writes_both_files(self, tmp_path: Path) -> None:
        """Lines partition cleanly into archive vs source on classify."""
        source = tmp_path / "src.jsonl"
        archive = tmp_path / "arc.jsonl"
        source.write_bytes(
            b"keep:1\nARCHIVE:1\nkeep:2\nARCHIVE:2\n",
        )
        archived, remaining = split_and_rewrite_jsonl(
            source,
            tmp_path,
            archive,
            tmp_path,
            self._classify_archive_marker,
        )
        assert archived == 2
        assert remaining == 2
        assert archive.read_text().splitlines() == ["ARCHIVE:1", "ARCHIVE:2"]
        assert source.read_text().splitlines() == ["keep:1", "keep:2"]

    def test_no_matching_lines_leaves_source_untouched(self, tmp_path: Path) -> None:
        """Source untouched + no archive when classify never matches."""
        source = tmp_path / "src.jsonl"
        archive = tmp_path / "arc.jsonl"
        source.write_bytes(b"keep:1\nkeep:2\n")
        result = split_and_rewrite_jsonl(
            source,
            tmp_path,
            archive,
            tmp_path,
            self._classify_archive_marker,
        )
        assert result == (0, 0)
        assert source.read_text() == "keep:1\nkeep:2\n"
        assert not archive.exists()

    def test_missing_source_returns_zero(self, tmp_path: Path) -> None:
        """Missing source is a no-op, not a failure."""
        source = tmp_path / "missing.jsonl"
        archive = tmp_path / "arc.jsonl"
        result = split_and_rewrite_jsonl(
            source,
            tmp_path,
            archive,
            tmp_path,
            self._classify_archive_marker,
        )
        assert result == (0, 0)
        assert not archive.exists()

    def test_blank_lines_dropped(self, tmp_path: Path) -> None:
        """Blank and whitespace-only lines drop out of both partitions."""
        source = tmp_path / "src.jsonl"
        archive = tmp_path / "arc.jsonl"
        source.write_bytes(b"keep:1\n\nARCHIVE:1\n   \n")
        archived, remaining = split_and_rewrite_jsonl(
            source,
            tmp_path,
            archive,
            tmp_path,
            self._classify_archive_marker,
        )
        assert archived == 1
        assert remaining == 1
        assert archive.read_text().splitlines() == ["ARCHIVE:1"]
        assert source.read_text().splitlines() == ["keep:1"]

    def test_output_matches_the_read_whole_file_reference(self, tmp_path: Path) -> None:
        r"""Streaming output is byte-identical to the buffered original.

        The reference below is the pre-streaming implementation: read the
        whole file, ``splitlines(keepends=True)``, partition into two
        lists. The fixture carries the cases where the two could diverge —
        an unterminated final line, a bare ``\r`` mid-file, and a ``\r\n``
        pair. (dogcat-2fxc)
        """
        fixture = b"keep:1\nARCHIVE:1\n\nkeep:2\r\nARCHIVE:2\rkeep:3\n   \nARCHIVE:3"

        def reference(raw: bytes) -> tuple[bytes, bytes]:
            archived: list[bytes] = []
            remaining: list[bytes] = []
            for raw_line in raw.splitlines(keepends=True):
                stripped = raw_line.strip()
                if not stripped:
                    continue
                bucket = (
                    archived if self._classify_archive_marker(stripped) else remaining
                )
                bucket.append(
                    raw_line if raw_line.endswith(b"\n") else raw_line + b"\n"
                )
            return b"".join(archived), b"".join(remaining)

        expected_archive, expected_source = reference(fixture)

        source = tmp_path / "src.jsonl"
        archive = tmp_path / "arc.jsonl"
        source.write_bytes(fixture)
        split_and_rewrite_jsonl(
            source,
            tmp_path,
            archive,
            tmp_path,
            self._classify_archive_marker,
        )

        assert archive.read_bytes() == expected_archive
        assert source.read_bytes() == expected_source

    @pytest.mark.parametrize("chunk_size", [1, 2, 3, 7, 64])
    def test_chunk_boundaries_do_not_change_the_partition(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        chunk_size: int,
    ) -> None:
        r"""Any read-chunk size yields the same two files.

        A ``\r\n`` split across two chunks is the case that would
        otherwise turn one line into two. (dogcat-2fxc)
        """
        import dogcat._jsonl_io as io_mod

        monkeypatch.setattr(io_mod, "_READ_CHUNK_SIZE", chunk_size)

        source = tmp_path / "src.jsonl"
        archive = tmp_path / "arc.jsonl"
        source.write_bytes(b"keep:1\r\nARCHIVE:1\r\nkeep:2\nARCHIVE:2")

        archived, remaining = split_and_rewrite_jsonl(
            source,
            tmp_path,
            archive,
            tmp_path,
            self._classify_archive_marker,
        )

        assert (archived, remaining) == (2, 2)
        assert archive.read_bytes() == b"ARCHIVE:1\r\nARCHIVE:2\n"
        assert source.read_bytes() == b"keep:1\r\nkeep:2\n"

    def test_classify_called_once_per_line(self, tmp_path: Path) -> None:
        """Three streaming passes must not mean three classify calls.

        The verdicts from the first pass are replayed by the write
        passes, so a classifier that parses JSON pays for it once.
        (dogcat-2fxc)
        """
        source = tmp_path / "src.jsonl"
        archive = tmp_path / "arc.jsonl"
        source.write_bytes(b"keep:1\nARCHIVE:1\nkeep:2\nARCHIVE:2\n")

        seen: list[bytes] = []

        def counting_classify(line: bytes) -> bool:
            seen.append(line)
            return self._classify_archive_marker(line)

        split_and_rewrite_jsonl(source, tmp_path, archive, tmp_path, counting_classify)
        assert len(seen) == 4

    def test_peak_memory_is_not_proportional_to_file_size(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Peak allocation tracks the chunk size, not the file.

        The old implementation held ~3x the file at once; 4 MB of input
        under a 64 KiB chunk must now peak well under the file size.
        (dogcat-2fxc)
        """
        import tracemalloc

        import dogcat._jsonl_io as io_mod

        monkeypatch.setattr(io_mod, "_READ_CHUNK_SIZE", 1 << 16)

        source = tmp_path / "src.jsonl"
        archive = tmp_path / "arc.jsonl"
        payload = b"".join(
            (b"ARCHIVE:" if i % 2 else b"keep:") + b"x" * 200 + b"\n"
            for i in range(20_000)
        )
        source.write_bytes(payload)
        file_size = len(payload)
        assert file_size > 4_000_000

        tracemalloc.start()
        try:
            split_and_rewrite_jsonl(
                source,
                tmp_path,
                archive,
                tmp_path,
                self._classify_archive_marker,
            )
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

        assert peak < file_size // 4, f"peak {peak} of {file_size} bytes"

    def test_partial_failure_leaves_records_in_both_files(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Document the current non-atomic two-step rewrite contract.

        When the second ``atomic_rewrite_jsonl`` call (source) fails
        after the archive has already been written, the archived records
        exist in BOTH files until the next compaction. If a future
        change makes the operation atomic, flip this test to assert no
        duplication. See ``dogcat._jsonl_io.split_and_rewrite_jsonl``.
        """
        source = tmp_path / "src.jsonl"
        archive = tmp_path / "arc.jsonl"
        source.write_bytes(b"keep:1\nARCHIVE:1\nkeep:2\nARCHIVE:2\n")

        import dogcat._jsonl_io as io_mod

        real_atomic = io_mod.atomic_rewrite_jsonl
        call_count = {"n": 0}

        def fail_second(
            target: Path,
            dogcats_dir: Path,
            write_fn: Callable[[IO[bytes]], int],
        ) -> int:
            call_count["n"] += 1
            if call_count["n"] == 2:
                msg = "Failed to write src.jsonl: simulated"
                raise RuntimeError(msg)
            return real_atomic(target, dogcats_dir, write_fn)

        monkeypatch.setattr(io_mod, "atomic_rewrite_jsonl", fail_second)

        with pytest.raises(RuntimeError, match=r"Failed to write src\.jsonl"):
            split_and_rewrite_jsonl(
                source,
                tmp_path,
                archive,
                tmp_path,
                self._classify_archive_marker,
            )

        # Archive was written; source is unchanged. The archived records
        # therefore exist in BOTH files — this is the documented gap.
        assert archive.read_text().splitlines() == ["ARCHIVE:1", "ARCHIVE:2"]
        # Source still has the original 4 lines including ARCHIVE:* rows.
        source_lines = source.read_text().splitlines()
        assert "ARCHIVE:1" in source_lines
        assert "ARCHIVE:2" in source_lines
