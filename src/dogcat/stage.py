"""Build an index blob of ``issues.jsonl`` that carries chosen issues only.

``dcat stage`` writes this blob into the git index so ``git commit`` takes
one issue's records and leaves every other issue's uncommitted writes in the
working tree (dogcat-42xb).

The base is the file as it stands in the index, not HEAD, so successive
``dcat stage`` calls accumulate the way ``git add`` does. The blob is always
the base's bytes, untouched, plus appended records:

- When every base line is still in the working file, the store has only
  been appended to, and the appended lines naming a staged id are copied
  across verbatim, in file order.
- When a base line is gone, the file was rewritten since (compaction,
  ``rename_namespace``, ``prune``, ...), so line identity no longer says
  what changed. Both sides are replayed to state instead, and each staged
  id gets its current issue record, ``add``/``remove`` records for edges
  that differ, and the event lines the base lacks.

An edge goes in only when both endpoints are in the base or in this run's
staged set; otherwise the commit would hold a dependency on an id it does
not contain, which ``dcat doctor --fix`` then deletes. Those edges are
reported as held back.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import orjson

from dogcat._records import (
    dependency_to_record,
    link_to_record,
    parse_dependency_record,
    parse_link_record,
)
from dogcat.constants import DEFAULT_NAMESPACE
from dogcat.models import classify_record, dict_to_issue, issue_to_dict

if TYPE_CHECKING:
    from collections.abc import Iterable

    from dogcat._records import DepMap, LinkMap
    from dogcat.models import Issue


@dataclass(frozen=True)
class HeldEdge:
    """A dependency or link left out because an endpoint is not staged."""

    kind: str  # "dependency" or "link"
    from_id: str
    to_id: str
    edge_type: str
    missing_id: str


@dataclass
class StagePlan:
    """The blob to stage and what went into it."""

    blob: bytes
    # Records appended per staged id; an edge counts toward both endpoints.
    staged: dict[str, int] = field(default_factory=dict[str, int])
    held_back: list[HeldEdge] = field(default_factory=list[HeldEdge])
    # Staged id -> its parent, when that parent is in neither the base nor
    # this run. The parent reference lives inside the issue record, so it
    # cannot be held back the way an edge record can.
    unstaged_parents: dict[str, str] = field(default_factory=dict[str, str])
    rewritten: bool = False

    @property
    def changed(self) -> bool:
        """Whether the blob differs from the base."""
        return any(self.staged.values())


@dataclass
class _State:
    issues: dict[str, Issue] = field(default_factory=dict[str, "Issue"])
    deps: DepMap = field(default_factory=dict[Any, Any])
    links: LinkMap = field(default_factory=dict[Any, Any])


def _lines(raw: bytes) -> list[bytes]:
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _load(line: bytes) -> dict[str, Any] | None:
    try:
        data = orjson.loads(line)
    except orjson.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None  # type: ignore[return-value]


def _issue_full_id(data: dict[str, Any]) -> str:
    return f"{data.get('namespace', DEFAULT_NAMESPACE)}-{data.get('id', '')}"


def _replay(lines: Iterable[bytes]) -> _State:
    """Replay JSONL lines to current state, skipping what fails to parse."""
    state = _State()
    for line in lines:
        data = _load(line)
        if data is None:
            continue
        try:
            rtype = classify_record(data)
            if rtype == "issue":
                issue = dict_to_issue(data)
                state.issues[issue.full_id] = issue
            elif rtype == "dependency":
                parse_dependency_record(data, state.deps)
            elif rtype == "link":
                parse_link_record(data, state.links)
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
    return state


def _edge(data: dict[str, Any], rtype: str) -> tuple[str, str, str]:
    if rtype == "dependency":
        return data["issue_id"], data["depends_on_id"], str(data.get("type", ""))
    return data["from_id"], data["to_id"], str(data.get("link_type", "relates_to"))


class _Collector:
    """Accumulate appended lines and per-id counts for one plan."""

    def __init__(self, ids: set[str], known: set[str]) -> None:
        self.ids = ids
        self.known = known | ids
        self.lines: list[bytes] = []
        self.counts: dict[str, int] = dict.fromkeys(ids, 0)
        self.held: dict[tuple[str, str, str, str], HeldEdge] = {}

    def add(self, line: bytes, owners: Iterable[str]) -> None:
        self.lines.append(line)
        for owner in owners:
            if owner in self.counts:
                self.counts[owner] += 1

    def add_edge(self, line: bytes, rtype: str, edge: tuple[str, str, str]) -> None:
        """Add an edge record touching a staged id, or hold it back."""
        src, dst, edge_type = edge
        missing = next((end for end in (src, dst) if end not in self.known), None)
        if missing is None:
            self.add(line, (src, dst))
            return
        key = (rtype, src, dst, edge_type)
        self.held.setdefault(
            key, HeldEdge(rtype, src, dst, edge_type, missing_id=missing)
        )


def _collect_appended(
    base_lines: Counter[bytes], working: list[bytes], col: _Collector
) -> None:
    """Copy appended working lines that name a staged id, in file order."""
    remaining = base_lines.copy()
    for line in working:
        if remaining[line] > 0:
            remaining[line] -= 1
            continue
        data = _load(line)
        if data is None:
            continue
        try:
            rtype = classify_record(data)
            if rtype == "issue":
                full_id = _issue_full_id(data)
                if full_id in col.ids:
                    col.add(line, (full_id,))
            elif rtype == "event":
                if data.get("issue_id") in col.ids:
                    col.add(line, (data["issue_id"],))
            elif rtype in ("dependency", "link"):
                edge = _edge(data, rtype)
                if edge[0] in col.ids or edge[1] in col.ids:
                    col.add_edge(line, rtype, edge)
        except (KeyError, TypeError):
            continue


def _collect_from_state(
    base: _State,
    base_lines: Counter[bytes],
    working_state: _State,
    working: list[bytes],
    col: _Collector,
) -> None:
    """Emit records that move each staged id from base state to working state."""
    for full_id in sorted(col.ids):
        issue = working_state.issues.get(full_id)
        if issue is None:
            continue
        record = issue_to_dict(issue)
        old = base.issues.get(full_id)
        if old is None or issue_to_dict(old) != record:
            col.add(orjson.dumps(record), (full_id,))

    def touches(key: tuple[str, str, str]) -> bool:
        return key[0] in col.ids or key[1] in col.ids

    for key, dep in working_state.deps.items():
        if touches(key) and key not in base.deps:
            col.add_edge(orjson.dumps(dependency_to_record(dep)), "dependency", key)
    for key, dep in base.deps.items():
        if touches(key) and key not in working_state.deps:
            col.add(orjson.dumps(dependency_to_record(dep, op="remove")), key[:2])
    for key, link in working_state.links.items():
        if touches(key) and key not in base.links:
            col.add_edge(orjson.dumps(link_to_record(link)), "link", key)
    for key, link in base.links.items():
        if touches(key) and key not in working_state.links:
            col.add(orjson.dumps(link_to_record(link, op="remove")), key[:2])

    # Compaction copies event lines verbatim, so a base event is still
    # recognisable by its bytes after a rewrite.
    remaining = base_lines.copy()
    for line in working:
        if remaining[line] > 0:
            remaining[line] -= 1
            continue
        data = _load(line)
        if data is None or data.get("record_type") != "event":
            continue
        if data.get("issue_id") in col.ids:
            col.add(line, (data["issue_id"],))


def plan_stage(base: bytes, working: bytes, ids: Iterable[str]) -> StagePlan:
    """Return the blob that adds ``ids``' uncommitted records to ``base``.

    Args:
        base: The file as it stands in the index (empty when untracked).
        working: The file in the working tree.
        ids: Full issue IDs to stage, already resolved.
    """
    id_set = set(ids)
    base_list = _lines(base)
    working_list = _lines(working)
    base_counts = Counter(base_list)
    rewritten = bool(base_counts - Counter(working_list))

    base_state = _replay(base_list)
    col = _Collector(id_set, set(base_state.issues))
    working_state: _State | None = None
    if rewritten:
        working_state = _replay(working_list)
        _collect_from_state(base_state, base_counts, working_state, working_list, col)
    else:
        _collect_appended(base_counts, working_list, col)

    if working_state is None:
        working_state = _replay(working_list)
    unstaged_parents: dict[str, str] = {}
    for full_id in sorted(id_set):
        issue = working_state.issues.get(full_id)
        if (
            col.counts[full_id]
            and issue is not None
            and issue.parent
            and issue.parent not in col.known
        ):
            unstaged_parents[full_id] = issue.parent

    blob = base
    if col.lines:
        if blob and not blob.endswith(b"\n"):
            blob += b"\n"
        blob += b"".join(line + b"\n" for line in col.lines)
    return StagePlan(
        blob=blob,
        staged=col.counts,
        held_back=list(col.held.values()),
        unstaged_parents=unstaged_parents,
        rewritten=rewritten,
    )
