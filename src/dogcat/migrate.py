"""Migration tool for converting beads issues to dogcat format."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import orjson

from dogcat.constants import DEFAULT_PRIORITY, DEFAULT_TYPE
from dogcat.models import Dependency, DependencyType, Issue, IssueType, Status
from dogcat.storage import JSONLStorage


def parse_datetime(date_str: str | None) -> datetime | None:
    """Parse ISO8601 datetime string to datetime object.

    Args:
        date_str: ISO8601 datetime string or None

    Returns:
        Parsed datetime or None
    """
    if not date_str:
        return None

    try:
        # Handle both with and without timezone
        if date_str.endswith("Z"):
            return datetime.fromisoformat(date_str)
        return datetime.fromisoformat(date_str)
    except ValueError:
        return None


def read_beads_jsonl(path: str) -> list[dict[str, Any]]:
    """Read issues from a beads JSONL file.

    Args:
        path: Path to beads issues.jsonl file

    Returns:
        List of issue dictionaries
    """
    issues: list[dict[str, Any]] = []
    beads_path = Path(path)

    if not beads_path.exists():
        msg = f"Beads file not found: {path}"
        raise FileNotFoundError(msg)

    try:
        with beads_path.open("rb") as f:
            for line in f:
                if line.strip():
                    issue = orjson.loads(line)
                    issues.append(issue)
    except orjson.JSONDecodeError as e:
        msg = f"Invalid JSON in beads file: {e}"
        raise ValueError(msg) from e

    return issues


def migrate_issue(beads_issue: dict[str, Any]) -> tuple[Issue, list[Dependency]]:
    """Convert a beads issue to a dogcat Issue with dependencies.

    Args:
        beads_issue: Dictionary from beads JSONL

    Returns:
        Tuple of (Issue, list of Dependencies)
    """
    # Extract basic fields
    raw_id = beads_issue.get("id", "")
    title = beads_issue.get("title", "")

    # Handle namespace/id migration - split old format "prefix-hash" into components
    if "namespace" in beads_issue:
        # New format: separate namespace and id fields
        namespace = beads_issue["namespace"]
        issue_id = raw_id
    elif "-" in raw_id:
        # Old format: id contains full ID like "dc-4kzj"
        namespace, issue_id = raw_id.rsplit("-", 1)
    else:
        namespace = "dc"
        issue_id = raw_id
    description = beads_issue.get("description")
    status_str = beads_issue.get("status", Status.OPEN.value)
    priority = beads_issue.get("priority", DEFAULT_PRIORITY)
    issue_type_str = beads_issue.get("issue_type", DEFAULT_TYPE)
    owner = beads_issue.get("owner")
    created_at_str = beads_issue.get("created_at")
    created_by = beads_issue.get("created_by")
    updated_at_str = beads_issue.get("updated_at")
    closed_at_str = beads_issue.get("closed_at")
    deleted_at_str = beads_issue.get("deleted_at")
    deleted_by = beads_issue.get("deleted_by")
    delete_reason = beads_issue.get("delete_reason")
    labels = beads_issue.get("labels", [])

    # Convert status
    try:
        status = Status(status_str)
    except ValueError:
        status = Status.OPEN

    # Convert issue_type
    try:
        issue_type = IssueType(issue_type_str)
    except ValueError:
        issue_type = IssueType.TASK

    # Create issue with parsed datetimes
    issue = Issue(
        id=issue_id,
        title=title,
        namespace=namespace,
        description=description,
        status=status,
        priority=priority,
        issue_type=issue_type,
        owner=owner,
        labels=labels,
        created_at=parse_datetime(created_at_str) or datetime.now(tz=timezone.utc),  # type: ignore
        created_by=created_by,
        updated_at=parse_datetime(updated_at_str) or datetime.now(tz=timezone.utc),  # type: ignore
        closed_at=parse_datetime(closed_at_str),
        deleted_at=parse_datetime(deleted_at_str),
        deleted_by=deleted_by,
        delete_reason=delete_reason,
        original_type=issue_type if status == Status.TOMBSTONE else None,
    )

    # Extract dependencies
    dependencies: list[Dependency] = []
    beads_deps = beads_issue.get("dependencies", [])
    for dep_dict in beads_deps:
        try:
            dep_type = DependencyType(dep_dict.get("type", "blocks"))
        except ValueError:
            dep_type = DependencyType.BLOCKS

        dep_created_at_str = dep_dict.get("created_at")
        dep = Dependency(
            issue_id=dep_dict.get("issue_id", issue_id),
            depends_on_id=dep_dict.get("depends_on_id", ""),
            type=dep_type,
            created_at=parse_datetime(dep_created_at_str) or datetime.now(tz=timezone.utc),  # type: ignore  # noqa: E501
            created_by=dep_dict.get("created_by"),
        )
        dependencies.append(dep)

    return issue, dependencies


def migrate_from_beads(
    beads_jsonl_path: str,
    output_dir: str = ".dogcats",
    verbose: bool = False,
    merge: bool = False,
) -> tuple[int, int, int]:
    """Import issues from beads to dogcat.

    Args:
        beads_jsonl_path: Path to beads issues.jsonl
        output_dir: Output directory for dogcat (default .dogcats)
        verbose: Print progress information
        merge: If True, merge into existing storage (skip existing IDs)

    Returns:
        Tuple of (issues_imported, issues_failed, issues_skipped)
    """
    # Read beads issues
    beads_issues = read_beads_jsonl(beads_jsonl_path)
    if verbose:
        print(f"Read {len(beads_issues)} issues from beads")

    # Initialize dogcat storage
    output_path = f"{output_dir}/issues.jsonl"
    Path(output_dir).mkdir(exist_ok=True)
    storage = JSONLStorage(output_path)

    # Get existing IDs if merging
    existing_ids: set[str] = storage.get_issue_ids() if merge else set()

    # Import issues and dependencies
    imported = 0
    failed = 0
    skipped = 0
    dependencies: list[Dependency] = []

    for beads_issue in beads_issues:
        try:
            issue, issue_deps = migrate_issue(beads_issue)

            # Skip if issue already exists in merge mode
            if merge and issue.full_id in existing_ids:
                skipped += 1
                if verbose:
                    print(f"⊘ Skipped {issue.full_id}: already exists")
                continue

            storage.create(issue)
            dependencies.extend(issue_deps)
            imported += 1
            if verbose:
                print(f"✓ Imported {issue.full_id}: {issue.title}")
        except Exception as e:
            failed += 1
            if verbose:
                print(f"✗ Failed to import {beads_issue.get('id', 'unknown')}: {e}")

    # Add dependencies
    for dep in dependencies:
        try:
            storage.add_dependency(
                dep.issue_id,
                dep.depends_on_id,
                dep.type.value,
                created_by=dep.created_by,
            )
        except Exception as e:  # noqa: PERF203
            if verbose:
                print(f"⚠ Failed to add dependency: {e}")

    return imported, failed, skipped
