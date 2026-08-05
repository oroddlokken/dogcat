"""Data models for Dogcat issues using dataclasses."""

import logging
import re as _re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, TypedDict, TypeVar, cast

from dogcat.constants import DEFAULT_NAMESPACE


class IssueMetadata(TypedDict, total=False):
    """Documented shape of :attr:`Issue.metadata`.

    Known keys are ``manual`` and ``no_agent`` (both treated as boolean flags
    that exclude an issue from automated workflows). The dict permits other
    arbitrary keys for forward compatibility — TypedDict cannot enforce
    "extra keys allowed", so the field annotation stays ``dict[str, Any]``
    and this TypedDict serves as a documented schema reference.
    """

    manual: bool
    no_agent: bool


def is_manual_issue(metadata: dict[str, Any]) -> bool:
    """Return True if ``metadata`` marks the issue as manual / no-agent.

    Centralizes the ``metadata.get("manual") or metadata.get("no_agent")``
    idiom used in 10+ call sites; either flag has the same effect.
    """
    return bool(metadata.get("manual") or metadata.get("no_agent"))


def set_manual_flag(metadata: dict[str, Any], *, manual: bool) -> dict[str, Any]:
    """Toggle the ``manual`` flag on a metadata dict (returning a fresh copy).

    Always strips the legacy ``no_agent`` key so the two synonyms don't
    drift. Returns a new dict — callers assign it back rather than mutate
    the original so the caller's pre-change snapshot stays valid for
    diffing/event emission.
    """
    new_metadata = dict(metadata)
    new_metadata.pop("no_agent", None)
    if manual:
        new_metadata["manual"] = True
    else:
        new_metadata.pop("manual", None)
    return new_metadata


_logger = logging.getLogger(__name__)
_UNKNOWN_STATUS_EMOJI = "?"


class Status(str, Enum):
    """Issue status enumeration."""

    DRAFT = "draft"
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    BLOCKED = "blocked"
    DEFERRED = "deferred"
    CLOSED = "closed"
    TOMBSTONE = "tombstone"
    # Sentinel used when a record from a newer dcat version contains a status
    # this reader does not recognize; preserves forward-compat for _load().
    UNKNOWN = "unknown"


class IssueType(str, Enum):
    """Issue type enumeration."""

    TASK = "task"
    BUG = "bug"
    FEATURE = "feature"
    STORY = "story"
    CHORE = "chore"
    EPIC = "epic"
    QUESTION = "question"
    UNKNOWN = "unknown"


class DependencyType(str, Enum):
    """Dependency type enumeration."""

    BLOCKS = "blocks"
    PARENT_CHILD = "parent-child"
    RELATED = "related"
    UNKNOWN = "unknown"


_E = TypeVar("_E", bound=Enum)

# value -> member maps, built once per enum class. ``dict_to_issue`` runs
# _safe_enum for every record in the store, and ``Enum.__call__`` is an
# order of magnitude slower than a dict hit.
_ENUM_VALUE_MAPS: dict[type[Enum], dict[object, Enum]] = {}


def _safe_enum(enum_cls: type[_E], raw_value: object, field_name: str) -> _E:
    """Coerce ``raw_value`` to a member of ``enum_cls``, falling back to UNKNOWN.

    Forward-compatibility hook: a record from a newer dcat version may carry
    an enum value this reader does not recognize. Rather than aborting the
    entire load (the JSONL is written only through the CLI, never hand-edited),
    log a warning and return the ``UNKNOWN`` sentinel so the rest of the file
    parses.
    """
    value_map = _ENUM_VALUE_MAPS.get(enum_cls)
    if value_map is None:
        value_map = {member.value: member for member in enum_cls}
        _ENUM_VALUE_MAPS[enum_cls] = value_map
    try:
        member = value_map.get(raw_value)
    except TypeError:
        # Unhashable raw_value — let Enum.__call__ produce the ValueError.
        member = None
    if member is not None:
        return cast("_E", member)
    try:
        return enum_cls(raw_value)
    except ValueError:
        _logger.warning(
            "Unknown %s value %r — coerced to UNKNOWN sentinel "
            "(record likely written by a newer dcat version)",
            field_name,
            raw_value,
        )
        return enum_cls["UNKNOWN"]


class LinkType(str, Enum):
    """Built-in link types between issues.

    The :class:`Link` ``link_type`` field accepts either a :class:`LinkType`
    member (recommended for known relations) or a free-form string for custom,
    user-defined relations. Use :func:`link_type_value` to convert either form
    to a string for serialization.
    """

    RELATES_TO = "relates_to"
    DUPLICATES = "duplicates"
    BLOCKS = "blocks"
    DEPENDS_ON = "depends_on"


def link_type_value(value: "LinkType | str") -> str:
    """Return the string form of a built-in :class:`LinkType` or custom string."""
    return value.value if isinstance(value, LinkType) else value


ISSUE_STATUS_EMOJIS: dict[Status, str] = {
    Status.DRAFT: "✎",
    Status.OPEN: "●",
    Status.IN_PROGRESS: "◐",
    Status.IN_REVIEW: "?",
    Status.BLOCKED: "■",
    Status.DEFERRED: "◇",
    Status.CLOSED: "✓",
    Status.TOMBSTONE: "☠",
}


@dataclass
class Comment:
    """A comment on an issue."""

    id: str
    issue_id: str
    author: str
    text: str
    created_at: datetime = field(default_factory=lambda: datetime.now().astimezone())


@dataclass
class Dependency:
    """A dependency relationship between issues."""

    issue_id: str
    depends_on_id: str
    dep_type: DependencyType
    created_at: datetime = field(default_factory=lambda: datetime.now().astimezone())
    created_by: str | None = None

    def to_export_dict(self) -> dict[str, Any]:
        """Serialize to the ``dcat admin export`` shape.

        Same field set as the JSONL record but without the storage-only
        ``record_type`` / ``dcat_version`` envelope, so the export path and
        the store never drift on which fields a dependency carries.
        """
        return {
            "issue_id": self.issue_id,
            "depends_on_id": self.depends_on_id,
            "type": self.dep_type.value,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
        }


@dataclass
class Link:
    """A general link/relation between issues."""

    from_id: str
    to_id: str
    # Accept either the LinkType enum (preferred for built-in relations) or a
    # plain string (custom user-defined relations). Serialization uses the
    # string form via ``link_type_value()``.
    link_type: "LinkType | str" = LinkType.RELATES_TO
    created_at: datetime = field(default_factory=lambda: datetime.now().astimezone())
    created_by: str | None = None

    def to_export_dict(self) -> dict[str, Any]:
        """Serialize to the ``dcat admin export`` shape.

        Mirror of :meth:`Dependency.to_export_dict` for links.
        """
        return {
            "from_id": self.from_id,
            "to_id": self.to_id,
            "link_type": self.link_type,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
        }


@dataclass
class Issue:
    """An issue in the tracking system."""

    id: str  # The hash part only (e.g., "4kzj")
    title: str
    namespace: str = DEFAULT_NAMESPACE  # The namespace/prefix (e.g., "dc")
    description: str | None = None
    status: Status = Status.OPEN
    priority: int = 2  # 0-4 range, lower is higher priority
    issue_type: IssueType = IssueType.TASK
    owner: str | None = None
    parent: str | None = None  # Parent issue ID
    labels: list[str] = field(default_factory=list[str])
    external_ref: str | None = None
    design: str | None = None
    acceptance: str | None = None
    notes: str | None = None
    closed_reason: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now().astimezone())
    created_by: str | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now().astimezone())
    updated_by: str | None = None
    closed_at: datetime | None = None
    closed_by: str | None = None
    deleted_at: datetime | None = None
    deleted_by: str | None = None
    deleted_reason: str | None = None
    original_type: IssueType | None = None  # For tombstones
    comments: list[Comment] = field(default_factory=list[Comment])
    duplicate_of: str | None = None  # ID of original if this is a duplicate
    snoozed_until: datetime | None = (
        None  # Snooze: hide from list/ready until this time
    )
    metadata: dict[str, Any] = field(default_factory=dict[str, Any])

    def is_closed(self) -> bool:
        """Check if the issue is closed."""
        return self.status == Status.CLOSED

    def is_tombstone(self) -> bool:
        """Check if the issue is a tombstone (soft deleted)."""
        return self.status == Status.TOMBSTONE

    def is_duplicate(self) -> bool:
        """Check if this issue is marked as a duplicate.

        Kept for parity with :meth:`is_closed` / :meth:`is_tombstone` as a
        member of the issue-predicate family.
        """
        return self.duplicate_of is not None

    @property
    def full_id(self) -> str:
        """Get the full ID including namespace (e.g., 'dc-4kzj')."""
        return f"{self.namespace}-{self.id}"

    def get_status_emoji(self) -> str:
        """Get an emoji representation of the status."""
        return ISSUE_STATUS_EMOJIS.get(self.status, _UNKNOWN_STATUS_EMOJI)


class ProposalStatus(str, Enum):
    """Proposal status enumeration."""

    OPEN = "open"
    CLOSED = "closed"
    TOMBSTONE = "tombstone"
    UNKNOWN = "unknown"


PROPOSAL_STATUS_EMOJIS: dict["ProposalStatus", str] = {
    ProposalStatus.OPEN: "●",
    ProposalStatus.CLOSED: "✓",
    ProposalStatus.TOMBSTONE: "☠",
}


@dataclass
class Proposal:
    """A cross-repo proposal stored in inbox.jsonl."""

    id: str  # The hash part only (e.g., "4kzj")
    title: str
    namespace: str = DEFAULT_NAMESPACE  # The namespace/prefix (e.g., "dogcat")
    description: str | None = None
    proposed_by: str | None = None
    source_repo: str | None = None
    status: ProposalStatus = ProposalStatus.OPEN
    created_at: datetime = field(default_factory=lambda: datetime.now().astimezone())
    updated_at: datetime = field(default_factory=lambda: datetime.now().astimezone())
    closed_at: datetime | None = None
    closed_by: str | None = None
    closed_reason: str | None = None
    resolved_issue: str | None = None  # ID of issue created from this proposal
    deleted_at: datetime | None = None
    deleted_by: str | None = None

    def is_closed(self) -> bool:
        """Check if the proposal is closed."""
        return self.status == ProposalStatus.CLOSED

    def is_tombstone(self) -> bool:
        """Check if the proposal is a tombstone (soft deleted)."""
        return self.status == ProposalStatus.TOMBSTONE

    @property
    def full_id(self) -> str:
        """Get the full ID including namespace (e.g., 'dogcat-inbox-4kzj')."""
        return f"{self.namespace}-inbox-{self.id}"

    def get_status_emoji(self) -> str:
        """Get an emoji representation of the status."""
        return PROPOSAL_STATUS_EMOJIS.get(self.status, _UNKNOWN_STATUS_EMOJI)


# Sentinel for "field not set" on UpdateRequest. ``None`` is not used because
# clearing a field (e.g. removing a parent or unsnoozing) requires explicitly
# passing ``None`` as the new value.
class _UnsetType:
    """Sentinel type so unset fields are distinguishable from explicit ``None``.

    The module constructs exactly one instance (``UNSET``) below, so the old
    ``__new__``/``_instance`` singleton guard could never fire — identity
    checks (``is UNSET``) already hold against that single instance.
    """

    def __repr__(self) -> str:
        return "UNSET"

    def __bool__(self) -> bool:
        return False


UNSET: Any = _UnsetType()


@dataclass
class FilterSpec:
    """Typed filter parameters for :meth:`JSONLStorage.list`.

    The legacy untyped ``dict[str, Any]`` shape is still accepted by
    ``list()`` for backwards compatibility (it converts via :meth:`from_dict`),
    but new callers should construct a ``FilterSpec`` so unknown keys and
    type mismatches are caught at construction.
    """

    status: "Status | str | None" = None
    priority: int | None = None
    issue_type: str | None = None  # mapped from legacy 'type' key
    label: "list[str] | str | None" = None
    owner: str | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "FilterSpec":
        """Build a FilterSpec from the legacy dict shape (rejects unknown keys)."""
        # Translate legacy 'type' alias to 'issue_type' so the dataclass field
        # name matches the Issue field for clarity.
        legacy_aliases = {"type": "issue_type"}
        normalized: dict[str, Any] = {}
        known = {"status", "priority", "issue_type", "label", "owner"}
        for key, value in raw.items():
            mapped = legacy_aliases.get(key, key)
            if mapped not in known:
                msg = (
                    f"Unknown filter key {key!r}. Valid keys: "
                    f"status, priority, type, label, owner"
                )
                raise ValueError(msg)
            normalized[mapped] = value
        return cls(**normalized)


@dataclass
class UpdateRequest:
    """Typed bag of optional field updates for :meth:`JSONLStorage.update`.

    Each field defaults to :data:`UNSET`; only fields that are explicitly
    assigned propagate via :meth:`to_dict`. ``None`` is a *meaningful* value
    for fields that support clearing (``parent``, ``snoozed_until``,
    ``duplicate_of``), so the ``UNSET`` sentinel is required to distinguish
    "leave alone" from "clear".

    Field names mirror :data:`JSONLStorage.UPDATABLE_FIELDS`; passing an
    unknown field is impossible because the dataclass schema rejects it.
    """

    title: Any = UNSET
    description: Any = UNSET
    status: Any = UNSET
    priority: Any = UNSET
    issue_type: Any = UNSET
    owner: Any = UNSET
    parent: Any = UNSET
    labels: Any = UNSET
    external_ref: Any = UNSET
    design: Any = UNSET
    acceptance: Any = UNSET
    notes: Any = UNSET
    closed_reason: Any = UNSET
    updated_by: Any = UNSET
    snoozed_until: Any = UNSET
    duplicate_of: Any = UNSET
    metadata: Any = UNSET

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "UpdateRequest":
        """Build an UpdateRequest from a dict, rejecting unknown field names.

        Mirrors :meth:`FilterSpec.from_dict`: lets callers that assemble a
        dynamic dict of changes (e.g. the TUI detail panel) route through the
        typed boundary so a mistyped field name fails loudly here instead of
        being silently ignored by :meth:`JSONLStorage.update`.
        """
        from dataclasses import fields as _fields

        known = {f.name for f in _fields(cls)}
        unknown = set(raw) - known
        if unknown:
            msg = (
                f"Unknown update field(s): {', '.join(sorted(unknown))}. "
                f"Valid fields: {', '.join(sorted(known))}"
            )
            raise ValueError(msg)
        return cls(**raw)

    def to_dict(self) -> dict[str, Any]:
        """Return a dict containing only fields that were explicitly set."""
        from dataclasses import fields as _fields

        return {
            f.name: getattr(self, f.name)
            for f in _fields(self)
            if getattr(self, f.name) is not UNSET
        }

    def is_empty(self) -> bool:
        """Return True when no field has been assigned a value."""
        return not self.to_dict()


def validate_priority(priority: Any) -> None:
    """Validate that priority is in valid range (0-4)."""
    # bool is an int subclass — exclude it explicitly so True/False can't
    # slip through and persist (e.g. via storage.create() / validate_issue).
    # storage._coerce_update_value also guards this on the update path.
    # ValueError (not TypeError) keeps the public contract stable for
    # callers that already catch ValueError on out-of-range values.
    if isinstance(priority, bool) or not isinstance(priority, int):
        msg = "Priority must be an integer between 0 and 4"
        raise ValueError(msg)  # noqa: TRY004
    if priority < 0 or priority > 4:
        msg = "Priority must be an integer between 0 and 4"
        raise ValueError(msg)


def validate_status(status: Any) -> None:
    """Validate that status is a valid Status enum value."""
    if not isinstance(status, Status):
        msg = f"Status must be a Status enum value, got {status}"
        raise TypeError(msg)


def validate_issue_type(issue_type: Any) -> None:
    """Validate that issue_type is a valid IssueType enum value."""
    if not isinstance(issue_type, IssueType):
        msg = f"IssueType must be an IssueType enum value, got {issue_type}"
        raise TypeError(msg)


# C0 controls (\x00-\x1f) minus \t/\n, plus DEL (\x7f) and C1 (\x80-\x9f).
_control_char_pattern = _re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def strip_control_bytes(text: str | None) -> str | None:
    r"""Strip C0/C1 control bytes from ``text`` (keep ``\\t`` and ``\\n``).

    Defense against terminal-escape injection via title/description/etc.
    Used by validate_issue/validate_proposal so the storage layer can never
    persist a record carrying ``\\x1b[2J`` or other prompt-injection payloads.
    Render-side has a complementary escape helper as defense-in-depth.
    """
    if text is None:
        return None
    return _control_char_pattern.sub("", text)


def sanitize_for_terminal(text: str | None) -> str:
    r"""Render-time escape: visualize control bytes that slipped through.

    Defense-in-depth — even if a record predates the validate-time strip,
    rendering it via this helper produces ``\\xNN`` placeholders instead of
    executing the escape sequence.
    """
    if not text:
        return text or ""
    out: list[str] = []
    for ch in text:
        if ch in {"\t", "\n"}:
            out.append(ch)
            continue
        cp = ord(ch)
        if cp < 0x20 or cp == 0x7F or 0x80 <= cp <= 0x9F:
            out.append(f"\\x{cp:02x}")
        else:
            out.append(ch)
    return "".join(out)


def _validate_text_caps(
    *,
    title: str | None,
    description: str | None,
    namespace: str,
    label: str,
) -> None:
    """Apply MAX_TITLE_LEN / MAX_DESC_LEN / namespace-rule shared with the web form."""
    from dogcat.constants import (
        MAX_DESC_LEN,
        MAX_NAMESPACE_LEN,
        MAX_TITLE_LEN,
        is_valid_namespace,
    )

    if title is not None and len(title) > MAX_TITLE_LEN:
        msg = (
            f"{label} title exceeds {MAX_TITLE_LEN}-character limit "
            f"({len(title)} chars)"
        )
        raise ValueError(msg)
    if description is not None and len(description) > MAX_DESC_LEN:
        msg = (
            f"{label} description exceeds {MAX_DESC_LEN}-character limit "
            f"({len(description)} chars)"
        )
        raise ValueError(msg)
    if not is_valid_namespace(namespace):
        msg = (
            f"{label} namespace {namespace!r} is invalid "
            f"(must match [A-Za-z0-9_-]+, 1-{MAX_NAMESPACE_LEN} chars)"
        )
        raise ValueError(msg)


def validate_issue(issue: Issue) -> None:
    """Validate that an issue has all required fields and valid data.

    Mutates the issue in place to strip terminal-escape control bytes from
    string fields (title, description, notes, owner, labels, comment text).
    Stripping happens at the storage boundary so no record can persist a
    prompt-injection payload — see :func:`strip_control_bytes`.
    """
    if not issue.title or not isinstance(
        issue.title,
        str,
    ):  # pyright: ignore[reportUnnecessaryIsInstance]
        msg = "Issue must have a non-empty title string"
        raise ValueError(msg)

    validate_priority(issue.priority)
    validate_status(issue.status)
    validate_issue_type(issue.issue_type)

    # Strip control bytes from every persisted string field (in-place).
    issue.title = strip_control_bytes(issue.title) or ""
    issue.description = strip_control_bytes(issue.description)
    issue.notes = strip_control_bytes(issue.notes)
    issue.owner = strip_control_bytes(issue.owner)
    issue.closed_reason = strip_control_bytes(issue.closed_reason)
    issue.deleted_reason = strip_control_bytes(issue.deleted_reason)
    issue.labels = [strip_control_bytes(lb) or "" for lb in issue.labels]
    for comment in issue.comments:
        comment.text = strip_control_bytes(comment.text) or ""
        comment.author = strip_control_bytes(comment.author) or ""

    if not issue.title:
        msg = "Issue title is empty after stripping control characters"
        raise ValueError(msg)

    _validate_text_caps(
        title=issue.title,
        description=issue.description,
        namespace=issue.namespace,
        label="Issue",
    )


def validate_proposal(proposal: Proposal) -> None:
    """Validate that a proposal has all required fields and valid data.

    See :func:`validate_issue` — same control-byte stripping applies here.
    """
    if not proposal.title or not isinstance(
        proposal.title,
        str,
    ):  # pyright: ignore[reportUnnecessaryIsInstance]
        msg = "Proposal must have a non-empty title string"
        raise ValueError(msg)

    if not isinstance(proposal.status, ProposalStatus):  # pyright: ignore[reportUnnecessaryIsInstance]
        msg = (
            f"Proposal status must be a ProposalStatus enum value, "
            f"got {proposal.status}"
        )
        raise TypeError(msg)

    proposal.title = strip_control_bytes(proposal.title) or ""
    proposal.description = strip_control_bytes(proposal.description)
    proposal.proposed_by = strip_control_bytes(proposal.proposed_by)
    proposal.source_repo = strip_control_bytes(proposal.source_repo)
    proposal.closed_reason = strip_control_bytes(proposal.closed_reason)

    if not proposal.title:
        msg = "Proposal title is empty after stripping control characters"
        raise ValueError(msg)

    _validate_text_caps(
        title=proposal.title,
        description=proposal.description,
        namespace=proposal.namespace,
        label="Proposal",
    )


# ---------------------------------------------------------------------------
# Backward-compatible re-exports
# ---------------------------------------------------------------------------
# The JSONL (de)serialization helpers moved to dogcat.models_serde. Callers
# still do ``from dogcat.models import issue_to_dict`` (tests also import the
# ``_migrate_*`` helpers), so expose the names here. models_serde imports the
# dataclasses from this module, so importing it eagerly would be a circular
# import; resolution is instead deferred to first attribute access via module
# ``__getattr__`` (PEP 562) — whichever module is imported first finishes
# loading before the other is pulled in, so neither import order deadlocks. The
# ``TYPE_CHECKING`` re-imports keep the names statically visible to type
# checkers without running at import time. The ``X as X`` spelling is the PEP
# 484 explicit re-export marker — without it pyright treats these as private to
# this module and rejects ``from dogcat.models import issue_to_dict`` — so
# PLC0414 ("import alias does not rename") is silenced rather than obeyed.
if TYPE_CHECKING:
    from dogcat.models_serde import (
        _migrate_close_reason as _migrate_close_reason,  # noqa: PLC0414
    )
    from dogcat.models_serde import (
        _migrate_notes as _migrate_notes,  # noqa: PLC0414
    )
    from dogcat.models_serde import (
        classify_record as classify_record,  # noqa: PLC0414
    )
    from dogcat.models_serde import (
        dict_to_issue as dict_to_issue,  # noqa: PLC0414
    )
    from dogcat.models_serde import (
        dict_to_proposal as dict_to_proposal,  # noqa: PLC0414
    )
    from dogcat.models_serde import (
        issue_to_dict as issue_to_dict,  # noqa: PLC0414
    )
    from dogcat.models_serde import (
        proposal_to_dict as proposal_to_dict,  # noqa: PLC0414
    )

_SERDE_REEXPORTS = frozenset(
    {
        "issue_to_dict",
        "dict_to_issue",
        "proposal_to_dict",
        "dict_to_proposal",
        "classify_record",
        "_migrate_close_reason",
        "_migrate_notes",
    },
)


def __getattr__(name: str) -> object:
    """Lazily resolve the serialization helpers re-exported from models_serde."""
    if name in _SERDE_REEXPORTS:
        from dogcat import models_serde

        return getattr(models_serde, name)
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
