"""Tests for the shared issue_queries visibility/reparenting rules (dogcat-1bxq)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from dogcat.issue_queries import (
    default_visible_issues,
    find_parent_cycles,
    hide_snoozed,
    hide_terminal,
    parent_cycle_ids,
    reparent_orphans,
)
from dogcat.models import Issue, Status
from dogcat.storage import JSONLStorage

if TYPE_CHECKING:
    from pathlib import Path


def _store(tmp_path: Path) -> JSONLStorage:
    storage = JSONLStorage(str(tmp_path / "issues.jsonl"), create_dir=True)
    storage.create(Issue(id="open1", namespace="dc", title="Open"))
    storage.create(
        Issue(id="closed1", namespace="dc", title="Closed", status=Status.CLOSED),
    )
    storage.create(
        Issue(id="tomb1", namespace="dc", title="Tomb", status=Status.TOMBSTONE),
    )
    future = datetime.now().astimezone() + timedelta(days=7)
    storage.create(
        Issue(id="snz1", namespace="dc", title="Snoozed", snoozed_until=future),
    )
    return storage


class TestVisibilityPrimitives:
    """Unit coverage for the individual filter rules."""

    def test_hide_terminal_drops_closed_and_tombstone(self, tmp_path: Path) -> None:
        """hide_terminal keeps only non-closed, non-tombstoned issues."""
        storage = _store(tmp_path)
        ids = {i.full_id for i in hide_terminal(storage.list())}
        assert "dc-closed1" not in ids
        assert "dc-tomb1" not in ids
        assert "dc-open1" in ids

    def test_hide_snoozed_drops_future_snooze(self, tmp_path: Path) -> None:
        """hide_snoozed drops issues snoozed past the cutoff."""
        storage = _store(tmp_path)
        ids = {i.full_id for i in hide_snoozed(storage.list())}
        assert "dc-snz1" not in ids


class TestBothSurfacesAgree:
    """The CLI default path and the TUI's default_visible_issues match."""

    def test_default_visible_matches_cli_default_visibility(
        self, tmp_path: Path
    ) -> None:
        """Same store → same visible set for TUI (issue_queries) and CLI list."""
        from dogcat.cli._cmd_read import _apply_default_visibility

        storage = _store(tmp_path)

        # What the TUI dashboard shows (issue_queries).
        tui_ids = {i.full_id for i in default_visible_issues(storage)}

        # What `dcat list` shows with no opt-in filters (CLI path).
        cli_ids = {
            i.full_id
            for i in _apply_default_visibility(
                storage.list(),
                status=None,
                closed=False,
                all_issues=False,
                closed_after=None,
                closed_before=None,
                include_snoozed=False,
            )
        }

        assert tui_ids == cli_ids
        # And both exclude every hidden category, leaving only the open issue.
        assert tui_ids == {"dc-open1"}


class TestReparentOrphans:
    """Orphaned children are rooted so tree walks still reach them."""

    def test_orphan_under_missing_parent_is_rooted(self) -> None:
        """A child whose parent is not in the visible set is placed under None."""
        parent = Issue(id="par1", namespace="dc", title="Parent")
        child = Issue(id="ch1", namespace="dc", title="Child", parent="dc-par1")
        orphan = Issue(id="orph1", namespace="dc", title="Orphan", parent="dc-gone")

        hierarchy = reparent_orphans([parent, child, orphan])

        # Real child stays under its parent; orphan is rooted.
        assert child in hierarchy["dc-par1"]
        assert orphan in hierarchy[None]
        assert parent in hierarchy[None]


class TestFindParentCycles:
    """Parent loops are found once each, and only the loop itself."""

    def test_no_loop(self) -> None:
        """A plain chain has no loop."""
        assert find_parent_cycles({"a": None, "b": "a", "c": "b"}) == []

    def test_self_parent(self) -> None:
        """An issue that is its own parent is a loop of one."""
        assert find_parent_cycles({"a": "a"}) == [["a"]]

    def test_two_issue_loop_reported_once(self) -> None:
        """Two issues that are each other's parent form one loop."""
        cycles = find_parent_cycles({"a": "b", "b": "a"})
        assert len(cycles) == 1
        assert sorted(cycles[0]) == ["a", "b"]

    def test_tail_into_loop_is_not_part_of_it(self) -> None:
        """An issue whose chain runs into a loop is not on the loop."""
        cycles = find_parent_cycles({"tail": "a", "a": "b", "b": "a"})
        assert len(cycles) == 1
        assert sorted(cycles[0]) == ["a", "b"]

    def test_missing_parent_ends_walk(self) -> None:
        """A parent outside the map is not a loop."""
        assert find_parent_cycles({"a": "gone"}) == []

    def test_long_chain_into_loop(self) -> None:
        """Iterative: a 10000-deep chain does not hit the recursion limit."""
        parent_of: dict[str, str | None] = {f"n{i}": f"n{i + 1}" for i in range(10000)}
        parent_of["n10000"] = "n9999"
        assert find_parent_cycles(parent_of) == [["n9999", "n10000"]]

    def test_parent_cycle_ids_ignores_links_out_of_set(self) -> None:
        """A loop through an issue outside the set is not a loop in the set."""
        a = Issue(id="a", namespace="dc", title="A", parent="dc-b")
        assert parent_cycle_ids([a]) == set()


class TestReparentOrphansWithLoops:
    """Issues on a parent loop are rooted instead of dropped."""

    def test_loop_members_are_rooted(self) -> None:
        """Both issues of a two-issue loop appear under None."""
        a = Issue(id="a", namespace="dc", title="A", parent="dc-b")
        b = Issue(id="b", namespace="dc", title="B", parent="dc-a")
        selfp = Issue(id="s", namespace="dc", title="S", parent="dc-s")

        hierarchy = reparent_orphans([a, b, selfp])

        assert {i.full_id for i in hierarchy[None]} == {"dc-a", "dc-b", "dc-s"}
        assert "dc-a" not in hierarchy
        assert "dc-b" not in hierarchy
        assert "dc-s" not in hierarchy

    def test_child_of_loop_member_stays_nested(self) -> None:
        """An issue hanging off a loop keeps its place under its parent."""
        a = Issue(id="a", namespace="dc", title="A", parent="dc-b")
        b = Issue(id="b", namespace="dc", title="B", parent="dc-a")
        child = Issue(id="c", namespace="dc", title="C", parent="dc-a")

        hierarchy = reparent_orphans([a, b, child])

        assert hierarchy["dc-a"] == [child]
