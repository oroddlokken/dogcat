"""Tests for the lazy issue map (dogcat-4g8d)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import orjson

from dogcat._lazy_issues import LazyIssueMap
from dogcat.models import Issue, issue_to_dict
from dogcat.storage import JSONLStorage

if TYPE_CHECKING:
    from pathlib import Path


def _raw(issue: Issue) -> dict[str, object]:
    return issue_to_dict(issue)


def _make_map(*issues: Issue) -> LazyIssueMap:
    m = LazyIssueMap()
    for issue in issues:
        m.set_raw(issue.full_id, _raw(issue))
    return m


class TestLazyIssueMap:
    """Unit tests for LazyIssueMap semantics."""

    def test_getitem_materializes_and_preserves_identity(self) -> None:
        """First access constructs the Issue; later accesses return it."""
        m = _make_map(Issue(id="a1", namespace="t", title="A"))

        first = m["t-a1"]
        assert isinstance(first, Issue)
        assert first.title == "A"
        assert m["t-a1"] is first  # same object — in-place mutations stick

    def test_key_operations_do_not_materialize(self) -> None:
        """len/contains/iter/keys stay on raw dicts."""
        m = _make_map(
            Issue(id="a1", namespace="t", title="A"),
            Issue(id="b2", namespace="t", title="B"),
        )

        assert len(m) == 2
        assert "t-a1" in m
        assert "missing" not in m
        assert sorted(m) == ["t-a1", "t-b2"]
        assert set(m.keys()) == {"t-a1", "t-b2"}
        assert not any(isinstance(v, Issue) for v in m._entries.values())

    def test_iter_id_parent_does_not_materialize(self) -> None:
        """Index rebuilds read (full_id, parent) off raw dicts."""
        m = _make_map(
            Issue(id="a1", namespace="t", title="A"),
            Issue(id="b2", namespace="t", title="B", parent="t-a1"),
        )
        # Materialize one entry so both branches are exercised
        _ = m["t-a1"]

        pairs = dict(m.iter_id_parent())
        assert pairs == {"t-a1": None, "t-b2": "t-a1"}
        assert not isinstance(m._entries["t-b2"], Issue)

    def test_values_iteration_materializes_all(self) -> None:
        """values() yields Issues; in-place replacement is iteration-safe."""
        m = _make_map(
            Issue(id="a1", namespace="t", title="A"),
            Issue(id="b2", namespace="t", title="B"),
        )

        titles = sorted(i.title for i in m.values())
        assert titles == ["A", "B"]
        assert all(isinstance(v, Issue) for v in m._entries.values())

    def test_last_write_wins_replay(self) -> None:
        """set_raw replaces an earlier record for the same id."""
        m = LazyIssueMap()
        old = Issue(id="a1", namespace="t", title="old")
        new = Issue(id="a1", namespace="t", title="new")
        m.set_raw(old.full_id, _raw(old))
        m.set_raw(new.full_id, _raw(new))

        assert len(m) == 1
        assert m["t-a1"].title == "new"

    def test_setitem_delitem_clear(self) -> None:
        """Mutating operations behave like a dict, without materializing."""
        m = _make_map(Issue(id="a1", namespace="t", title="A"))
        created = Issue(id="b2", namespace="t", title="B")
        m[created.full_id] = created

        assert m["t-b2"] is created
        del m["t-a1"]
        assert "t-a1" not in m

        m.clear()
        assert len(m) == 0


class TestStorageLaziness:
    """JSONLStorage only materializes what a command touches."""

    def _write_store(self, temp_workspace: Path, count: int) -> Path:
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        with storage_path.open("wb") as f:
            for i in range(count):
                issue = Issue(id=f"i{i}", namespace="t", title=f"Issue {i}")
                f.write(orjson.dumps(issue_to_dict(issue)))
                f.write(b"\n")
        return storage_path

    def test_get_materializes_only_target(self, temp_workspace: Path) -> None:
        """Dcat show-style access constructs one Issue, not the store."""
        storage_path = self._write_store(temp_workspace, 50)
        s = JSONLStorage(str(storage_path))

        materialized = sum(isinstance(v, Issue) for v in s._issues._entries.values())
        assert materialized == 0

        issue = s.get("t-i7")
        assert issue is not None
        assert issue.title == "Issue 7"

        materialized = sum(isinstance(v, Issue) for v in s._issues._entries.values())
        assert materialized == 1

    def test_list_still_returns_everything(self, temp_workspace: Path) -> None:
        """Full scans behave exactly as before."""
        storage_path = self._write_store(temp_workspace, 20)
        s = JSONLStorage(str(storage_path))

        issues = s.list()
        assert len(issues) == 20
        assert {i.full_id for i in issues} == {f"t-i{n}" for n in range(20)}
