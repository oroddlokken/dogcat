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
            if self == target and "ab" in args:
                msg = "disk full"
                raise OSError(msg)
            return real_open(self, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(Path, "open", boom)

        with pytest.raises(RuntimeError, match=r"Failed to append to log\.jsonl"):
            append_jsonl_payload(target, b"x\n")


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
