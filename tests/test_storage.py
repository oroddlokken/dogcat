"""Tests for JSONL storage module."""

import json
from pathlib import Path

import pytest

from dogcat.models import DependencyType, Issue, IssueType, Status
from dogcat.storage import JSONLStorage


@pytest.fixture
def storage(temp_dogcats_dir: Path) -> JSONLStorage:
    """Create a storage instance with temporary directory."""
    storage_path = temp_dogcats_dir / "issues.jsonl"
    return JSONLStorage(str(storage_path), create_dir=True)


class TestStorageInitialization:
    """Test storage initialization."""

    def test_storage_fails_without_directory(self, temp_workspace: Path) -> None:
        """Test that storage fails if directory doesn't exist and create_dir=False."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        with pytest.raises(ValueError, match="does not exist"):
            JSONLStorage(str(storage_path))

    def test_storage_creates_directory_with_flag(self, temp_workspace: Path) -> None:
        """Test that storage creates directory when create_dir=True."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        JSONLStorage(str(storage_path), create_dir=True)

        assert storage_path.parent.exists()
        assert storage_path.parent.is_dir()

    def test_storage_creates_issues_file(self, temp_workspace: Path) -> None:
        """Test that storage creates issues.jsonl file."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        # Create an issue to trigger save
        issue = Issue(id="test-1", title="Test")
        storage.create(issue)

        assert storage_path.exists()

    def test_storage_loads_existing_issues(self, temp_workspace: Path) -> None:
        """Test that storage loads existing issues from file."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"

        # Create storage and add issue
        storage1 = JSONLStorage(str(storage_path), create_dir=True)
        issue1 = Issue(id="test-1", title="Test Issue")
        storage1.create(issue1)

        # Create new storage instance pointing to same file (dir exists now)
        storage2 = JSONLStorage(str(storage_path))

        # Should load the existing issue
        assert storage2.get("test-1") is not None


class TestCRUDOperations:
    """Test CRUD operations."""

    def test_create_issue(self, storage: JSONLStorage) -> None:
        """Test creating an issue."""
        issue = Issue(id="issue-1", title="Test Issue")
        created = storage.create(issue)

        assert created.id == "issue-1"
        assert created.title == "Test Issue"

    def test_create_duplicate_id_raises(self, storage: JSONLStorage) -> None:
        """Test that creating issue with duplicate ID raises."""
        issue1 = Issue(id="issue-1", title="Test 1")
        storage.create(issue1)

        issue2 = Issue(id="issue-1", title="Test 2")
        with pytest.raises(ValueError, match="already exists"):
            storage.create(issue2)

    def test_create_empty_title_raises(self, storage: JSONLStorage) -> None:
        """Test that creating issue without title raises."""
        issue = Issue(id="issue-1", title="")
        with pytest.raises(ValueError, match="must have a non-empty title"):
            storage.create(issue)

    def test_get_issue(self, storage: JSONLStorage) -> None:
        """Test getting an issue by ID."""
        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)

        retrieved = storage.get("issue-1")
        assert retrieved is not None
        assert retrieved.id == "issue-1"
        assert retrieved.title == "Test"

    def test_get_nonexistent_issue(self, storage: JSONLStorage) -> None:
        """Test that getting nonexistent issue returns None."""
        result = storage.get("nonexistent")
        assert result is None

    def test_list_all_issues(self, storage: JSONLStorage) -> None:
        """Test listing all issues."""
        for i in range(3):
            issue = Issue(id=f"issue-{i}", title=f"Test {i}")
            storage.create(issue)

        issues = storage.list()
        assert len(issues) == 3

    def test_list_filter_by_status(self, storage: JSONLStorage) -> None:
        """Test filtering issues by status."""
        issue1 = Issue(id="issue-1", title="Open", status=Status.OPEN)
        issue2 = Issue(id="issue-2", title="Closed", status=Status.CLOSED)
        storage.create(issue1)
        storage.create(issue2)

        open_issues = storage.list({"status": "open"})
        assert len(open_issues) == 1
        assert open_issues[0].id == "issue-1"

    def test_list_filter_by_priority(self, storage: JSONLStorage) -> None:
        """Test filtering issues by priority."""
        issue1 = Issue(id="issue-1", title="High", priority=0)
        issue2 = Issue(id="issue-2", title="Medium", priority=2)
        storage.create(issue1)
        storage.create(issue2)

        high_priority = storage.list({"priority": 0})
        assert len(high_priority) == 1
        assert high_priority[0].id == "issue-1"

    def test_list_filter_by_type(self, storage: JSONLStorage) -> None:
        """Test filtering issues by type."""
        issue1 = Issue(id="issue-1", title="Bug", issue_type=IssueType.BUG)
        issue2 = Issue(id="issue-2", title="Feature", issue_type=IssueType.FEATURE)
        storage.create(issue1)
        storage.create(issue2)

        bugs = storage.list({"type": "bug"})
        assert len(bugs) == 1
        assert bugs[0].id == "issue-1"

    def test_list_filter_by_label(self, storage: JSONLStorage) -> None:
        """Test filtering issues by label."""
        issue1 = Issue(id="issue-1", title="Test", labels=["urgent", "bug"])
        issue2 = Issue(id="issue-2", title="Test", labels=["feature"])
        storage.create(issue1)
        storage.create(issue2)

        urgent = storage.list({"label": "urgent"})
        assert len(urgent) == 1
        assert urgent[0].id == "issue-1"

    def test_list_filter_by_owner(self, storage: JSONLStorage) -> None:
        """Test filtering issues by owner."""
        issue1 = Issue(id="issue-1", title="Test", owner="user1@example.com")
        issue2 = Issue(id="issue-2", title="Test", owner="user2@example.com")
        storage.create(issue1)
        storage.create(issue2)

        user1_issues = storage.list({"owner": "user1@example.com"})
        assert len(user1_issues) == 1
        assert user1_issues[0].id == "issue-1"

    def test_update_issue(self, storage: JSONLStorage) -> None:
        """Test updating an issue."""
        issue = Issue(id="issue-1", title="Original")
        storage.create(issue)

        updated = storage.update("issue-1", {"title": "Updated"})
        assert updated.title == "Updated"

        retrieved = storage.get("issue-1")
        assert retrieved is not None
        assert retrieved.title == "Updated"

    def test_update_nonexistent_issue_raises(self, storage: JSONLStorage) -> None:
        """Test that updating nonexistent issue raises."""
        with pytest.raises(ValueError, match="not found"):
            storage.update("nonexistent", {"title": "New"})

    def test_update_timestamp_changes(self, storage: JSONLStorage) -> None:
        """Test that update changes updated_at timestamp."""
        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)
        original_issue = storage.get("issue-1")
        assert original_issue is not None
        original_time = original_issue.updated_at

        # Wait a moment and update
        import time

        time.sleep(0.01)
        storage.update("issue-1", {"title": "Updated"})

        updated_issue = storage.get("issue-1")
        assert updated_issue is not None
        new_time = updated_issue.updated_at
        assert new_time > original_time

    def test_close_issue(self, storage: JSONLStorage) -> None:
        """Test closing an issue."""
        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)

        closed = storage.close("issue-1", reason="Fixed")
        assert closed.status == Status.CLOSED
        assert closed.closed_at is not None

    def test_close_nonexistent_issue_raises(self, storage: JSONLStorage) -> None:
        """Test that closing nonexistent issue raises."""
        with pytest.raises(ValueError, match="not found"):
            storage.close("nonexistent")

    def test_delete_issue_creates_tombstone(self, storage: JSONLStorage) -> None:
        """Test that deleting an issue creates a tombstone."""
        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)

        deleted = storage.delete("issue-1", reason="Duplicate")
        assert deleted.status == Status.TOMBSTONE
        assert deleted.deleted_at is not None
        assert deleted.delete_reason == "Duplicate"

    def test_delete_nonexistent_issue_raises(self, storage: JSONLStorage) -> None:
        """Test that deleting nonexistent issue raises."""
        with pytest.raises(ValueError, match="not found"):
            storage.delete("nonexistent")


class TestDependencies:
    """Test dependency management."""

    def test_add_dependency(self, storage: JSONLStorage) -> None:
        """Test adding a dependency."""
        issue1 = Issue(id="1", namespace="test", title="Test 1")
        issue2 = Issue(id="2", namespace="test", title="Test 2")
        storage.create(issue1)
        storage.create(issue2)

        dep = storage.add_dependency("test-1", "test-2", "blocks")
        assert dep.issue_id == "test-1"
        assert dep.depends_on_id == "test-2"
        assert dep.dep_type == DependencyType.BLOCKS

    def test_add_dependency_nonexistent_issue_raises(
        self,
        storage: JSONLStorage,
    ) -> None:
        """Test that adding dependency to nonexistent issue raises."""
        issue1 = Issue(id="1", namespace="test", title="Test 1")
        storage.create(issue1)

        with pytest.raises(ValueError, match="not found"):
            storage.add_dependency("test-1", "nonexistent", "blocks")

    def test_get_dependencies(self, storage: JSONLStorage) -> None:
        """Test getting dependencies of an issue."""
        issue1 = Issue(id="1", namespace="test", title="Test 1")
        issue2 = Issue(id="2", namespace="test", title="Test 2")
        issue3 = Issue(id="3", namespace="test", title="Test 3")
        storage.create(issue1)
        storage.create(issue2)
        storage.create(issue3)

        storage.add_dependency("test-1", "test-2", "blocks")
        storage.add_dependency("test-1", "test-3", "blocks")

        deps = storage.get_dependencies("test-1")
        assert len(deps) == 2
        assert all(d.issue_id == "test-1" for d in deps)

    def test_get_dependents(self, storage: JSONLStorage) -> None:
        """Test getting issues that depend on this one."""
        issue1 = Issue(id="1", namespace="test", title="Test 1")
        issue2 = Issue(id="2", namespace="test", title="Test 2")
        issue3 = Issue(id="3", namespace="test", title="Test 3")
        storage.create(issue1)
        storage.create(issue2)
        storage.create(issue3)

        storage.add_dependency("test-2", "test-1", "blocks")
        storage.add_dependency("test-3", "test-1", "blocks")

        dependents = storage.get_dependents("test-1")
        assert len(dependents) == 2
        assert all(d.depends_on_id == "test-1" for d in dependents)

    def test_remove_dependency(self, storage: JSONLStorage) -> None:
        """Test removing a dependency."""
        issue1 = Issue(id="1", namespace="test", title="Test 1")
        issue2 = Issue(id="2", namespace="test", title="Test 2")
        storage.create(issue1)
        storage.create(issue2)

        storage.add_dependency("test-1", "test-2", "blocks")
        assert len(storage.get_dependencies("test-1")) == 1

        storage.remove_dependency("test-1", "test-2")
        assert len(storage.get_dependencies("test-1")) == 0

    def test_duplicate_dependency_not_added(self, storage: JSONLStorage) -> None:
        """Test that duplicate dependencies are not added."""
        issue1 = Issue(id="1", namespace="test", title="Test 1")
        issue2 = Issue(id="2", namespace="test", title="Test 2")
        storage.create(issue1)
        storage.create(issue2)

        storage.add_dependency("test-1", "test-2", "blocks")
        storage.add_dependency("test-1", "test-2", "blocks")

        deps = storage.get_dependencies("test-1")
        assert len(deps) == 1


class TestAtomicWrites:
    """Test atomic write operations."""

    def test_save_creates_valid_jsonl(self, temp_workspace: Path) -> None:
        """Test that save creates valid JSONL file."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)

        # Read the file and verify each line is valid JSON
        with storage_path.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    json.loads(line)  # Should not raise

    def test_persistence_across_instances(self, temp_workspace: Path) -> None:
        """Test that data persists across storage instances."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"

        storage1 = JSONLStorage(str(storage_path), create_dir=True)
        issue = Issue(id="issue-1", title="Test")
        storage1.create(issue)

        # Create new instance (dir exists now)
        storage2 = JSONLStorage(str(storage_path))
        retrieved = storage2.get("issue-1")

        assert retrieved is not None
        assert retrieved.title == "Test"


class TestErrorHandling:
    """Test error handling."""

    def test_corrupted_jsonl_file_raises(self, temp_workspace: Path) -> None:
        """Test that corrupted JSONL raises error."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage_path.parent.mkdir(parents=True, exist_ok=True)

        # Write invalid JSON
        storage_path.write_text("invalid json line\n")

        with pytest.raises(ValueError, match="Invalid JSONL"):
            JSONLStorage(str(storage_path))

    def test_empty_jsonl_file_ok(self, temp_workspace: Path) -> None:
        """Test that empty JSONL file is handled gracefully."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        # Should not raise
        issues = storage.list()
        assert len(issues) == 0


class TestLargeDataset:
    """Test with large datasets."""

    def test_many_issues(self, storage: JSONLStorage) -> None:
        """Test creating and retrieving many issues."""
        count = 100
        for i in range(count):
            issue = Issue(id=f"issue-{i}", title=f"Issue {i}")
            storage.create(issue)

        # Verify all were stored
        issues = storage.list()
        assert len(issues) == count

        # Verify retrieval works
        issue_50 = storage.get("issue-50")
        assert issue_50 is not None
        assert issue_50.title == "Issue 50"

    def test_many_dependencies(self, storage: JSONLStorage) -> None:
        """Test creating many dependencies."""
        # Create issues
        for i in range(10):
            issue = Issue(id=f"issue-{i}", title=f"Issue {i}")
            storage.create(issue)

        # Create dependencies
        dep_count = 0
        for i in range(1, 10):
            storage.add_dependency("issue-0", f"issue-{i}", "blocks")
            dep_count += 1

        # Verify
        deps = storage.get_dependencies("issue-0")
        assert len(deps) == dep_count


class TestParentChildRelationships:
    """Test parent-child issue relationships."""

    def test_get_children(self, storage: JSONLStorage) -> None:
        """Test getting child issues of a parent."""
        parent = Issue(id="p1", namespace="test", title="Parent Issue")
        child1 = Issue(
            id="c1",
            namespace="test",
            title="Child Issue 1",
            parent="test-p1",
        )
        child2 = Issue(
            id="c2",
            namespace="test",
            title="Child Issue 2",
            parent="test-p1",
        )
        orphan = Issue(id="o1", namespace="test", title="Orphan Issue")

        storage.create(parent)
        storage.create(child1)
        storage.create(child2)
        storage.create(orphan)

        children = storage.get_children("test-p1")
        assert len(children) == 2
        assert all(c.parent == "test-p1" for c in children)
        child_ids = {c.full_id for c in children}
        assert child_ids == {"test-c1", "test-c2"}

    def test_get_children_no_children(self, storage: JSONLStorage) -> None:
        """Test get_children returns empty list when no children exist."""
        parent = Issue(id="p1", namespace="test", title="Parent Issue")
        storage.create(parent)

        children = storage.get_children("test-p1")
        assert len(children) == 0

    def test_get_children_with_partial_id(self, storage: JSONLStorage) -> None:
        """Test get_children works with partial ID resolution."""
        parent = Issue(id="parent", namespace="dc", title="Parent Issue")
        child = Issue(
            id="child",
            namespace="dc",
            title="Child Issue",
            parent="dc-parent",
        )

        storage.create(parent)
        storage.create(child)

        # Use partial ID (just the hash part)
        children = storage.get_children("parent")
        assert len(children) == 1
        assert children[0].full_id == "dc-child"


class TestUpdateFieldAllowlist:
    """Test that update() only modifies allowed fields."""

    def test_update_allowed_field(self, storage: JSONLStorage) -> None:
        """Test that allowed fields can be updated."""
        issue = Issue(id="issue-1", title="Original")
        storage.create(issue)

        updated = storage.update("issue-1", {"title": "Updated"})
        assert updated.title == "Updated"

    def test_update_ignores_id(self, storage: JSONLStorage) -> None:
        """Test that update() cannot overwrite the id field."""
        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)

        storage.update("issue-1", {"id": "hacked"})
        retrieved = storage.get("issue-1")
        assert retrieved is not None
        assert retrieved.id == "issue-1"

    def test_update_ignores_namespace(self, storage: JSONLStorage) -> None:
        """Test that update() cannot overwrite the namespace field."""
        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)

        storage.update("issue-1", {"namespace": "evil"})
        retrieved = storage.get("issue-1")
        assert retrieved is not None
        assert retrieved.namespace == "dc"

    def test_update_ignores_created_at(self, storage: JSONLStorage) -> None:
        """Test that update() cannot overwrite created_at."""
        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)
        original_created_at = issue.created_at

        from datetime import datetime

        storage.update("issue-1", {"created_at": datetime(2000, 1, 1).astimezone()})
        retrieved = storage.get("issue-1")
        assert retrieved is not None
        assert retrieved.created_at == original_created_at

    def test_update_ignores_comments(self, storage: JSONLStorage) -> None:
        """Test that update() cannot overwrite comments."""
        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)

        storage.update("issue-1", {"comments": [{"fake": "comment"}]})
        retrieved = storage.get("issue-1")
        assert retrieved is not None
        assert retrieved.comments == []


class TestCloseReasonField:
    """Test that close reason uses a dedicated field instead of notes."""

    def test_close_sets_close_reason(self, storage: JSONLStorage) -> None:
        """Test that closing with a reason sets the close_reason field."""
        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)

        closed = storage.close("issue-1", reason="Fixed the bug")
        assert closed.close_reason == "Fixed the bug"

    def test_close_does_not_embed_reason_in_notes(self, storage: JSONLStorage) -> None:
        """Test that closing does not embed the reason in notes."""
        issue = Issue(id="issue-1", title="Test", notes="Some notes")
        storage.create(issue)

        closed = storage.close("issue-1", reason="Fixed")
        assert closed.notes == "Some notes"
        assert "Closed:" not in (closed.notes or "")

    def test_close_without_reason(self, storage: JSONLStorage) -> None:
        """Test closing without a reason leaves close_reason as None."""
        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)

        closed = storage.close("issue-1")
        assert closed.close_reason is None

    def test_close_reason_persists(self, temp_workspace: Path) -> None:
        """Test that close_reason survives save/load cycle."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)
        storage.close("issue-1", reason="Done")

        # Reload from disk
        storage2 = JSONLStorage(str(storage_path))
        loaded = storage2.get("issue-1")
        assert loaded is not None
        assert loaded.close_reason == "Done"

    def test_legacy_close_reason_migrated_from_notes(
        self,
    ) -> None:
        """Test that old issues with close reason in notes are migrated."""
        from dogcat.models import _migrate_close_reason, _migrate_notes

        notes = "User notes\n\nClosed: Legacy reason"
        assert _migrate_close_reason(notes, None) == "Legacy reason"
        assert _migrate_notes(notes, None) == "User notes"

    def test_migration_preserves_existing_close_reason(self) -> None:
        """Test that migration does not overwrite existing close_reason."""
        from dogcat.models import _migrate_close_reason, _migrate_notes

        notes = "Notes with\n\nClosed: something"
        assert _migrate_close_reason(notes, "Real reason") == "Real reason"
        assert _migrate_notes(notes, "Real reason") == notes


class TestCloseDeleteUpdatedAt:
    """Test that close() and delete() set updated_at."""

    def test_close_sets_updated_at(self, storage: JSONLStorage) -> None:
        """Test that close() updates the updated_at timestamp."""
        import time

        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)
        original_time = issue.updated_at

        time.sleep(0.01)
        closed = storage.close("issue-1", reason="Done")
        assert closed.updated_at > original_time
        assert closed.updated_at >= closed.closed_at

    def test_delete_sets_updated_at(self, storage: JSONLStorage) -> None:
        """Test that delete() updates the updated_at timestamp."""
        import time

        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)
        original_time = issue.updated_at

        time.sleep(0.01)
        deleted = storage.delete("issue-1", reason="Dup")
        assert deleted.updated_at > original_time
        assert deleted.updated_at >= deleted.deleted_at


class TestAppendOnlyStorage:
    """Test that mutations append instead of rewriting the entire file."""

    def test_create_appends_single_line(self, temp_workspace: Path) -> None:
        """Test that creating an issue appends one line rather than rewriting."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        storage.create(Issue(id="issue-1", title="First"))
        lines_after_first = _count_lines(storage_path)

        storage.create(Issue(id="issue-2", title="Second"))
        lines_after_second = _count_lines(storage_path)

        # Should have added exactly one line
        assert lines_after_second == lines_after_first + 1

    def test_update_appends_single_line(self, temp_workspace: Path) -> None:
        """Test that updating an issue appends one line."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        storage.create(Issue(id="issue-1", title="Original"))
        lines_before = _count_lines(storage_path)

        storage.update("issue-1", {"title": "Updated"})
        lines_after = _count_lines(storage_path)

        assert lines_after == lines_before + 1

    def test_update_persists_through_reload(self, temp_workspace: Path) -> None:
        """Test that appended updates are correctly loaded by a new instance."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        storage.create(Issue(id="issue-1", title="Original"))
        storage.update("issue-1", {"title": "Updated"})

        # Reload from disk
        storage2 = JSONLStorage(str(storage_path))
        loaded = storage2.get("issue-1")
        assert loaded is not None
        assert loaded.title == "Updated"

    def test_add_dependency_appends(self, temp_workspace: Path) -> None:
        """Test that adding a dependency appends one line."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        lines_before = _count_lines(storage_path)

        storage.add_dependency("t-a", "t-b", "blocks")
        lines_after = _count_lines(storage_path)

        assert lines_after == lines_before + 1

    def test_remove_dependency_appends_removal(self, temp_workspace: Path) -> None:
        """Test that removing a dep appends a removal record and reloads correctly."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        storage.add_dependency("t-a", "t-b", "blocks")
        assert len(storage.get_dependencies("t-a")) == 1

        storage.remove_dependency("t-a", "t-b")
        assert len(storage.get_dependencies("t-a")) == 0

        # Reload and verify removal is persisted
        storage2 = JSONLStorage(str(storage_path))
        assert len(storage2.get_dependencies("t-a")) == 0

    def test_add_link_appends(self, temp_workspace: Path) -> None:
        """Test that adding a link appends one line."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        lines_before = _count_lines(storage_path)

        storage.add_link("t-a", "t-b")
        lines_after = _count_lines(storage_path)

        assert lines_after == lines_before + 1

    def test_remove_link_appends_removal(self, temp_workspace: Path) -> None:
        """Test that removing a link appends a removal record and reloads correctly."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        storage.add_link("t-a", "t-b")
        assert len(storage.get_links("t-a")) == 1

        storage.remove_link("t-a", "t-b")
        assert len(storage.get_links("t-a")) == 0

        # Reload and verify removal is persisted
        storage2 = JSONLStorage(str(storage_path))
        assert len(storage2.get_links("t-a")) == 0

    def test_compaction_reduces_file_size(self, temp_workspace: Path) -> None:
        """Test that compaction eliminates superseded records."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        # Create an issue and update it several times
        storage.create(Issue(id="issue-1", title="v0"))
        for i in range(1, 6):
            storage.update("issue-1", {"title": f"v{i}"})

        # File should have 1 + 5 = 6 lines (original + 5 updates)
        assert _count_lines(storage_path) == 6

        # Force compaction
        storage._save()

        # After compaction, only 1 line (current state)
        assert _count_lines(storage_path) == 1

        # Data still correct after compaction
        storage2 = JSONLStorage(str(storage_path))
        loaded = storage2.get("issue-1")
        assert loaded is not None
        assert loaded.title == "v5"


def _count_lines(path: Path) -> int:
    """Count non-empty lines in a file."""
    with path.open() as f:
        return sum(1 for line in f if line.strip())
