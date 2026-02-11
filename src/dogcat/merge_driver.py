"""Custom git merge driver for JSONL issue files.

Understands JSONL record semantics to auto-resolve merges that git's
default text driver would flag as conflicts. Registered via .gitattributes
and installed with ``dcat git setup``.

Invoked by git via ``dcat git merge-driver %O %A %B``.
The merged result is written to the ours file (%A).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import orjson

if TYPE_CHECKING:
    from pathlib import Path

from dogcat.models import classify_record


def _parse_jsonl(path: Path) -> list[dict[str, Any]]:
    """Parse a JSONL file into a list of dicts, skipping invalid lines."""
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    for line in path.read_bytes().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(orjson.loads(line))
        except orjson.JSONDecodeError:
            continue
    return records


def _issue_full_id(record: dict[str, Any]) -> str:
    """Extract the full issue ID from an issue record."""
    ns = record.get("namespace", "dc")
    hash_id = record.get("id", "")
    return f"{ns}-{hash_id}"


def _dep_key(record: dict[str, Any]) -> tuple[str, str, str]:
    """Return unique identity tuple for a dependency record."""
    return (
        record.get("issue_id", ""),
        record.get("depends_on_id", ""),
        record.get("type", ""),
    )


def _link_key(record: dict[str, Any]) -> tuple[str, str, str]:
    """Return unique identity tuple for a link record."""
    return (
        record.get("from_id", ""),
        record.get("to_id", ""),
        record.get("link_type", ""),
    )


def _event_key(record: dict[str, Any]) -> tuple[str, str, str]:
    """Return unique identity tuple for an event record."""
    return (
        record.get("issue_id", ""),
        record.get("timestamp", ""),
        record.get("event_type", ""),
    )


def merge_jsonl(
    _base_records: list[dict[str, Any]],
    ours_records: list[dict[str, Any]],
    theirs_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge three sets of JSONL records using JSONL-aware semantics.

    - Issues: union by full_id, latest ``updated_at`` wins for conflicts.
    - Events: union (deduplicated by issue_id + timestamp + event_type).
    - Dependencies: union of add/remove operations (deduplicated by key).
    - Links: union of add/remove operations (deduplicated by key).

    The base records are accepted for interface compatibility with
    git's three-way merge but not used — the union of ours + theirs
    with last-write-wins is sufficient for JSONL append-only semantics.

    Returns the merged list of records.
    """
    # --- Issues: last-write-wins by updated_at ---
    issues: dict[str, dict[str, Any]] = {}
    for record in [*ours_records, *theirs_records]:
        if classify_record(record) != "issue":
            continue
        fid = _issue_full_id(record)
        existing = issues.get(fid)
        if existing is None:
            issues[fid] = record
        else:
            # Keep the one with the later updated_at
            new_ts = record.get("updated_at", "")
            old_ts = existing.get("updated_at", "")
            if new_ts >= old_ts:
                issues[fid] = record

    # --- Events: keep all, deduplicate ---
    events: dict[tuple[str, str, str], dict[str, Any]] = {}
    for record in [*ours_records, *theirs_records]:
        if classify_record(record) != "event":
            continue
        key = _event_key(record)
        if key not in events:
            events[key] = record

    # --- Dependencies: keep all operations, deduplicate ---
    deps: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for record in [*ours_records, *theirs_records]:
        if classify_record(record) != "dependency":
            continue
        op = record.get("op", "add")
        key = (*_dep_key(record), op)
        if key not in deps:
            deps[key] = record

    # --- Links: keep all operations, deduplicate ---
    links: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for record in [*ours_records, *theirs_records]:
        if classify_record(record) != "link":
            continue
        op = record.get("op", "add")
        key = (*_link_key(record), op)
        if key not in links:
            links[key] = record

    # Assemble: issues first, then deps, links, events (matches compaction order)
    result: list[dict[str, Any]] = []
    result.extend(issues.values())
    result.extend(deps.values())
    result.extend(links.values())
    # Sort events by timestamp for consistent ordering
    sorted_events = sorted(events.values(), key=lambda e: e.get("timestamp", ""))
    result.extend(sorted_events)

    return result
