"""Dependency tracking and ready work detection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from dogcat.models import Dependency, Issue, Status

if TYPE_CHECKING:
    from dogcat.storage import JSONLStorage


_BLOCKING_STATUSES = (Status.OPEN, Status.IN_PROGRESS, Status.BLOCKED)


@dataclass
class BlockedIssue:
    """An issue that is blocked by dependencies."""

    issue_id: str
    blocking_ids: list[str]
    reason: str


def _build_dep_map(storage: JSONLStorage) -> dict[str, list[Dependency]]:
    """Build a {issue_full_id: [Dependency, ...]} map in one pass."""
    dep_map: dict[str, list[Dependency]] = {}
    for dep in storage.all_dependencies:
        dep_map.setdefault(dep.issue_id, []).append(dep)
    return dep_map


def get_ready_work(
    storage: JSONLStorage,
    filters: dict[str, Any] | None = None,
    *,
    include_snoozed: bool = False,
) -> list[Issue]:
    """Get issues ready to work (no blocking dependencies).

    Args:
        storage: The storage instance
        filters: Optional filters to apply
        include_snoozed: If True, include currently snoozed issues

    Returns:
        List of issues with no blockers, sorted by priority
    """
    # Pre-build lookups once: ancestor walk needs the full unfiltered set.
    issues_by_id: dict[str, Issue] = {i.full_id: i for i in storage.list()}
    dep_map = _build_dep_map(storage)

    all_issues = storage.list(filters) if filters else list(issues_by_id.values())

    work_issues = [
        i for i in all_issues if i.status in (Status.OPEN, Status.IN_PROGRESS)
    ]

    deferred_memo: dict[str, bool] = {}

    def _has_deferred_ancestor(issue: Issue) -> bool:
        chain: list[str] = []
        current_parent = issue.parent
        while current_parent:
            if current_parent in deferred_memo:
                result = deferred_memo[current_parent]
                for cid in chain:
                    deferred_memo[cid] = result
                return result
            parent_issue = issues_by_id.get(current_parent)
            if parent_issue is None:
                for cid in chain:
                    deferred_memo[cid] = False
                return False
            if parent_issue.status == Status.DEFERRED:
                deferred_memo[current_parent] = True
                for cid in chain:
                    deferred_memo[cid] = True
                return True
            chain.append(current_parent)
            current_parent = parent_issue.parent
        for cid in chain:
            deferred_memo[cid] = False
        return False

    work_issues = [i for i in work_issues if not _has_deferred_ancestor(i)]

    if not include_snoozed:
        now = datetime.now().astimezone()
        work_issues = [
            i for i in work_issues if i.snoozed_until is None or i.snoozed_until <= now
        ]

    ready: list[Issue] = []
    for issue in work_issues:
        deps = dep_map.get(issue.full_id, ())
        has_open_blocker = any(
            (blocker := issues_by_id.get(dep.depends_on_id)) is not None
            and blocker.status in _BLOCKING_STATUSES
            for dep in deps
        )
        if not has_open_blocker:
            ready.append(issue)

    ready.sort(key=lambda i: i.priority)
    return ready


def get_blocked_issues(storage: JSONLStorage) -> list[BlockedIssue]:
    """Get all blocked issues with their blockers.

    Args:
        storage: The storage instance

    Returns:
        List of blocked issues with blocking IDs
    """
    issues_by_id: dict[str, Issue] = {i.full_id: i for i in storage.list()}
    dep_map = _build_dep_map(storage)

    blocked_list: list[BlockedIssue] = []
    for issue in issues_by_id.values():
        if issue.status == Status.TOMBSTONE:
            continue

        deps = dep_map.get(issue.full_id, ())
        blocking_ids: list[str] = [
            dep.depends_on_id
            for dep in deps
            if (blocker := issues_by_id.get(dep.depends_on_id)) is not None
            and blocker.status in _BLOCKING_STATUSES
        ]

        if blocking_ids:
            reason = f"Blocked by {len(blocking_ids)} issue(s)"
            blocked_list.append(
                BlockedIssue(
                    issue_id=issue.full_id,
                    blocking_ids=blocking_ids,
                    reason=reason,
                ),
            )

    return blocked_list


def detect_cycles(storage: JSONLStorage) -> list[list[str]]:
    """Detect circular dependencies using iterative DFS.

    Args:
        storage: The storage instance

    Returns:
        List of cycles (each cycle is a list of issue IDs)

    Iterative implementation (regression for dogcat-1r7h): a recursive
    DFS hit Python's default 1000-frame limit on a 1001-deep dependency
    chain and crashed the entire CLI with RecursionError. The iterative
    walk uses an explicit stack of ``(node, neighbor_iter)`` so depth
    is bounded only by available memory.
    """
    dep_map = _build_dep_map(storage)
    all_issue_ids = [i.full_id for i in storage.list()]

    seen_cycles: set[tuple[str, ...]] = set()
    cycles: list[list[str]] = []
    visited: set[str] = set()
    rec_stack: set[str] = set()

    for root in all_issue_ids:
        if root in visited:
            continue
        path: list[str] = [root]
        visited.add(root)
        rec_stack.add(root)
        # Stack of (node, iterator over outgoing dependencies).
        stack: list[tuple[str, Any]] = [(root, iter(dep_map.get(root, ())))]
        while stack:
            node, it = stack[-1]
            try:
                dep = next(it)
            except StopIteration:
                # Done with this node — pop frame.
                rec_stack.discard(node)
                if path and path[-1] == node:
                    path.pop()
                stack.pop()
                continue
            neighbor = dep.depends_on_id
            if neighbor not in visited:
                visited.add(neighbor)
                rec_stack.add(neighbor)
                path.append(neighbor)
                stack.append((neighbor, iter(dep_map.get(neighbor, ()))))
            elif neighbor in rec_stack:
                cycle_start = path.index(neighbor)
                cycle = [*path[cycle_start:], neighbor]
                cycle_key = tuple(cycle)
                if cycle_key not in seen_cycles:
                    seen_cycles.add(cycle_key)
                    cycles.append(cycle)

    return cycles


def has_blockers(storage: JSONLStorage, issue_id: str) -> bool:
    """Check if an issue has any open blockers.

    Args:
        storage: The storage instance
        issue_id: The issue to check

    Returns:
        True if the issue has open blockers, False otherwise
    """
    deps = storage.get_dependencies(issue_id)

    for dep in deps:
        blocker = storage.get(dep.depends_on_id)
        if blocker and blocker.status in _BLOCKING_STATUSES:
            return True

    return False


def would_create_cycle(
    storage: JSONLStorage,
    issue_id: str,
    depends_on_id: str,
) -> bool:
    """Check if adding a dependency would create a circular dependency.

    Args:
        storage: The storage instance
        issue_id: The issue that would have the dependency
        depends_on_id: The issue it would depend on

    Returns:
        True if adding this dependency would create a cycle, False otherwise
    """
    # Self-dependency is always a cycle
    if issue_id == depends_on_id:
        return True

    # Iterative reachability: from depends_on_id, can we reach issue_id
    # through existing dependencies? Walking 10000+ deep chains used to
    # blow Python's recursion limit. (dogcat-1r7h)
    dep_map = _build_dep_map(storage)
    visited: set[str] = {depends_on_id}
    stack: list[str] = [depends_on_id]
    while stack:
        node = stack.pop()
        if node == issue_id:
            return True
        for dep in dep_map.get(node, ()):
            nxt = dep.depends_on_id
            if nxt not in visited:
                visited.add(nxt)
                stack.append(nxt)
    return False


def get_dependency_chain(
    storage: JSONLStorage,
    issue_id: str,
    _visited: set[str] | None = None,
) -> list[str]:
    """Get the dependency chain for an issue (iterative DFS).

    Args:
        storage: The storage instance
        issue_id: The issue to trace
        _visited: Internal set to prevent infinite recursion on cycles

    Returns:
        List of issue IDs in the dependency chain

    Iterative — see :func:`detect_cycles` for the depth-limit context
    (dogcat-1r7h). The argument ``_visited`` is preserved for source
    compatibility with callers that pre-populate the set.
    """
    visited: set[str] = _visited if _visited is not None else set()
    chain: list[str] = []
    stack: list[str] = [issue_id]
    while stack:
        node = stack.pop()
        if node in visited:
            continue
        visited.add(node)
        chain.append(node)
        # Reverse so the order matches the recursive form (dep iteration).
        deps = storage.get_dependencies(node)
        stack.extend(
            dep.depends_on_id
            for dep in reversed(list(deps))
            if dep.depends_on_id not in visited
        )
    return list(dict.fromkeys(chain))
