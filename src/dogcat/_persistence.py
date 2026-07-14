"""Compaction snapshot writer for the issues JSONL store.

The *policy* for when to compact lives in :mod:`dogcat._compaction`
(``should_compact``); the low-level atomic tempfile-rename primitives live in
:mod:`dogcat._jsonl_io`. This module owns the piece in between: the
domain-aware snapshot writer that serializes the current in-memory state
(issues + dependencies + links) and preserves the append-only event records
from the existing file.

Extracted from the ``_write`` closure formerly nested inside
:meth:`dogcat.storage.JSONLStorage._save_locked` so the ~85-line rewrite body
is a module-level free function taking explicit state — independently testable
without constructing a storage instance or holding the file lock.
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
    prune_event_ids: set[str] | None = None,
    rename_event_ids: dict[str, str] | None = None,
) -> int:
    """Write a compacted snapshot to ``out`` and return the line count.

    Emits one JSONL line per issue, dependency, and link (dropping superseded
    issue records and removed deps/links, since ``issues``/``dependencies``/
    ``links`` are already the resolved current state), then copies the event
    records from ``source`` so the audit log survives compaction.

    Args:
        out: Open binary file handle to write the snapshot to (typically the
            tempfile handed in by :func:`dogcat._jsonl_io.atomic_rewrite_jsonl`).
        issues: Current issues, in output order.
        dependencies: Current dependency edges.
        links: Current link edges.
        source: The existing store file to read preserved event records from.
            Read while ``out`` (a separate tempfile) is written, so reading the
            soon-to-be-replaced file is safe.
        prune_event_ids: If set, drop event records whose ``issue_id`` is in
            this set (used by ``prune_tombstones``).
        rename_event_ids: If set, rewrite ``issue_id`` in event records
            according to this old→new mapping (used by ``change_namespace``).
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
