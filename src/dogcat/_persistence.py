"""Compaction snapshot writer for the issues JSONL store.

The *policy* for when to compact lives in :mod:`dogcat._compaction`
(``should_compact``); the low-level atomic tempfile-rename primitives live in
:mod:`dogcat._jsonl_io`. This module owns the piece in between: the
domain-aware snapshot writer that serializes the current in-memory state
(issues + dependencies + links) and preserves the append-only event records
from the existing file.

It takes state explicitly rather than reading a storage instance, so it can be
tested without constructing a store or holding the file lock.
"""

from __future__ import annotations

import logging
from typing import IO, TYPE_CHECKING, Any, cast

import orjson

from dogcat._records import dependency_to_record, link_to_record
from dogcat.models import issue_to_dict

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from dogcat.models import Dependency, Issue, Link

_logger = logging.getLogger(__name__)


def compact_snapshot(
    out: IO[bytes],
    *,
    issues: Iterable[Issue],
    dependencies: Iterable[Dependency],
    links: Iterable[Link],
    source: Path,
    preserved: Iterable[dict[str, Any]] = (),
    prune_event_ids: set[str] | None = None,
    rename_event_ids: dict[str, str] | None = None,
) -> int:
    """Write a compacted snapshot to ``out`` and return the line count.

    Emits one JSONL line per issue, dependency, and link (dropping superseded
    issue records and removed deps/links, since ``issues``/``dependencies``/
    ``links`` are already the resolved current state), then copies the event
    records from ``source`` so the audit log survives compaction, then the
    records of kinds this dcat does not model.

    Args:
        out: Open binary file handle to write the snapshot to (typically the
            tempfile handed in by :func:`dogcat._jsonl_io.atomic_rewrite_jsonl`).
        issues: Current issues, in output order.
        dependencies: Current dependency edges.
        links: Current link edges.
        source: The existing store file to read preserved event records from.
            Read while ``out`` (a separate tempfile) is written, so reading the
            soon-to-be-replaced file is safe.
        preserved: Records whose ``record_type`` this dcat does not model
            (``JSONLStorage._preserved``). Written last, sorted by canonical
            serialization so a rewrite is stable, and emitted with their own
            key order so a record round-trips byte-for-byte. Omitting them
            here deletes them on the next compaction, which is the storage
            half of dogcat-68ij. Not read from ``source``: the caller has
            already resolved them, and a rewrite driven by in-memory state
            must not resurrect a record another process removed.
        prune_event_ids: If set, drop event records whose ``issue_id`` is in
            this set (used by ``prune_tombstones``).
        rename_event_ids: If set, rewrite ``issue_id`` in event records
            according to this old→new mapping (used by ``change_namespace``).
            Not applied to ``preserved`` records — the id fields of a kind we
            do not model cannot be located, so a namespace rename leaves them
            pointing at the old namespace.
    """
    line_count = 0
    for issue in issues:
        out.write(orjson.dumps(issue_to_dict(issue)))
        out.write(b"\n")
        line_count += 1

    # Reuse the canonical record serializers so a new persisted
    # dependency/link field only has to be added in one place —
    # missing this copy would silently drop the field on every
    # compaction rewrite.
    for dep in dependencies:
        out.write(orjson.dumps(dependency_to_record(dep)))
        out.write(b"\n")
        line_count += 1

    for link in links:
        out.write(orjson.dumps(link_to_record(link)))
        out.write(b"\n")
        line_count += 1

    line_count += _preserve_events(
        out,
        source=source,
        prune_event_ids=prune_event_ids,
        rename_event_ids=rename_event_ids,
    )

    # Sorted by canonical serialization, matching how merge_jsonl orders the
    # same records, so two rewrites of one store agree byte for byte.
    for record in sorted(
        preserved, key=lambda r: orjson.dumps(r, option=orjson.OPT_SORT_KEYS)
    ):
        out.write(orjson.dumps(record))
        out.write(b"\n")
        line_count += 1

    return line_count


def _preserve_events(
    out: IO[bytes],
    *,
    source: Path,
    prune_event_ids: set[str] | None,
    rename_event_ids: dict[str, str] | None,
) -> int:
    """Copy event records from ``source`` to ``out``; return lines written.

    Applies the prune/rename filters and tolerates malformed lines the same
    way ``_load`` does: a corrupt last line that ``_load`` skipped (setting
    ``_needs_compaction``) must not crash the next rewrite, so
    the same exception set + non-dict guard is caught and the line skipped.
    """
    if not source.exists():
        return 0

    written = 0
    with source.open("rb") as src:
        for line_idx, raw_line in enumerate(src):
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                raw_data = orjson.loads(stripped)
                if not isinstance(raw_data, dict):
                    msg = f"expected JSON object, got {type(raw_data).__name__}"
                    raise TypeError(msg)  # noqa: TRY301
                data = cast("dict[str, Any]", raw_data)
            except (
                orjson.JSONDecodeError,
                ValueError,
                KeyError,
                AttributeError,
                TypeError,
            ) as e:
                _logger.warning(
                    "Skipping malformed line %d in %s during compaction: %s",
                    line_idx + 1,
                    source,
                    e,
                )
                continue
            if data.get("record_type") != "event":
                continue
            eid = data.get("issue_id", "")
            if prune_event_ids and eid in prune_event_ids:
                continue
            if rename_event_ids and eid in rename_event_ids:
                data["issue_id"] = rename_event_ids[eid]
                stripped = orjson.dumps(data)
            out.write(stripped)
            out.write(b"\n")
            written += 1
    return written
