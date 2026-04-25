"""Custom git merge driver for JSONL issue files.

Understands JSONL record semantics to auto-resolve merges that git's
default text driver would flag as conflicts. Registered via .gitattributes
and installed with ``dcat git setup``.

Invoked by git via ``dcat git merge-driver %O %A %B``.
The merged result is written to the ours file (%A).

Merge algebra
-------------
The merger is a state-based three-way merge per record kind. It is
*effectively* a CRDT — the same set of concurrent edits produces the
same merged state regardless of which side is labeled "ours" — but
the guarantees are informal, not formally verified. The invariants
below describe what callers can rely on.

**Issues** (LWW by ``updated_at``)

- *Idempotent*: merging a record set with itself returns the same set.
- *Deterministic*: for fixed ``ours`` and ``theirs`` arguments the
  result is fully determined — ours is iterated first, theirs second,
  and ``new_ts >= old_ts`` is the wins rule, so on equal timestamps
  theirs wins. Argument order matters because git always assigns
  ours/theirs unambiguously per merge invocation; both sides of a
  ``git merge`` invoking this driver see the same labels.
- *Monotonic in updated_at*: a later edit to a given issue can only
  ever be replaced by an even later edit; older versions never
  resurrect.

**Proposals** (LWW by status finality, then ``updated_at``)

- Status order: ``open < closed < tombstone``. Once a proposal reaches
  a more final state on either side, it stays there after merge.
  Concurrent edits cannot revert a closure or a tombstone.
- Within the same status rank, falls back to ``updated_at`` (then
  ``created_at`` for legacy records that pre-date ``updated_at``).
- *Monotonic in status finality*: tombstone is absorbing — it cannot
  be undone by a concurrent edit on either branch.

**Dependencies and Links** (proper three-way merge)

The base set is the common ancestor; ours and theirs each have an
effective state computed by replaying ``add``/``remove`` ops in
order. For each key (identity tuple) in the union of base, ours, and theirs:

- Present in **both** sides → keep theirs (representative; both sides
  agree on identity, and dependency rows have no payload that differs
  meaningfully).
- Present in ours, **not** in theirs:
    - If also in base → theirs deleted it; honor the deletion.
    - If not in base → ours added it; keep it.
- Present in theirs, **not** in ours:
    - If also in base → ours deleted it; honor the deletion.
    - If not in base → theirs added it; keep it.
- *A delete on either side wins over a no-op on the other side*. A
  re-add by the other side wins over a delete (because the re-add is
  observed as "present in that side, not in base"). This matches a
  2P-Set-like semantic but without explicit tombstones — the base set
  acts as the boundary between "present, then removed" and "added by
  one side".

**Events** (union, deduplicated by identity tuple)

- Identity tuple is ``(issue_id, timestamp, event_type, by, changes_signature)``.
  Two events with the same identity from both sides collapse to one.
- *Strictly grow-only*: events are never removed by merge; the
  resulting list is sorted by ``timestamp`` for stable output.

**Invariants that hold across all kinds**

- *No data loss for additive edits*: any ``add``/``create`` present on
  exactly one side and not in base survives the merge.
- *Deletes win against silence*: a delete (issue tombstone, ``op=remove``
  for deps/links, status finality bump for proposals) is preserved
  even if the other side made no observation.
- *Last-line-wins is bounded by base*: for deps/links, "last write
  wins" only applies among records *both* sides observed; truly
  concurrent adds and deletes resolve via the three-way comparison
  above, not by timestamp.

**Scope notes**

- Issue/proposal merge is whole-record LWW: two concurrent edits to
  *different* fields of the same record keep only the side with the
  newer ``updated_at``. Per-field merging would require either
  per-field timestamps on every issue record (schema-breaking change
  affecting every reader) or deriving state from the event log (a
  different merge algorithm entirely). Both sit outside the scope of
  documenting the existing algebra (issue 5dzc) and would themselves
  be tracked as separate features if/when concurrent same-issue
  edits become common enough to matter — the post-merge concurrent-
  edit detector (``dcat doctor --post-merge``) surfaces this case
  today so it's visible rather than silent.
- For dep/link records, ``_dep_key`` / ``_link_key`` are the source of
  truth for identity and the only fields that matter for graph
  correctness. The remaining fields (``created_at``, ``created_by``)
  are audit metadata; collapsing two concurrent ``add`` ops with the
  same identity to one record is the intended behavior, not a defect.
- Formal verification with a model checker is explicitly out of scope
  per issue 5dzc ("at minimum the invariants that hold across
  concurrent edits — even if not formally verified"). The invariants
  above are exercised by the test suite in ``tests/test_merge.py``
  and ``tests/test_merge_driver.py``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

import orjson

if TYPE_CHECKING:
    from pathlib import Path

from dogcat.models import classify_record

logger = logging.getLogger(__name__)

_CONFLICT_MARKERS = (b"<<<<<<<", b"=======", b">>>>>>>")


def parse_conflicted_jsonl(
    raw: bytes,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Extract base, ours, and theirs records from a JSONL file with conflict markers.

    Parses the standard git conflict format::

        <<<<<<< ours
        ... ours records ...
        ||||||| base (merge.conflictStyle=diff3)
        ... base records ...
        =======
        ... theirs records ...
        >>>>>>> theirs

    When ``merge.conflictStyle`` is not ``diff3``, there is no base section
    between ``|||||||`` and ``=======``. In that case, both the ours and theirs
    sections still contain valid JSONL records and the base is empty.
    Non-conflicted lines outside markers are treated as shared context and
    included in both ours and theirs.

    Returns:
        (base_records, ours_records, theirs_records)
    """
    # States: "outside", "ours", "base", "theirs"
    state = "outside"
    shared: list[dict[str, Any]] = []
    ours_lines: list[tuple[int, bytes]] = []
    base_lines: list[tuple[int, bytes]] = []
    theirs_lines: list[tuple[int, bytes]] = []
    had_conflicts = False

    for line_num, line in enumerate(raw.splitlines(), 1):
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith(b"<<<<<<<"):
            state = "ours"
            had_conflicts = True
            continue
        if stripped.startswith(b"|||||||"):
            state = "base"
            continue
        if stripped.startswith(b"======="):
            state = "theirs"
            continue
        if stripped.startswith(b">>>>>>>"):
            state = "outside"
            continue

        if state == "outside":
            try:
                shared.append(orjson.loads(stripped))
            except orjson.JSONDecodeError:
                logger.warning(
                    "Skipping malformed JSONL at line %d in shared section",
                    line_num,
                )
        elif state == "ours":
            ours_lines.append((line_num, stripped))
        elif state == "base":
            base_lines.append((line_num, stripped))
        elif state == "theirs":
            theirs_lines.append((line_num, stripped))

    if not had_conflicts:
        return [], [], []

    def _parse_lines(
        lines: list[tuple[int, bytes]], section: str
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for line_num, raw_line in lines:
            try:
                records.append(orjson.loads(raw_line))
            except orjson.JSONDecodeError:  # noqa: PERF203
                logger.warning(
                    "Skipping malformed JSONL at line %d in %s section",
                    line_num,
                    section,
                )
        return records

    base_records = _parse_lines(base_lines, "base")
    ours_records = shared + _parse_lines(ours_lines, "ours")
    theirs_records = shared + _parse_lines(theirs_lines, "theirs")

    return base_records, ours_records, theirs_records


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


def _proposal_full_id(record: dict[str, Any]) -> str:
    """Extract the full proposal ID from a proposal record."""
    ns = record.get("namespace", "dc")
    hash_id = record.get("id", "")
    return f"{ns}-inbox-{hash_id}"


# Proposal statuses ordered by finality (higher = more final).
_PROPOSAL_STATUS_RANK: dict[str, int] = {
    "open": 0,
    "closed": 1,
    "tombstone": 2,
}


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
    field_names = (
        sorted(cast("dict[str, Any]", changes).keys())
        if isinstance(changes, dict)
        else []
    )
    changes_sig = ",".join(sorted(field_names))
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

    # --- Proposals: last-write-wins by status finality, then updated_at ---
    # Merge strategy: higher status finality always wins (TOMBSTONE > CLOSED > OPEN).
    # When both sides have the same status, the record with the latest updated_at
    # (falling back to created_at for older records) wins. This ensures that
    # deletions and closures are never reverted by concurrent edits.
    proposals: dict[str, dict[str, Any]] = {}
    for record in [*ours_records, *theirs_records]:
        if classify_record(record) != "proposal":
            continue
        fid = _proposal_full_id(record)
        existing = proposals.get(fid)
        if existing is None:
            proposals[fid] = record
        else:
            new_rank = _PROPOSAL_STATUS_RANK.get(
                record.get("status", "open"),
                0,
            )
            old_rank = _PROPOSAL_STATUS_RANK.get(
                existing.get("status", "open"),
                0,
            )
            if new_rank > old_rank:
                proposals[fid] = record
            elif new_rank == old_rank:
                new_ts = record.get("updated_at", record.get("created_at", ""))
                old_ts = existing.get("updated_at", existing.get("created_at", ""))
                if new_ts >= old_ts:
                    proposals[fid] = record

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

    # Assemble: issues, proposals, deps, links, events (matches compaction order)
    result: list[dict[str, Any]] = []
    result.extend(issues.values())
    result.extend(proposals.values())
    result.extend(merged_deps.values())
    result.extend(merged_links.values())
    # Sort events by timestamp for consistent ordering
    sorted_events = sorted(events.values(), key=lambda e: e.get("timestamp", ""))
    result.extend(sorted_events)

    return result
