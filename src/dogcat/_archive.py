"""Archive eligibility and partitioning for the issues store.

:func:`partition_archivable` decides which of a candidate set may move. It
reads the issue graph through the :class:`ArchiveQueries` protocol (satisfied by
``JSONLStorage``) so it can be exercised against a lightweight fake with no real
store or file lock. The lock-holding ``archive()`` orchestration and the
in-memory state mutation in ``remove_archived`` stay on the storage class —
they own the lock and the index bookkeeping.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from dogcat.models import Status

if TYPE_CHECKING:
    from dogcat.models import Dependency, Issue, Link


@dataclass(frozen=True)
class ArchivePartition:
    """Result of partitioning candidates into archivable + skipped sets."""

    archivable: list[Issue]
    skipped: list[tuple[Issue, str]]


class ArchiveQueries(Protocol):
    """The issue-graph reads :func:`partition_archivable` needs from a store."""

    def get(self, issue_id: str) -> Issue | None: ...
    def get_children(self, issue_id: str) -> list[Issue]: ...
    def get_dependencies(self, issue_id: str) -> list[Dependency]: ...
    def get_dependents(self, issue_id: str) -> list[Dependency]: ...
    def get_links(self, issue_id: str) -> list[Link]: ...
    def get_incoming_links(self, issue_id: str) -> list[Link]: ...


def partition_archivable(
    candidates: list[Issue], queries: ArchiveQueries
) -> ArchivePartition:
    """Split ``candidates`` into archivable issues and skipped-with-reason.

    An issue is archivable iff it has no non-closed children (any child not
    in status ``closed`` blocks — deferred, blocked, draft and tombstone
    included), no parent staying behind, no dependencies / dependents /
    links / incoming links pointing outside the candidate set.
    ``candidates`` is treated as the set under consideration — a dependency
    on another candidate is not a blocker.
    """
    candidate_ids = {i.full_id for i in candidates}
    archivable: list[Issue] = []
    skipped: list[tuple[Issue, str]] = []

    for issue in candidates:
        children = queries.get_children(issue.full_id)
        open_children = [c for c in children if c.status != Status.CLOSED]
        if open_children:
            skipped.append(
                (
                    issue,
                    f"has {len(open_children)} open child(ren): "
                    + ", ".join(c.full_id for c in open_children[:3]),
                )
            )
            continue

        if issue.parent and issue.parent not in candidate_ids:
            parent_issue = queries.get(issue.parent)
            parent_status = parent_issue.status.value if parent_issue else "unknown"
            skipped.append(
                (
                    issue,
                    (
                        f"parent {issue.parent} is not being archived"
                        f" (status: {parent_status})"
                    ),
                )
            )
            continue

        deps = queries.get_dependencies(issue.full_id)
        bad_deps = [d for d in deps if d.depends_on_id not in candidate_ids]
        if bad_deps:
            skipped.append(
                (
                    issue,
                    "depends on non-archived issue(s): "
                    + ", ".join(d.depends_on_id for d in bad_deps[:3]),
                )
            )
            continue

        dependents = queries.get_dependents(issue.full_id)
        bad_dependents = [d for d in dependents if d.issue_id not in candidate_ids]
        if bad_dependents:
            skipped.append(
                (
                    issue,
                    "is depended on by non-archived issue(s): "
                    + ", ".join(d.issue_id for d in bad_dependents[:3]),
                )
            )
            continue

        links = queries.get_links(issue.full_id)
        bad_links = [link for link in links if link.to_id not in candidate_ids]
        if bad_links:
            skipped.append(
                (
                    issue,
                    "has links to non-archived issue(s): "
                    + ", ".join(link.to_id for link in bad_links[:3]),
                )
            )
            continue

        incoming_links = queries.get_incoming_links(issue.full_id)
        bad_incoming = [
            link for link in incoming_links if link.from_id not in candidate_ids
        ]
        if bad_incoming:
            skipped.append(
                (
                    issue,
                    "has incoming links from non-archived issue(s): "
                    + ", ".join(link.from_id for link in bad_incoming[:3]),
                )
            )
            continue

        archivable.append(issue)

    return ArchivePartition(archivable=archivable, skipped=skipped)
