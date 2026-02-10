"""Data models for Dogcat issues using dataclasses."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from dogcat._version import version as _dcat_version


class Status(str, Enum):
    """Issue status enumeration."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    BLOCKED = "blocked"
    DEFERRED = "deferred"
    CLOSED = "closed"
    TOMBSTONE = "tombstone"


class IssueType(str, Enum):
    """Issue type enumeration."""

    TASK = "task"
    BUG = "bug"
    FEATURE = "feature"
    STORY = "story"
    CHORE = "chore"
    EPIC = "epic"
    SUBTASK = "subtask"
    QUESTION = "question"
    DRAFT = "draft"


class DependencyType(str, Enum):
    """Dependency type enumeration."""

    BLOCKS = "blocks"
    PARENT_CHILD = "parent-child"
    RELATED = "related"


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


@dataclass
class Link:
    """A general link/relation between issues."""

    from_id: str
    to_id: str
    link_type: str = "relates_to"  # relates_to, duplicates, blocks, depends_on, etc.
    created_at: datetime = field(default_factory=lambda: datetime.now().astimezone())
    created_by: str | None = None


@dataclass
class Issue:
    """An issue in the tracking system."""

    id: str  # The hash part only (e.g., "4kzj")
    title: str
    namespace: str = "dc"  # The namespace/prefix (e.g., "dc")
    description: str | None = None
    status: Status = Status.OPEN
    priority: int = 2  # 0-4 range, lower is higher priority
    issue_type: IssueType = IssueType.TASK
    owner: str | None = None
    parent: str | None = None  # Parent issue ID for subtasks
    labels: list[str] = field(default_factory=list[str])
    external_ref: str | None = None
    design: str | None = None
    acceptance: str | None = None
    notes: str | None = None
    close_reason: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now().astimezone())
    created_by: str | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now().astimezone())
    updated_by: str | None = None
    closed_at: datetime | None = None
    closed_by: str | None = None
    deleted_at: datetime | None = None
    deleted_by: str | None = None
    delete_reason: str | None = None
    original_type: IssueType | None = None  # For tombstones
    comments: list[Comment] = field(default_factory=list[Comment])
    duplicate_of: str | None = None  # ID of original if this is a duplicate
    metadata: dict[str, Any] = field(default_factory=dict[str, Any])

    def is_closed(self) -> bool:
        """Check if the issue is closed."""
        return self.status == Status.CLOSED

    def is_tombstone(self) -> bool:
        """Check if the issue is a tombstone (soft deleted)."""
        return self.status == Status.TOMBSTONE

    def is_duplicate(self) -> bool:
        """Check if this issue is marked as a duplicate."""
        return self.duplicate_of is not None

    @property
    def full_id(self) -> str:
        """Get the full ID including namespace (e.g., 'dc-4kzj')."""
        return f"{self.namespace}-{self.id}"

    def get_status_emoji(self) -> str:
        """Get an emoji representation of the status."""
        status_emojis = {
            Status.OPEN: "●",
            Status.IN_PROGRESS: "◐",
            Status.IN_REVIEW: "?",
            Status.BLOCKED: "■",
            Status.DEFERRED: "◇",
            Status.CLOSED: "✓",
            Status.TOMBSTONE: "☠",
        }
        return status_emojis.get(self.status, "?")


def validate_priority(priority: Any) -> None:
    """Validate that priority is in valid range (0-4)."""
    if not isinstance(priority, int) or priority < 0 or priority > 4:
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


def validate_issue(issue: Issue) -> None:
    """Validate that an issue has all required fields and valid data."""
    if not issue.title or not isinstance(
        issue.title,
        str,
    ):  # pyright: ignore[reportUnnecessaryIsInstance]
        msg = "Issue must have a non-empty title string"
        raise ValueError(msg)

    validate_priority(issue.priority)
    validate_status(issue.status)
    validate_issue_type(issue.issue_type)


def issue_to_dict(issue: Issue) -> dict[str, Any]:
    """Convert an Issue to a dictionary, serializing datetimes."""
    # Get the status and issue_type values
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
        "close_reason": issue.close_reason,
        "created_at": issue.created_at.isoformat(),
        "created_by": issue.created_by,
        "updated_at": issue.updated_at.isoformat(),
        "updated_by": issue.updated_by,
        "closed_at": issue.closed_at.isoformat() if issue.closed_at else None,
        "closed_by": issue.closed_by,
        "deleted_at": issue.deleted_at.isoformat() if issue.deleted_at else None,
        "deleted_by": issue.deleted_by,
        "delete_reason": issue.delete_reason,
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
        "metadata": issue.metadata,
    }


def _migrate_close_reason(notes: str | None, close_reason: str | None) -> str | None:
    """Extract close_reason from legacy notes if not already set."""
    if close_reason is not None:
        return close_reason
    if notes and "\n\nClosed: " in notes:
        parts = notes.split("\n\nClosed: ")
        return parts[-1].strip() or None
    return None


def _migrate_notes(notes: str | None, close_reason: str | None) -> str | None:
    """Strip legacy close reason from notes if close_reason is not yet a field."""
    if close_reason is not None:
        # Already migrated; notes are clean
        return notes
    if notes and "\n\nClosed: " in notes:
        parts = notes.split("\n\nClosed: ")
        cleaned = "\n\nClosed: ".join(parts[:-1]).strip()
        return cleaned or None
    return notes


def dict_to_issue(data: dict[str, Any]) -> Issue:
    """Convert a dictionary to an Issue, deserializing datetimes."""
    # Handle namespace/id migration
    if "namespace" in data:
        # New format: separate namespace and id fields
        namespace = data["namespace"]
        issue_id = data["id"]
    else:
        # Old format: id contains full ID like "dc-4kzj"
        full_id = data["id"]
        if "-" in full_id:
            # Split on last hyphen to handle multi-part namespaces
            namespace, issue_id = full_id.rsplit("-", 1)
        else:
            namespace = "dc"
            issue_id = full_id

    # Parse datetimes
    created_at = datetime.fromisoformat(data["created_at"])
    updated_at = datetime.fromisoformat(data["updated_at"])
    closed_at = (
        datetime.fromisoformat(data["closed_at"]) if data.get("closed_at") else None
    )
    deleted_at = (
        datetime.fromisoformat(data["deleted_at"]) if data.get("deleted_at") else None
    )

    # Parse comments
    comments: list[Comment] = []
    for comment_data in data.get("comments", []):
        comment = Comment(
            id=comment_data["id"],
            issue_id=comment_data["issue_id"],
            author=comment_data["author"],
            text=comment_data["text"],
            created_at=datetime.fromisoformat(comment_data["created_at"]),
        )
        comments.append(comment)

    # Create issue
    return Issue(
        id=issue_id,
        title=data["title"],
        namespace=namespace,
        description=data.get("description"),
        status=Status(data.get("status", Status.OPEN.value)),
        priority=data.get("priority", 2),  # Default priority defined in constants
        issue_type=IssueType(data.get("issue_type", IssueType.TASK.value)),
        owner=data.get("owner"),
        parent=data.get("parent"),
        labels=data.get("labels", []),
        external_ref=data.get("external_ref"),
        design=data.get("design"),
        acceptance=data.get("acceptance"),
        notes=_migrate_notes(data.get("notes"), data.get("close_reason")),
        close_reason=_migrate_close_reason(data.get("notes"), data.get("close_reason")),
        created_at=created_at,
        created_by=data.get("created_by"),
        updated_at=updated_at,
        updated_by=data.get("updated_by"),
        closed_at=closed_at,
        closed_by=data.get("closed_by"),
        deleted_at=deleted_at,
        deleted_by=data.get("deleted_by"),
        delete_reason=data.get("delete_reason"),
        original_type=(
            IssueType(data["original_type"]) if data.get("original_type") else None
        ),
        comments=comments,
        duplicate_of=data.get("duplicate_of"),
        metadata=data.get("metadata", {}),
    )


def classify_record(data: dict[str, Any]) -> str:
    """Classify a JSONL record as 'issue', 'dependency', 'link', or 'event'.

    Checks for an explicit ``record_type`` field first, then falls back to
    field-sniffing for backward compatibility with older records.
    """
    explicit = data.get("record_type")
    if explicit in ("issue", "dependency", "link", "event"):
        return explicit  # type: ignore[return-value]

    if "from_id" in data and "to_id" in data:
        return "link"
    if "issue_id" in data and "depends_on_id" in data:
        return "dependency"
    return "issue"
