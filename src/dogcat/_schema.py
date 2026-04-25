"""Schema versioning for JSONL records.

Every record written to ``issues.jsonl`` and ``inbox.jsonl`` carries a
``dcat_version`` field — the value of :data:`dogcat._version.version`
at the moment the record was serialized. This module documents how
that field is intended to be used and provides a load-time check that
warns when a database has been touched by a newer tool than the one
currently running.

What ``dcat_version`` is
------------------------

It is the **tool version that wrote the record**, not a separate
schema-version number. The two co-evolve: when we change the JSONL
shape, we ship a new tool release, and the new release-version is
recorded as ``dcat_version``. Each record keeps its own copy because
the JSONL log is append-only — older records hold the version that
was current when they were appended, even after newer code rewrites
the file.

Compatibility expectations
--------------------------

- **Older records, newer tool**: always supported. The tool reads
  every historical version of the schema; migrations live in
  :mod:`dogcat.models` (e.g. ``_migrate_namespace``,
  ``_migrate_issue_type``).
- **Newer records, older tool**: best-effort. Unknown record types or
  fields are skipped/ignored where possible (see ``classify_record``
  and the ``data.get(key, default)`` pattern in ``dict_to_issue``),
  but new semantics may not be honored. A startup warning is emitted
  by :func:`warn_if_records_from_newer_version` so users aren't
  surprised.
- **Breaking changes**: bump the ``MAJOR`` component of the tool
  version. Until that happens, the schema is considered backward-
  compatible — readers can ignore the ``dcat_version`` value for
  parsing decisions.

Comparison rules
----------------

Versions are PEP 440 strings (e.g. ``0.11.7.post1.dev4+gabcd1234``).
For the "newer than current" check we only compare the leading
``MAJOR.MINOR.PATCH`` triple — pre/post/dev/local segments don't
indicate schema drift, just build provenance, and dragging in
``packaging.version`` for a single warning is overkill. If the regex
doesn't match (malformed version), the record is treated as
"unknown / older" and ignored.

Adding a new schema-affecting change
------------------------------------

1. Update the writer (``issue_to_dict``, ``proposal_to_dict``,
   storage append helpers) and bump the package version.
2. Update the reader to migrate or default the new field.
3. If older readers cannot safely ignore the change, raise
   :data:`SCHEMA_BREAKING_THRESHOLD` to the new MAJOR.MINOR (so the
   warning kicks in instead of silently corrupting state). Today the
   threshold is unused because no breaking change has shipped — the
   constant is documented here so future commits know where to put
   one.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from dogcat._version import version as _dcat_version

if TYPE_CHECKING:
    from collections.abc import Iterable

logger = logging.getLogger(__name__)

VersionTuple = tuple[int, int, int]

# Bump this only when a schema change is *not* backward compatible —
# i.e. an older tool would corrupt or misinterpret records written by
# the new tool. None means "no breaking change has shipped"; readers
# only warn when records are strictly newer than the running tool.
SCHEMA_BREAKING_THRESHOLD: VersionTuple | None = None

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)")


def parse_version(version: str | None) -> VersionTuple | None:
    """Extract the leading ``(MAJOR, MINOR, PATCH)`` triple from a version.

    Returns ``None`` for empty or unparseable inputs so callers can
    treat malformed records as "unknown / ignore".
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
