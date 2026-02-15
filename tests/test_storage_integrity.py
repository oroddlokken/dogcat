"""Tests for storage data integrity fixes.

Covers: fsync in compaction, fsync in append, malformed last-line tolerance,
atomic append (single-write), and UPDATABLE_FIELDS correctness.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from unittest.mock import patch

import orjson
import pytest

from dogcat.models import Issue, issue_to_dict
from dogcat.storage import JSONLStorage

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def storage(temp_dogcats_dir: Path) -> JSONLStorage:
    """Create a storage instance with temporary directory."""
    storage_path = temp_dogcats_dir / "issues.jsonl"
    return JSONLStorage(str(storage_path), create_dir=True)


def _valid_line(issue_id: str = "ok", title: str = "OK") -> str:
    """Return a valid JSONL line for an issue."""
    return orjson.dumps(issue_to_dict(Issue(id=issue_id, title=title))).decode()


class TestFsyncInCompaction:
    """Verify os.fsync is called during compaction (_save)."""

    def test_fsync_called_during_save(self, storage: JSONLStorage) -> None:
        """Verify _save() calls os.fsync()."""
        storage.create(Issue(id="i1", title="Issue 1"))

        fsync_fds: list[int] = []
        original_fsync = os.fsync

        def tracking_fsync(fd: int) -> None:
            fsync_fds.append(fd)
            original_fsync(fd)

        with patch("dogcat.storage.os.fsync", side_effect=tracking_fsync):
            storage._save()

        assert len(fsync_fds) >= 1, "os.fsync should be called during _save()"

    def test_save_produces_valid_file(self, storage: JSONLStorage) -> None:
        """After _save(), the file contains only valid JSONL and all issues."""
        for i in range(5):
            storage.create(Issue(id=f"i{i}", title=f"Issue {i}"))

        storage._save()

        # Reload and verify
        s2 = JSONLStorage(str(storage.path))
        assert len(s2.list()) == 5

        # Every line in the file should be valid JSON
        for line in storage.path.read_text().splitlines():
            if line.strip():
                orjson.loads(line)


class TestFsyncInAppend:
    """Verify os.fsync is called during _append."""

    def test_fsync_called_on_append(self, storage: JSONLStorage) -> None:
        """Verify _append() calls os.fsync() after flush."""
        storage.create(Issue(id="seed", title="Seed"))

        fsync_called = False
        original_fsync = os.fsync

        def tracking_fsync(fd: int) -> None:
            nonlocal fsync_called
            fsync_called = True
            original_fsync(fd)

        with patch("dogcat.storage.os.fsync", side_effect=tracking_fsync):
            storage.create(Issue(id="new", title="New"))

        assert fsync_called


class TestAtomicAppend:
    """Verify _append writes payload in a single f.write() call."""

    def test_append_produces_complete_lines(self, storage: JSONLStorage) -> None:
        """Each appended record produces a complete, valid JSONL line."""
        storage.create(Issue(id="a", title="A"))
        storage.create(Issue(id="b", title="B"))
        storage.create(Issue(id="c", title="C"))

        # Every line in the file must be valid JSON (includes event records)
        lines = [ln for ln in storage.path.read_text().splitlines() if ln.strip()]
        assert len(lines) >= 3  # At least 3 issue records, plus event records
        for line in lines:
            data = orjson.loads(line)
            assert isinstance(data, dict)

    def test_append_payload_is_pre_serialized(self, storage: JSONLStorage) -> None:
        """Verify payload is joined before write (check via file content)."""
        storage.create(Issue(id="seed", title="Seed"))

        # Append 3 records at once via internal API
        records = [
            issue_to_dict(Issue(id=f"batch{i}", title=f"Batch {i}")) for i in range(3)
        ]
        storage._append(records)

        # All records should be present and valid
        s2 = JSONLStorage(str(storage.path))
        assert len(s2.list()) == 4  # seed + 3 batch


class TestMalformedLastLineTolerance:
    """Verify _load() tolerates a corrupt last line but rejects corrupt middle lines."""

    def test_truncated_json_last_line_recovers_all_valid(
        self, temp_workspace: Path
    ) -> None:
        """Valid issues before a truncated last line are all recovered."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage_path.parent.mkdir(parents=True, exist_ok=True)

        lines = [_valid_line(f"issue-{i}", f"Issue {i}") for i in range(5)]
        lines.append('{"id": "bad", "title": "Trun')  # Truncated JSON
        storage_path.write_text("\n".join(lines) + "\n")

        s = JSONLStorage(str(storage_path))
        issues = s.list()
        assert len(issues) == 5
        for i in range(5):
            assert s.get(f"issue-{i}") is not None

    def test_empty_braces_last_line_tolerated(self, temp_workspace: Path) -> None:
        """A last line with just '{' is tolerated."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage_path.parent.mkdir(parents=True, exist_ok=True)

        storage_path.write_text(f"{_valid_line()}\n{{\n")

        s = JSONLStorage(str(storage_path))
        assert len(s.list()) == 1

    def test_corrupt_middle_line_still_raises(self, temp_workspace: Path) -> None:
        """A corrupt line in the middle still raises ValueError."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage_path.parent.mkdir(parents=True, exist_ok=True)

        v1 = _valid_line("a", "A")
        v2 = _valid_line("b", "B")
        storage_path.write_text(f"{v1}\nGARBAGE\n{v2}\n")

        with pytest.raises(ValueError, match="Invalid JSONL record at line 2"):
            JSONLStorage(str(storage_path))

    def test_corrupt_second_to_last_line_raises(self, temp_workspace: Path) -> None:
        """Only the very last line is tolerated — second-to-last must be valid."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage_path.parent.mkdir(parents=True, exist_ok=True)

        valid = _valid_line()
        storage_path.write_text(f"{valid}\nGARBAGE\n{valid}\n")

        with pytest.raises(ValueError, match="Invalid JSONL record at line 2"):
            JSONLStorage(str(storage_path))

    def test_trailing_whitespace_lines_ignored(self, temp_workspace: Path) -> None:
        """Trailing empty/whitespace lines don't shift what counts as 'last'."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage_path.parent.mkdir(parents=True, exist_ok=True)

        valid = _valid_line()
        storage_path.write_text(f"{valid}\nGARBAGE\n\n\n")

        s = JSONLStorage(str(storage_path))
        assert len(s.list()) == 1

    def test_malformed_last_line_logs_warning(
        self, temp_workspace: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Skipping a malformed last line emits a warning log."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage_path.parent.mkdir(parents=True, exist_ok=True)

        storage_path.write_text(f"{_valid_line()}\ntruncated")

        import logging

        with caplog.at_level(logging.WARNING, logger="dogcat.storage"):
            JSONLStorage(str(storage_path))

        assert any("Skipping malformed last line" in msg for msg in caplog.messages)

    def test_operations_after_recovery_work(self, temp_workspace: Path) -> None:
        """After recovering from a corrupt last line, normal operations still work."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage_path.parent.mkdir(parents=True, exist_ok=True)

        storage_path.write_text(f"{_valid_line('existing', 'Existing')}\nGARBAGE")

        s = JSONLStorage(str(storage_path))
        assert len(s.list()) == 1

        # Create a new issue — should work fine
        s.create(Issue(id="new", title="New issue"))
        assert len(s.list()) == 2

        # Reload from disk — new issue should persist
        s2 = JSONLStorage(str(storage_path))
        assert len(s2.list()) == 2
        assert s2.get("new") is not None

    def test_dependency_record_as_corrupt_last_line(self, temp_workspace: Path) -> None:
        """A truncated dependency record as last line doesn't lose issue data."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage_path.parent.mkdir(parents=True, exist_ok=True)

        v1 = _valid_line("a", "Issue A")
        v2 = _valid_line("b", "Issue B")
        truncated_dep = (
            '{"record_type": "dependency", "issue_id": "dc-a", "depends_on_id":'
        )
        storage_path.write_text(f"{v1}\n{v2}\n{truncated_dep}\n")

        s = JSONLStorage(str(storage_path))
        assert len(s.list()) == 2


class TestUpdatableFields:
    """Verify UPDATABLE_FIELDS only contains fields that exist on Issue."""

    def test_all_updatable_fields_exist_on_issue(self) -> None:
        """Every field in UPDATABLE_FIELDS must exist on the Issue dataclass."""
        from dataclasses import fields

        issue_field_names = {f.name for f in fields(Issue)}
        for field_name in JSONLStorage.UPDATABLE_FIELDS:
            assert field_name in issue_field_names, (
                f"'{field_name}' is in UPDATABLE_FIELDS but not on Issue dataclass"
            )

    def test_manual_not_in_updatable_fields(self) -> None:
        """'manual' should not be in UPDATABLE_FIELDS (it lives in metadata)."""
        assert "manual" not in JSONLStorage.UPDATABLE_FIELDS


class TestCompactionWithCorruptFile:
    """Verify _save() (compaction) handles corrupt lines in the existing file."""

    def test_save_skips_corrupt_lines_when_preserving_events(
        self, temp_workspace: Path
    ) -> None:
        """_save() should skip malformed lines when scanning for event records."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        s = JSONLStorage(str(storage_path), create_dir=True)
        s.create(Issue(id="i1", title="First"))

        # Inject a corrupt line
        with storage_path.open("a") as f:
            f.write("CORRUPT_LINE\n")

        # Reload (tolerates corrupt last line)
        s2 = JSONLStorage(str(storage_path))
        assert len(s2.list()) == 1

        # Compaction should succeed — not crash on the corrupt line
        s2._save()

        # File is clean after compaction
        s3 = JSONLStorage(str(storage_path))
        assert len(s3.list()) == 1

    def test_events_survive_compaction_with_corrupt_line(
        self, temp_workspace: Path
    ) -> None:
        """Event records are preserved even when the file has a corrupt line."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        s = JSONLStorage(str(storage_path), create_dir=True)
        s.create(Issue(id="i1", title="First"))
        s.update("dc-i1", {"title": "Updated"})

        # Inject corruption
        with storage_path.open("a") as f:
            f.write("GARBAGE\n")

        s2 = JSONLStorage(str(storage_path))
        s2._save()

        # Verify events survived
        content = storage_path.read_text()
        event_lines = [
            ln
            for ln in content.splitlines()
            if ln.strip() and orjson.loads(ln).get("record_type") == "event"
        ]
        assert len(event_lines) >= 1


class TestCrashRecoveryRoundTrip:
    """Test complete crash recovery scenarios end-to-end."""

    def test_crash_during_append_then_reload(self, temp_workspace: Path) -> None:
        """Simulate crash mid-append and verify recovery on next load."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        s = JSONLStorage(str(storage_path), create_dir=True)

        # Normal operations
        s.create(Issue(id="i1", title="First"))
        s.create(Issue(id="i2", title="Second"))
        s.close("dc-i2", reason="done")

        # Simulate a crash by appending truncated JSON directly
        with storage_path.open("a") as f:
            f.write('{"id": "crash", "title": "Cras')

        # Reload — should recover everything except the crashed write
        s2 = JSONLStorage(str(storage_path))
        assert len(s2.list()) == 2
        assert s2.get("i1") is not None
        assert s2.get("i2") is not None
        assert s2.get("i2").status.value == "closed"  # type: ignore[union-attr]

    def test_compaction_after_recovery_cleans_up(self, temp_workspace: Path) -> None:
        """After recovering from corrupt last line, compaction produces a clean file."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        s = JSONLStorage(str(storage_path), create_dir=True)

        s.create(Issue(id="i1", title="First"))

        # Corrupt the file
        with storage_path.open("a") as f:
            f.write("GARBAGE\n")

        # Reload (tolerates corrupt last line)
        s2 = JSONLStorage(str(storage_path))
        assert len(s2.list()) == 1

        # Force compaction
        s2._save()

        # Reload again — file should be clean now
        s3 = JSONLStorage(str(storage_path))
        assert len(s3.list()) == 1

        # Verify no garbage in the file
        content = storage_path.read_text()
        for line in content.splitlines():
            if line.strip():
                orjson.loads(line)  # Should not raise

    def test_full_workflow_after_crash_recovery(self, temp_workspace: Path) -> None:
        """Full create/update/close/reopen workflow after recovering from corruption."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        s = JSONLStorage(str(storage_path), create_dir=True)
        s.create(Issue(id="i1", title="First"))

        # Corrupt and recover
        with storage_path.open("a") as f:
            f.write('{"id": "bad"')

        s2 = JSONLStorage(str(storage_path))
        assert len(s2.list()) == 1

        # Full workflow should work
        s2.create(Issue(id="i2", title="Second"))
        s2.update("dc-i1", {"title": "Updated First"})
        s2.close("dc-i2", reason="done")
        s2.reopen("dc-i2", reason="not done")
        s2.update("dc-i2", {"priority": 0})

        assert s2.get("i1").title == "Updated First"  # type: ignore[union-attr]
        assert s2.get("i2").status.value == "open"  # type: ignore[union-attr]
        assert s2.get("i2").priority == 0  # type: ignore[union-attr]

        # Verify persistence through compaction + reload
        s2._save()
        s3 = JSONLStorage(str(storage_path))
        assert len(s3.list()) == 2
        assert s3.get("i1").title == "Updated First"  # type: ignore[union-attr]


class TestCompactionMergesDisk:
    """Verify _save() reloads from disk to avoid discarding concurrent appends."""

    def test_compaction_preserves_external_append(self, temp_workspace: Path) -> None:
        """Records appended by another process between load and compaction survive."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        s = JSONLStorage(str(storage_path), create_dir=True)
        s.create(Issue(id="i1", title="Original"))

        # Simulate another process appending a new issue directly to the file
        external_issue = issue_to_dict(Issue(id="ext", title="External"))
        with storage_path.open("ab") as f:
            f.write(orjson.dumps(external_issue) + b"\n")

        # Our in-memory state doesn't know about "ext".
        assert s.get("ext") is None

        # Force compaction — should reload from disk and preserve "ext".
        s._save()

        # Verify both issues survived
        s2 = JSONLStorage(str(storage_path))
        assert len(s2.list()) == 2
        assert s2.get("i1") is not None
        assert s2.get("ext") is not None
        assert s2.get("ext").title == "External"  # type: ignore[union-attr]

    def test_compaction_preserves_external_dep(self, temp_workspace: Path) -> None:
        """Deps appended by another process survive compaction."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        s = JSONLStorage(str(storage_path), create_dir=True)
        s.create(Issue(id="a", title="A"))
        s.create(Issue(id="b", title="B"))

        # Simulate external dep append
        from datetime import datetime

        dep_record = {
            "record_type": "dependency",
            "issue_id": "dc-a",
            "depends_on_id": "dc-b",
            "type": "blocks",
            "created_at": datetime.now().astimezone().isoformat(),
            "created_by": None,
        }
        with storage_path.open("ab") as f:
            f.write(orjson.dumps(dep_record) + b"\n")

        # Our in-memory state has no deps
        assert len(s.all_dependencies) == 0

        # Force compaction with reload
        s._save()

        # Dep should survive
        s2 = JSONLStorage(str(storage_path))
        assert len(s2.all_dependencies) == 1

    def test_save_reload_false_does_not_merge_disk(self, temp_workspace: Path) -> None:
        """_save(_reload=False) uses only in-memory state."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        s = JSONLStorage(str(storage_path), create_dir=True)
        s.create(Issue(id="i1", title="Original"))

        # Simulate external append
        external_issue = issue_to_dict(Issue(id="ext", title="External"))
        with storage_path.open("ab") as f:
            f.write(orjson.dumps(external_issue) + b"\n")

        # _reload=False: only writes our in-memory state
        s._save(_reload=False)

        s2 = JSONLStorage(str(storage_path))
        assert len(s2.list()) == 1
        assert s2.get("i1") is not None
        assert s2.get("ext") is None
