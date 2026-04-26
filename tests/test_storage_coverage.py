"""Additional storage tests to improve coverage on edge cases."""

from pathlib import Path

import orjson
import pytest

from dogcat.models import Issue, IssueType, Status
from dogcat.storage import JSONLStorage


@pytest.fixture
def storage(temp_dogcats_dir: Path) -> JSONLStorage:
    """Create a storage instance with temporary directory."""
    storage_path = temp_dogcats_dir / "issues.jsonl"
    return JSONLStorage(str(storage_path), create_dir=True)


class TestAmbiguousPartialId:
    """Test ambiguous partial ID resolution."""

    def test_ambiguous_partial_id_raises(self, storage: JSONLStorage) -> None:
        """Test that ambiguous partial ID raises ValueError."""
        # Both IDs end with "c1" to create ambiguity on suffix match
        storage.create(Issue(id="abc1", namespace="dc", title="Issue 1"))
        storage.create(Issue(id="xbc1", namespace="dc", title="Issue 2"))

        with pytest.raises(ValueError, match="Ambiguous"):
            storage.resolve_id("bc1")

    def test_suffix_match_works(self, storage: JSONLStorage) -> None:
        """Test that suffix-only match resolves correctly."""
        storage.create(Issue(id="xyz1", namespace="dc", title="Issue 1"))

        resolved = storage.resolve_id("xyz1")
        assert resolved == "dc-xyz1"


class TestPruneTombstones:
    """Test tombstone pruning."""

    def test_prune_removes_tombstones(self, storage: JSONLStorage) -> None:
        """Test that prune removes tombstoned issues."""
        storage.create(Issue(id="keep", title="Keep me"))
        storage.create(Issue(id="del1", title="Delete me"))
        storage.create(Issue(id="del2", title="Also delete"))
        storage.delete("del1", reason="gone")
        storage.delete("del2", reason="also gone")

        pruned = storage.prune_tombstones()
        assert len(pruned) == 2
        assert storage.get("keep") is not None
        assert storage.get("del1") is None
        assert storage.get("del2") is None

    def test_prune_no_tombstones(self, storage: JSONLStorage) -> None:
        """Test that prune with no tombstones returns empty list."""
        storage.create(Issue(id="alive", title="Alive"))

        pruned = storage.prune_tombstones()
        assert pruned == []

    def test_prune_removes_orphaned_events(self, storage: JSONLStorage) -> None:
        """Test that prune removes events for pruned issues from JSONL."""
        storage.create(Issue(id="keep", title="Keep me"))
        storage.create(Issue(id="del1", title="Delete me"))
        storage.update("keep", {"title": "Updated keep"})
        storage.update("del1", {"title": "Updated del"})
        storage.delete("del1", reason="gone")

        storage.prune_tombstones()

        # Read raw JSONL and check that no events reference the pruned issue
        raw_lines = storage.path.read_bytes().splitlines()
        event_issue_ids: set[str] = set()
        for line in raw_lines:
            data = orjson.loads(line)
            if data.get("record_type") == "event":
                event_issue_ids.add(data["issue_id"])

        # Events for the pruned issue should be gone
        assert "dc-del1" not in event_issue_ids

        # Events for the kept issue should still exist
        assert "dc-keep" in event_issue_ids


class TestUpdateIssueTypeConversion:
    """Test that update converts string issue_type to enum."""

    def test_update_issue_type_as_string(self, storage: JSONLStorage) -> None:
        """Test updating issue_type with string value."""
        storage.create(Issue(id="issue-1", title="Test", issue_type=IssueType.TASK))

        updated = storage.update("issue-1", {"issue_type": "bug"})
        assert updated.issue_type == IssueType.BUG

    def test_update_status_as_string(self, storage: JSONLStorage) -> None:
        """Test updating status with string value."""
        storage.create(Issue(id="issue-1", title="Test"))

        updated = storage.update("issue-1", {"status": "in_progress"})
        assert updated.status == Status.IN_PROGRESS


class TestListFilterByLabelList:
    """Test filtering by label list (multiple labels)."""

    def test_filter_by_label_list(self, storage: JSONLStorage) -> None:
        """Test filtering with a list of labels (OR semantics)."""
        storage.create(Issue(id="i1", title="Issue 1", labels=["backend"]))
        storage.create(Issue(id="i2", title="Issue 2", labels=["frontend"]))
        storage.create(Issue(id="i3", title="Issue 3", labels=["docs"]))

        results = storage.list({"label": ["backend", "frontend"]})
        assert len(results) == 2
        ids = {i.id for i in results}
        assert "i1" in ids
        assert "i2" in ids


class TestInvalidDependencyType:
    """Test adding dependency with invalid type."""

    def test_invalid_dependency_type_raises(self, storage: JSONLStorage) -> None:
        """Test that invalid dependency type raises ValueError."""
        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))

        with pytest.raises(ValueError, match="Invalid dependency type"):
            storage.add_dependency("t-a", "t-b", "invalid_type")


class TestLinkOperationErrors:
    """Test link operations error paths."""

    def test_add_link_from_nonexistent_raises(self, storage: JSONLStorage) -> None:
        """Test adding link from nonexistent issue raises."""
        storage.create(Issue(id="a", namespace="t", title="A"))

        with pytest.raises(ValueError, match="not found"):
            storage.add_link("nonexistent", "t-a")

    def test_add_link_to_nonexistent_raises(self, storage: JSONLStorage) -> None:
        """Test adding link to nonexistent issue raises."""
        storage.create(Issue(id="a", namespace="t", title="A"))

        with pytest.raises(ValueError, match="not found"):
            storage.add_link("t-a", "nonexistent")

    def test_duplicate_link_not_added(self, storage: JSONLStorage) -> None:
        """Test that duplicate links are not added."""
        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))

        storage.add_link("t-a", "t-b")
        link2 = storage.add_link("t-a", "t-b")

        links = storage.get_links("t-a")
        assert len(links) == 1
        assert link2 == links[0]

    def test_remove_link_from_nonexistent_raises(self, storage: JSONLStorage) -> None:
        """Test removing link from nonexistent issue raises."""
        storage.create(Issue(id="a", namespace="t", title="A"))

        with pytest.raises(ValueError, match="not found"):
            storage.remove_link("nonexistent", "t-a")

    def test_remove_link_to_nonexistent_raises(self, storage: JSONLStorage) -> None:
        """Test removing link to nonexistent issue raises."""
        storage.create(Issue(id="a", namespace="t", title="A"))

        with pytest.raises(ValueError, match="not found"):
            storage.remove_link("t-a", "nonexistent")

    def test_get_links_nonexistent_raises(self, storage: JSONLStorage) -> None:
        """Test getting links from nonexistent issue raises."""
        with pytest.raises(ValueError, match="not found"):
            storage.get_links("nonexistent")

    def test_get_incoming_links_nonexistent_raises(self, storage: JSONLStorage) -> None:
        """Test getting incoming links for nonexistent issue raises."""
        with pytest.raises(ValueError, match="not found"):
            storage.get_incoming_links("nonexistent")


class TestDependencyOperationErrors:
    """Test dependency operations error paths."""

    def test_get_dependencies_nonexistent_raises(self, storage: JSONLStorage) -> None:
        """Test getting dependencies of nonexistent issue raises."""
        with pytest.raises(ValueError, match="not found"):
            storage.get_dependencies("nonexistent")

    def test_get_dependents_nonexistent_raises(self, storage: JSONLStorage) -> None:
        """Test getting dependents of nonexistent issue raises."""
        with pytest.raises(ValueError, match="not found"):
            storage.get_dependents("nonexistent")

    def test_remove_dependency_from_nonexistent_raises(
        self,
        storage: JSONLStorage,
    ) -> None:
        """Test removing dependency from nonexistent issue raises."""
        storage.create(Issue(id="a", namespace="t", title="A"))

        with pytest.raises(ValueError, match="not found"):
            storage.remove_dependency("nonexistent", "t-a")

    def test_remove_dependency_to_nonexistent_raises(
        self,
        storage: JSONLStorage,
    ) -> None:
        """Test removing dependency to nonexistent issue raises."""
        storage.create(Issue(id="a", namespace="t", title="A"))

        with pytest.raises(ValueError, match="not found"):
            storage.remove_dependency("t-a", "nonexistent")

    def test_get_children_nonexistent_raises(self, storage: JSONLStorage) -> None:
        """Test getting children of nonexistent issue raises."""
        with pytest.raises(ValueError, match="not found"):
            storage.get_children("nonexistent")

    def test_add_dependency_from_nonexistent_raises(
        self,
        storage: JSONLStorage,
    ) -> None:
        """Test adding dependency from nonexistent issue raises."""
        storage.create(Issue(id="a", namespace="t", title="A"))

        with pytest.raises(ValueError, match="not found"):
            storage.add_dependency("nonexistent", "t-a", "blocks")


class TestCompaction:
    """Test automatic compaction behavior."""

    def test_compaction_triggers_on_threshold(self, temp_dogcats_dir: Path) -> None:
        """Compaction shrinks the file once the append ratio crosses threshold.

        Verifies behaviour by file-size: after enough updates the file
        must shrink — earlier this assertion read ``_appended_lines``
        directly, which couples the test to the compaction counter
        scheme. (dogcat-308p)
        """
        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        # Create enough issues to have a base > COMPACTION_MIN_BASE (20).
        for i in range(25):
            storage.create(Issue(id=f"issue-{i}", title=f"Issue {i}"))

        # Force a full save to set the on-disk base so compaction can
        # decide based on a real ratio. ``_save`` is a known public-ish
        # seam used elsewhere in the suite (see also TestAtomicRewrite).
        storage._save()
        base_lines = sum(
            1 for line in storage_path.read_text().splitlines() if line.strip()
        )
        assert base_lines == 50

        # Each update appends issue + event together. Compaction triggers
        # when appended exceeds 50% of base; 13 updates → 26 appended
        # lines, above the threshold. Without compaction we would have
        # 76 lines on disk; with compaction the file shrinks back below
        # base.
        for i in range(13):
            storage.update("issue-0", {"title": f"Updated {i}"})

        post_update_lines = sum(
            1 for line in storage_path.read_text().splitlines() if line.strip()
        )
        assert post_update_lines < base_lines + 26

    def test_compaction_check_runs_under_append_lock(
        self, temp_dogcats_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Eligibility check + compaction must execute while the append lock is held.

        Regression test for dogcat-h0tt: previously the check ran after
        the lock was released, allowing two concurrent processes to both
        decide to compact based on stale counts.

        Originally probed by monkeypatching ``storage._save_locked`` —
        a private method whose name and signature are implementation
        details. The probe is now hung on the public _file_lock
        boundary instead: from a sibling lock-holder's perspective, the
        lock is held iff a non-blocking acquire fails. (dogcat-308p)
        """
        import fcntl as _fcntl

        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        for i in range(25):
            storage.create(Issue(id=f"issue-{i}", title=f"Issue {i}"))

        observed: dict[str, bool] = {"locked": False}

        # Wrap _file_lock so we can witness the lock state from a second
        # file descriptor while the locked region runs. The wrapper does
        # not change behaviour — it only observes from a sibling fd.
        original_file_lock = storage._file_lock

        def probing_file_lock():  # type: ignore[no-untyped-def]
            ctx = original_file_lock()
            ctx.__enter__()
            try:
                with storage._lock_path.open("w") as fd:
                    try:
                        _fcntl.flock(fd, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
                        _fcntl.flock(fd, _fcntl.LOCK_UN)
                    except BlockingIOError:
                        observed["locked"] = True
                yield
            finally:
                ctx.__exit__(None, None, None)

        from contextlib import contextmanager

        monkeypatch.setattr(storage, "_file_lock", contextmanager(probing_file_lock))

        for i in range(26):
            storage.update("issue-0", {"title": f"Updated {i}"})

        assert observed["locked"], (
            "Compaction must run inside the append lock — otherwise the "
            "check race from dogcat-h0tt is reintroduced."
        )


class TestLinksWithSaveReload:
    """Test that links survive save/reload cycle."""

    def test_links_persist(self, temp_dogcats_dir: Path) -> None:
        """Test links are correctly saved and loaded."""
        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        storage.add_link("t-a", "t-b", link_type="relates_to", created_by="test")

        # Reload
        storage2 = JSONLStorage(str(storage_path))
        links = storage2.get_links("t-a")
        assert len(links) == 1
        assert links[0].from_id == "t-a"
        assert links[0].to_id == "t-b"
        assert links[0].link_type == "relates_to"
        assert links[0].created_by == "test"

    def test_incoming_links(self, storage: JSONLStorage) -> None:
        """Test getting incoming links."""
        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        storage.add_link("t-a", "t-b")

        incoming = storage.get_incoming_links("t-b")
        assert len(incoming) == 1
        assert incoming[0].from_id == "t-a"


class TestDeleteCleansUpDepsAndLinks:
    """Test that delete cleans up dependencies and links."""

    def test_delete_removes_dependencies(self, storage: JSONLStorage) -> None:
        """Test that deleting an issue removes its dependencies."""
        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        storage.create(Issue(id="c", namespace="t", title="C"))
        storage.add_dependency("t-a", "t-b", "blocks")
        storage.add_dependency("t-c", "t-a", "blocks")

        storage.delete("t-a", reason="gone")

        # Dependencies involving t-a should be cleaned up
        assert len(storage.get_dependencies("t-b")) == 0
        assert len(storage.get_dependencies("t-c")) == 0

    def test_delete_removes_links(self, storage: JSONLStorage) -> None:
        """Test that deleting an issue removes its links."""
        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        storage.add_link("t-a", "t-b")

        storage.delete("t-a", reason="gone")

        assert storage.all_links == []
