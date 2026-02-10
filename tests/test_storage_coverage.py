"""Additional storage tests to improve coverage on edge cases."""

from pathlib import Path

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
        """Test that compaction triggers when append ratio exceeds threshold."""
        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        # Create enough issues to have a base > COMPACTION_MIN_BASE (20)
        for i in range(25):
            storage.create(Issue(id=f"issue-{i}", title=f"Issue {i}"))

        # Force a full save to set base_lines
        # Each issue + event = 2 lines on disk, but _save() counts issues + deps +
        # links + events, so 25 issues + 25 events = 50 base lines
        storage._save()
        assert storage._base_lines == 50
        assert storage._appended_lines == 0

        # _append() only counts issue records (not event log records written
        # separately by EventLog.append), so each update adds 1 to _appended_lines.
        # Compaction triggers when _appended_lines > base_lines * 0.5 = 25,
        # so we need 26 updates.
        for i in range(26):
            storage.update("issue-0", {"title": f"Updated {i}"})

        # Compaction should have triggered, resetting appended_lines
        assert storage._appended_lines == 0


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

        assert len(storage._links) == 0
