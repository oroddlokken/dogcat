"""Lookup indexes derived from issue/dependency/link source lists.

Extracted from ``storage.py`` so the index-rebuild rules live in one place
and storage code can stay focused on persistence concerns.

The indexes are *derived* state — every entry in them is reproducible from
``issues``, ``dependencies``, and ``links``. Any mutation of those lists
that should be reflected in lookups must be followed by a full rebuild via
:func:`rebuild_indexes`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from dogcat.models import Dependency, Issue, Link

if TYPE_CHECKING:
    from collections.abc import Iterable


@dataclass
class IssueIndexes:
    """Bundle of dict indexes for fast issue/dep/link lookups.

    All five maps are owned together because they're rebuilt as a unit and
    storage code needs them in lockstep.
    """

    deps_by_issue: dict[str, list[Dependency]] = field(
        default_factory=dict[str, list[Dependency]],
    )
    deps_by_depends_on: dict[str, list[Dependency]] = field(
        default_factory=dict[str, list[Dependency]],
    )
    links_by_from: dict[str, list[Link]] = field(
        default_factory=dict[str, list[Link]],
    )
    links_by_to: dict[str, list[Link]] = field(
        default_factory=dict[str, list[Link]],
    )
    children_by_parent: dict[str, list[str]] = field(
        default_factory=dict[str, list[str]],
    )


def rebuild_indexes(
    issues: Iterable[Issue],
    dependencies: Iterable[Dependency],
    links: Iterable[Link],
) -> IssueIndexes:
    """Compute a fresh :class:`IssueIndexes` from the given source lists."""
    indexes = IssueIndexes()
    for dep in dependencies:
        indexes.deps_by_issue.setdefault(dep.issue_id, []).append(dep)
        indexes.deps_by_depends_on.setdefault(dep.depends_on_id, []).append(dep)
    for link in links:
        indexes.links_by_from.setdefault(link.from_id, []).append(link)
        indexes.links_by_to.setdefault(link.to_id, []).append(link)
    for issue in issues:
        if issue.parent:
            indexes.children_by_parent.setdefault(issue.parent, []).append(
                issue.full_id,
            )
    return indexes
