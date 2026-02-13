"""JSONL-based storage for issues with atomic writes."""

from __future__ import annotations

import fcntl
import subprocess
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Iterator

import logging

import orjson

from dogcat._version import version as _dcat_version
from dogcat.constants import TRACKED_FIELDS
from dogcat.models import (
    Dependency,
    DependencyType,
    Issue,
    Link,
    Status,
    classify_record,
    dict_to_issue,
    issue_to_dict,
)


class JSONLStorage:
    """Manages atomic JSONL storage for issues."""

    # Compact when appended lines exceed this fraction of the base file size.
    _COMPACTION_RATIO = 0.5
    # Minimum base size before ratio-based compaction kicks in.
    _COMPACTION_MIN_BASE = 20

    def __init__(
        self,
        path: str = ".dogcats/issues.jsonl",
        create_dir: bool = False,
    ) -> None:
        """Initialize storage.

        Args:
            path: Path to the JSONL storage file (default: .dogcats/issues.jsonl)
            create_dir: If True, create the directory if it doesn't exist.
                       If False (default), raise an error if directory doesn't exist.
        """
        self.path = Path(path)
        self.dogcats_dir = self.path.parent
        self._issues: dict[str, Issue] = {}
        self._dependencies: list[Dependency] = []
        self._links: list[Link] = []
        # Indexes for O(1) dependency/link lookups
        self._deps_by_issue: dict[str, list[Dependency]] = {}
        self._deps_by_depends_on: dict[str, list[Dependency]] = {}
        self._links_by_from: dict[str, list[Link]] = {}
        self._links_by_to: dict[str, list[Link]] = {}
        self._children_by_parent: dict[str, list[str]] = {}
        # Track lines for compaction decisions
        self._base_lines: int = 0
        self._appended_lines: int = 0

        if create_dir:
            # Create .dogcats directory if it doesn't exist (used by init)
            self.dogcats_dir.mkdir(parents=True, exist_ok=True)
        elif not self.dogcats_dir.exists():
            # Fail if directory doesn't exist and create_dir is False
            msg = (
                f"Directory '{self.dogcats_dir}' does not exist. "
                f"Run 'dcat init' first to initialize the repository."
            )
            raise ValueError(
                msg,
            )

        self._lock_path = self.dogcats_dir / ".issues.lock"

        # Initialize event log for change tracking
        from dogcat.event_log import EventLog

        self._event_log = EventLog(self.dogcats_dir)

        # Load existing issues if file exists
        if self.path.exists():
            self._load()

    def _load(self) -> None:
        """Load issues from JSONL file into memory.

        Replays the append-only log: later issue records override earlier ones
        (last-write-wins by ID).  Dependency and link records may carry an
        ``"op"`` field (``"add"`` or ``"remove"``); the default is ``"add"``
        for backwards compatibility with files written before append-only mode.
        """
        self._issues.clear()
        self._dependencies.clear()
        self._links.clear()

        # Use sets keyed by identity tuple for efficient add/remove replay
        dep_map: dict[tuple[str, str, str], Dependency] = {}
        link_map: dict[tuple[str, str, str], Link] = {}
        line_count = 0

        try:
            with self.path.open("rb") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    line_count += 1

                    try:
                        data = orjson.loads(line)
                        rtype = classify_record(data)
                        if rtype == "link":
                            op = data.get("op", "add")
                            key = (
                                data["from_id"],
                                data["to_id"],
                                data.get("link_type", "relates_to"),
                            )
                            if op == "remove":
                                link_map.pop(key, None)
                            else:
                                link = Link(
                                    from_id=data["from_id"],
                                    to_id=data["to_id"],
                                    link_type=data.get("link_type", "relates_to"),
                                    created_at=datetime.fromisoformat(
                                        data["created_at"],
                                    ),
                                    created_by=data.get("created_by"),
                                )
                                link_map[key] = link
                        elif rtype == "dependency":
                            op = data.get("op", "add")
                            key = (
                                data["issue_id"],
                                data["depends_on_id"],
                                data["type"],
                            )
                            if op == "remove":
                                dep_map.pop(key, None)
                            else:
                                dep = Dependency(
                                    issue_id=data["issue_id"],
                                    depends_on_id=data["depends_on_id"],
                                    dep_type=DependencyType(data["type"]),
                                    created_at=datetime.fromisoformat(
                                        data["created_at"],
                                    ),
                                    created_by=data.get("created_by"),
                                )
                                dep_map[key] = dep
                        elif rtype == "event":
                            continue
                        else:
                            # Issue record — last-write-wins
                            issue = dict_to_issue(data)
                            self._issues[issue.full_id] = issue
                    except (orjson.JSONDecodeError, ValueError, KeyError) as e:
                        msg = f"Invalid JSONL record: {e}"
                        raise ValueError(msg) from e
        except OSError as e:
            msg = f"Failed to read storage file: {e}"
            raise RuntimeError(msg) from e

        self._dependencies = list(dep_map.values())
        self._links = list(link_map.values())
        self._base_lines = line_count
        self._appended_lines = 0
        self._rebuild_indexes()

    def _rebuild_indexes(self) -> None:
        """Rebuild dependency and link indexes from the source lists."""
        self._deps_by_issue = {}
        self._deps_by_depends_on = {}
        for dep in self._dependencies:
            self._deps_by_issue.setdefault(dep.issue_id, []).append(dep)
            self._deps_by_depends_on.setdefault(dep.depends_on_id, []).append(dep)

        self._links_by_from = {}
        self._links_by_to = {}
        for link in self._links:
            self._links_by_from.setdefault(link.from_id, []).append(link)
            self._links_by_to.setdefault(link.to_id, []).append(link)

        self._children_by_parent = {}
        for issue in self._issues.values():
            if issue.parent:
                self._children_by_parent.setdefault(issue.parent, []).append(
                    issue.full_id,
                )

    @contextmanager
    def _file_lock(self) -> Iterator[None]:
        """Acquire an advisory file lock for exclusive writes."""
        lock_fd = self._lock_path.open("w")
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()

    def _save(self) -> None:
        """Compact: rewrite the entire file with only current state.

        Eliminates superseded issue records, removed dependencies/links,
        and resets the append counter.
        """
        with self._file_lock():
            # Write to temporary file first
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=self.dogcats_dir,
                delete=False,
                suffix=".jsonl",
            ) as tmp_file:
                tmp_path = Path(tmp_file.name)

                try:
                    line_count = 0
                    # Write all issues
                    for issue in self._issues.values():
                        data = issue_to_dict(issue)
                        tmp_file.write(orjson.dumps(data))
                        tmp_file.write(b"\n")
                        line_count += 1

                    # Write all dependencies
                    for dep in self._dependencies:
                        dep_data = {
                            "record_type": "dependency",
                            "dcat_version": _dcat_version,
                            "issue_id": dep.issue_id,
                            "depends_on_id": dep.depends_on_id,
                            "type": dep.dep_type.value,
                            "created_at": dep.created_at.isoformat(),
                            "created_by": dep.created_by,
                        }
                        tmp_file.write(orjson.dumps(dep_data))
                        tmp_file.write(b"\n")
                        line_count += 1

                    # Write all links
                    for link in self._links:
                        link_data = {
                            "record_type": "link",
                            "dcat_version": _dcat_version,
                            "from_id": link.from_id,
                            "to_id": link.to_id,
                            "link_type": link.link_type,
                            "created_at": link.created_at.isoformat(),
                            "created_by": link.created_by,
                        }
                        tmp_file.write(orjson.dumps(link_data))
                        tmp_file.write(b"\n")
                        line_count += 1

                    # Preserve event records from the current file
                    if self.path.exists():
                        with self.path.open("rb") as src:
                            for raw_line in src:
                                raw_line = raw_line.strip()
                                if not raw_line:
                                    continue
                                data = orjson.loads(raw_line)
                                if data.get("record_type") == "event":
                                    tmp_file.write(raw_line)
                                    tmp_file.write(b"\n")
                                    line_count += 1

                    tmp_file.flush()
                except Exception as e:
                    tmp_path.unlink(missing_ok=True)
                    msg = f"Failed to write to temporary file: {e}"
                    raise RuntimeError(msg) from e

            # Atomic rename to target file
            try:
                tmp_path.replace(self.path)
            except OSError as e:
                tmp_path.unlink(missing_ok=True)
                msg = f"Failed to write storage file: {e}"
                raise RuntimeError(msg) from e

            self._base_lines = line_count
            self._appended_lines = 0

    def _append(self, records: list[dict[str, Any]]) -> None:
        """Append records to the JSONL file without rewriting it.

        Args:
            records: List of dicts to serialize and append as JSONL lines.
        """
        with self._file_lock():
            try:
                with self.path.open("ab") as f:
                    for record in records:
                        f.write(orjson.dumps(record))
                        f.write(b"\n")
                    f.flush()
            except OSError as e:
                msg = f"Failed to append to storage file: {e}"
                raise RuntimeError(msg) from e

        self._appended_lines += len(records)
        self._maybe_compact()

    _DEFAULT_BRANCHES = frozenset({"main", "master"})

    def _is_default_branch(self) -> bool:
        """Check whether the working tree is on a default branch (main/master).

        Returns True if not in a git repository (safe to compact).
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                check=False,
                cwd=str(self.dogcats_dir),
            )
            if result.returncode != 0:
                return True  # Not a git repo — safe to compact
            return result.stdout.strip() in self._DEFAULT_BRANCHES
        except FileNotFoundError:
            return True  # git not installed — safe to compact

    def _maybe_compact(self) -> None:
        """Compact the file if appended lines exceed the threshold.

        Skips automatic compaction on non-default branches to prevent
        merge conflicts when multiple branches compact independently.
        """
        if (
            self._base_lines >= self._COMPACTION_MIN_BASE
            and self._appended_lines > self._base_lines * self._COMPACTION_RATIO
            and self._is_default_branch()
        ):
            self._save()

    # -- Event emission helpers ------------------------------------------

    def _emit_event(
        self,
        event_type: str,
        issue: Issue,
        changes: dict[str, dict[str, Any]],
        by: str | None = None,
    ) -> None:
        """Emit an event to the event log (best-effort)."""
        from dogcat.event_log import EventRecord

        if not changes:
            return

        event = EventRecord(
            event_type=event_type,
            issue_id=issue.full_id,
            timestamp=issue.updated_at.isoformat(),
            by=by,
            title=issue.title,
            changes=changes,
        )
        try:
            self._event_log.append(event)
        except Exception:
            logging.getLogger(__name__).debug(
                "Failed to write event for %s",
                issue.full_id,
                exc_info=True,
            )

    @staticmethod
    def _field_value(value: Any) -> Any:
        """Normalize a field value for event storage."""
        if hasattr(value, "value"):
            return value.value  # Enum -> string
        return value

    def _tracked_changes(
        self,
        old_values: dict[str, Any],
        new_values: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        """Compute tracked field changes between old and new values."""
        changes: dict[str, dict[str, Any]] = {}
        for field_name in old_values:
            if field_name not in TRACKED_FIELDS:
                continue
            old = self._field_value(old_values[field_name])
            new = self._field_value(new_values[field_name])
            if old != new:
                changes[field_name] = {"old": old, "new": new}
        return changes

    @staticmethod
    def _issue_record(issue: Issue) -> dict[str, Any]:
        """Serialize an issue to a dict for appending."""
        return issue_to_dict(issue)

    @staticmethod
    def _dep_record(dep: Dependency, *, op: str = "add") -> dict[str, Any]:
        """Serialize a dependency to a dict for appending."""
        d: dict[str, Any] = {
            "record_type": "dependency",
            "dcat_version": _dcat_version,
            "issue_id": dep.issue_id,
            "depends_on_id": dep.depends_on_id,
            "type": dep.dep_type.value,
            "created_at": dep.created_at.isoformat(),
            "created_by": dep.created_by,
        }
        if op != "add":
            d["op"] = op
        return d

    @staticmethod
    def _link_record(link: Link, *, op: str = "add") -> dict[str, Any]:
        """Serialize a link to a dict for appending."""
        d: dict[str, Any] = {
            "record_type": "link",
            "dcat_version": _dcat_version,
            "from_id": link.from_id,
            "to_id": link.to_id,
            "link_type": link.link_type,
            "created_at": link.created_at.isoformat(),
            "created_by": link.created_by,
        }
        if op != "add":
            d["op"] = op
        return d

    def create(self, issue: Issue) -> Issue:
        """Create a new issue.

        Args:
            issue: The issue to create

        Returns:
            The created issue

        Raises:
            ValueError: If ID already exists or issue is invalid
        """
        from dogcat.models import validate_priority

        if issue.full_id in self._issues:
            msg = f"Issue with ID {issue.full_id} already exists"
            raise ValueError(msg)

        if not issue.title:
            msg = "Issue must have a non-empty title"
            raise ValueError(msg)

        validate_priority(issue.priority)

        self._issues[issue.full_id] = issue
        if issue.parent:
            self._children_by_parent.setdefault(issue.parent, []).append(issue.full_id)
        self._append([self._issue_record(issue)])

        # Emit creation event
        changes: dict[str, dict[str, Any]] = {}
        for field_name in TRACKED_FIELDS:
            value = getattr(issue, field_name, None)
            if value is not None and value != [] and value != "":
                changes[field_name] = {
                    "old": None,
                    "new": self._field_value(value),
                }
        self._emit_event("created", issue, changes, by=issue.created_by)

        return issue

    def resolve_id(self, partial_id: str) -> str | None:
        """Resolve a partial ID to a full issue ID.

        Supports multiple formats:
        - Full ID: "dc-3hup" -> "dc-3hup"
        - Hash only: "3hup" -> "dc-3hup"
        - Short hash: "hup" -> matches if unique

        Args:
            partial_id: Full or partial issue ID

        Returns:
            The full issue ID, or None if not found

        Raises:
            ValueError: If partial ID matches multiple issues (ambiguous)
        """
        # Exact match first
        if partial_id in self._issues:
            return partial_id

        # Try matching as suffix (hash part)
        matches = [
            issue_id
            for issue_id in self._issues
            if issue_id.endswith(partial_id) or issue_id.split("-", 1)[-1] == partial_id
        ]

        if len(matches) == 1:
            return matches[0]

        if len(matches) > 1:
            msg = (
                f"Ambiguous partial ID '{partial_id}' matches {len(matches)} issues: "
                f"{', '.join(sorted(matches)[:5])}"
                + (f" and {len(matches) - 5} more" if len(matches) > 5 else "")
            )
            raise ValueError(msg)

        return None

    def get(self, issue_id: str) -> Issue | None:
        """Get an issue by ID.

        Args:
            issue_id: The ID of the issue to retrieve (supports partial IDs)

        Returns:
            The issue, or None if not found
        """
        resolved_id = self.resolve_id(issue_id)
        if resolved_id:
            return self._issues.get(resolved_id)
        return None

    def list(self, filters: dict[str, Any] | None = None) -> list[Issue]:
        """List all issues, optionally filtered.

        Args:
            filters: Optional filters (status, priority, type, label, owner)

        Returns:
            List of matching issues
        """
        issues = list(self._issues.values())

        if not filters:
            return issues

        # Apply filters
        if "status" in filters:
            status_filter = filters["status"]
            if isinstance(status_filter, str):
                status_filter = Status(status_filter)
            issues = [i for i in issues if i.status == status_filter]

        if "priority" in filters:
            priority = filters["priority"]
            issues = [i for i in issues if i.priority == priority]

        if "type" in filters:
            issue_type = filters["type"]
            issues = [i for i in issues if i.issue_type.value == issue_type]

        if "label" in filters:
            label_filter = filters["label"]
            if isinstance(label_filter, list):
                label_set: set[str] = set(cast("list[str]", label_filter))
                issues = [i for i in issues if label_set & set(i.labels)]
            else:
                issues = [i for i in issues if label_filter in i.labels]

        if "owner" in filters:
            owner = filters["owner"]
            issues = [i for i in issues if i.owner == owner]

        return issues

    # Fields that callers are allowed to modify via update().
    # Internal/identity fields (id, namespace, full_id, created_at, etc.) are excluded.
    UPDATABLE_FIELDS: frozenset[str] = frozenset(
        {
            "title",
            "description",
            "status",
            "priority",
            "issue_type",
            "owner",
            "parent",
            "labels",
            "external_ref",
            "design",
            "acceptance",
            "notes",
            "close_reason",
            "updated_by",
            "closed_at",
            "closed_by",
            "deleted_at",
            "deleted_by",
            "delete_reason",
            "original_type",
            "duplicate_of",
            "metadata",
            "manual",
            "comments",
        },
    )

    def update(self, issue_id: str, updates: dict[str, Any]) -> Issue:
        """Update an issue.

        Args:
            issue_id: The ID of the issue to update (supports partial IDs)
            updates: Dictionary of fields to update

        Returns:
            The updated issue

        Raises:
            ValueError: If issue doesn't exist or updates contain disallowed fields
        """
        from dogcat.models import IssueType, validate_priority

        resolved_id = self.resolve_id(issue_id)
        if resolved_id is None:
            msg = f"Issue {issue_id} not found"
            raise ValueError(msg)

        issue = self._issues[resolved_id]

        # Track old parent for index maintenance
        old_parent = issue.parent

        # Capture old values for event emission
        old_values: dict[str, Any] = {
            k: getattr(issue, k, None) for k in updates if k in TRACKED_FIELDS
        }

        # Update fields — only UPDATABLE_FIELDS are allowed
        for key, value in updates.items():
            if key not in self.UPDATABLE_FIELDS:
                continue
            # Validate priority
            if key == "priority":
                validate_priority(value)
            # Convert string values to proper enums
            if key == "status" and isinstance(value, str):
                value = Status(value)
            elif key == "issue_type" and isinstance(value, str):
                value = IssueType(value)
            setattr(issue, key, value)

        # Maintain parent-child index if parent changed
        if issue.parent != old_parent:
            if old_parent and old_parent in self._children_by_parent:
                children = self._children_by_parent[old_parent]
                if resolved_id in children:
                    children.remove(resolved_id)
                if not children:
                    del self._children_by_parent[old_parent]
            if issue.parent:
                self._children_by_parent.setdefault(issue.parent, []).append(
                    resolved_id,
                )

        # Update timestamp
        issue.updated_at = datetime.now().astimezone()

        self._append([self._issue_record(issue)])

        # Emit update event
        new_values = {k: getattr(issue, k, None) for k in old_values}
        changes = self._tracked_changes(old_values, new_values)
        by = updates.get("updated_by") or issue.updated_by
        event_type = "updated"
        if "status" in changes and changes["status"]["new"] == "closed":
            event_type = "closed"
        self._emit_event(event_type, issue, changes, by=by)

        return issue

    def close(
        self,
        issue_id: str,
        reason: str | None = None,
        closed_by: str | None = None,
    ) -> Issue:
        """Close an issue.

        Args:
            issue_id: The ID of the issue to close (supports partial IDs)
            reason: Optional reason for closing
            closed_by: Optional operator who closed the issue

        Returns:
            The closed issue

        Raises:
            ValueError: If issue doesn't exist
        """
        resolved_id = self.resolve_id(issue_id)
        if resolved_id is None:
            msg = f"Issue {issue_id} not found"
            raise ValueError(msg)

        issue = self._issues[resolved_id]
        old_status = issue.status.value

        now = datetime.now().astimezone()
        issue.status = Status.CLOSED
        issue.closed_at = now
        issue.updated_at = now
        if reason:
            issue.close_reason = reason
        if closed_by:
            issue.closed_by = closed_by

        self._append([self._issue_record(issue)])

        # Emit close event
        self._emit_event(
            "closed",
            issue,
            {"status": {"old": old_status, "new": "closed"}},
            by=closed_by,
        )

        return issue

    def delete(
        self,
        issue_id: str,
        reason: str | None = None,
        deleted_by: str | None = None,
    ) -> Issue:
        """Soft delete an issue (create tombstone).

        Args:
            issue_id: The ID of the issue to delete (supports partial IDs)
            reason: Optional reason for deletion
            deleted_by: Optional operator who deleted the issue

        Returns:
            The tombstoned issue

        Raises:
            ValueError: If issue doesn't exist
        """
        resolved_id = self.resolve_id(issue_id)
        if resolved_id is None:
            msg = f"Issue {issue_id} not found"
            raise ValueError(msg)

        issue = self._issues[resolved_id]
        old_status = issue.status.value

        now = datetime.now().astimezone()
        issue.status = Status.TOMBSTONE
        issue.deleted_at = now
        issue.updated_at = now
        issue.delete_reason = reason
        issue.original_type = issue.issue_type
        if deleted_by:
            issue.deleted_by = deleted_by

        # Collect deps/links to remove (for append-only removal records)
        removed_deps = [
            d
            for d in self._dependencies
            if d.issue_id == resolved_id or d.depends_on_id == resolved_id
        ]
        removed_links = [
            link
            for link in self._links
            if link.from_id == resolved_id or link.to_id == resolved_id
        ]

        # Clean up in-memory state
        self._dependencies = [
            d
            for d in self._dependencies
            if d.issue_id != resolved_id and d.depends_on_id != resolved_id
        ]
        self._links = [
            link
            for link in self._links
            if link.from_id != resolved_id and link.to_id != resolved_id
        ]
        self._rebuild_indexes()

        # Append tombstone + removal records (instead of rewriting the file)
        records: list[dict[str, Any]] = [issue_to_dict(issue)]
        records.extend(self._dep_record(d, op="remove") for d in removed_deps)
        records.extend(self._link_record(lnk, op="remove") for lnk in removed_links)
        self._append(records)

        # Emit delete event
        self._emit_event(
            "deleted",
            issue,
            {"status": {"old": old_status, "new": "tombstone"}},
            by=deleted_by,
        )

        return issue

    def add_dependency(
        self,
        issue_id: str,
        depends_on_id: str,
        dep_type: str,
        created_by: str | None = None,
    ) -> Dependency:
        """Add a dependency between issues.

        Args:
            issue_id: The issue with the dependency (supports partial IDs)
            depends_on_id: What it depends on (supports partial IDs)
            dep_type: Type of dependency
            created_by: Who created this dependency

        Returns:
            The created dependency

        Raises:
            ValueError: If either issue doesn't exist or if adding the dependency
                would create a circular dependency
        """
        # Validate dependency type first
        try:
            validated_dep_type = DependencyType(dep_type)
        except ValueError:
            valid_types = [t.value for t in DependencyType]
            msg = f"Invalid dependency type '{dep_type}'. Valid types: {valid_types}"
            raise ValueError(msg) from None

        resolved_issue_id = self.resolve_id(issue_id)
        if resolved_issue_id is None:
            msg = f"Issue {issue_id} not found"
            raise ValueError(msg)

        resolved_depends_on_id = self.resolve_id(depends_on_id)
        if resolved_depends_on_id is None:
            msg = f"Issue {depends_on_id} not found"
            raise ValueError(msg)

        # Check if dependency already exists (O(1) index lookup)
        for dep in self._deps_by_issue.get(resolved_issue_id, []):
            if (
                dep.depends_on_id == resolved_depends_on_id
                and dep.dep_type.value == dep_type
            ):
                return dep

        # Check for circular dependency
        from dogcat.deps import would_create_cycle

        if would_create_cycle(self, resolved_issue_id, resolved_depends_on_id):
            msg = (
                f"Cannot add dependency: {resolved_issue_id} -> "
                f"{resolved_depends_on_id} would create a circular dependency"
            )
            raise ValueError(msg)

        dependency = Dependency(
            issue_id=resolved_issue_id,
            depends_on_id=resolved_depends_on_id,
            dep_type=validated_dep_type,
            created_by=created_by,
        )
        self._dependencies.append(dependency)
        self._deps_by_issue.setdefault(resolved_issue_id, []).append(dependency)
        self._deps_by_depends_on.setdefault(resolved_depends_on_id, []).append(
            dependency,
        )
        self._append([self._dep_record(dependency)])
        return dependency

    def remove_dependency(self, issue_id: str, depends_on_id: str) -> None:
        """Remove a dependency.

        Args:
            issue_id: The issue with the dependency (supports partial IDs)
            depends_on_id: What it was depending on (supports partial IDs)

        Raises:
            ValueError: If either issue doesn't exist
        """
        resolved_issue_id = self.resolve_id(issue_id)
        if resolved_issue_id is None:
            msg = f"Issue {issue_id} not found"
            raise ValueError(msg)

        resolved_depends_on_id = self.resolve_id(depends_on_id)
        if resolved_depends_on_id is None:
            msg = f"Issue {depends_on_id} not found"
            raise ValueError(msg)

        # Collect removed deps for append-only removal records
        removed = [
            d
            for d in self._dependencies
            if d.issue_id == resolved_issue_id
            and d.depends_on_id == resolved_depends_on_id
        ]
        self._dependencies = [
            d
            for d in self._dependencies
            if not (
                d.issue_id == resolved_issue_id
                and d.depends_on_id == resolved_depends_on_id
            )
        ]
        self._rebuild_indexes()
        if removed:
            self._append([self._dep_record(d, op="remove") for d in removed])

    def get_dependencies(self, issue_id: str) -> list[Dependency]:
        """Get all dependencies of an issue.

        Args:
            issue_id: The issue to query (supports partial IDs)

        Returns:
            List of dependencies

        Raises:
            ValueError: If issue doesn't exist
        """
        resolved_id = self.resolve_id(issue_id)
        if resolved_id is None:
            msg = f"Issue {issue_id} not found"
            raise ValueError(msg)
        return list(self._deps_by_issue.get(resolved_id, []))

    def get_dependents(self, issue_id: str) -> list[Dependency]:
        """Get all issues that depend on this one.

        Args:
            issue_id: The issue to query (supports partial IDs)

        Returns:
            List of dependencies pointing to this issue

        Raises:
            ValueError: If issue doesn't exist
        """
        resolved_id = self.resolve_id(issue_id)
        if resolved_id is None:
            msg = f"Issue {issue_id} not found"
            raise ValueError(msg)
        return list(self._deps_by_depends_on.get(resolved_id, []))

    def add_link(
        self,
        from_id: str,
        to_id: str,
        link_type: str = "relates_to",
        created_by: str | None = None,
    ) -> Link:
        """Add a link between issues.

        Args:
            from_id: The source issue (supports partial IDs)
            to_id: The target issue (supports partial IDs)
            link_type: Type of link (default: relates_to)
            created_by: Who created this link

        Returns:
            The created link

        Raises:
            ValueError: If either issue doesn't exist or link already exists
        """
        resolved_from_id = self.resolve_id(from_id)
        if resolved_from_id is None:
            msg = f"Issue {from_id} not found"
            raise ValueError(msg)

        resolved_to_id = self.resolve_id(to_id)
        if resolved_to_id is None:
            msg = f"Issue {to_id} not found"
            raise ValueError(msg)

        # Check if link already exists (O(1) index lookup)
        for link in self._links_by_from.get(resolved_from_id, []):
            if link.to_id == resolved_to_id and link.link_type == link_type:
                return link

        link = Link(
            from_id=resolved_from_id,
            to_id=resolved_to_id,
            link_type=link_type,
            created_by=created_by,
        )
        self._links.append(link)
        self._links_by_from.setdefault(resolved_from_id, []).append(link)
        self._links_by_to.setdefault(resolved_to_id, []).append(link)
        self._append([self._link_record(link)])
        return link

    def remove_link(self, from_id: str, to_id: str) -> None:
        """Remove a link between issues.

        Args:
            from_id: The source issue (supports partial IDs)
            to_id: The target issue (supports partial IDs)

        Raises:
            ValueError: If either issue doesn't exist
        """
        resolved_from_id = self.resolve_id(from_id)
        if resolved_from_id is None:
            msg = f"Issue {from_id} not found"
            raise ValueError(msg)

        resolved_to_id = self.resolve_id(to_id)
        if resolved_to_id is None:
            msg = f"Issue {to_id} not found"
            raise ValueError(msg)

        # Collect removed links for append-only removal records
        removed = [
            link
            for link in self._links
            if link.from_id == resolved_from_id and link.to_id == resolved_to_id
        ]
        self._links = [
            link
            for link in self._links
            if not (link.from_id == resolved_from_id and link.to_id == resolved_to_id)
        ]
        self._rebuild_indexes()
        if removed:
            self._append([self._link_record(lnk, op="remove") for lnk in removed])

    def get_links(self, issue_id: str) -> list[Link]:
        """Get all links from an issue.

        Args:
            issue_id: The issue to query (supports partial IDs)

        Returns:
            List of links originating from this issue

        Raises:
            ValueError: If issue doesn't exist
        """
        resolved_id = self.resolve_id(issue_id)
        if resolved_id is None:
            msg = f"Issue {issue_id} not found"
            raise ValueError(msg)
        return list(self._links_by_from.get(resolved_id, []))

    def get_incoming_links(self, issue_id: str) -> list[Link]:
        """Get all links pointing to an issue.

        Args:
            issue_id: The issue to query (supports partial IDs)

        Returns:
            List of links pointing to this issue

        Raises:
            ValueError: If issue doesn't exist
        """
        resolved_id = self.resolve_id(issue_id)
        if resolved_id is None:
            msg = f"Issue {issue_id} not found"
            raise ValueError(msg)
        return list(self._links_by_to.get(resolved_id, []))

    def get_children(self, issue_id: str) -> list[Issue]:
        """Get all child issues of an issue.

        Args:
            issue_id: The parent issue to query (supports partial IDs)

        Returns:
            List of issues that have this issue as their parent

        Raises:
            ValueError: If issue doesn't exist
        """
        resolved_id = self.resolve_id(issue_id)
        if resolved_id is None:
            msg = f"Issue {issue_id} not found"
            raise ValueError(msg)
        return [
            self._issues[cid]
            for cid in self._children_by_parent.get(resolved_id, [])
            if cid in self._issues
        ]

    def get_issue_ids(self) -> set[str]:
        """Get all issue IDs in storage.

        Returns:
            Set of all issue IDs
        """
        return set(self._issues.keys())

    def reload(self) -> None:
        """Reload storage from disk.

        This re-reads the JSONL file and updates the in-memory state.
        """
        self._load()

    def remove_archived(self, archived_ids: set[str], remaining_lines: int) -> None:
        """Remove archived issues, dependencies, and links from in-memory state.

        Called after the archive command has already rewritten the JSONL files.
        Updates indexes and bookkeeping to reflect the new file contents.

        Args:
            archived_ids: Set of issue IDs that were archived.
            remaining_lines: Number of lines in the rewritten storage file.
        """
        for issue_id in archived_ids:
            self._issues.pop(issue_id, None)

        self._dependencies = [
            dep
            for dep in self._dependencies
            if dep.issue_id not in archived_ids or dep.depends_on_id not in archived_ids
        ]

        self._links = [
            link
            for link in self._links
            if link.from_id not in archived_ids or link.to_id not in archived_ids
        ]

        self._rebuild_indexes()
        self._base_lines = remaining_lines
        self._appended_lines = 0

    @property
    def all_dependencies(self) -> list[Dependency]:
        """Return all dependency records."""
        return list(self._dependencies)

    @property
    def all_links(self) -> list[Link]:
        """Return all link records."""
        return list(self._links)

    def check_id_uniqueness(self) -> bool:
        """Check if all issue IDs are unique.

        Returns:
            True if all IDs are unique (dict keys are always unique,
            so this checks the loaded state is consistent).
        """
        # Since _issues is a dict, IDs are unique by construction after replay.
        # This always returns True but provides a public API for doctor checks.
        return True

    def find_dangling_dependencies(self) -> list[Dependency]:
        """Find dependencies that reference non-existent issues.

        Returns:
            List of dependencies where either issue_id or depends_on_id
            is not in storage.
        """
        return [
            dep
            for dep in self._dependencies
            if dep.issue_id not in self._issues or dep.depends_on_id not in self._issues
        ]

    def remove_dependencies(self, deps_to_remove: list[Dependency]) -> None:
        """Remove specific dependency records and rewrite storage.

        Args:
            deps_to_remove: Dependencies to remove.
        """
        remove_set = {(d.issue_id, d.depends_on_id, d.dep_type) for d in deps_to_remove}
        self._dependencies = [
            d
            for d in self._dependencies
            if (d.issue_id, d.depends_on_id, d.dep_type) not in remove_set
        ]
        self._rebuild_indexes()
        self._save()

    def prune_tombstones(self) -> list[str]:
        """Permanently remove tombstoned issues from storage.

        Returns:
            List of pruned issue IDs
        """
        tombstone_ids = [
            issue_id
            for issue_id, issue in self._issues.items()
            if issue.status == Status.TOMBSTONE
        ]

        for issue_id in tombstone_ids:
            del self._issues[issue_id]

        if tombstone_ids:
            self._save()

        return tombstone_ids
