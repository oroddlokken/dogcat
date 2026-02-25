"""Tests for JSONL storage module."""

import json
from pathlib import Path

import orjson
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

        # Read the file and verify each line is valid JSON with expected structure
        records: list[dict[str, object]] = []
        with storage_path.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))

        assert len(records) >= 1
        assert any(r.get("id") == "issue-1" for r in records)
        assert any(r.get("title") == "Test" for r in records)

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

    def test_corrupted_jsonl_middle_line_raises(self, temp_workspace: Path) -> None:
        """Test that a corrupted non-last line raises error."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage_path.parent.mkdir(parents=True, exist_ok=True)

        # Valid first line, corrupt second, valid third
        import orjson

        from dogcat.models import issue_to_dict

        valid = orjson.dumps(issue_to_dict(Issue(id="ok", title="OK"))).decode()
        storage_path.write_text(f"{valid}\ninvalid json line\n{valid}\n")

        with pytest.raises(ValueError, match="Invalid JSONL record at line 2"):
            JSONLStorage(str(storage_path))

    def test_corrupted_last_line_tolerated(self, temp_workspace: Path) -> None:
        """Test that a corrupted last line is tolerated (crash recovery)."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage_path.parent.mkdir(parents=True, exist_ok=True)

        import orjson

        from dogcat.models import issue_to_dict

        valid = orjson.dumps(issue_to_dict(Issue(id="ok", title="OK"))).decode()
        storage_path.write_text(f"{valid}\ntruncated garbage")

        # Should NOT raise — malformed last line is skipped
        s = JSONLStorage(str(storage_path))
        issues = s.list()
        assert len(issues) == 1
        assert issues[0].title == "OK"

    def test_corrupted_only_line_tolerated(self, temp_workspace: Path) -> None:
        """Test that a single corrupt line (only line) is tolerated."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage_path.parent.mkdir(parents=True, exist_ok=True)

        storage_path.write_text("invalid json line\n")

        # Single corrupt line is the last line — tolerated
        s = JSONLStorage(str(storage_path))
        assert len(s.list()) == 0

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


class TestChildrenByParentIndex:
    """Test the _children_by_parent index is maintained correctly."""

    def test_index_populated_on_create(self, storage: JSONLStorage) -> None:
        """Test index is updated when creating issues with a parent."""
        parent = Issue(id="p1", namespace="test", title="Parent")
        child = Issue(id="c1", namespace="test", title="Child", parent="test-p1")
        storage.create(parent)
        storage.create(child)

        assert "test-c1" in storage._children_by_parent.get("test-p1", [])

    def test_index_updated_on_reparent(self, storage: JSONLStorage) -> None:
        """Test index is updated when an issue's parent changes."""
        p1 = Issue(id="p1", namespace="test", title="Parent 1")
        p2 = Issue(id="p2", namespace="test", title="Parent 2")
        child = Issue(id="c1", namespace="test", title="Child", parent="test-p1")
        storage.create(p1)
        storage.create(p2)
        storage.create(child)

        storage.update("test-c1", {"parent": "test-p2"})

        assert "test-c1" not in storage._children_by_parent.get("test-p1", [])
        assert "test-c1" in storage._children_by_parent.get("test-p2", [])

    def test_index_updated_on_parent_removed(self, storage: JSONLStorage) -> None:
        """Test index is updated when parent is set to None."""
        parent = Issue(id="p1", namespace="test", title="Parent")
        child = Issue(id="c1", namespace="test", title="Child", parent="test-p1")
        storage.create(parent)
        storage.create(child)

        storage.update("test-c1", {"parent": None})

        assert storage._children_by_parent.get("test-p1", []) == []

    def test_index_survives_reload(self, storage: JSONLStorage) -> None:
        """Test index is rebuilt correctly after reload."""
        parent = Issue(id="p1", namespace="test", title="Parent")
        child = Issue(id="c1", namespace="test", title="Child", parent="test-p1")
        storage.create(parent)
        storage.create(child)

        storage.reload()

        children = storage.get_children("test-p1")
        assert len(children) == 1
        assert children[0].full_id == "test-c1"
        assert "test-c1" in storage._children_by_parent["test-p1"]

    def test_index_empty_for_no_children(self, storage: JSONLStorage) -> None:
        """Test index has no entry for issues without children."""
        issue = Issue(id="p1", namespace="test", title="No children")
        storage.create(issue)

        assert "test-p1" not in storage._children_by_parent


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

    def test_update_allows_comments(self, storage: JSONLStorage) -> None:
        """Test that update() can set comments via UPDATABLE_FIELDS."""
        from dogcat.models import Comment

        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)

        comment = Comment(id="c1", issue_id="issue-1", author="alice", text="hello")
        storage.update("issue-1", {"comments": [comment]})
        retrieved = storage.get("issue-1")
        assert retrieved is not None
        assert len(retrieved.comments) == 1
        assert retrieved.comments[0].text == "hello"


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
        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)
        original_time = issue.updated_at

        closed = storage.close("issue-1", reason="Done")
        assert closed.updated_at > original_time
        assert closed.closed_at is not None
        assert closed.updated_at >= closed.closed_at

    def test_delete_sets_updated_at(self, storage: JSONLStorage) -> None:
        """Test that delete() updates the updated_at timestamp."""
        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)
        original_time = issue.updated_at

        deleted = storage.delete("issue-1", reason="Dup")
        assert deleted.updated_at > original_time
        assert deleted.deleted_at is not None
        assert deleted.updated_at >= deleted.deleted_at


class TestCloseDeleteOperator:
    """Test that close() and delete() accept operator parameters."""

    def test_close_sets_closed_by(self, storage: JSONLStorage) -> None:
        """Test that close() sets closed_by when provided."""
        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)

        closed = storage.close("issue-1", reason="Done", closed_by="alice")
        assert closed.closed_by == "alice"

    def test_close_without_closed_by(self, storage: JSONLStorage) -> None:
        """Test that close() leaves closed_by as None when not provided."""
        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)

        closed = storage.close("issue-1", reason="Done")
        assert closed.closed_by is None

    def test_delete_sets_deleted_by(self, storage: JSONLStorage) -> None:
        """Test that delete() sets deleted_by when provided."""
        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)

        deleted = storage.delete("issue-1", reason="Dup", deleted_by="bob")
        assert deleted.deleted_by == "bob"

    def test_delete_without_deleted_by(self, storage: JSONLStorage) -> None:
        """Test that delete() leaves deleted_by as None when not provided."""
        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)

        deleted = storage.delete("issue-1", reason="Dup")
        assert deleted.deleted_by is None

    def test_close_with_closed_by_persists(self, temp_workspace: Path) -> None:
        """Test that closed_by survives save/load cycle."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)
        storage.close("issue-1", reason="Done", closed_by="alice")

        storage2 = JSONLStorage(str(storage_path))
        loaded = storage2.get("issue-1")
        assert loaded is not None
        assert loaded.closed_by == "alice"

    def test_close_writes_single_event(self, temp_workspace: Path) -> None:
        """Test that close with closed_by writes one issue record + one event record."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)

        lines_before = storage_path.read_text().strip().count("\n") + 1
        storage.close("issue-1", reason="Done", closed_by="alice")
        lines_after = storage_path.read_text().strip().count("\n") + 1

        # Each close appends 2 lines: issue record + event record
        assert lines_after - lines_before == 2

    def test_delete_includes_deleted_by_in_tombstone_record(
        self,
        temp_workspace: Path,
    ) -> None:
        """Test that delete with deleted_by includes it in the tombstone record."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)
        storage.delete("issue-1", reason="Dup", deleted_by="bob")

        # Delete is append-only: the last issue record should be the tombstone
        import orjson

        lines = storage_path.read_text().strip().split("\n")
        issue_records = [
            orjson.loads(line)
            for line in lines
            if orjson.loads(line).get("id") == "issue-1"
        ]
        assert len(issue_records) >= 1
        # Last-write-wins: the final record is the tombstone
        tombstone = issue_records[-1]
        assert tombstone["deleted_by"] == "bob"
        assert tombstone["status"] == "tombstone"


class TestAppendOnlyStorage:
    """Test that mutations append instead of rewriting the entire file."""

    def test_create_appends_single_line(self, temp_workspace: Path) -> None:
        """Test that creating an issue appends lines rather than rewriting."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        storage.create(Issue(id="issue-1", title="First"))
        lines_after_first = _count_lines(storage_path)

        storage.create(Issue(id="issue-2", title="Second"))
        lines_after_second = _count_lines(storage_path)

        # Each create appends 2 lines: issue record + event record
        assert lines_after_second == lines_after_first + 2

    def test_update_appends_single_line(self, temp_workspace: Path) -> None:
        """Test that updating an issue appends lines."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        storage.create(Issue(id="issue-1", title="Original"))
        lines_before = _count_lines(storage_path)

        storage.update("issue-1", {"title": "Updated"})
        lines_after = _count_lines(storage_path)

        # Each update appends 2 lines: issue record + event record
        assert lines_after == lines_before + 2

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

        # Each op appends 2 lines (issue + event): 1 create + 5 updates = 12
        assert _count_lines(storage_path) == 12

        # Force compaction
        storage._save()

        # After compaction: 1 issue line + 6 preserved event records = 7 lines
        assert _count_lines(storage_path) == 7

        # Data still correct after compaction
        storage2 = JSONLStorage(str(storage_path))
        loaded = storage2.get("issue-1")
        assert loaded is not None
        assert loaded.title == "v5"


class TestUpdatableFieldsAllowlist:
    """Test that storage.update() enforces UPDATABLE_FIELDS allowlist."""

    def test_disallowed_field_is_ignored(self, storage: JSONLStorage) -> None:
        """Fields not in UPDATABLE_FIELDS are silently skipped."""
        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)

        original_id = issue.id
        storage.update("issue-1", {"id": "hacked", "title": "Updated"})

        retrieved = storage.get("issue-1")
        assert retrieved is not None
        assert retrieved.id == original_id
        assert retrieved.title == "Updated"

    def test_comments_in_updatable_fields(self, storage: JSONLStorage) -> None:
        """Comments field is in UPDATABLE_FIELDS and can be updated."""
        from dogcat.models import Comment

        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)

        comment = Comment(id="c1", issue_id="issue-1", author="alice", text="hello")
        storage.update("issue-1", {"comments": [comment]})

        retrieved = storage.get("issue-1")
        assert retrieved is not None
        assert len(retrieved.comments) == 1
        assert retrieved.comments[0].text == "hello"

    def test_updated_by_in_updatable_fields(self, storage: JSONLStorage) -> None:
        """updated_by field is in UPDATABLE_FIELDS and gets persisted."""
        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)

        storage.update("issue-1", {"status": "in_progress", "updated_by": "alice"})

        retrieved = storage.get("issue-1")
        assert retrieved is not None
        assert retrieved.updated_by == "alice"
        assert retrieved.status == Status.IN_PROGRESS


class TestRemoveArchived:
    """Test remove_archived() method."""

    def test_remove_archived_removes_issues(self, storage: JSONLStorage) -> None:
        """Test that archived issue IDs are removed from _issues."""
        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        storage.create(Issue(id="c", namespace="t", title="C"))

        storage.remove_archived({"t-a", "t-c"}, remaining_lines=1)

        assert storage.get("t-a") is None
        assert storage.get("t-b") is not None
        assert storage.get("t-c") is None

    def test_remove_archived_filters_dependencies_both_archived(
        self,
        storage: JSONLStorage,
    ) -> None:
        """Test that deps are removed when both sides are archived."""
        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        storage.create(Issue(id="c", namespace="t", title="C"))
        storage.add_dependency("t-a", "t-b", "blocks")
        storage.add_dependency("t-b", "t-c", "blocks")

        # Archive both a and b; dep t-a -> t-b should be filtered
        # (both issue_id AND depends_on_id are in archived_ids)
        storage.remove_archived({"t-a", "t-b"}, remaining_lines=1)

        # Only t-b -> t-c dep remains (t-b is archived but t-c is not)
        remaining_deps = storage.all_dependencies
        assert len(remaining_deps) == 1
        assert remaining_deps[0].issue_id == "t-b"
        assert remaining_deps[0].depends_on_id == "t-c"

    def test_remove_archived_keeps_deps_with_one_non_archived(
        self,
        storage: JSONLStorage,
    ) -> None:
        """Test that deps are kept when only one side is archived."""
        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        storage.add_dependency("t-a", "t-b", "blocks")

        # Archive only a; dep should remain because t-b is not archived
        storage.remove_archived({"t-a"}, remaining_lines=1)

        remaining_deps = storage.all_dependencies
        assert len(remaining_deps) == 1

    def test_remove_archived_filters_links_both_archived(
        self,
        storage: JSONLStorage,
    ) -> None:
        """Test that links are removed when both sides are archived."""
        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        storage.create(Issue(id="c", namespace="t", title="C"))
        storage.add_link("t-a", "t-b")
        storage.add_link("t-b", "t-c")

        # Archive both a and b; link t-a -> t-b should be filtered
        storage.remove_archived({"t-a", "t-b"}, remaining_lines=1)

        remaining_links = storage.all_links
        assert len(remaining_links) == 1
        assert remaining_links[0].from_id == "t-b"
        assert remaining_links[0].to_id == "t-c"

    def test_remove_archived_keeps_links_with_one_non_archived(
        self,
        storage: JSONLStorage,
    ) -> None:
        """Test that links are kept when only one side is archived."""
        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        storage.add_link("t-a", "t-b")

        # Archive only a; link should remain because t-b is not archived
        storage.remove_archived({"t-a"}, remaining_lines=1)

        remaining_links = storage.all_links
        assert len(remaining_links) == 1

    def test_remove_archived_rebuilds_indexes(self, storage: JSONLStorage) -> None:
        """Test that indexes are rebuilt after removing archived issues."""
        storage.create(
            Issue(id="parent", namespace="t", title="Parent"),
        )
        storage.create(
            Issue(id="child", namespace="t", title="Child", parent="t-parent"),
        )

        # Archive child
        storage.remove_archived({"t-child"}, remaining_lines=1)

        # Children index should be rebuilt without the archived child
        children = storage.get_children("t-parent")
        assert len(children) == 0

    def test_remove_archived_updates_line_counts(self, storage: JSONLStorage) -> None:
        """Test that _base_lines and _appended_lines are updated."""
        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))

        storage.remove_archived({"t-a"}, remaining_lines=42)

        assert storage._base_lines == 42
        assert storage._appended_lines == 0

    def test_remove_archived_no_ids(self, storage: JSONLStorage) -> None:
        """Test remove_archived with empty set does not remove anything."""
        storage.create(Issue(id="a", namespace="t", title="A"))

        storage.remove_archived(set(), remaining_lines=1)

        assert storage.get("t-a") is not None


class TestAllDependenciesAndLinksProperties:
    """Test all_dependencies and all_links properties."""

    def test_all_dependencies_returns_copy(self, storage: JSONLStorage) -> None:
        """Test that all_dependencies returns a copy of the internal list."""
        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        storage.add_dependency("t-a", "t-b", "blocks")

        deps = storage.all_dependencies
        assert len(deps) == 1
        assert deps[0].issue_id == "t-a"
        assert deps[0].depends_on_id == "t-b"

        # Modifying the returned list should not affect internal state
        deps.clear()
        assert len(storage.all_dependencies) == 1

    def test_all_dependencies_empty(self, storage: JSONLStorage) -> None:
        """Test all_dependencies returns empty list when no deps exist."""
        storage.create(Issue(id="a", namespace="t", title="A"))

        assert storage.all_dependencies == []

    def test_all_links_returns_copy(self, storage: JSONLStorage) -> None:
        """Test that all_links returns a copy of the internal list."""
        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        storage.add_link("t-a", "t-b")

        links = storage.all_links
        assert len(links) == 1
        assert links[0].from_id == "t-a"
        assert links[0].to_id == "t-b"

        # Modifying the returned list should not affect internal state
        links.clear()
        assert len(storage.all_links) == 1

    def test_all_links_empty(self, storage: JSONLStorage) -> None:
        """Test all_links returns empty list when no links exist."""
        storage.create(Issue(id="a", namespace="t", title="A"))

        assert storage.all_links == []


class TestCheckIdUniqueness:
    """Test check_id_uniqueness() method."""

    def test_check_id_uniqueness_returns_true(self, storage: JSONLStorage) -> None:
        """Test that check_id_uniqueness always returns True."""
        assert storage.check_id_uniqueness() is True

    def test_check_id_uniqueness_with_issues(self, storage: JSONLStorage) -> None:
        """Test check_id_uniqueness with populated storage."""
        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))

        assert storage.check_id_uniqueness() is True

    def test_check_id_uniqueness_empty_storage(self, storage: JSONLStorage) -> None:
        """Test check_id_uniqueness with empty storage."""
        assert storage.check_id_uniqueness() is True


class TestFindDanglingDependencies:
    """Test find_dangling_dependencies() method."""

    def test_no_dangling_deps(self, storage: JSONLStorage) -> None:
        """Test that no dangling deps found when all issues exist."""
        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        storage.add_dependency("t-a", "t-b", "blocks")

        dangling = storage.find_dangling_dependencies()
        assert dangling == []

    def test_dangling_dep_issue_id_missing(self, storage: JSONLStorage) -> None:
        """Test finding deps where issue_id no longer exists."""
        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        storage.add_dependency("t-a", "t-b", "blocks")

        # Simulate that t-a was removed from _issues (e.g. by external manipulation)
        del storage._issues["t-a"]

        dangling = storage.find_dangling_dependencies()
        assert len(dangling) == 1
        assert dangling[0].issue_id == "t-a"

    def test_dangling_dep_depends_on_id_missing(self, storage: JSONLStorage) -> None:
        """Test finding deps where depends_on_id no longer exists."""
        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        storage.add_dependency("t-a", "t-b", "blocks")

        # Simulate that t-b was removed
        del storage._issues["t-b"]

        dangling = storage.find_dangling_dependencies()
        assert len(dangling) == 1
        assert dangling[0].depends_on_id == "t-b"

    def test_no_dangling_when_no_deps(self, storage: JSONLStorage) -> None:
        """Test that empty list returned when there are no dependencies."""
        storage.create(Issue(id="a", namespace="t", title="A"))

        dangling = storage.find_dangling_dependencies()
        assert dangling == []


class TestRemoveDependencies:
    """Test remove_dependencies() method."""

    def test_remove_specific_dependencies(self, storage: JSONLStorage) -> None:
        """Test removing specific dependency records."""
        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        storage.create(Issue(id="c", namespace="t", title="C"))
        dep1 = storage.add_dependency("t-a", "t-b", "blocks")
        storage.add_dependency("t-a", "t-c", "blocks")

        storage.remove_dependencies([dep1])

        remaining = storage.all_dependencies
        assert len(remaining) == 1
        assert remaining[0].depends_on_id == "t-c"

    def test_remove_dependencies_rebuilds_indexes(self, storage: JSONLStorage) -> None:
        """Test that indexes are rebuilt after removing dependencies."""
        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        dep = storage.add_dependency("t-a", "t-b", "blocks")

        storage.remove_dependencies([dep])

        # Index-based lookup should reflect the removal
        assert len(storage.get_dependencies("t-a")) == 0
        assert len(storage.get_dependents("t-b")) == 0

    def test_remove_dependencies_persists(self, temp_workspace: Path) -> None:
        """Test that remove_dependencies rewrites storage file."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        dep = storage.add_dependency("t-a", "t-b", "blocks")

        storage.remove_dependencies([dep])

        # Reload from disk
        storage2 = JSONLStorage(str(storage_path))
        assert len(storage2.all_dependencies) == 0

    def test_remove_empty_list(self, storage: JSONLStorage) -> None:
        """Test removing empty list of dependencies is a no-op."""
        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        storage.add_dependency("t-a", "t-b", "blocks")

        storage.remove_dependencies([])

        assert len(storage.all_dependencies) == 1


class TestFileLock:
    """Test _file_lock() for concurrent write safety."""

    def test_file_lock_creates_lock_file(self, temp_workspace: Path) -> None:
        """Test that file lock creates a lock file."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        with storage._file_lock():
            assert storage._lock_path.exists()

    def test_file_lock_is_reentrant_safe(self, temp_workspace: Path) -> None:
        """Test that sequential lock acquisitions work correctly."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        # Acquire and release lock twice in sequence
        with storage._file_lock():
            acquired_first = True
        with storage._file_lock():
            acquired_second = True

        assert acquired_first
        assert acquired_second

        # Verify storage still works after sequential lock cycles
        storage.create(Issue(id="lock-1", title="After locks"))
        assert storage.get("lock-1") is not None

    def test_concurrent_writes_dont_corrupt(self, temp_workspace: Path) -> None:
        """Test that concurrent writes under lock don't corrupt data."""
        import threading

        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        JSONLStorage(str(storage_path), create_dir=True)

        errors: list[Exception] = []

        def create_issues(start: int, count: int) -> None:
            try:
                local_storage = JSONLStorage(str(storage_path))
                for i in range(start, start + count):
                    local_storage.create(Issue(id=f"issue-{i}", title=f"Issue {i}"))
            except Exception as e:
                errors.append(e)

        # Create issues from two threads
        t1 = threading.Thread(target=create_issues, args=(0, 10))
        t2 = threading.Thread(target=create_issues, args=(100, 10))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Reload and verify data integrity
        final_storage = JSONLStorage(str(storage_path))
        all_issues = final_storage.list()

        # Should not have any errors (though duplicate IDs might if threads overlap)
        # The important thing is no corruption - all existing issues can be loaded
        assert len(all_issues) > 0
        # Each line in the file should be valid JSON
        with storage_path.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    json.loads(line)  # Should not raise


def _count_lines(path: Path) -> int:
    """Count non-empty lines in a file."""
    with path.open() as f:
        return sum(1 for line in f if line.strip())


class TestChangeNamespace:
    """Test change_namespace() method."""

    def test_basic_namespace_change(self, storage: JSONLStorage) -> None:
        """Test changing an issue's namespace."""
        issue = Issue(id="abc1", title="Test", namespace="dc")
        storage.create(issue)

        updated = storage.change_namespace("dc-abc1", "newns")
        assert updated.namespace == "newns"
        assert updated.full_id == "newns-abc1"
        assert storage.get("newns-abc1") is not None
        assert storage.get("dc-abc1") is None

    def test_noop_when_same_namespace(self, storage: JSONLStorage) -> None:
        """Test that no-op when namespace doesn't change."""
        issue = Issue(id="abc1", title="Test", namespace="dc")
        storage.create(issue)

        updated = storage.change_namespace("dc-abc1", "dc")
        assert updated.full_id == "dc-abc1"

    def test_error_on_id_conflict(self, storage: JSONLStorage) -> None:
        """Test that error is raised if new ID already exists."""
        issue1 = Issue(id="abc1", title="Issue 1", namespace="dc")
        issue2 = Issue(id="abc1", title="Issue 2", namespace="other")
        storage.create(issue1)
        storage.create(issue2)

        with pytest.raises(ValueError, match="already exists"):
            storage.change_namespace("dc-abc1", "other")

    def test_error_on_nonexistent_issue(self, storage: JSONLStorage) -> None:
        """Test that error is raised for nonexistent issue."""
        with pytest.raises(ValueError, match="not found"):
            storage.change_namespace("dc-nope", "newns")

    def test_cascades_to_parent_references(self, storage: JSONLStorage) -> None:
        """Test that parent references in children are updated."""
        parent = Issue(id="par1", title="Parent", namespace="dc")
        storage.create(parent)
        child = Issue(id="ch1", title="Child", namespace="dc", parent="dc-par1")
        storage.create(child)

        storage.change_namespace("dc-par1", "newns")

        # Child's parent reference should point to new ID
        updated_child = storage.get("dc-ch1")
        assert updated_child is not None
        assert updated_child.parent == "newns-par1"

        # Parent-child index should work
        children = storage.get_children("newns-par1")
        assert len(children) == 1
        assert children[0].full_id == "dc-ch1"

    def test_cascades_to_duplicate_of(self, storage: JSONLStorage) -> None:
        """Test that duplicate_of references are updated."""
        original = Issue(id="orig1", title="Original", namespace="dc")
        storage.create(original)
        dup = Issue(
            id="dup1", title="Duplicate", namespace="dc", duplicate_of="dc-orig1"
        )
        storage.create(dup)

        storage.change_namespace("dc-orig1", "newns")

        updated_dup = storage.get("dc-dup1")
        assert updated_dup is not None
        assert updated_dup.duplicate_of == "newns-orig1"

    def test_cascades_to_dependencies(self, storage: JSONLStorage) -> None:
        """Test that dependency records are updated."""
        issue1 = Issue(id="is1", title="Issue 1", namespace="dc")
        issue2 = Issue(id="is2", title="Issue 2", namespace="dc")
        storage.create(issue1)
        storage.create(issue2)
        storage.add_dependency("dc-is1", "dc-is2", "blocks")

        storage.change_namespace("dc-is2", "newns")

        # Dependency should now reference the new ID
        deps = storage.get_dependencies("dc-is1")
        assert len(deps) == 1
        assert deps[0].depends_on_id == "newns-is2"

        # Reverse lookup should also work
        dependents = storage.get_dependents("newns-is2")
        assert len(dependents) == 1
        assert dependents[0].issue_id == "dc-is1"

    def test_cascades_to_links(self, storage: JSONLStorage) -> None:
        """Test that link records are updated."""
        issue1 = Issue(id="is1", title="Issue 1", namespace="dc")
        issue2 = Issue(id="is2", title="Issue 2", namespace="dc")
        storage.create(issue1)
        storage.create(issue2)
        storage.add_link("dc-is1", "dc-is2", "relates_to")

        storage.change_namespace("dc-is1", "newns")

        # Link should now reference the new ID
        links = storage.get_links("newns-is1")
        assert len(links) == 1
        assert links[0].from_id == "newns-is1"
        assert links[0].to_id == "dc-is2"

        # Incoming link lookup should work too
        incoming = storage.get_incoming_links("dc-is2")
        assert len(incoming) == 1
        assert incoming[0].from_id == "newns-is1"

    def test_persists_after_reload(self, storage: JSONLStorage) -> None:
        """Test that namespace change persists after reload."""
        parent = Issue(id="par1", title="Parent", namespace="dc")
        storage.create(parent)
        child = Issue(id="ch1", title="Child", namespace="dc", parent="dc-par1")
        storage.create(child)
        storage.add_dependency("dc-ch1", "dc-par1", "blocks")

        storage.change_namespace("dc-par1", "newns")

        # Reload from disk
        storage.reload()

        assert storage.get("newns-par1") is not None
        assert storage.get("dc-par1") is None

        updated_child = storage.get("dc-ch1")
        assert updated_child is not None
        assert updated_child.parent == "newns-par1"

        deps = storage.get_dependencies("dc-ch1")
        assert len(deps) == 1
        assert deps[0].depends_on_id == "newns-par1"

    def test_namespace_change_updates_event_ids(self, storage: JSONLStorage) -> None:
        """Test that events have issue_id rewritten after namespace change."""
        issue = Issue(id="ev1", title="Evented", namespace="dc")
        storage.create(issue)
        storage.update("dc-ev1", {"title": "Updated title"})

        storage.change_namespace("dc-ev1", "newns")

        # Read raw JSONL and collect event issue_ids
        raw_lines = storage.path.read_bytes().splitlines()
        event_issue_ids: set[str] = set()
        for line in raw_lines:
            data = orjson.loads(line)
            if data.get("record_type") == "event":
                event_issue_ids.add(data["issue_id"])

        # Old namespace should not appear in any events
        assert "dc-ev1" not in event_issue_ids

        # Events should reference the new namespace
        assert "newns-ev1" in event_issue_ids


class TestGetNamespaces:
    """Test the get_namespaces() utility function."""

    def test_counts_issues_by_namespace(self, temp_dogcats_dir: Path) -> None:
        """Counts issues grouped by namespace."""
        from dogcat.storage import NamespaceCounts, get_namespaces

        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)
        storage.create(Issue(id="a1", title="A1", namespace="ns-a"))
        storage.create(Issue(id="a2", title="A2", namespace="ns-a"))
        storage.create(Issue(id="b1", title="B1", namespace="ns-b"))

        result = get_namespaces(storage, include_inbox=False)
        assert result == {
            "ns-a": NamespaceCounts(issues=2),
            "ns-b": NamespaceCounts(issues=1),
        }

    def test_excludes_tombstones(self, temp_dogcats_dir: Path) -> None:
        """Tombstoned issues are excluded from counts."""
        from dogcat.storage import NamespaceCounts, get_namespaces

        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)
        storage.create(Issue(id="a1", title="A1", namespace="ns-a"))
        storage.create(Issue(id="a2", title="A2", namespace="ns-a"))
        storage.delete("ns-a-a1")

        result = get_namespaces(storage, include_inbox=False)
        assert result == {"ns-a": NamespaceCounts(issues=1)}

    def test_includes_inbox_proposals(self, temp_dogcats_dir: Path) -> None:
        """Inbox proposals are included when include_inbox=True."""
        from dogcat.inbox import InboxStorage
        from dogcat.models import Proposal
        from dogcat.storage import NamespaceCounts, get_namespaces

        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)
        storage.create(Issue(id="a1", title="A1", namespace="ns-a"))

        inbox = InboxStorage(dogcats_dir=str(temp_dogcats_dir))
        inbox.create(Proposal(id="p1", title="P1", namespace="ns-new"))

        result = get_namespaces(storage, dogcats_dir=str(temp_dogcats_dir))
        assert result["ns-a"] == NamespaceCounts(issues=1)
        assert result["ns-new"] == NamespaceCounts(inbox=1)

    def test_inbox_counts_separate_from_issues(self, temp_dogcats_dir: Path) -> None:
        """Inbox proposals in same namespace tracked separately."""
        from dogcat.inbox import InboxStorage
        from dogcat.models import Proposal
        from dogcat.storage import NamespaceCounts, get_namespaces

        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)
        storage.create(Issue(id="a1", title="A1", namespace="ns-a"))

        inbox = InboxStorage(dogcats_dir=str(temp_dogcats_dir))
        inbox.create(Proposal(id="p1", title="P1", namespace="ns-a"))

        result = get_namespaces(storage, dogcats_dir=str(temp_dogcats_dir))
        assert result == {"ns-a": NamespaceCounts(issues=1, inbox=1)}
        assert result["ns-a"].total == 2

    def test_no_inbox_file_is_safe(self, temp_dogcats_dir: Path) -> None:
        """Missing inbox.jsonl does not cause errors."""
        from dogcat.storage import NamespaceCounts, get_namespaces

        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)
        storage.create(Issue(id="a1", title="A1", namespace="ns-a"))

        result = get_namespaces(storage)
        assert result == {"ns-a": NamespaceCounts(issues=1)}

    def test_empty_storage(self, temp_dogcats_dir: Path) -> None:
        """Empty storage returns empty dict."""
        from dogcat.storage import get_namespaces

        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        result = get_namespaces(storage, include_inbox=False)
        assert result == {}

    def test_pinned_namespaces_always_included(self, temp_dogcats_dir: Path) -> None:
        """Pinned namespaces appear even with no issues or proposals."""
        from dogcat.config import save_config
        from dogcat.storage import NamespaceCounts, get_namespaces

        save_config(str(temp_dogcats_dir), {"pinned_namespaces": ["pinned-ns"]})
        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        result = get_namespaces(
            storage, dogcats_dir=str(temp_dogcats_dir), include_inbox=False
        )
        assert result == {"pinned-ns": NamespaceCounts()}

    def test_pinned_namespace_with_existing_issues(
        self, temp_dogcats_dir: Path
    ) -> None:
        """Pinned namespace that also has issues shows correct counts."""
        from dogcat.config import save_config
        from dogcat.storage import NamespaceCounts, get_namespaces

        save_config(str(temp_dogcats_dir), {"pinned_namespaces": ["ns-a"]})
        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)
        storage.create(Issue(id="a1", title="A1", namespace="ns-a"))

        result = get_namespaces(
            storage, dogcats_dir=str(temp_dogcats_dir), include_inbox=False
        )
        assert result == {"ns-a": NamespaceCounts(issues=1)}
