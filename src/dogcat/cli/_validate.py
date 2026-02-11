"""JSONL data validation functions.

Pure validation logic with no CLI dependencies. Used by ``dcat doctor``
to perform deep data integrity checks on issues.jsonl.
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import orjson

from dogcat.constants import TRACKED_FIELDS
from dogcat.models import IssueType, Status, classify_record

# Fields required on every issue record
_REQUIRED_ISSUE_FIELDS = frozenset(
    {"id", "namespace", "title", "status", "priority", "issue_type"},
)

_VALID_STATUSES = frozenset(s.value for s in Status)
_VALID_TYPES = frozenset(t.value for t in IssueType)
_MIN_PRIORITY = 0
_MAX_PRIORITY = 4


def parse_raw_records(
    path: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Parse a JSONL file, returning records and per-line errors."""
    records: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    if not path.exists():
        errors.append({"level": "error", "message": f"{path} does not exist"})
        return records, errors

    for lineno, raw in enumerate(path.read_bytes().splitlines(), start=1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = orjson.loads(raw)
        except orjson.JSONDecodeError as exc:
            errors.append(
                {
                    "level": "error",
                    "message": f"Line {lineno}: invalid JSON — {exc}",
                },
            )
            continue

        if not isinstance(data, dict):
            errors.append(
                {
                    "level": "error",
                    "message": (
                        f"Line {lineno}: expected JSON object,"
                        f" got {type(data).__name__}"
                    ),
                },
            )
            continue

        record = cast("dict[str, Any]", data)

        if "record_type" not in record:
            errors.append(
                {
                    "level": "warning",
                    "message": f"Line {lineno}: missing record_type field",
                },
            )

        records.append(record)
    return records, errors


def validate_issue(
    record: dict[str, Any],
    lineno: int,
) -> list[dict[str, str]]:
    """Validate a single issue record."""
    errors: list[dict[str, str]] = []
    full_id = f"{record.get('namespace', '?')}-{record.get('id', '?')}"

    # Required fields
    errors.extend(
        {
            "level": "error",
            "message": (
                f"Line {lineno}: issue {full_id} missing required field '{field}'"
            ),
        }
        for field in _REQUIRED_ISSUE_FIELDS
        if field not in record
    )

    # Status validation
    status = record.get("status")
    if status is not None and status not in _VALID_STATUSES:
        errors.append(
            {
                "level": "error",
                "message": (
                    f"Line {lineno}: issue {full_id} has invalid status '{status}'"
                ),
            },
        )

    # Issue type validation
    issue_type = record.get("issue_type")
    if issue_type is not None and issue_type not in _VALID_TYPES:
        errors.append(
            {
                "level": "error",
                "message": (
                    f"Line {lineno}: issue {full_id} has invalid"
                    f" issue_type '{issue_type}'"
                ),
            },
        )

    # Priority validation
    priority = record.get("priority")
    if priority is not None and (
        not isinstance(priority, int)
        or priority < _MIN_PRIORITY
        or priority > _MAX_PRIORITY
    ):
        errors.append(
            {
                "level": "error",
                "message": (
                    f"Line {lineno}: issue {full_id} has invalid"
                    f" priority '{priority}'"
                    f" (must be {_MIN_PRIORITY}-{_MAX_PRIORITY})"
                ),
            },
        )

    # Timestamp validation
    for ts_field in ("created_at", "updated_at", "closed_at", "deleted_at"):
        ts = record.get(ts_field)
        if ts is not None:
            try:
                datetime.fromisoformat(ts)
            except (ValueError, TypeError):
                errors.append(
                    {
                        "level": "error",
                        "message": (
                            f"Line {lineno}: issue {full_id} has invalid"
                            f" timestamp in '{ts_field}': {ts}"
                        ),
                    },
                )

    return errors


def validate_references(
    records: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Validate referential integrity across all records."""
    errors: list[dict[str, str]] = []

    # Build set of known issue full IDs (last-write-wins)
    known_issues: set[str] = set()
    for record in records:
        if classify_record(record) == "issue":
            ns = record.get("namespace", "dc")
            rid = record.get("id", "")
            known_issues.add(f"{ns}-{rid}")

    # Check parent references
    for record in records:
        if classify_record(record) != "issue":
            continue
        parent = record.get("parent")
        if parent and parent not in known_issues:
            full_id = f"{record.get('namespace', '?')}-{record.get('id', '?')}"
            errors.append(
                {
                    "level": "error",
                    "message": (
                        f"Issue {full_id} references non-existent parent '{parent}'"
                    ),
                },
            )

    # Check dependency references
    dep_graph: dict[str, set[str]] = {}
    for record in records:
        if classify_record(record) != "dependency":
            continue
        op = record.get("op", "add")
        if op == "remove":
            continue
        issue_id = record.get("issue_id", "")
        depends_on = record.get("depends_on_id", "")

        if issue_id and issue_id not in known_issues:
            errors.append(
                {
                    "level": "error",
                    "message": (
                        f"Dependency references non-existent issue '{issue_id}'"
                    ),
                },
            )
        if depends_on and depends_on not in known_issues:
            errors.append(
                {
                    "level": "error",
                    "message": (
                        f"Dependency references"
                        f" non-existent depends_on '{depends_on}'"
                    ),
                },
            )

        # Build graph for cycle detection
        if issue_id and depends_on:
            dep_graph.setdefault(issue_id, set()).add(depends_on)

    # Check for circular dependencies (DFS)
    errors.extend(_detect_cycles(dep_graph))

    # Check event references
    for record in records:
        if classify_record(record) != "event":
            continue
        issue_id = record.get("issue_id", "")
        if issue_id and issue_id not in known_issues:
            errors.append(
                {
                    "level": "warning",
                    "message": (f"Event references non-existent issue '{issue_id}'"),
                },
            )

    return errors


def validate_jsonl(path: Path) -> list[dict[str, str]]:
    """Run all validation checks on a JSONL file.

    Returns a list of error/warning dicts with 'level' and 'message' keys.
    """
    records, errors = parse_raw_records(path)

    for lineno, record in enumerate(records, start=1):
        if classify_record(record) == "issue":
            errors.extend(validate_issue(record, lineno))

    errors.extend(validate_references(records))
    return errors


def _detect_cycles(
    graph: dict[str, set[str]],
) -> list[dict[str, str]]:
    """Detect circular dependencies using DFS."""
    errors: list[dict[str, str]] = []
    visited: set[str] = set()
    in_stack: set[str] = set()

    def _dfs(node: str, path: list[str]) -> None:
        if node in in_stack:
            cycle_start = path.index(node)
            cycle = [*path[cycle_start:], node]
            errors.append(
                {
                    "level": "error",
                    "message": (f"Circular dependency detected: {' -> '.join(cycle)}"),
                },
            )
            return
        if node in visited:
            return
        visited.add(node)
        in_stack.add(node)
        path.append(node)
        for neighbor in graph.get(node, set()):
            _dfs(neighbor, path)
        path.pop()
        in_stack.discard(node)

    for node in graph:
        if node not in visited:
            _dfs(node, [])

    return errors


# ---------------------------------------------------------------------------
# Post-merge concurrent edit detection
# ---------------------------------------------------------------------------


def _git_cmd(
    *args: str,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a git command, returning the CompletedProcess."""
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(cwd) if cwd else None,
    )


def _load_issues_at_ref(
    ref: str,
    storage_rel: str,
    cwd: Path,
) -> dict[str, dict[str, Any]]:
    """Load issue states from a git ref."""
    result = _git_cmd("show", f"{ref}:{storage_rel}", cwd=cwd)
    if result.returncode != 0:
        return {}

    issues: dict[str, dict[str, Any]] = {}
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = orjson.loads(line)
            if classify_record(data) == "issue":
                ns = data.get("namespace", "dc")
                rid = data.get("id", "")
                issues[f"{ns}-{rid}"] = data
        except (orjson.JSONDecodeError, ValueError, KeyError):
            continue
    return issues


def _field_value(value: Any) -> Any:
    """Normalize a field value for comparison."""
    if hasattr(value, "value"):
        return value.value
    return value


def detect_concurrent_edits(
    cwd: Path | None = None,
    storage_rel: str = ".dogcats/issues.jsonl",
) -> list[dict[str, Any]]:
    """Detect issues modified on both sides of the latest merge.

    Returns a list of warning dicts describing concurrent edits.
    Each warning has 'level', 'message', and 'fields' keys.
    """
    warnings: list[dict[str, Any]] = []
    work_dir = cwd or Path.cwd()

    # Find latest merge commit
    result = _git_cmd(
        "log",
        "--merges",
        "-1",
        "--format=%H",
        cwd=work_dir,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return warnings
    merge_commit = result.stdout.strip()

    # Get both parent commits
    result = _git_cmd(
        "rev-parse",
        f"{merge_commit}^1",
        f"{merge_commit}^2",
        cwd=work_dir,
    )
    if result.returncode != 0:
        return warnings
    parents = result.stdout.strip().splitlines()
    if len(parents) != 2:  # noqa: PLR2004
        return warnings
    parent1, parent2 = parents

    # Find merge base
    result = _git_cmd("merge-base", parent1, parent2, cwd=work_dir)
    if result.returncode != 0:
        return warnings
    base = result.stdout.strip()

    # Load issue states at each ref
    base_issues = _load_issues_at_ref(base, storage_rel, work_dir)
    p1_issues = _load_issues_at_ref(parent1, storage_rel, work_dir)
    p2_issues = _load_issues_at_ref(parent2, storage_rel, work_dir)

    # Find issues modified in BOTH parents relative to base
    p1_modified = {
        fid
        for fid in p1_issues
        if fid in base_issues and p1_issues[fid] != base_issues[fid]
    }
    p2_modified = {
        fid
        for fid in p2_issues
        if fid in base_issues and p2_issues[fid] != base_issues[fid]
    }
    both_modified = p1_modified & p2_modified

    for fid in sorted(both_modified):
        base_state = base_issues[fid]
        p1_state = p1_issues[fid]
        p2_state = p2_issues[fid]

        # Compute field-level diffs
        field_diffs: dict[str, dict[str, Any]] = {}
        for field in TRACKED_FIELDS:
            base_val = _field_value(base_state.get(field))
            p1_val = _field_value(p1_state.get(field))
            p2_val = _field_value(p2_state.get(field))

            both_changed = p1_val != base_val or p2_val != base_val
            if both_changed and p1_val != p2_val:
                field_diffs[field] = {
                    "base": base_val,
                    "branch_1": p1_val,
                    "branch_2": p2_val,
                }

        if field_diffs:
            title = p1_state.get("title", p2_state.get("title", fid))
            warnings.append(
                {
                    "level": "warning",
                    "message": (
                        f"Issue {fid} ({title}) was modified on"
                        f" both branches"
                        f" ({len(field_diffs)} field(s))"
                    ),
                    "issue_id": fid,
                    "fields": field_diffs,
                },
            )

    return warnings
