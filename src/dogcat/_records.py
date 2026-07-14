"""JSONL record (de)serialization and archive classification.

Pure functions that translate domain objects (:class:`~dogcat.models.Dependency`,
:class:`~dogcat.models.Link`) to and from their on-disk JSONL dict form, plus the
archive-membership decision for a single raw JSONL line. Extracted from
:class:`~dogcat.storage.JSONLStorage` so the god class shrinks toward cohesive
units and the serialization / classification rules live in one place and are
independently testable.

Issue serialization already lives in :func:`dogcat.models.issue_to_dict` /
:func:`dogcat.models.dict_to_issue`; this module covers the dependency and link
record shapes (both directions) plus the archive-line classifier.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import orjson

from dogcat._version import version as _dcat_version
from dogcat.constants import DEFAULT_NAMESPACE
from dogcat.models import (
    Dependency,
    DependencyType,
    Link,
    _safe_enum,
    classify_record,
)

_logger = logging.getLogger(__name__)

# Replay maps are keyed by the record's identity tuple so an ``op: remove``
# record can cancel the matching ``add`` during append-only log replay.
DepMap = dict[tuple[str, str, str], Dependency]
LinkMap = dict[tuple[str, str, str], Link]


def dependency_to_record(dep: Dependency, *, op: str = "add") -> dict[str, Any]:
    """Serialize a dependency to its JSONL dict form."""
    record: dict[str, Any] = {
        "record_type": "dependency",
        "dcat_version": _dcat_version,
        "issue_id": dep.issue_id,
        "depends_on_id": dep.depends_on_id,
        "type": dep.dep_type.value,
        "created_at": dep.created_at.isoformat(),
        "created_by": dep.created_by,
    }
    if op != "add":
        record["op"] = op
    return record


def link_to_record(link: Link, *, op: str = "add") -> dict[str, Any]:
    """Serialize a link to its JSONL dict form."""
    record: dict[str, Any] = {
        "record_type": "link",
        "dcat_version": _dcat_version,
        "from_id": link.from_id,
        "to_id": link.to_id,
        "link_type": link.link_type,
        "created_at": link.created_at.isoformat(),
        "created_by": link.created_by,
    }
    if op != "add":
        record["op"] = op
    return record


def parse_link_record(data: dict[str, Any], link_map: LinkMap) -> None:
    """Apply one link record (``add`` or ``remove`` op) to ``link_map``.

    Mutates the map in place during append-only log replay: ``remove`` cancels
    the matching ``add`` keyed on (from_id, to_id, link_type).
    """
    op = data.get("op", "add")
    key = (data["from_id"], data["to_id"], data.get("link_type", "relates_to"))
    if op == "remove":
        link_map.pop(key, None)
        return
    link_map[key] = Link(
        from_id=data["from_id"],
        to_id=data["to_id"],
        link_type=data.get("link_type", "relates_to"),
        created_at=datetime.fromisoformat(data["created_at"]),
        created_by=data.get("created_by"),
    )


def parse_dependency_record(data: dict[str, Any], dep_map: DepMap) -> None:
    """Apply one dependency record (``add`` or ``remove`` op) to ``dep_map``.

    Mutates the map in place during append-only log replay: ``remove`` cancels
    the matching ``add`` keyed on (issue_id, depends_on_id, type).
    """
    op = data.get("op", "add")
    key = (data["issue_id"], data["depends_on_id"], data["type"])
    if op == "remove":
        dep_map.pop(key, None)
        return
    dep_map[key] = Dependency(
        issue_id=data["issue_id"],
        depends_on_id=data["depends_on_id"],
        dep_type=_safe_enum(DependencyType, data["type"], "dependency.type"),
        created_at=datetime.fromisoformat(data["created_at"]),
        created_by=data.get("created_by"),
    )


@dataclass(frozen=True)
class ArchiveClassification:
    """Whether a JSONL line belongs in the archive, and its record type.

    ``record_type`` is the classified kind (``"issue"``, ``"dependency"``,
    ``"link"``, ``"event"``) when known, or ``None`` for a line that couldn't
    be parsed or classified. Callers use it to count archived deps/links.
    """

    archive: bool
    record_type: str | None = None


def classify_archived_line(
    stripped: bytes, archivable_ids: set[str]
) -> ArchiveClassification:
    """Decide whether a raw JSONL line should move to the archive.

    A link/dependency is archived only when *both* endpoints are archived; an
    event or issue is archived when its issue id is in ``archivable_ids``.

    Unparseable JSON, or a parseable-but-malformed record missing an expected
    key (e.g. a link row without ``from_id``, or an issue without ``id``), is
    kept in the source partition rather than raising — a single bad row must
    not abort the whole archive under the lock.
    """
    try:
        data = orjson.loads(stripped)
    except orjson.JSONDecodeError:
        return ArchiveClassification(archive=False)

    try:
        rtype = classify_record(data)
        if rtype == "link":
            archive = (
                data["from_id"] in archivable_ids and data["to_id"] in archivable_ids
            )
        elif rtype == "dependency":
            archive = (
                data["issue_id"] in archivable_ids
                and data["depends_on_id"] in archivable_ids
            )
        elif rtype == "event":
            archive = data.get("issue_id") in archivable_ids
        else:
            # Issue record — resolve full_id from the raw dict.
            if "namespace" in data:
                full_id = f"{data['namespace']}-{data['id']}"
            elif "-" in str(data.get("id", "")):
                full_id = data["id"]
            else:
                full_id = f"{DEFAULT_NAMESPACE}-{data['id']}"
            archive = full_id in archivable_ids
    except (KeyError, TypeError):
        _logger.warning(
            "Keeping malformed record during archive (missing expected key): %.200s",
            stripped,
        )
        return ArchiveClassification(archive=False)
    else:
        return ArchiveClassification(archive=archive, record_type=rtype)
