"""Pure read queries over the in-memory issue state.

Extracted from :class:`~dogcat.storage.JSONLStorage` (dogcat-5qii, continues
dogcat-4cza) so the query logic with actual branching — the ``list`` filter
ladder, the child lookup, and the dangling-dependency scan — can be tested
directly against plain dicts/lists rather than only through a constructed store.

The store's remaining getters (``get_dependencies``/``get_dependents``/
``get_links``/``get_incoming_links``) are single-expression index reads
(``list(index.get(id, []))``); wrapping those in free functions would add
indirection without improving testability, so they stay inline on the store.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dogcat.models import Status

if TYPE_CHECKING:
    from collections.abc import Mapping

    from dogcat.models import Dependency, FilterSpec, Issue


def filter_issues(issues: list[Issue], spec: FilterSpec) -> list[Issue]:
    """Return the subset of ``issues`` matching every set field of ``spec``.

    Unset (``None``) filter fields are ignored. ``label`` accepts a single
    label (membership test) or a list (any-overlap test).
    """
    if spec.status is not None:
        status_filter = (
            spec.status if isinstance(spec.status, Status) else Status(spec.status)
        )
        issues = [i for i in issues if i.status == status_filter]

    if spec.priority is not None:
        issues = [i for i in issues if i.priority == spec.priority]

    if spec.issue_type is not None:
        issues = [i for i in issues if i.issue_type.value == spec.issue_type]

    if spec.label is not None:
        if isinstance(spec.label, list):
            label_set: set[str] = set(spec.label)
            issues = [i for i in issues if label_set & set(i.labels)]
        else:
            issues = [i for i in issues if spec.label in i.labels]

    if spec.owner is not None:
        issues = [i for i in issues if i.owner == spec.owner]

    return issues


def children_of(
    children_by_parent: dict[str, list[str]],
    issues: Mapping[str, Issue],
    parent_id: str,
) -> list[Issue]:
    """Return the issues whose parent is ``parent_id`` (existing issues only)."""
    return [
        issues[cid] for cid in children_by_parent.get(parent_id, []) if cid in issues
    ]


def dangling_dependencies(
    dependencies: list[Dependency], issues: Mapping[str, Issue]
) -> list[Dependency]:
    """Return dependencies whose endpoint issue no longer exists."""
    return [
        dep
        for dep in dependencies
        if dep.issue_id not in issues or dep.depends_on_id not in issues
    ]
