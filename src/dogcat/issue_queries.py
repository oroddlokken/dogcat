"""Shared issue visibility / namespace / reparenting rules.

The default-visibility rule (hide closed/tombstoned and snoozed issues),
namespace filtering, and orphan reparenting were implemented once for
``dcat list`` and then re-implemented inline in the TUI dashboard. When one
copy changed, the two surfaces could silently show different issue sets.
This module is the single source of truth consumed by both (and, later, the
web UI). (dogcat-1bxq)
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from dogcat.constants import TERMINAL_STATUSES

if TYPE_CHECKING:
    from collections.abc import Callable

    from dogcat.models import Issue
    from dogcat.storage import JSONLStorage


def hide_terminal(issues: list[Issue]) -> list[Issue]:
    """Drop closed / tombstoned issues (the terminal statuses)."""
    return [i for i in issues if i.status.value not in TERMINAL_STATUSES]


def hide_snoozed(
    issues: list[Issue],
    *,
    now: datetime | None = None,
) -> list[Issue]:
    """Drop issues whose snooze extends past ``now`` (default: current time)."""
    cutoff = now if now is not None else datetime.now().astimezone()
    return [i for i in issues if i.snoozed_until is None or i.snoozed_until <= cutoff]


def apply_namespace_filter(
    issues: list[Issue],
    ns_filter: Callable[[str], bool] | None,
) -> list[Issue]:
    """Keep only issues whose namespace passes ``ns_filter`` (None keeps all)."""
    if ns_filter is None:
        return issues
    return [i for i in issues if ns_filter(i.namespace)]


def default_visible_issues(
    storage: JSONLStorage,
    *,
    ns_filter: Callable[[str], bool] | None = None,
    include_snoozed: bool = False,
) -> list[Issue]:
    """Return the default "active" view of a store.

    Non-terminal (not closed/tombstoned), in-namespace, and — unless
    ``include_snoozed`` — not currently snoozed. This is the baseline both
    the TUI dashboard and ``dcat list`` (with no opt-in filters) show.
    """
    issues = hide_terminal(storage.list())
    issues = apply_namespace_filter(issues, ns_filter)
    if not include_snoozed:
        issues = hide_snoozed(issues)
    return issues


def reparent_orphans(issues: list[Issue]) -> dict[str | None, list[Issue]]:
    """Build a ``parent_id -> children`` map, rooting orphaned children.

    A child whose parent is not in the visible set (tombstoned, closed, or
    namespace-filtered away) is placed under the root key ``None`` so a tree
    walk starting at ``parent_id=None`` still reaches it. Insertion order is
    preserved within each bucket.
    """
    visible_ids = {i.full_id for i in issues}
    hierarchy: dict[str | None, list[Issue]] = {}
    for issue in issues:
        parent_key = issue.parent if issue.parent in visible_ids else None
        hierarchy.setdefault(parent_key, []).append(issue)
    return hierarchy
