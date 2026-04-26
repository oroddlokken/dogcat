"""Direct unit tests for ``JSONLStorage.archivable_partition``.

The CLI ``dcat archive`` exercises these branches end-to-end, but the
seven skip-reason branches were not covered at the API level. Each test
below targets one branch and asserts the human-readable reason string.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from dogcat.models import DependencyType, Issue, LinkType, Status
from dogcat.storage import JSONLStorage

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def storage(tmp_path: Path) -> JSONLStorage:
    """Fresh storage rooted at tmp_path/.dogcats."""
    return JSONLStorage(str(tmp_path / ".dogcats" / "issues.jsonl"), create_dir=True)


def _make(
    storage: JSONLStorage, issue_id: str, status: Status = Status.CLOSED, **kw: object
) -> Issue:
    issue = Issue(id=issue_id, title=f"Issue {issue_id}", status=status, **kw)  # type: ignore[arg-type]
    return storage.create(issue)


class TestArchivablePartitionSkipReasons:
    """One test per skip-reason branch in archivable_partition."""

    def test_skipped_for_open_children(self, storage: JSONLStorage) -> None:
        """Skipped for open children."""
        parent = _make(storage, "p1", status=Status.CLOSED)
        _make(storage, "c1", status=Status.OPEN, parent=parent.full_id)

        partition = storage.archivable_partition([parent])
        assert partition.archivable == []
        assert len(partition.skipped) == 1
        skipped_issue, reason = partition.skipped[0]
        assert skipped_issue.full_id == parent.full_id
        assert "open child" in reason

    def test_skipped_for_parent_outside_candidate_set(
        self, storage: JSONLStorage
    ) -> None:
        """Skipped for parent outside candidate set."""
        parent = _make(storage, "p2", status=Status.OPEN)
        child = _make(storage, "c2", status=Status.CLOSED, parent=parent.full_id)

        partition = storage.archivable_partition([child])
        assert partition.archivable == []
        skipped_issue, reason = partition.skipped[0]
        assert skipped_issue.full_id == child.full_id
        assert "parent" in reason
        assert parent.full_id in reason

    def test_skipped_for_dependency_outside_candidate_set(
        self, storage: JSONLStorage
    ) -> None:
        """Skipped for dependency outside candidate set."""
        a = _make(storage, "a", status=Status.CLOSED)
        b = _make(storage, "b", status=Status.OPEN)
        storage.add_dependency(a.full_id, b.full_id, DependencyType.BLOCKS.value)

        partition = storage.archivable_partition([a])
        assert partition.archivable == []
        reason = partition.skipped[0][1]
        assert "depends on non-archived" in reason
        assert b.full_id in reason

    def test_skipped_for_dependent_outside_candidate_set(
        self, storage: JSONLStorage
    ) -> None:
        """Skipped for dependent outside candidate set."""
        a = _make(storage, "aa", status=Status.OPEN)
        b = _make(storage, "bb", status=Status.CLOSED)
        storage.add_dependency(a.full_id, b.full_id, DependencyType.BLOCKS.value)

        partition = storage.archivable_partition([b])
        assert partition.archivable == []
        reason = partition.skipped[0][1]
        assert "depended on by non-archived" in reason
        assert a.full_id in reason

    def test_skipped_for_outgoing_link_to_open(self, storage: JSONLStorage) -> None:
        """Skipped for outgoing link to open."""
        a = _make(storage, "ax", status=Status.CLOSED)
        b = _make(storage, "bx", status=Status.OPEN)
        storage.add_link(a.full_id, b.full_id, LinkType.RELATES_TO.value)

        partition = storage.archivable_partition([a])
        assert partition.archivable == []
        reason = partition.skipped[0][1]
        assert "links to non-archived" in reason
        assert b.full_id in reason

    def test_skipped_for_incoming_link_from_open(self, storage: JSONLStorage) -> None:
        """Skipped for incoming link from open."""
        a = _make(storage, "ay", status=Status.OPEN)
        b = _make(storage, "by", status=Status.CLOSED)
        storage.add_link(a.full_id, b.full_id, LinkType.RELATES_TO.value)

        partition = storage.archivable_partition([b])
        assert partition.archivable == []
        reason = partition.skipped[0][1]
        assert "incoming links from non-archived" in reason
        assert a.full_id in reason

    def test_archivable_when_all_relations_inside_candidate_set(
        self, storage: JSONLStorage
    ) -> None:
        """Archivable when all relations inside candidate set."""
        a = _make(storage, "z1", status=Status.CLOSED)
        b = _make(storage, "z2", status=Status.CLOSED)
        storage.add_dependency(a.full_id, b.full_id, DependencyType.BLOCKS.value)
        storage.add_link(a.full_id, b.full_id, LinkType.RELATES_TO.value)

        partition = storage.archivable_partition([a, b])
        assert partition.skipped == []
        archived_ids = {i.full_id for i in partition.archivable}
        assert archived_ids == {a.full_id, b.full_id}

    def test_archivable_when_no_relations(self, storage: JSONLStorage) -> None:
        """Archivable when no relations."""
        a = _make(storage, "lone", status=Status.CLOSED)
        partition = storage.archivable_partition([a])
        assert partition.archivable == [a]
        assert partition.skipped == []
