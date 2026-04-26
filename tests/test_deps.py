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
from dogcat.models import Issue
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


def _inject_cycle_via_jsonl(
    storage: JSONLStorage, edges: list[tuple[str, str]]
) -> JSONLStorage:
    """Append raw dependency records and re-load so storage sees a cycle.

    ``add_dependency`` rejects cycle-creating edges, so cycle-detection
    tests need a way to inject a malformed graph. Earlier the suite
    pushed Dependency objects onto ``storage._dependencies`` and called
    ``_rebuild_indexes`` — both private. The on-disk equivalent is to
    append dependency JSONL lines and reopen the storage; the same
    state arrives via the public load path. (dogcat-308p)
    """
    with storage.path.open("a") as f:
        for issue_id, depends_on_id in edges:
            f.write(
                '{"record_type": "dependency", '
                f'"issue_id": "{issue_id}", '
                f'"depends_on_id": "{depends_on_id}", '
                '"type": "blocks", '
                '"created_at": "2026-04-25T12:00:00+00:00"}\n'
            )
    return JSONLStorage(str(storage.path))


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

    def test_ready_work_excludes_children_of_deferred_parent(
        self,
        storage_with_issues: JSONLStorage,
    ) -> None:
        """Test that children of deferred parents are excluded from ready work."""
        # Create a deferred parent epic
        parent = Issue(id="epic1", namespace="t", title="Deferred Epic", priority=2)
        storage_with_issues.create(parent)
        storage_with_issues.update("t-epic1", {"status": "deferred"})

        # Create an open child under the deferred parent
        child = Issue(
            id="child1",
            namespace="t",
            title="Child Task",
            priority=2,
            parent="t-epic1",
        )
        storage_with_issues.create(child)

        ready = get_ready_work(storage_with_issues)

        # The child of the deferred parent should NOT be in ready work
        ready_ids = [i.full_id for i in ready]
        assert "t-child1" not in ready_ids
        # The deferred parent itself is also excluded (status != open/in_progress)
        assert "t-epic1" not in ready_ids

    def test_ready_work_excludes_grandchildren_of_deferred_parent(
        self,
        storage_with_issues: JSONLStorage,
    ) -> None:
        """Test that grandchildren of deferred parents are also excluded."""
        # Deferred grandparent
        grandparent = Issue(
            id="gp1",
            namespace="t",
            title="Deferred Grandparent",
            priority=2,
        )
        storage_with_issues.create(grandparent)
        storage_with_issues.update("t-gp1", {"status": "deferred"})

        # Open parent under deferred grandparent
        parent = Issue(
            id="p1",
            namespace="t",
            title="Parent Task",
            priority=2,
            parent="t-gp1",
        )
        storage_with_issues.create(parent)

        # Open grandchild
        grandchild = Issue(
            id="gc1",
            namespace="t",
            title="Grandchild Task",
            priority=2,
            parent="t-p1",
        )
        storage_with_issues.create(grandchild)

        ready = get_ready_work(storage_with_issues)

        ready_ids = [i.full_id for i in ready]
        assert "t-p1" not in ready_ids
        assert "t-gc1" not in ready_ids


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
        storage_with_issues = _inject_cycle_via_jsonl(
            storage_with_issues,
            [("t-i0", "t-i1"), ("t-i1", "t-i0")],
        )

        cycles = detect_cycles(storage_with_issues)

        assert len(cycles) > 0

    def test_complex_cycle_detected_in_preexisting_data(
        self,
        storage_with_issues: JSONLStorage,
    ) -> None:
        """Test detection of a complex cycle in pre-existing data.

        Simulates data imported from external source that already has cycles.
        """
        storage_with_issues = _inject_cycle_via_jsonl(
            storage_with_issues,
            [("t-i0", "t-i1"), ("t-i1", "t-i2"), ("t-i2", "t-i0")],
        )

        cycles = detect_cycles(storage_with_issues)

        assert len(cycles) > 0

    def test_no_duplicate_cycles(
        self,
        storage_with_issues: JSONLStorage,
    ) -> None:
        """Test that detect_cycles returns no duplicate cycle entries."""
        storage_with_issues = _inject_cycle_via_jsonl(
            storage_with_issues,
            [("t-i0", "t-i1"), ("t-i1", "t-i0")],
        )

        cycles = detect_cycles(storage_with_issues)

        # Convert to tuples for set-based dedup check
        cycle_tuples = [tuple(c) for c in cycles]
        assert len(cycle_tuples) == len(set(cycle_tuples))


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

    def test_chain_with_cycle_does_not_recurse_infinitely(
        self,
        storage_with_issues: JSONLStorage,
    ) -> None:
        """Dependency chain with a cycle terminates instead of infinite recursion."""
        storage_with_issues = _inject_cycle_via_jsonl(
            storage_with_issues,
            [("t-i0", "t-i1"), ("t-i1", "t-i0")],
        )

        # Should terminate without RecursionError
        chain = get_dependency_chain(storage_with_issues, "t-i0")

        assert "t-i0" in chain
        assert "t-i1" in chain


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


class TestDeepDependencyChain:
    """Cycle detection / reachability must handle deep chains.

    Regression for dogcat-1r7h: the recursive DFS hit Python's default
    1000-frame limit on a 1001-deep chain and crashed every subsequent
    dcat invocation. The iterative form scales to ~10k+ depth.
    """

    @staticmethod
    def _build_deep_chain(storage: JSONLStorage, depth: int) -> JSONLStorage:
        """Create ``depth`` issues with t-i{n} blocks t-i{n+1}.

        Drives the chain from real on-disk JSONL input: we append issue
        records via the public API, then write dependency records
        directly to the file, then re-load. This avoids paying the
        per-call cycle-prevention cost in ``add_dependency`` (each call
        is O(N), making 10k of them O(N²) and unusable as test setup)
        while keeping the test honest at the public-API boundary.
        (dogcat-308p)
        """
        for i in range(depth):
            storage.create(Issue(id=f"i{i}", namespace="t", title=f"Issue {i}"))

        with storage.path.open("a") as f:
            for i in range(depth - 1):
                f.write(
                    '{"record_type": "dependency", '
                    f'"issue_id": "t-i{i}", '
                    f'"depends_on_id": "t-i{i + 1}", '
                    '"type": "blocks", '
                    '"created_at": "2026-04-25T12:00:00+00:00"}\n'
                )
        # Reload from disk to pick up the dep records.
        return JSONLStorage(str(storage.path))

    def test_detect_cycles_handles_10000_deep_chain(
        self, temp_dogcats_dir: Path
    ) -> None:
        """detect_cycles does not raise RecursionError on a 10k-deep chain."""
        storage = JSONLStorage(str(temp_dogcats_dir / "issues.jsonl"))
        storage = self._build_deep_chain(storage, 10000)
        cycles = detect_cycles(storage)
        # Linear chain has no cycle.
        assert cycles == []

    def test_would_create_cycle_handles_10000_deep_chain(
        self, temp_dogcats_dir: Path
    ) -> None:
        """would_create_cycle handles 10k-deep reachability."""
        storage = JSONLStorage(str(temp_dogcats_dir / "issues.jsonl"))
        storage = self._build_deep_chain(storage, 10000)
        # Adding t-i9999 -> t-i0 would close the chain into a cycle.
        assert would_create_cycle(storage, "t-i9999", "t-i0") is True
        # A side-edge between two non-related ids does not create a cycle.
        storage.create(
            Issue(id="other", namespace="t", title="Other"),
        )
        assert would_create_cycle(storage, "t-other", "t-i0") is False

    def test_get_dependency_chain_handles_deep_chain(
        self, temp_dogcats_dir: Path
    ) -> None:
        """get_dependency_chain walks a 5k-deep chain without recursion."""
        storage = JSONLStorage(str(temp_dogcats_dir / "issues.jsonl"))
        storage = self._build_deep_chain(storage, 5000)
        chain = get_dependency_chain(storage, "t-i0")
        assert len(chain) == 5000
