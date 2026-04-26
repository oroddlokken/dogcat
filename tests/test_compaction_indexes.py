"""Unit tests for the compaction policy and index-rebuild helpers."""

from __future__ import annotations

from dogcat._compaction import COMPACTION_MIN_BASE, COMPACTION_RATIO, should_compact
from dogcat._indexes import rebuild_indexes
from dogcat.models import Dependency, DependencyType, Issue, Link, LinkType


class TestShouldCompact:
    """Test the additive compaction trigger."""

    def test_returns_false_below_min_base(self) -> None:
        """Files below the minimum base size never auto-compact."""
        assert not should_compact(base_lines=0, appended_lines=100)
        assert not should_compact(
            base_lines=COMPACTION_MIN_BASE - 1, appended_lines=100
        )

    def test_returns_false_below_ratio_threshold(self) -> None:
        """At/above min base, must also exceed appended-vs-base ratio."""
        base = COMPACTION_MIN_BASE
        below = int(base * COMPACTION_RATIO)
        assert not should_compact(base_lines=base, appended_lines=below)

    def test_returns_true_above_both_thresholds(self) -> None:
        """When both thresholds are exceeded, compaction is triggered."""
        base = COMPACTION_MIN_BASE * 4
        appended = int(base * COMPACTION_RATIO) + 1
        assert should_compact(base_lines=base, appended_lines=appended)

    def test_exact_min_base_trigger_boundary(self) -> None:
        """At exactly (base=20, appended=11) — both thresholds satisfied."""
        # COMPACTION_MIN_BASE is 20; 20 * 0.5 = 10; appended must exceed 10.
        # So (20, 11) is the smallest pair that triggers compaction.
        assert COMPACTION_MIN_BASE == 20
        assert should_compact(base_lines=20, appended_lines=11)
        # And (20, 10) is the largest pair that does not trigger.
        assert not should_compact(base_lines=20, appended_lines=10)


class TestRebuildIndexes:
    """Test that rebuild_indexes returns correctly-shaped maps."""

    def test_dependency_index_groups_by_issue(self) -> None:
        """Dependencies are grouped under both endpoints."""
        deps = [
            Dependency(
                issue_id="t-a",
                depends_on_id="t-b",
                dep_type=DependencyType.BLOCKS,
            ),
        ]
        idx = rebuild_indexes(issues=[], dependencies=deps, links=[])
        assert idx.deps_by_issue == {"t-a": deps}
        assert idx.deps_by_depends_on == {"t-b": deps}

    def test_link_index_groups_by_endpoint(self) -> None:
        """Links are grouped under both endpoints."""
        links = [Link(from_id="t-a", to_id="t-b", link_type=LinkType.RELATES_TO)]
        idx = rebuild_indexes(issues=[], dependencies=[], links=links)
        assert idx.links_by_from == {"t-a": links}
        assert idx.links_by_to == {"t-b": links}

    def test_children_index_skips_parentless_issues(self) -> None:
        """Only issues with a parent appear in children_by_parent."""
        i1 = Issue(id="root", namespace="t", title="root")
        i2 = Issue(id="child", namespace="t", title="child", parent="t-root")
        idx = rebuild_indexes(issues=[i1, i2], dependencies=[], links=[])
        assert idx.children_by_parent == {"t-root": ["t-child"]}
