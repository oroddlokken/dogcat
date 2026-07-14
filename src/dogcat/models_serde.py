"""JSONL (de)serialization for the domain models.

Split out of :mod:`dogcat.models` so the dataclass definitions and
the serialization helpers live in separate modules. This holds the issue /
proposal dict<->object converters, the ``_migrate_*`` backward-compat helpers,
and ``classify_record``.

Import direction is one-way at the source level — this module imports the
dataclasses from :mod:`dogcat.models`. For backward compatibility ``models``
re-exports these names at the bottom of its own module (so existing
``from dogcat.models import issue_to_dict`` imports keep working); that
re-export is the *only* importer of this module, which keeps the cycle safe:
``dogcat.models`` is always the entry point and is fully defined before its
bottom re-export triggers loading this module.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from dogcat._version import version as _dcat_version
from dogcat.constants import DEFAULT_NAMESPACE
from dogcat.models import (
    Comment,
    Issue,
    IssueType,
    Proposal,
    ProposalStatus,
    Status,
    _safe_enum,
    validate_proposal,
)

_logger = logging.getLogger(__name__)
_KNOWN_RECORD_TYPES = frozenset(
    {"issue", "dependency", "link", "event", "proposal"},
)


def issue_to_dict(issue: Issue) -> dict[str, Any]:
    """Convert an Issue to a dictionary, serializing datetimes."""
    status_value = issue.status.value
    issue_type_value = issue.issue_type.value

    return {
        "record_type": "issue",
        "dcat_version": _dcat_version,
        "namespace": issue.namespace,
        "id": issue.id,
        "title": issue.title,
        "description": issue.description,
        "status": status_value,
        "priority": issue.priority,
        "issue_type": issue_type_value,
        "owner": issue.owner,
        "parent": issue.parent,
        "labels": issue.labels,
        "external_ref": issue.external_ref,
        "design": issue.design,
        "acceptance": issue.acceptance,
        "notes": issue.notes,
        "closed_reason": issue.closed_reason,
        "created_at": issue.created_at.isoformat(),
        "created_by": issue.created_by,
        "updated_at": issue.updated_at.isoformat(),
        "updated_by": issue.updated_by,
        "closed_at": issue.closed_at.isoformat() if issue.closed_at else None,
        "closed_by": issue.closed_by,
        "deleted_at": issue.deleted_at.isoformat() if issue.deleted_at else None,
        "deleted_by": issue.deleted_by,
        "deleted_reason": issue.deleted_reason,
        "original_type": issue.original_type.value if issue.original_type else None,
        "comments": [
            {
                "id": comment.id,
                "issue_id": comment.issue_id,
                "author": comment.author,
                "text": comment.text,
                "created_at": comment.created_at.isoformat(),
            }
            for comment in issue.comments
        ],
        "duplicate_of": issue.duplicate_of,
        "snoozed_until": (
            issue.snoozed_until.isoformat() if issue.snoozed_until else None
        ),
        "metadata": issue.metadata,
    }


def _migrate_close_reason(notes: str | None, closed_reason: str | None) -> str | None:
    """Extract closed_reason from legacy notes if not already set."""
    if closed_reason is not None:
        return closed_reason
    if notes and "\n\nClosed: " in notes:
        parts = notes.split("\n\nClosed: ")
        return parts[-1].strip() or None
    return None


def _migrate_notes(notes: str | None, closed_reason: str | None) -> str | None:
    """Strip legacy close reason from notes if closed_reason is not yet a field."""
    if closed_reason is not None:
        # Already migrated; notes are clean
        return notes
    if notes and "\n\nClosed: " in notes:
        parts = notes.split("\n\nClosed: ")
        cleaned = "\n\nClosed: ".join(parts[:-1]).strip()
        return cleaned or None
    return notes


def _migrate_namespace(data: dict[str, Any]) -> tuple[str, str]:
    """Resolve (namespace, issue_id) from new or legacy id format."""
    if "namespace" in data:
        return data["namespace"], data["id"]
    full_id = data["id"]
    if "-" in full_id:
        # Split on last hyphen to handle multi-part namespaces
        namespace, issue_id = full_id.rsplit("-", 1)
        return namespace, issue_id
    return DEFAULT_NAMESPACE, full_id


def _migrate_issue_type(data: dict[str, Any]) -> tuple[str, str]:
    """Resolve (issue_type, status), migrating legacy 'draft' / 'subtask' types."""
    raw_issue_type = data.get("issue_type", IssueType.TASK.value)
    raw_status = data.get("status", Status.OPEN.value)
    # Legacy issue_type=draft -> status=draft, issue_type=task
    if raw_issue_type == "draft":
        raw_issue_type = IssueType.TASK.value
        if raw_status not in (
            Status.DRAFT.value,
            Status.CLOSED.value,
            Status.TOMBSTONE.value,
        ):
            raw_status = Status.DRAFT.value
    # Legacy issue_type=subtask -> issue_type=task
    if raw_issue_type == "subtask":
        raw_issue_type = IssueType.TASK.value
    return raw_issue_type, raw_status


def _migrate_original_type(data: dict[str, Any]) -> str | None:
    """Migrate legacy original_type values stored on tombstones."""
    raw = data.get("original_type")
    if raw in ("draft", "subtask"):
        return IssueType.TASK.value
    return raw


def dict_to_issue(data: dict[str, Any]) -> Issue:
    """Convert a dictionary to an Issue, deserializing datetimes."""
    namespace, issue_id = _migrate_namespace(data)

    created_at = datetime.fromisoformat(data["created_at"])
    updated_at = datetime.fromisoformat(data["updated_at"])
    closed_at = (
        datetime.fromisoformat(data["closed_at"]) if data.get("closed_at") else None
    )
    deleted_at = (
        datetime.fromisoformat(data["deleted_at"]) if data.get("deleted_at") else None
    )

    comments: list[Comment] = [
        Comment(
            id=cd["id"],
            issue_id=cd["issue_id"],
            author=cd["author"],
            text=cd["text"],
            created_at=datetime.fromisoformat(cd["created_at"]),
        )
        for cd in data.get("comments", [])
    ]

    raw_issue_type, raw_status = _migrate_issue_type(data)
    raw_original_type = _migrate_original_type(data)

    # Accept both old (close_reason / delete_reason) and new
    # (closed_reason / deleted_reason) keys for backward compatibility.
    raw_closed_reason = data.get("closed_reason", data.get("close_reason"))
    raw_deleted_reason = data.get("deleted_reason", data.get("delete_reason"))

    return Issue(
        id=issue_id,
        title=data["title"],
        namespace=namespace,
        description=data.get("description"),
        status=_safe_enum(Status, raw_status, "status"),
        priority=data.get("priority", 2),  # Default priority defined in constants
        issue_type=_safe_enum(IssueType, raw_issue_type, "issue_type"),
        owner=data.get("owner"),
        parent=data.get("parent"),
        labels=data.get("labels", []),
        external_ref=data.get("external_ref"),
        design=data.get("design"),
        acceptance=data.get("acceptance"),
        notes=_migrate_notes(data.get("notes"), raw_closed_reason),
        closed_reason=_migrate_close_reason(data.get("notes"), raw_closed_reason),
        created_at=created_at,
        created_by=data.get("created_by"),
        updated_at=updated_at,
        updated_by=data.get("updated_by"),
        closed_at=closed_at,
        closed_by=data.get("closed_by"),
        deleted_at=deleted_at,
        deleted_by=data.get("deleted_by"),
        deleted_reason=raw_deleted_reason,
        original_type=(
            _safe_enum(IssueType, raw_original_type, "original_type")
            if raw_original_type
            else None
        ),
        comments=comments,
        duplicate_of=data.get("duplicate_of"),
        snoozed_until=(
            datetime.fromisoformat(data["snoozed_until"])
            if data.get("snoozed_until")
            else None
        ),
        metadata=data.get("metadata", {}),
    )


def precheck_issue_record(data: dict[str, Any]) -> str:
    """Verify ``data`` can be materialized by :func:`dict_to_issue`; return its full id.

    Performs every operation in ``dict_to_issue`` that can raise — required
    keys, datetime parses, the legacy-notes migration — WITHOUT constructing
    Issue/Comment objects. ``JSONLStorage._load`` runs this eagerly so
    malformed records are rejected at load time (landing in ``_bad_lines``
    exactly as before), while the expensive construction is deferred to
    first access via :class:`~dogcat._lazy_issues.LazyIssueMap`.

    Must stay in sync with ``dict_to_issue``'s failure modes —
    ``tests/test_models.py`` has a consistency test asserting both raise on
    the same corrupt records.

    Returns:
        The record's full id (``namespace-id``), the replay map key.

    Raises:
        KeyError, ValueError, TypeError, AttributeError: the same failure
            modes ``dict_to_issue`` would hit on this record.
    """
    namespace, issue_id = _migrate_namespace(data)
    _ = data["title"]

    datetime.fromisoformat(data["created_at"])
    datetime.fromisoformat(data["updated_at"])
    for key in ("closed_at", "deleted_at", "snoozed_until"):
        if data.get(key):
            datetime.fromisoformat(data[key])

    # _migrate_notes / _migrate_close_reason do `"..." in notes`
    notes = data.get("notes")
    if notes is not None and not isinstance(notes, str):
        msg = f"notes must be a string, got {type(notes).__name__}"
        raise TypeError(msg)

    for cd in data.get("comments", []):
        _ = cd["id"], cd["issue_id"], cd["author"], cd["text"]
        datetime.fromisoformat(cd["created_at"])

    return f"{namespace}-{issue_id}"


def proposal_to_dict(proposal: Proposal) -> dict[str, Any]:
    """Convert a Proposal to a dictionary, serializing datetimes."""
    return {
        "record_type": "proposal",
        "dcat_version": _dcat_version,
        "namespace": proposal.namespace,
        "id": proposal.id,
        "title": proposal.title,
        "description": proposal.description,
        "proposed_by": proposal.proposed_by,
        "source_repo": proposal.source_repo,
        "status": proposal.status.value,
        "created_at": proposal.created_at.isoformat(),
        "updated_at": proposal.updated_at.isoformat(),
        "closed_at": proposal.closed_at.isoformat() if proposal.closed_at else None,
        "closed_by": proposal.closed_by,
        "closed_reason": proposal.closed_reason,
        "resolved_issue": proposal.resolved_issue,
        "deleted_at": proposal.deleted_at.isoformat() if proposal.deleted_at else None,
        "deleted_by": proposal.deleted_by,
    }


def dict_to_proposal(data: dict[str, Any]) -> Proposal:
    """Convert a dictionary to a Proposal, deserializing datetimes."""
    created_at = datetime.fromisoformat(data["created_at"])
    updated_at = (
        datetime.fromisoformat(data["updated_at"])
        if data.get("updated_at")
        else created_at
    )
    closed_at = (
        datetime.fromisoformat(data["closed_at"]) if data.get("closed_at") else None
    )
    deleted_at = (
        datetime.fromisoformat(data["deleted_at"]) if data.get("deleted_at") else None
    )

    proposal = Proposal(
        id=data["id"],
        title=data["title"],
        namespace=data.get("namespace", DEFAULT_NAMESPACE),
        description=data.get("description"),
        proposed_by=data.get("proposed_by"),
        source_repo=data.get("source_repo"),
        status=_safe_enum(ProposalStatus, data.get("status", "open"), "status"),
        created_at=created_at,
        updated_at=updated_at,
        closed_at=closed_at,
        closed_by=data.get("closed_by"),
        closed_reason=data.get("closed_reason", data.get("close_reason")),
        resolved_issue=data.get("resolved_issue"),
        deleted_at=deleted_at,
        deleted_by=data.get("deleted_by"),
    )
    validate_proposal(proposal)
    return proposal


def classify_record(data: dict[str, Any]) -> str:
    """Classify a JSONL record as 'issue', 'dependency', 'link', 'event', 'proposal'.

    Checks for an explicit ``record_type`` field first, then falls back to
    field-sniffing for backward compatibility with older records.

    Returns ``"unknown"`` (and logs a warning) when ``record_type`` is set
    to a value outside :data:`_KNOWN_RECORD_TYPES`. Callers compare against
    specific strings, so unknown records are skipped rather than silently
    misclassified as ``"issue"`` and merged with the wrong semantics.
    """
    explicit = data.get("record_type")
    if explicit is not None:
        if explicit in _KNOWN_RECORD_TYPES:
            return explicit  # type: ignore[return-value]
        _logger.warning(
            "Unknown record_type %r — skipping. "
            "Add it to _KNOWN_RECORD_TYPES in models_serde.py and update the "
            "merge driver / loaders if this is a new record kind.",
            explicit,
        )
        return "unknown"

    if "from_id" in data and "to_id" in data:
        return "link"
    if "issue_id" in data and "depends_on_id" in data:
        return "dependency"
    return "issue"
