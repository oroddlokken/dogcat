"""Schema versioning for JSONL records.

Every record written to ``issues.jsonl`` and ``inbox.jsonl`` carries a
``dcat_version`` field — the value of :data:`dogcat._version.version`
at the moment the record was serialized.

Two facts drive everything here. First, ``dcat_version`` is the **tool
version that wrote the record**, not a separate schema number; each record
keeps its own copy because the log is append-only, so old records carry the
version current when they were appended even after a rewrite. Second, only
the leading ``MAJOR.MINOR.PATCH`` triple is ever compared — these are PEP 440
strings (``0.11.7.post1.dev4+gabcd1234``) whose pre/post/dev/local segments
are build provenance, not schema drift. A version the regex cannot parse is
treated as older and ignored.

Older records with a newer tool always work; migrations live in
:mod:`dogcat.models`. Newer records with an older tool are best-effort —
unknown types and fields are skipped where possible, and
:func:`warn_if_records_from_newer_version` warns at load.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import TYPE_CHECKING

from dogcat._version import version as _dcat_version

if TYPE_CHECKING:
    from collections.abc import Iterable

logger = logging.getLogger(__name__)

VersionTuple = tuple[int, int, int]

# Set to the MAJOR.MINOR of a schema change an older tool would corrupt or
# misinterpret, so it warns instead of proceeding. None means no such change
# has shipped, and readers then only warn on records strictly newer than the
# running tool.
SCHEMA_BREAKING_THRESHOLD: VersionTuple | None = None

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)")


@lru_cache(maxsize=1024)
def parse_version(version: str | None) -> VersionTuple | None:
    """Extract the leading ``(MAJOR, MINOR, PATCH)`` triple from a version.

    Returns ``None`` for empty or unparseable inputs so callers can
    treat malformed records as "unknown / ignore".

    Cached: :func:`find_newest_record_version` calls this once per loaded
    record, but a store rarely holds more than a handful of distinct
    ``dcat_version`` strings.
    """
    if not version:
        return None
    match = _VERSION_RE.match(version)
    if not match:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def current_version_tuple() -> VersionTuple | None:
    """Return the ``(MAJOR, MINOR, PATCH)`` of the running tool, if parseable."""
    return parse_version(_dcat_version)


def find_newest_record_version(
    records: Iterable[dict[str, object]],
) -> tuple[VersionTuple, str] | None:
    """Return the highest ``(version_tuple, raw_version)`` seen in records.

    Returns ``None`` if no record has a parseable ``dcat_version``.
    """
    best: tuple[VersionTuple, str] | None = None
    for record in records:
        raw = record.get("dcat_version")
        if not isinstance(raw, str):
            continue
        parsed = parse_version(raw)
        if parsed is None:
            continue
        if best is None or parsed > best[0]:
            best = (parsed, raw)
    return best


def warn_if_records_from_newer_version(
    records: Iterable[dict[str, object]],
    *,
    source: str,
) -> None:
    """Emit a logging warning when any record was written by a newer tool.

    Args:
        records: The parsed records loaded from a JSONL file.
        source: Human-readable identifier (e.g. file path) used in the
            warning message.
    """
    current = current_version_tuple()
    if current is None:
        return
    newest = find_newest_record_version(records)
    if newest is None:
        return
    newest_tuple, newest_raw = newest
    if newest_tuple <= current:
        return
    logger.warning(
        "%s contains records written by dcat %s; "
        "running tool is %s. Older versions read newer records "
        "best-effort — upgrade dcat to silence this warning.",
        source,
        newest_raw,
        _dcat_version,
    )
