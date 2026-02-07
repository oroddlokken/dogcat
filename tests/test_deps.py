"""Tests for dependency tracking and ready work detection."""

from pathlib import Path

import pytest

from dogcat.deps import (
    detect_cycles,
    get_blocked_issues,
    get_dependency_chain,
    get_ready_work,
    has_blockers,
    would_create_cycle,
)
from dogcat.models import Dependency, DependencyType, Issue
from dogcat.storage import JSONLStorage


@pytest.fixture
def storage_with_issues(temp_dogcats_dir: Path) -> JSONLStorage:
    """Create a storage with test issues."""
    storage_path = temp_dogcats_dir / "issues.jsonl"
    storage = JSONLStorage(str(storage_path))

    # Create test issues with explicit namespace
    for i in range(5):
        issue = Issue(id=f"i{i}", namespace="t", title=f"Issue {i}", priority=i)
        storage.create(issue)

    return storage


class TestGetReadyWork:
    """Test ready work detection."""

    def test_ready_work_empty(self, storage_with_issues: JSONLStorage) -> None:
        """Test ready work on empty storage."""
        ready = get_ready_work(storage_with_issues)
        # All 5 issues have no dependencies
        assert len(ready) == 5

    def test_ready_work_with_blockers(self, storage_with_issues: JSONLStorage) -> None:
        """Test that blocked issues are filtered out."""
        # t-i0 blocks t-i1
        storage_with_issues.add_dependency("t-i1", "t-i0", "blocks")

        ready = get_ready_work(storage_with_issues)

        # t-i1 should not be ready since it depends on t-i0
        assert len(ready) == 4
        assert all(i.id != "t-i1" for i in ready)

    def test_ready_work_sorted_by_priority(
        self,
        storage_with_issues: JSONLStorage,
    ) -> None:
        """Test that ready work is sorted by priority."""
        ready = get_ready_work(storage_with_issues)

        # Should be sorted by priority (0 < 1 < 2 < 3 < 4)
        for i in range(len(ready) - 1):
            assert ready[i].priority <= ready[i + 1].priority

    def test_ready_work_ignores_closed(self, storage_with_issues: JSONLStorage) -> None:
        """Test that closed issues are not in ready work."""
        storage_with_issues.close("t-i0")

        ready = get_ready_work(storage_with_issues)

        # t-i0 is closed, so it shouldn't be in ready work
        assert len(ready) == 4
        assert all(i.id != "t-i0" for i in ready)

    def test_ready_work_with_filter(self, storage_with_issues: JSONLStorage) -> None:
        """Test ready work with filters."""
        # Only get issues with priority > 2
        ready = get_ready_work(storage_with_issues, {"priority": 3})

        assert len(ready) == 1
        assert ready[0].full_id == "t-i3"


class TestGetBlockedIssues:
    """Test blocked issues detection."""

    def test_no_blocked_issues(self, storage_with_issues: JSONLStorage) -> None:
        """Test detection when no issues are blocked."""
        blocked = get_blocked_issues(storage_with_issues)
        assert len(blocked) == 0

    def test_single_blocked_issue(self, storage_with_issues: JSONLStorage) -> None:
        """Test detection of a single blocked issue."""
        storage_with_issues.add_dependency("t-i1", "t-i0", "blocks")

        blocked = get_blocked_issues(storage_with_issues)

        assert len(blocked) == 1
        assert blocked[0].issue_id == "t-i1"
        assert "t-i0" in blocked[0].blocking_ids

    def test_multiple_blockers(self, storage_with_issues: JSONLStorage) -> None:
        """Test issue blocked by multiple issues."""
        storage_with_issues.add_dependency("t-i2", "t-i0", "blocks")
        storage_with_issues.add_dependency("t-i2", "t-i1", "blocks")

        blocked = get_blocked_issues(storage_with_issues)

        blocked_issue = next(b for b in blocked if b.issue_id == "t-i2")
        assert len(blocked_issue.blocking_ids) == 2

    def test_blocked_by_closed_issue_not_blocking(
        self,
        storage_with_issues: JSONLStorage,
    ) -> None:
        """Test that issues blocked only by closed issues are not blocked."""
        storage_with_issues.add_dependency("t-i1", "t-i0", "blocks")
        storage_with_issues.close("t-i0")

        blocked = get_blocked_issues(storage_with_issues)

        # t-i1 should not be blocked since its blocker is closed
        assert len(blocked) == 0


class TestDetectCycles:
    """Test cycle detection."""

    def test_no_cycles(self, storage_with_issues: JSONLStorage) -> None:
        """Test detection when no cycles exist."""
        storage_with_issues.add_dependency("t-i1", "t-i0", "blocks")
        storage_with_issues.add_dependency("t-i2", "t-i1", "blocks")

        cycles = detect_cycles(storage_with_issues)

        assert len(cycles) == 0

    def test_simple_cycle_detected_in_preexisting_data(
        self,
        storage_with_issues: JSONLStorage,
    ) -> None:
        """Test detection of a simple cycle in pre-existing data.

        Simulates data imported from external source that already has cycles.
        """
        # Directly add dependencies to simulate imported data with cycles
        # t-i0 -> t-i1 -> t-i0
        storage_with_issues._dependencies.append(
            Dependency(
                issue_id="t-i0",
                depends_on_id="t-i1",
                dep_type=DependencyType.BLOCKS,
            ),
        )
        storage_with_issues._dependencies.append(
            Dependency(
                issue_id="t-i1",
                depends_on_id="t-i0",
                dep_type=DependencyType.BLOCKS,
            ),
        )
        storage_with_issues._rebuild_indexes()

        cycles = detect_cycles(storage_with_issues)

        assert len(cycles) > 0

    def test_complex_cycle_detected_in_preexisting_data(
        self,
        storage_with_issues: JSONLStorage,
    ) -> None:
        """Test detection of a complex cycle in pre-existing data.

        Simulates data imported from external source that already has cycles.
        """
        # Directly add dependencies to simulate imported data with cycles
        # Create a chain: 0 -> 1 -> 2 -> 0
        storage_with_issues._dependencies.append(
            Dependency(
                issue_id="t-i0",
                depends_on_id="t-i1",
                dep_type=DependencyType.BLOCKS,
            ),
        )
        storage_with_issues._dependencies.append(
            Dependency(
                issue_id="t-i1",
                depends_on_id="t-i2",
                dep_type=DependencyType.BLOCKS,
            ),
        )
        storage_with_issues._dependencies.append(
            Dependency(
                issue_id="t-i2",
                depends_on_id="t-i0",
                dep_type=DependencyType.BLOCKS,
            ),
        )
        storage_with_issues._rebuild_indexes()

        cycles = detect_cycles(storage_with_issues)

        assert len(cycles) > 0


class TestWouldCreateCycle:
    """Test circular dependency prevention."""

    def test_self_dependency_creates_cycle(
        self,
        storage_with_issues: JSONLStorage,
    ) -> None:
        """Test that self-referential dependency is detected as cycle."""
        assert would_create_cycle(storage_with_issues, "t-i0", "t-i0")

    def test_direct_cycle_detected(
        self,
        storage_with_issues: JSONLStorage,
    ) -> None:
        """Test detection of direct cycle (A->B, then B->A)."""
        storage_with_issues.add_dependency("t-i0", "t-i1", "blocks")

        # B->A would create a cycle
        assert would_create_cycle(storage_with_issues, "t-i1", "t-i0")

    def test_transitive_cycle_detected(
        self,
        storage_with_issues: JSONLStorage,
    ) -> None:
        """Test detection of transitive cycle (A->B->C, then C->A)."""
        storage_with_issues.add_dependency("t-i0", "t-i1", "blocks")
        storage_with_issues.add_dependency("t-i1", "t-i2", "blocks")

        # C->A would create a cycle
        assert would_create_cycle(storage_with_issues, "t-i2", "t-i0")

    def test_no_cycle_for_valid_dependency(
        self,
        storage_with_issues: JSONLStorage,
    ) -> None:
        """Test that valid dependencies don't trigger cycle detection."""
        storage_with_issues.add_dependency("t-i0", "t-i1", "blocks")

        # C->B is fine, doesn't create a cycle
        assert not would_create_cycle(storage_with_issues, "t-i2", "t-i1")

    def test_add_dependency_rejects_cycle(
        self,
        storage_with_issues: JSONLStorage,
    ) -> None:
        """Test that add_dependency raises ValueError on cycle attempt."""
        storage_with_issues.add_dependency("t-i0", "t-i1", "blocks")

        with pytest.raises(ValueError, match="circular dependency"):
            storage_with_issues.add_dependency("t-i1", "t-i0", "blocks")

    def test_add_dependency_rejects_transitive_cycle(
        self,
        storage_with_issues: JSONLStorage,
    ) -> None:
        """Test that add_dependency rejects transitive cycles."""
        storage_with_issues.add_dependency("t-i0", "t-i1", "blocks")
        storage_with_issues.add_dependency("t-i1", "t-i2", "blocks")

        with pytest.raises(ValueError, match="circular dependency"):
            storage_with_issues.add_dependency("t-i2", "t-i0", "blocks")


class TestHasBlockers:
    """Test blocker detection."""

    def test_no_blockers(self, storage_with_issues: JSONLStorage) -> None:
        """Test issue with no blockers."""
        assert not has_blockers(storage_with_issues, "t-i0")

    def test_has_blockers(self, storage_with_issues: JSONLStorage) -> None:
        """Test issue with blockers."""
        storage_with_issues.add_dependency("t-i1", "t-i0", "blocks")

        assert has_blockers(storage_with_issues, "t-i1")
        assert not has_blockers(storage_with_issues, "t-i0")

    def test_blocker_closed_no_blockers(
        self,
        storage_with_issues: JSONLStorage,
    ) -> None:
        """Test that closed blockers don't count."""
        storage_with_issues.add_dependency("t-i1", "t-i0", "blocks")
        storage_with_issues.close("t-i0")

        assert not has_blockers(storage_with_issues, "t-i1")


class TestGetDependencyChain:
    """Test dependency chain extraction."""

    def test_simple_chain(self, storage_with_issues: JSONLStorage) -> None:
        """Test extracting a simple dependency chain."""
        storage_with_issues.add_dependency("t-i0", "t-i1", "blocks")
        storage_with_issues.add_dependency("t-i1", "t-i2", "blocks")

        chain = get_dependency_chain(storage_with_issues, "t-i0")

        assert chain[0] == "t-i0"
        assert "t-i1" in chain
        assert "t-i2" in chain

    def test_no_dependencies_chain(self, storage_with_issues: JSONLStorage) -> None:
        """Test chain for issue with no dependencies."""
        chain = get_dependency_chain(storage_with_issues, "t-i0")

        assert chain == ["t-i0"]

    def test_branching_chain(self, storage_with_issues: JSONLStorage) -> None:
        """Test chain with branching dependencies."""
        storage_with_issues.add_dependency("t-i0", "t-i1", "blocks")
        storage_with_issues.add_dependency("t-i0", "t-i2", "blocks")

        chain = get_dependency_chain(storage_with_issues, "t-i0")

        assert chain[0] == "t-i0"
        assert "t-i1" in chain
        assert "t-i2" in chain


class TestIntegrationDeps:
    """Integration tests for dependencies."""

    def test_dependency_workflow(self, storage_with_issues: JSONLStorage) -> None:
        """Test a complete dependency workflow."""
        # Create a scenario:
        # t-i0 (task 1)
        # t-i1 (task 2, depends on task 1)
        # t-i2 (task 3, depends on task 2)

        storage_with_issues.add_dependency("t-i1", "t-i0", "blocks")
        storage_with_issues.add_dependency("t-i2", "t-i1", "blocks")

        # All are open, so nothing is ready
        ready = get_ready_work(storage_with_issues)
        assert "t-i0" in [i.full_id for i in ready]
        assert "t-i1" not in [i.full_id for i in ready]

        # Close t-i0
        storage_with_issues.close("t-i0")

        # Now t-i1 should be ready
        ready = get_ready_work(storage_with_issues)
        assert "t-i1" in [i.full_id for i in ready]
        assert "t-i2" not in [i.full_id for i in ready]

        # Close t-i1
        storage_with_issues.close("t-i1")

        # Now t-i2 should be ready
        ready = get_ready_work(storage_with_issues)
        assert "t-i2" in [i.full_id for i in ready]
