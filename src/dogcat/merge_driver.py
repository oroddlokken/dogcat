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
the guarantees are informal: formal model-checking is out of scope, so
the invariants below are what callers can rely on, backed by the test
suite (``tests/test_merge.py``, ``tests/test_merge_driver.py``).

**Issues** (LWW by status finality, then ``updated_at``)

- Status order: ``draft < open/in_progress/in_review/blocked/deferred <
  closed < tombstone``. A more final status wins over ``updated_at`` so a
  concurrent edit that left the issue active on one branch cannot
  silently revert a ``closed`` or ``tombstone`` from the other. The five
  active statuses share one rank.
- *Idempotent*: merging a record set with itself returns the same set.
- *Deterministic and order-independent*: within a status rank the later
  ``updated_at`` wins. On an exact tie the winner is decided by a
  canonical serialization of the two records, not by which side was
  iterated first — so ``merge(base, ours, theirs)`` and
  ``merge(base, theirs, ours)`` agree. The rule used to be
  ``new_ts >= old_ts``, which resolved ties by arrival order and meant two
  collaborators merging the same pair of branches in opposite directions
  could end up with different content (dogcat-1xgi).
- *Monotonic within a rank*: among edits at the same finality a later
  edit can only ever be replaced by an even later edit; older versions
  never resurrect. Across ranks a more final status always wins,
  regardless of ``updated_at``.

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

- Present in **both** sides → keep the record whose canonical
  serialization ranks higher. Both sides agree on identity, so the only
  fields in play are ``created_at``/``created_by``; picking by content
  rather than by side label is what makes the choice survive a merge
  run in the opposite direction (dogcat-4ol3).
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
- *Deterministic and order-independent*: the key union is iterated in
  sorted order and both-sides conflicts resolve on content, so the rows
  come out identical — same records, same lines — no matter which side
  was labeled ours or which process ran the merge.

**Events** (union, deduplicated by identity tuple)

- Identity tuple is ``(issue_id, timestamp, event_type, by, changes_signature)``.
  Two events with the same identity from both sides collapse to one.
- *Strictly grow-only*: events are never removed by merge; the
  resulting list is sorted by ``timestamp`` for stable output.

**Unknown kinds** (union, deduplicated by exact content)

A record whose ``record_type`` is set to something outside
``_KNOWN_RECORD_TYPES`` — most plausibly a kind written by a newer dcat
— classifies as ``"unknown"``. Such records pass through the merge
verbatim, appended after the events. They are deduplicated by canonical
serialization, since an unknown kind has no identity fields this module
can key on, and sorted by that same serialization so the output does not
depend on argument order.

- *Never deleted by this merger*: ``base`` is not consulted, so
  "present in base, absent from one side" is **not** honored as a
  deletion the way it is for deps and links. An older tool cannot tell
  an edit of a kind it does not understand from a delete of it, and
  keeping a stale copy is recoverable where dropping the only copy is
  not (dogcat-68ij).
- The cost of that choice: if one side edits an unknown record, both the
  pre-edit and post-edit copies survive the merge. The tool that owns
  the kind has to reconcile them.

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

- Issue/proposal merge is whole-record LWW: concurrent edits to
  *different* fields of one record keep only the newer-``updated_at``
  side and drop the other. Per-field merging is out of scope (it would
  need per-field timestamps or event-log-derived state); ``dcat doctor
  --post-merge`` surfaces the dropped edit so the loss is visible.
- *The three-way merge is only as three-way as its caller.* ``merge_jsonl``
  trusts ``base_records``; it has no way to tell a genuinely empty common
  ancestor from one the caller could not find. ``dcat git merge-driver``
  is handed a real base file by git. ``dcat git rebase`` has to recover
  one — from a ``|||||||`` section, which git writes only under
  ``merge.conflictStyle=diff3``/``zdiff3``, or from index stage 1 while
  the conflicted operation is still in progress. Where it can do neither
  it passes an empty base, every row reads as "added by one side", and a
  dependency or link deleted on one branch comes back. That command
  reports the case per file rather than resolving it silently
  (dogcat-5cvm).
- *Octopus merges are not supported.* Git's octopus strategy
  (``git merge a b c``) bypasses per-file merge drivers when any
  branch produces a content conflict and aborts with "Should not be
  doing an octopus." Sequential merges (``git merge a && git merge
  b && git merge c``) work. Exercised by
  ``tests/test_git_workflows.py::test_octopus_merge_aborts_use_sequential``.
- For dep/link records, ``_dep_key`` / ``_link_key`` are the source of
  truth for identity. Collapsing two concurrent ``add`` ops with the
  same identity to one record is the intended behavior, not a defect —
  but which of the two ``created_at``/``created_by`` pairs survives is
  decided by content, not by side, so both collaborators keep the same
  one.
- *This module and the storage layer break an exact tie differently.*
  Here, two records for one id with equal ``updated_at`` resolve on
  canonical serialization; ``JSONLStorage._parse_issue_record`` resolves
  two lines for one issue id by file position, so the last line wins
  whatever it contains. A store holding such a pair would have ``dcat
  show`` and this merger name different winners. Nothing observed
  produces one — ``datetime.now().astimezone()`` is microsecond
  resolution and the paths that share a single ``now`` compact rather
  than append — so the two rules are documented rather than unified
  (dogcat-4ol3).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, cast

import orjson

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

from dogcat.constants import DEFAULT_NAMESPACE
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
        (base_records, ours_records, theirs_records).

        ``([], [], [])`` when ``raw`` carries no ``<<<<<<<`` marker at all —
        indistinguishable from a genuinely conflicted but empty file, and
        ``git_rebase`` relies on exactly that conflation in its
        ``if not ours and not theirs: continue`` guard. Callers that need to
        tell the two apart must test for the marker themselves before
        calling.
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


def parse_jsonl_bytes(raw_bytes: bytes, source: str) -> list[dict[str, Any]]:
    """Parse JSONL bytes into a list of dicts, skipping invalid lines.

    Logs warnings for malformed lines and git conflict markers so that
    silent data loss during merges is visible in ``git merge`` output.

    ``source`` names the origin in those warnings. It is a path for a file
    on disk and a git ref (``:1:.dogcats/issues.jsonl``) for a blob read out
    of the index, which is why this takes bytes rather than a path.
    """
    records: list[dict[str, Any]] = []
    for line_num, raw in enumerate(raw_bytes.splitlines(), 1):
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith(_CONFLICT_MARKERS):
            logger.warning(
                "Git conflict marker at line %d in %s — file has unresolved conflicts",
                line_num,
                source,
            )
            continue
        try:
            records.append(orjson.loads(stripped))
        except orjson.JSONDecodeError:
            logger.warning(
                "Skipping malformed JSONL at line %d in %s",
                line_num,
                source,
            )
            continue
    return records


def _parse_jsonl(path: Path) -> list[dict[str, Any]]:
    """Parse a JSONL file into a list of dicts, skipping invalid lines.

    Returns an empty list for a path that does not exist — the merge driver
    is handed a base file that git leaves absent for an add/add conflict.
    """
    if not path.exists():
        return []
    return parse_jsonl_bytes(path.read_bytes(), str(path))


_MIN_AWARE = datetime.min.replace(tzinfo=timezone.utc)


def _parse_iso_ts(value: str) -> datetime:
    """Parse an ISO-8601 timestamp to a tz-aware UTC ``datetime``.

    Plain lexicographic comparison of ISO strings is wrong across mixed
    offsets (``2026-04-25T10:00:00+05:00`` < ``2026-04-25T08:00:00+00:00``
    by string but earlier in absolute time), and ``Z`` vs ``+00:00`` for
    the same instant compare unequal. We parse the ISO string, treat
    naive timestamps as UTC, and normalize to UTC for comparison so the
    LWW rule reflects absolute time.

    Returns ``_MIN_AWARE`` for unparseable / empty strings so older or
    legacy records always lose any tie-break against a parseable peer.
    """
    if not value:
        return _MIN_AWARE
    try:
        # Python 3.11 `fromisoformat` accepts trailing 'Z'; we still
        # normalize manually for older streams that mix `Z` and `+00:00`.
        text = value.replace("Z", "+00:00") if value.endswith("Z") else value
        dt = datetime.fromisoformat(text)
    except ValueError:
        return _MIN_AWARE
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _issue_full_id(record: dict[str, Any]) -> str:
    """Extract the full issue ID from an issue record."""
    ns = record.get("namespace", DEFAULT_NAMESPACE)
    hash_id = record.get("id", "")
    return f"{ns}-{hash_id}"


def _proposal_full_id(record: dict[str, Any]) -> str:
    """Extract the full proposal ID from a proposal record."""
    ns = record.get("namespace", DEFAULT_NAMESPACE)
    hash_id = record.get("id", "")
    return f"{ns}-inbox-{hash_id}"


# Proposal statuses ordered by finality (higher = more final).
_PROPOSAL_STATUS_RANK: dict[str, int] = {
    "open": 0,
    "closed": 1,
    "tombstone": 2,
}


# Issue statuses ordered by finality. tombstone is final because a deletion
# must never be reverted by a concurrent edit on a feature branch. closed is
# "final-ish" — branches can still reopen, but a
# concurrent edit that left the issue OPEN should not silently overwrite
# a CLOSED record from the other side.
_ISSUE_STATUS_RANK: dict[str, int] = {
    "draft": 0,
    "open": 1,
    "in_progress": 1,
    "in_review": 1,
    "blocked": 1,
    "deferred": 1,
    "closed": 2,
    "tombstone": 3,
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


def _replay_with_ops(
    records: list[dict[str, Any]],
    *,
    record_type: str,
    key_fn: Callable[[dict[str, Any]], tuple[str, ...]],
) -> dict[tuple[str, ...], dict[str, Any]]:
    """Replay add/remove records of one type to get effective state."""
    state: dict[tuple[str, ...], dict[str, Any]] = {}
    for record in records:
        if classify_record(record) != record_type:
            continue
        key = key_fn(record)
        if record.get("op", "add") == "remove":
            state.pop(key, None)
        else:
            state[key] = record
    return state


def _tie_break_key(record: dict[str, Any]) -> bytes:
    """Content-derived ordering key for an exact rank+timestamp tie.

    Which record this ranks higher is arbitrary — only that it ranks them
    the same way every time matters, since that is what makes
    ``merge(base, ours, theirs)`` and ``merge(base, theirs, ours)`` agree.
    See the module docstring for the ``new_ts >= old_ts`` bug this replaced
    (dogcat-1xgi). ``full_id`` cannot serve as the key: on an exact tie it is
    equal on both sides by construction.
    """
    return orjson.dumps(record, option=orjson.OPT_SORT_KEYS)


def _merge_issues_lww(
    ours_records: list[dict[str, Any]],
    theirs_records: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Merge issues by status finality, then ``updated_at``.

    Ranks come from :data:`_ISSUE_STATUS_RANK`; the module docstring has the
    finality argument.
    """
    issues: dict[str, dict[str, Any]] = {}
    for record in [*ours_records, *theirs_records]:
        if classify_record(record) != "issue":
            continue
        fid = _issue_full_id(record)
        existing = issues.get(fid)
        if existing is None:
            issues[fid] = record
            continue
        # The 1 is the rank of "open" here: an unrecognised status — a
        # Status.UNKNOWN sentinel from a newer dcat — merges as active, so it
        # never overrides a close or tombstone and never loses to a draft.
        # _merge_proposals uses 0 for the same rule; the literals differ only
        # because that table has no draft tier below open, not because the two
        # kinds are treated differently. Keep them tied to their own "open".
        new_rank = _ISSUE_STATUS_RANK.get(record.get("status", "open"), 1)
        old_rank = _ISSUE_STATUS_RANK.get(existing.get("status", "open"), 1)
        if new_rank > old_rank:
            issues[fid] = record
        elif new_rank == old_rank:
            new_ts = _parse_iso_ts(record.get("updated_at", ""))
            old_ts = _parse_iso_ts(existing.get("updated_at", ""))
            if new_ts > old_ts or (
                new_ts == old_ts and _tie_break_key(record) > _tie_break_key(existing)
            ):
                issues[fid] = record
    return issues


def _merge_proposals(
    ours_records: list[dict[str, Any]],
    theirs_records: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Merge proposals by status finality, then ``updated_at`` / ``created_at``.

    Ranks come from :data:`_PROPOSAL_STATUS_RANK`; the module docstring has
    the finality argument. The ``created_at`` fallback covers legacy records
    written before proposals carried ``updated_at``.
    """
    proposals: dict[str, dict[str, Any]] = {}
    for record in [*ours_records, *theirs_records]:
        if classify_record(record) != "proposal":
            continue
        fid = _proposal_full_id(record)
        existing = proposals.get(fid)
        if existing is None:
            proposals[fid] = record
            continue
        # 0 is the rank of "open" in _PROPOSAL_STATUS_RANK — same
        # unknown-merges-as-open rule as _merge_issues_lww, which spells it 1
        # because its table starts at draft. Normalising the two literals to
        # match would change which record wins.
        new_rank = _PROPOSAL_STATUS_RANK.get(record.get("status", "open"), 0)
        old_rank = _PROPOSAL_STATUS_RANK.get(existing.get("status", "open"), 0)
        if new_rank > old_rank:
            proposals[fid] = record
        elif new_rank == old_rank:
            new_ts = _parse_iso_ts(
                record.get("updated_at", record.get("created_at", ""))
            )
            old_ts = _parse_iso_ts(
                existing.get("updated_at", existing.get("created_at", ""))
            )
            if new_ts > old_ts or (
                new_ts == old_ts and _tie_break_key(record) > _tie_break_key(existing)
            ):
                proposals[fid] = record
    return proposals


def _merge_events(
    ours_records: list[dict[str, Any]],
    theirs_records: list[dict[str, Any]],
) -> dict[tuple[str, str, str, str, str], dict[str, Any]]:
    """Union events from both sides, deduplicating by identity tuple."""
    events: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for record in [*ours_records, *theirs_records]:
        if classify_record(record) != "event":
            continue
        key = _event_key(record)
        if key not in events:
            events[key] = record
    return events


def _merge_unknown(
    ours_records: list[dict[str, Any]],
    theirs_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Union records of unrecognised kinds, deduplicated by exact content.

    ``classify_record`` returns ``"unknown"`` only for an explicit
    ``record_type`` outside its known set; a record with no ``record_type``
    at all is field-sniffed into issue/dependency/link and never reaches
    here.

    Identity is the canonical serialization: an unknown kind exposes no
    identity fields this module can key on, so byte-equal records are one
    record and everything else is two. That over-keeps and never
    over-deletes, which is the whole point — see the module docstring for
    why ``base_records`` is not a parameter (dogcat-68ij).

    Returns:
        The records sorted by canonical serialization, so the output is
        independent of which side was labeled ours.
    """
    unknown: dict[bytes, dict[str, Any]] = {}
    for record in [*ours_records, *theirs_records]:
        if classify_record(record) != "unknown":
            continue
        unknown.setdefault(_tie_break_key(record), record)
    return [unknown[key] for key in sorted(unknown)]


def _merge_three_way(
    base_records: list[dict[str, Any]],
    ours_records: list[dict[str, Any]],
    theirs_records: list[dict[str, Any]],
    *,
    record_type: str,
    key_fn: Callable[[dict[str, Any]], tuple[str, ...]],
) -> dict[tuple[str, ...], dict[str, Any]]:
    """Three-way merge for add/remove records (deps, links).

    Replays each side to its effective state, then for each key in the union:
    a deletion by one side wins over a no-op on the other; an add not in base
    is kept; an add by both sides collapses to the record that ranks higher
    under :func:`_tie_break_key`, so the surviving audit metadata does not
    depend on which side was labeled theirs.

    Returns:
        The merged records keyed by identity tuple, iterating in sorted key
        order. Sorting is what makes the output byte-stable: the union of
        three ``set``s of string tuples iterates in an order that Python's
        per-process hash randomization changes from run to run, so two
        collaborators merging the same branches produced the same records
        on different lines (dogcat-4ol3).
    """
    base = _replay_with_ops(base_records, record_type=record_type, key_fn=key_fn)
    ours = _replay_with_ops(ours_records, record_type=record_type, key_fn=key_fn)
    theirs = _replay_with_ops(theirs_records, record_type=record_type, key_fn=key_fn)

    merged: dict[tuple[str, ...], dict[str, Any]] = {}
    for key in sorted(set(base) | set(ours) | set(theirs)):
        in_base = key in base
        in_ours = key in ours
        in_theirs = key in theirs

        if in_ours and in_theirs:
            merged[key] = max(ours[key], theirs[key], key=_tie_break_key)
        elif in_ours and not in_theirs:
            if not in_base:
                merged[key] = ours[key]
        elif in_theirs and not in_ours and not in_base:
            merged[key] = theirs[key]
    return merged


def merge_jsonl(
    base_records: list[dict[str, Any]],
    ours_records: list[dict[str, Any]],
    theirs_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge three sets of JSONL records using JSONL-aware semantics.

    Index of what each kind does; the module docstring is the merge algebra.

    - Issues: union by full_id, status finality then latest ``updated_at`` wins.
    - Proposals: union by full_id, status finality then latest timestamp wins.
    - Events: union (deduplicated by identity tuple).
    - Dependencies & Links: proper three-way merge using base records.
      A deletion by either side (present in base, absent from that side)
      is honored unless the other side also re-added it.
    - Unknown kinds: union of both sides, deduplicated by exact content
      and never deleted. Base is not consulted for them.

    Returns:
        The merged records, assembled in compaction order: issues,
        proposals, dependencies, links, events sorted by absolute
        timestamp, then records of unrecognised kinds sorted by canonical
        serialization. This list *is* the file content — both callers
        (``dcat git merge-driver`` and ``dcat git rebase``) write it over
        the target verbatim.

        A record the five known kinds do not cover — most plausibly a
        ``record_type`` written by a newer dcat — survives verbatim
        rather than being dropped. Because the callers overwrite the
        file, dropping it here would erase it from the store rather than
        merely leave it unmerged (dogcat-68ij). Unknown records go last
        so the known kinds keep the byte-for-byte layout compaction
        produces.
    """
    issues = _merge_issues_lww(ours_records, theirs_records)
    proposals = _merge_proposals(ours_records, theirs_records)
    events = _merge_events(ours_records, theirs_records)
    merged_deps = _merge_three_way(
        base_records,
        ours_records,
        theirs_records,
        record_type="dependency",
        key_fn=_dep_key,
    )
    merged_links = _merge_three_way(
        base_records,
        ours_records,
        theirs_records,
        record_type="link",
        key_fn=_link_key,
    )

    # Assemble: issues, proposals, deps, links, events (matches compaction order),
    # then unknown kinds. Events are sorted by absolute time so cross-timezone
    # records come out in the right order.
    result: list[dict[str, Any]] = []
    result.extend(issues.values())
    result.extend(proposals.values())
    result.extend(merged_deps.values())
    result.extend(merged_links.values())
    result.extend(
        sorted(events.values(), key=lambda e: _parse_iso_ts(e.get("timestamp", "")))
    )
    result.extend(_merge_unknown(ours_records, theirs_records))
    return result
