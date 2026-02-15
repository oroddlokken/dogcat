"""Custom git merge driver for JSONL issue files.

Understands JSONL record semantics to auto-resolve merges that git's
default text driver would flag as conflicts. Registered via .gitattributes
and installed with ``dcat git setup``.

Invoked by git via ``dcat git merge-driver %O %A %B``.
The merged result is written to the ours file (%A).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import orjson

if TYPE_CHECKING:
    from pathlib import Path

from dogcat.models import classify_record

logger = logging.getLogger(__name__)

_CONFLICT_MARKERS = (b"<<<<<<<", b"=======", b">>>>>>>")


def _parse_jsonl(path: Path) -> list[dict[str, Any]]:
    """Parse a JSONL file into a list of dicts, skipping invalid lines.

    Logs warnings for malformed lines and git conflict markers so that
    silent data loss during merges is visible in ``git merge`` output.
    """
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    for line_num, raw in enumerate(path.read_bytes().splitlines(), 1):
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith(_CONFLICT_MARKERS):
            logger.warning(
                "Git conflict marker at line %d in %s — file has unresolved conflicts",
                line_num,
                path,
            )
            continue
        try:
            records.append(orjson.loads(stripped))
        except orjson.JSONDecodeError:
            logger.warning(
                "Skipping malformed JSONL at line %d in %s",
                line_num,
                path,
            )
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


def _event_key(record: dict[str, Any]) -> tuple[str, str, str, str, str]:
    """Return unique identity tuple for an event record.

    Includes ``by`` and the sorted set of changed field names so that
    distinct events sharing the same timestamp and type are not collapsed.
    """
    changes = record.get("changes", {})
    changes_sig = ",".join(sorted(changes.keys())) if isinstance(changes, dict) else ""
    return (
        record.get("issue_id", ""),
        record.get("timestamp", ""),
        record.get("event_type", ""),
        record.get("by", "") or "",
        changes_sig,
    )


def _replay_deps(
    records: list[dict[str, Any]],
) -> dict[tuple[str, str, str], dict[str, Any]]:
    """Replay dependency add/remove records to get effective state."""
    state: dict[tuple[str, str, str], dict[str, Any]] = {}
    for record in records:
        if classify_record(record) != "dependency":
            continue
        key = _dep_key(record)
        if record.get("op", "add") == "remove":
            state.pop(key, None)
        else:
            state[key] = record
    return state


def _replay_links(
    records: list[dict[str, Any]],
) -> dict[tuple[str, str, str], dict[str, Any]]:
    """Replay link add/remove records to get effective state."""
    state: dict[tuple[str, str, str], dict[str, Any]] = {}
    for record in records:
        if classify_record(record) != "link":
            continue
        key = _link_key(record)
        if record.get("op", "add") == "remove":
            state.pop(key, None)
        else:
            state[key] = record
    return state


def merge_jsonl(
    base_records: list[dict[str, Any]],
    ours_records: list[dict[str, Any]],
    theirs_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge three sets of JSONL records using JSONL-aware semantics.

    - Issues: union by full_id, latest ``updated_at`` wins for conflicts.
    - Events: union (deduplicated by issue_id + timestamp + event_type).
    - Dependencies & Links: proper three-way merge using base records.
      A deletion by either side (present in base, absent from that side)
      is honored unless the other side also re-added it.

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
    events: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for record in [*ours_records, *theirs_records]:
        if classify_record(record) != "event":
            continue
        key = _event_key(record)
        if key not in events:
            events[key] = record

    # --- Dependencies: three-way merge ---
    base_deps = _replay_deps(base_records)
    ours_deps = _replay_deps(ours_records)
    theirs_deps = _replay_deps(theirs_records)

    merged_deps: dict[tuple[str, str, str], dict[str, Any]] = {}
    for key in set(base_deps) | set(ours_deps) | set(theirs_deps):
        in_base = key in base_deps
        in_ours = key in ours_deps
        in_theirs = key in theirs_deps

        if in_ours and in_theirs:
            merged_deps[key] = theirs_deps[key]
        elif in_ours and not in_theirs:
            if not in_base:
                # New in ours — keep it
                merged_deps[key] = ours_deps[key]
        elif in_theirs and not in_ours and not in_base:
            merged_deps[key] = theirs_deps[key]

    # --- Links: three-way merge ---
    base_links = _replay_links(base_records)
    ours_links = _replay_links(ours_records)
    theirs_links = _replay_links(theirs_records)

    merged_links: dict[tuple[str, str, str], dict[str, Any]] = {}
    for key in set(base_links) | set(ours_links) | set(theirs_links):
        in_base = key in base_links
        in_ours = key in ours_links
        in_theirs = key in theirs_links

        if in_ours and in_theirs:
            merged_links[key] = theirs_links[key]
        elif in_ours and not in_theirs:
            if not in_base:
                merged_links[key] = ours_links[key]
        elif in_theirs and not in_ours and not in_base:
            merged_links[key] = theirs_links[key]

    # Assemble: issues first, then deps, links, events (matches compaction order)
    result: list[dict[str, Any]] = []
    result.extend(issues.values())
    result.extend(merged_deps.values())
    result.extend(merged_links.values())
    # Sort events by timestamp for consistent ordering
    sorted_events = sorted(events.values(), key=lambda e: e.get("timestamp", ""))
    result.extend(sorted_events)

    return result
