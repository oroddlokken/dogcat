"""Integration tests for Phase 1 modules working together."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from dogcat.idgen import IDGenerator
from dogcat.models import DependencyType, Issue, IssueType, Status
from dogcat.storage import JSONLStorage


@pytest.fixture
def workspace_with_storage(
    temp_workspace: Path,
) -> tuple[Path, JSONLStorage, IDGenerator]:
    """Create a workspace with storage and ID generator."""
    storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
    storage = JSONLStorage(str(storage_path), create_dir=True)
    idgen = IDGenerator()
    return temp_workspace, storage, idgen


class TestPhase1Integration:
    """Test Phase 1 modules working together."""

    def test_full_workflow(
        self,
        workspace_with_storage: tuple[Path, JSONLStorage, IDGenerator],
    ) -> None:
        """Test a complete workflow: create -> list -> update -> close."""
        _, storage, idgen = workspace_with_storage
        timestamp = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

        # Create issues
        issue_id = idgen.generate_issue_id("Fix login bug", timestamp=timestamp)
        issue1 = Issue(
            id=issue_id,
            title="Fix login bug",
            description="Login is broken on mobile",
            priority=0,  # Critical
            issue_type=IssueType.BUG,
            owner="dev@example.com",
        )
        storage.create(issue1)

        # Create another issue
        issue_id2 = idgen.generate_issue_id("Add unit tests", timestamp=timestamp)
        issue2 = Issue(
            id=issue_id2,
            title="Add unit tests",
            priority=2,
            issue_type=IssueType.TASK,
            owner="qa@example.com",
        )
        storage.create(issue2)

        # List and verify
        all_issues = storage.list()
        assert len(all_issues) == 2

        open_issues = storage.list({"status": "open"})
        assert len(open_issues) == 2

        critical_issues = storage.list({"priority": 0})
        assert len(critical_issues) == 1

        # Create dependency
        dep = storage.add_dependency(issue_id2, issue_id, "blocks")
        assert dep.type == DependencyType.BLOCKS

        # Verify dependency relationships
        deps_of_issue2 = storage.get_dependencies(issue_id2)
        assert len(deps_of_issue2) == 1

        dependents_of_issue1 = storage.get_dependents(issue_id)
        assert len(dependents_of_issue1) == 1

        # Update issue
        updated = storage.update(issue_id, {"status": "in_progress"})
        assert updated.status == Status.IN_PROGRESS

        # Close issue
        closed = storage.close(issue_id)
        assert closed.status == Status.CLOSED

        # Verify final state
        final_issue = storage.get(issue_id)
        assert final_issue is not None
        assert final_issue.status == Status.CLOSED
        assert final_issue.closed_at is not None

    def test_idgen_with_storage(
        self,
        workspace_with_storage: tuple[Path, JSONLStorage, IDGenerator],
    ) -> None:
        """Test that ID generator integrates with storage."""
        _, storage, idgen = workspace_with_storage

        # Generate unique IDs
        id1 = idgen.generate_issue_id("Test Issue")
        id2 = idgen.generate_issue_id("Test Issue")
        assert id1 != id2

        # Create issues with generated IDs
        issue1 = Issue(id=id1, title="Test Issue")
        issue2 = Issue(id=id2, title="Test Issue")
        storage.create(issue1)
        storage.create(issue2)

        # Verify both are stored
        assert storage.get(id1) is not None
        assert storage.get(id2) is not None

    def test_complex_dependency_graph(
        self,
        workspace_with_storage: tuple[Path, JSONLStorage, IDGenerator],
    ) -> None:
        """Test complex dependency relationships."""
        _, storage, idgen = workspace_with_storage

        # Create 5 related issues
        issue_full_ids: list[str] = []
        for i in range(5):
            issue_id = idgen.generate_issue_id(f"Issue {i}")
            issue = Issue(id=issue_id, title=f"Issue {i}")
            storage.create(issue)
            issue_full_ids.append(issue.full_id)

        # Create a dependency chain: 0 -> 1 -> 2 -> 3 -> 4
        for i in range(4):
            storage.add_dependency(issue_full_ids[i], issue_full_ids[i + 1], "blocks")

        # Verify dependencies
        for i in range(4):
            deps = storage.get_dependencies(issue_full_ids[i])
            assert len(deps) == 1
            assert deps[0].depends_on_id == issue_full_ids[i + 1]

        # Verify dependents
        for i in range(1, 5):
            dependents = storage.get_dependents(issue_full_ids[i])
            assert len(dependents) == 1
            assert dependents[0].issue_id == issue_full_ids[i - 1]

    def test_filtering_with_labels(
        self,
        workspace_with_storage: tuple[Path, JSONLStorage, IDGenerator],
    ) -> None:
        """Test filtering by labels."""
        _, storage, idgen = workspace_with_storage

        # Create issues with different labels
        labels_to_issues = {
            "urgent": ["Critical bug", "Urgent feature"],
            "backend": ["Add auth", "Fix API"],
            "frontend": ["Fix UI", "Add animation"],
        }

        issue_id_map = {}
        for labels, titles in labels_to_issues.items():
            for title in titles:
                issue_id = idgen.generate_issue_id(title)
                issue = Issue(id=issue_id, title=title, labels=[labels])
                storage.create(issue)
                issue_id_map[(labels, title)] = issue_id

        # Test filtering
        urgent = storage.list({"label": "urgent"})
        assert len(urgent) == 2

        backend = storage.list({"label": "backend"})
        assert len(backend) == 2

        # Verify no cross-contamination
        urgent_titles = {i.title for i in urgent}
        assert "Critical bug" in urgent_titles
        assert "Urgent feature" in urgent_titles

    def test_persistence_and_reload(
        self,
        workspace_with_storage: tuple[Path, JSONLStorage, IDGenerator],
    ) -> None:
        """Test that data persists and reloads correctly."""
        workspace, storage, _idgen = workspace_with_storage
        storage_path = workspace / ".dogcats" / "issues.jsonl"

        # Create some issues
        issue1 = Issue(id="issue-1", title="Test 1", priority=1)
        issue2 = Issue(id="issue-2", title="Test 2", priority=2)
        storage.create(issue1)
        storage.create(issue2)

        # Add dependency
        storage.add_dependency("issue-1", "issue-2", "blocks")

        # Create new storage instance pointing to same file
        storage2 = JSONLStorage(str(storage_path))

        # Verify all data is loaded
        assert storage2.get("issue-1") is not None
        assert storage2.get("issue-2") is not None

        deps = storage2.get_dependencies("issue-1")
        assert len(deps) == 1

    def test_issue_lifecycle(
        self,
        workspace_with_storage: tuple[Path, JSONLStorage, IDGenerator],
    ) -> None:
        """Test complete issue lifecycle: create -> update -> close -> delete."""
        _, storage, idgen = workspace_with_storage

        # Create
        issue_id = idgen.generate_issue_id("Lifecycle Test")
        issue = Issue(id=issue_id, title="Lifecycle Test", status=Status.OPEN)
        created = storage.create(issue)
        assert created.status == Status.OPEN

        # Update
        updated = storage.update(issue_id, {"status": Status.IN_PROGRESS})
        assert updated.status == Status.IN_PROGRESS

        # Close
        closed = storage.close(issue_id, reason="Fixed in PR #123")
        assert closed.status == Status.CLOSED
        assert "PR #123" in (closed.notes or "")

        # Delete (tombstone)  # noqa: ERA001
        deleted = storage.delete(issue_id, reason="Duplicate of #456")
        assert deleted.status == Status.TOMBSTONE
        assert deleted.delete_reason == "Duplicate of #456"

        # Verify state persists
        final = storage.get(issue_id)
        assert final is not None
        assert final.status == Status.TOMBSTONE

    def test_multi_owner_workflow(
        self,
        workspace_with_storage: tuple[Path, JSONLStorage, IDGenerator],
    ) -> None:
        """Test workflow with multiple owners and updaters."""
        _, storage, idgen = workspace_with_storage

        # Alice creates an issue
        alice_issue_id = idgen.generate_issue_id("Alice's Task")
        alice_issue = Issue(
            id=alice_issue_id,
            title="Alice's Task",
            owner="alice@example.com",
            created_by="alice@example.com",
        )
        storage.create(alice_issue)

        # Bob works on it
        updated_by_bob = storage.update(
            alice_issue_id,
            {"status": Status.IN_PROGRESS, "updated_by": "bob@example.com"},
        )
        assert updated_by_bob.updated_by == "bob@example.com"

        # Charlie closes it
        closed_by_charlie = storage.close(alice_issue_id)
        assert closed_by_charlie.status == Status.CLOSED

        # Verify ownership is preserved
        final = storage.get(alice_issue_id)
        assert final is not None
        assert final.owner == "alice@example.com"
        assert final.created_by == "alice@example.com"

    def test_issue_with_all_fields(
        self,
        workspace_with_storage: tuple[Path, JSONLStorage, IDGenerator],
    ) -> None:
        """Test creating and retrieving issue with all optional fields."""
        _, storage, _ = workspace_with_storage

        issue = Issue(
            id="issue-full",
            title="Complete Issue",
            description="Full description",
            status=Status.IN_PROGRESS,
            priority=1,
            issue_type=IssueType.FEATURE,
            owner="owner@example.com",
            parent="parent-issue",
            labels=["feature", "important"],
            external_ref="https://github.com/project/issues/123",
            design="https://figma.com/design",
            acceptance="Should work on mobile",
            notes="Implementation in progress",
            created_by="creator@example.com",
            updated_by="dev@example.com",
        )
        storage.create(issue)

        retrieved = storage.get("issue-full")
        assert retrieved is not None
        assert retrieved.title == "Complete Issue"
        assert retrieved.description == "Full description"
        assert retrieved.priority == 1
        assert retrieved.issue_type == IssueType.FEATURE
        assert retrieved.owner == "owner@example.com"
        assert retrieved.parent == "parent-issue"
        assert retrieved.labels == ["feature", "important"]
        assert retrieved.external_ref == "https://github.com/project/issues/123"
        assert retrieved.design == "https://figma.com/design"
        assert retrieved.acceptance == "Should work on mobile"
        assert retrieved.notes == "Implementation in progress"
