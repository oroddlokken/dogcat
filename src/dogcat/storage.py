"""JSONL-based storage for issues with atomic writes."""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import orjson

from dogcat.models import (
    Dependency,
    DependencyType,
    Issue,
    Link,
    Status,
    dict_to_issue,
    issue_to_dict,
)


class JSONLStorage:
    """Manages atomic JSONL storage for issues."""

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

        # Load existing issues if file exists
        if self.path.exists():
            self._load()

    def _load(self) -> None:
        """Load issues from JSONL file into memory."""
        self._issues.clear()
        self._dependencies.clear()
        self._links.clear()

        try:
            with self.path.open("rb") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        data = orjson.loads(line)
                        if "from_id" in data and "to_id" in data:
                            # This is a link record
                            link = Link(
                                from_id=data["from_id"],
                                to_id=data["to_id"],
                                link_type=data.get("link_type", "relates_to"),
                                created_at=datetime.fromisoformat(data["created_at"]),
                                created_by=data.get("created_by"),
                            )
                            self._links.append(link)
                        elif "issue_id" in data and "depends_on_id" in data:
                            # This is a dependency record
                            dep = Dependency(
                                issue_id=data["issue_id"],
                                depends_on_id=data["depends_on_id"],
                                dep_type=DependencyType(data["type"]),
                                created_at=datetime.fromisoformat(data["created_at"]),
                                created_by=data.get("created_by"),
                            )
                            self._dependencies.append(dep)
                        else:
                            # This is an issue record
                            issue = dict_to_issue(data)
                            self._issues[issue.full_id] = issue
                    except (orjson.JSONDecodeError, ValueError, KeyError) as e:
                        msg = f"Invalid JSONL record: {e}"
                        raise ValueError(msg) from e
        except OSError as e:
            msg = f"Failed to read storage file: {e}"
            raise RuntimeError(msg) from e

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

    def _save(self) -> None:
        """Save all issues and dependencies to JSONL file atomically."""
        # Write to temporary file first
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=self.dogcats_dir,
            delete=False,
            suffix=".jsonl",
        ) as tmp_file:
            tmp_path = Path(tmp_file.name)

            try:
                # Write all issues
                for issue in self._issues.values():
                    data = issue_to_dict(issue)
                    tmp_file.write(orjson.dumps(data))
                    tmp_file.write(b"\n")

                # Write all dependencies
                for dep in self._dependencies:
                    dep_data = {
                        "issue_id": dep.issue_id,
                        "depends_on_id": dep.depends_on_id,
                        "type": dep.dep_type.value,
                        "created_at": dep.created_at.isoformat(),
                        "created_by": dep.created_by,
                    }
                    tmp_file.write(orjson.dumps(dep_data))
                    tmp_file.write(b"\n")

                # Write all links
                for link in self._links:
                    link_data = {
                        "from_id": link.from_id,
                        "to_id": link.to_id,
                        "link_type": link.link_type,
                        "created_at": link.created_at.isoformat(),
                        "created_by": link.created_by,
                    }
                    tmp_file.write(orjson.dumps(link_data))
                    tmp_file.write(b"\n")

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
        self._save()
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
            label = filters["label"]
            issues = [i for i in issues if label in i.labels]

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
            "no_agent",
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

        # Update fields
        for key, value in updates.items():
            if key not in self.UPDATABLE_FIELDS:
                continue
            if hasattr(issue, key):
                # Validate priority
                if key == "priority":
                    validate_priority(value)
                # Convert string values to proper enums
                if key == "status" and isinstance(value, str):
                    value = Status(value)
                elif key == "issue_type" and isinstance(value, str):
                    value = IssueType(value)
                setattr(issue, key, value)

        # Update timestamp
        issue.updated_at = datetime.now().astimezone()

        self._save()
        return issue

    def close(self, issue_id: str, reason: str | None = None) -> Issue:
        """Close an issue.

        Args:
            issue_id: The ID of the issue to close (supports partial IDs)
            reason: Optional reason for closing

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

        now = datetime.now().astimezone()
        issue.status = Status.CLOSED
        issue.closed_at = now
        issue.updated_at = now
        if reason:
            issue.close_reason = reason

        self._save()
        return issue

    def delete(self, issue_id: str, reason: str | None = None) -> Issue:
        """Soft delete an issue (create tombstone).

        Args:
            issue_id: The ID of the issue to delete (supports partial IDs)
            reason: Optional reason for deletion

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

        now = datetime.now().astimezone()
        issue.status = Status.TOMBSTONE
        issue.deleted_at = now
        issue.updated_at = now
        issue.delete_reason = reason
        issue.original_type = issue.issue_type

        # Clean up dependencies pointing to or from this issue
        self._dependencies = [
            d
            for d in self._dependencies
            if d.issue_id != resolved_id and d.depends_on_id != resolved_id
        ]

        # Clean up links pointing to or from this issue
        self._links = [
            link
            for link in self._links
            if link.from_id != resolved_id and link.to_id != resolved_id
        ]

        self._rebuild_indexes()
        self._save()
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
        self._save()
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

        self._dependencies = [
            d
            for d in self._dependencies
            if not (
                d.issue_id == resolved_issue_id
                and d.depends_on_id == resolved_depends_on_id
            )
        ]
        self._rebuild_indexes()
        self._save()

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
        self._save()
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

        self._links = [
            link
            for link in self._links
            if not (link.from_id == resolved_from_id and link.to_id == resolved_to_id)
        ]
        self._rebuild_indexes()
        self._save()

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
        return [issue for issue in self._issues.values() if issue.parent == resolved_id]

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
