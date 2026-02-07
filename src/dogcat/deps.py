"""Dependency tracking and ready work detection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from dogcat.models import Issue, IssueType, Status

if TYPE_CHECKING:
    from dogcat.storage import JSONLStorage


@dataclass
class BlockedIssue:
    """An issue that is blocked by dependencies."""

    issue_id: str
    blocking_ids: list[str]
    reason: str


def get_ready_work(
    storage: JSONLStorage,
    filters: dict[str, Any] | None = None,
) -> list[Issue]:
    """Get issues ready to work (no blocking dependencies).

    Args:
        storage: The storage instance
        filters: Optional filters to apply

    Returns:
        List of issues with no blockers, sorted by priority
    """
    # Get all issues
    all_issues = storage.list(filters) if filters else storage.list()

    # Filter to open/in_progress issues, excluding drafts
    work_issues = [
        i
        for i in all_issues
        if i.status in (Status.OPEN, Status.IN_PROGRESS)
        and i.issue_type != IssueType.DRAFT
    ]

    # Find issues with no blocking dependencies
    ready: list[Issue] = []
    for issue in work_issues:
        # Get dependencies (what this issue depends on)
        deps = storage.get_dependencies(issue.full_id)

        # Check if any dependency is open (blocking)
        has_open_blocker = False
        for dep in deps:
            blocker = storage.get(dep.depends_on_id)
            if blocker and blocker.status in (
                Status.OPEN,
                Status.IN_PROGRESS,
                Status.BLOCKED,
            ):
                has_open_blocker = True
                break

        if not has_open_blocker:
            ready.append(issue)

    # Sort by priority (lower number = higher priority)
    ready.sort(key=lambda i: i.priority)

    return ready


def get_blocked_issues(storage: JSONLStorage) -> list[BlockedIssue]:
    """Get all blocked issues with their blockers.

    Args:
        storage: The storage instance

    Returns:
        List of blocked issues with blocking IDs
    """
    blocked_list: list[BlockedIssue] = []

    # Check each issue
    for issue in storage.list():
        if issue.status == Status.TOMBSTONE:
            continue

        # Get dependencies
        deps = storage.get_dependencies(issue.full_id)
        blocking_ids: list[str] = []

        for dep in deps:
            blocker = storage.get(dep.depends_on_id)
            if blocker and blocker.status in (
                Status.OPEN,
                Status.IN_PROGRESS,
                Status.BLOCKED,
            ):
                blocking_ids.append(dep.depends_on_id)

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
    """Detect circular dependencies using DFS.

    Args:
        storage: The storage instance

    Returns:
        List of cycles (each cycle is a list of issue IDs)
    """
    seen_cycles: set[tuple[str, ...]] = set()
    cycles: list[list[str]] = []
    visited: set[str] = set()
    rec_stack: set[str] = set()

    def dfs(node: str, path: list[str]) -> None:
        """Depth-first search to detect cycles."""
        visited.add(node)
        rec_stack.add(node)
        path.append(node)

        # Get dependencies
        deps = storage.get_dependencies(node)

        for dep in deps:
            neighbor = dep.depends_on_id

            if neighbor not in visited:
                dfs(neighbor, path[:])
            elif neighbor in rec_stack:
                # Found a cycle
                cycle_start = path.index(neighbor)
                cycle = [*path[cycle_start:], neighbor]
                cycle_key = tuple(cycle)
                if cycle_key not in seen_cycles:
                    seen_cycles.add(cycle_key)
                    cycles.append(cycle)

        rec_stack.discard(node)

    # Check all issues
    for issue in storage.list():
        if issue.full_id not in visited:
            dfs(issue.full_id, [])

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
        if blocker and blocker.status in (
            Status.OPEN,
            Status.IN_PROGRESS,
            Status.BLOCKED,
        ):
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

    # Check if depends_on_id can reach issue_id through existing dependencies
    # (i.e., if depends_on_id already depends on issue_id directly or transitively)
    visited: set[str] = set()

    def can_reach(from_id: str, target_id: str) -> bool:
        """Check if from_id can reach target_id through dependencies."""
        if from_id == target_id:
            return True
        if from_id in visited:
            return False

        visited.add(from_id)
        deps = storage.get_dependencies(from_id)

        return any(can_reach(dep.depends_on_id, target_id) for dep in deps)

    return can_reach(depends_on_id, issue_id)


def get_dependency_chain(storage: JSONLStorage, issue_id: str) -> list[str]:
    """Get the dependency chain for an issue.

    Args:
        storage: The storage instance
        issue_id: The issue to trace

    Returns:
        List of issue IDs in the dependency chain
    """
    chain = [issue_id]
    deps = storage.get_dependencies(issue_id)

    for dep in deps:
        chain.extend(get_dependency_chain(storage, dep.depends_on_id))

    return list(dict.fromkeys(chain))  # Remove duplicates while preserving order
