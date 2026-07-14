"""JSONL data validation functions.

Pure validation logic with no CLI dependencies. Used by ``dcat doctor``
to perform deep data integrity checks on issues.jsonl and inbox.jsonl.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, cast

import orjson

from dogcat.constants import DEFAULT_NAMESPACE, TRACKED_FIELDS
from dogcat.models import IssueType, ProposalStatus, Status, classify_record


@dataclass(frozen=True)
class ValidationError:
    """A typed validation error for a JSONL line.

    Canonical shape for issue / proposal validation results — every
    ``validate_*`` helper returns ``list[ValidationError]`` so Pyright
    catches field typos. :meth:`to_dict` serializes to the legacy
    ``{"level": ..., "message": ...}`` shape at the JSON-output boundary
    (``dcat doctor --json``).
    """

    level: Literal["error", "warning"]
    message: str

    def to_dict(self) -> dict[str, str]:
        """Serialize to the legacy ``{"level": ..., "message": ...}`` shape."""
        return {"level": self.level, "message": self.message}


@dataclass(frozen=True)
class ConcurrentFieldDiff:
    """A field-level diff across the two sides of a merge.

    ``base`` is the field's value at the merge base; ``branch_1`` and
    ``branch_2`` are the conflicting parent-side values.
    """

    base: Any
    branch_1: Any
    branch_2: Any

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the legacy ``{"base", "branch_1", "branch_2"}`` shape."""
        return {
            "base": self.base,
            "branch_1": self.branch_1,
            "branch_2": self.branch_2,
        }


@dataclass(frozen=True)
class ConcurrentEditWarning:
    """A warning that an issue was edited on both sides of the latest merge.

    ``fields`` maps each field name to the per-side diff. Doctor's
    pretty-printer was previously stringly-typed against the dict shape
    via ``warn['message']``/``warn.get('fields', {})``.
    """

    level: Literal["warning"]
    message: str
    issue_id: str
    fields: dict[str, ConcurrentFieldDiff] = dc_field(
        default_factory=dict[str, "ConcurrentFieldDiff"],
    )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the legacy nested-dict shape consumed by the renderer."""
        return {
            "level": self.level,
            "message": self.message,
            "issue_id": self.issue_id,
            "fields": {name: diff.to_dict() for name, diff in self.fields.items()},
        }


# Fields required on every issue record
_REQUIRED_ISSUE_FIELDS = frozenset(
    {"id", "namespace", "title", "status", "priority", "issue_type"},
)

# Fields required on every proposal record
_REQUIRED_PROPOSAL_FIELDS = frozenset(
    {"id", "namespace", "title", "status"},
)

_VALID_STATUSES = frozenset(s.value for s in Status)
_VALID_PROPOSAL_STATUSES = frozenset(s.value for s in ProposalStatus)
# Includes legacy values migrated on load (see models.dict_to_issue)
_VALID_TYPES = frozenset(t.value for t in IssueType) | {"draft", "subtask"}
_MIN_PRIORITY = 0
_MAX_PRIORITY = 4


def parse_raw_records(
    path: Path,
) -> tuple[list[dict[str, Any]], list[ValidationError]]:
    """Parse a JSONL file, returning records and per-line errors."""
    records: list[dict[str, Any]] = []
    errors: list[ValidationError] = []
    if not path.exists():
        errors.append(ValidationError(level="error", message=f"{path} does not exist"))
        return records, errors

    for lineno, raw in enumerate(path.read_bytes().splitlines(), start=1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = orjson.loads(raw)
        except orjson.JSONDecodeError as exc:
            errors.append(
                ValidationError(
                    level="error", message=f"Line {lineno}: invalid JSON — {exc}"
                ),
            )
            continue

        if not isinstance(data, dict):
            errors.append(
                ValidationError(
                    level="error",
                    message=f"Line {lineno}: expected JSON object,"
                    f" got {type(data).__name__}",
                ),
            )
            continue

        record = cast("dict[str, Any]", data)

        if "record_type" not in record:
            errors.append(
                ValidationError(
                    level="warning", message=f"Line {lineno}: missing record_type field"
                ),
            )

        records.append(record)
    return records, errors


def validate_issue_record(
    record: dict[str, Any],
    lineno: int,
) -> list[ValidationError]:
    """Validate a single issue record from the JSONL log.

    Mirrors :func:`validate_proposal_record` in this module — the
    ``_record`` suffix disambiguates this from
    :func:`dogcat.models.validate_issue`, which validates an in-memory
    ``Issue`` dataclass instead of a raw dict, and would otherwise
    collide on import.
    """
    errors: list[ValidationError] = []
    full_id = f"{record.get('namespace', '?')}-{record.get('id', '?')}"

    # Required fields
    errors.extend(
        ValidationError(
            level="error",
            message=f"Line {lineno}: issue {full_id} missing required field '{field}'",
        )
        for field in _REQUIRED_ISSUE_FIELDS
        if field not in record
    )

    # Status validation
    status = record.get("status")
    if status is not None and status not in _VALID_STATUSES:
        errors.append(
            ValidationError(
                level="error",
                message=f"Line {lineno}: issue {full_id} has invalid status '{status}'",
            ),
        )

    # Issue type validation
    issue_type = record.get("issue_type")
    if issue_type is not None and issue_type not in _VALID_TYPES:
        errors.append(
            ValidationError(
                level="error",
                message=f"Line {lineno}: issue {full_id} has invalid"
                f" issue_type '{issue_type}'",
            ),
        )

    # Priority validation
    priority = record.get("priority")
    if priority is not None and (
        not isinstance(priority, int)
        or priority < _MIN_PRIORITY
        or priority > _MAX_PRIORITY
    ):
        errors.append(
            ValidationError(
                level="error",
                message=f"Line {lineno}: issue {full_id} has invalid"
                f" priority '{priority}'"
                f" (must be {_MIN_PRIORITY}-{_MAX_PRIORITY})",
            ),
        )

    errors.extend(
        _validate_timestamps(
            record,
            ("created_at", "updated_at", "closed_at", "deleted_at"),
            context=f"issue {full_id}",
            lineno=lineno,
        ),
    )

    return errors


def _validate_timestamps(
    record: dict[str, Any],
    timestamp_fields: tuple[str, ...],
    *,
    context: str,
    lineno: int,
) -> list[ValidationError]:
    """Validate ISO8601 timestamp fields on a record.

    ``context`` is the human-readable subject (e.g. ``"issue dc-abc1"`` or
    ``"proposal dc-inbox-4kzj"``) used in error messages.
    """
    errors: list[ValidationError] = []
    for ts_field in timestamp_fields:
        ts = record.get(ts_field)
        if ts is None:
            continue
        try:
            datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            errors.append(
                ValidationError(
                    level="error",
                    message=f"Line {lineno}: {context} has invalid"
                    f" timestamp in '{ts_field}': {ts}",
                ),
            )
    return errors


def validate_references(
    records: list[dict[str, Any]],
) -> list[ValidationError]:
    """Validate referential integrity of the resolved store state.

    The log is append-only: issue records supersede earlier ones
    (last-write-wins by full id) and dependency records replay
    ``add``/``remove`` ops. Reference checks therefore run on the
    *resolved* state only — a superseded record's parent legitimately goes
    stale when the referenced issue is later pruned or renamed, and the
    next compaction drops the record entirely. Event
    references stay per-record (events are never superseded) and are
    warnings, not errors.
    """
    errors: list[ValidationError] = []

    # Resolve issue records last-write-wins, mirroring JSONLStorage._load
    resolved_issues: dict[str, dict[str, Any]] = {}
    for record in records:
        if classify_record(record) == "issue":
            ns = record.get("namespace", DEFAULT_NAMESPACE)
            rid = record.get("id", "")
            resolved_issues[f"{ns}-{rid}"] = record
    known_issues = frozenset(resolved_issues)

    # Check parent references on the resolved records only
    for full_id, record in resolved_issues.items():
        parent = record.get("parent")
        if parent and parent not in known_issues:
            errors.append(
                ValidationError(
                    level="error",
                    message=(
                        f"Issue {full_id} references non-existent parent '{parent}'"
                    ),
                ),
            )

    # Replay dependency ops; keyed like storage's parse_dependency_record
    # so a ``remove`` cancels the matching ``add``
    resolved_deps: dict[tuple[str, str, Any], dict[str, Any]] = {}
    for record in records:
        if classify_record(record) != "dependency":
            continue
        key = (
            record.get("issue_id", ""),
            record.get("depends_on_id", ""),
            record.get("type"),
        )
        if record.get("op", "add") == "remove":
            resolved_deps.pop(key, None)
        else:
            resolved_deps[key] = record

    dep_graph: dict[str, set[str]] = {}
    for issue_id, depends_on, _dep_type in resolved_deps:
        if issue_id and issue_id not in known_issues:
            errors.append(
                ValidationError(
                    level="error",
                    message=f"Dependency references non-existent issue '{issue_id}'",
                ),
            )
        if depends_on and depends_on not in known_issues:
            errors.append(
                ValidationError(
                    level="error",
                    message=(
                        f"Dependency references non-existent depends_on '{depends_on}'"
                    ),
                ),
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
                ValidationError(
                    level="warning",
                    message=f"Event references non-existent issue '{issue_id}'",
                ),
            )

    return errors


def validate_jsonl(path: Path) -> list[ValidationError]:
    """Run all validation checks on a JSONL file.

    Returns a ``list[ValidationError]`` — access ``.level`` (``"error"`` or
    ``"warning"``) and ``.message`` as attributes; call ``.to_dict()`` for
    the legacy ``{"level", "message"}`` JSON shape.
    """
    records, errors = parse_raw_records(path)

    for lineno, record in enumerate(records, start=1):
        if classify_record(record) == "issue":
            errors.extend(validate_issue_record(record, lineno))

    errors.extend(validate_references(records))
    return errors


def validate_proposal_record(
    record: dict[str, Any],
    lineno: int,
) -> list[ValidationError]:
    """Validate a single proposal record."""
    errors: list[ValidationError] = []
    full_id = f"{record.get('namespace', '?')}-inbox-{record.get('id', '?')}"

    # Required fields
    errors.extend(
        ValidationError(
            level="error",
            message=(
                f"Line {lineno}: proposal {full_id} missing required field '{field}'"
            ),
        )
        for field in _REQUIRED_PROPOSAL_FIELDS
        if field not in record
    )

    # Status validation
    status = record.get("status")
    if status is not None and status not in _VALID_PROPOSAL_STATUSES:
        errors.append(
            ValidationError(
                level="error",
                message=(
                    f"Line {lineno}: proposal {full_id} has invalid status '{status}'"
                ),
            ),
        )

    errors.extend(
        _validate_timestamps(
            record,
            ("created_at", "updated_at", "closed_at"),
            context=f"proposal {full_id}",
            lineno=lineno,
        ),
    )

    return errors


def validate_inbox_jsonl(path: Path) -> list[ValidationError]:
    """Run validation checks on an inbox.jsonl file.

    Returns a ``list[ValidationError]`` — access ``.level`` (``"error"`` or
    ``"warning"``) and ``.message`` as attributes; call ``.to_dict()`` for
    the legacy ``{"level", "message"}`` JSON shape.
    """
    records, errors = parse_raw_records(path)

    for lineno, record in enumerate(records, start=1):
        if classify_record(record) == "proposal":
            errors.extend(validate_proposal_record(record, lineno))

    return errors


def _detect_cycles(
    graph: dict[str, set[str]],
) -> list[ValidationError]:
    """Detect circular dependencies using iterative DFS.

    Iterative — recursive form blew Python's frame limit on a 1001-deep
    chain. Uses explicit ``(node, neighbor_iter)`` frames.
    """
    errors: list[ValidationError] = []
    visited: set[str] = set()
    in_stack: set[str] = set()

    for root in graph:
        if root in visited:
            continue
        path: list[str] = [root]
        visited.add(root)
        in_stack.add(root)
        stack: list[tuple[str, Any]] = [(root, iter(graph.get(root, set())))]
        while stack:
            node, it = stack[-1]
            try:
                neighbor = next(it)
            except StopIteration:
                in_stack.discard(node)
                if path and path[-1] == node:
                    path.pop()
                stack.pop()
                continue
            if neighbor in in_stack:
                cycle_start = path.index(neighbor)
                cycle = [*path[cycle_start:], neighbor]
                errors.append(
                    ValidationError(
                        level="error",
                        message=f"Circular dependency detected: {' -> '.join(cycle)}",
                    ),
                )
            elif neighbor not in visited:
                visited.add(neighbor)
                in_stack.add(neighbor)
                path.append(neighbor)
                stack.append((neighbor, iter(graph.get(neighbor, set()))))

    return errors


# Post-merge concurrent edit detection


def _load_issues_at_ref(
    ref: str,
    storage_rel: str,
    cwd: Path,
) -> dict[str, dict[str, Any]] | None:
    """Load issue states from a git ref.

    Returns ``None`` when ``git show <ref>:<path>`` fails (missing ref,
    missing path at that ref, permission denied, git unavailable). Callers
    must distinguish this from an empty dict, which legitimately means
    ``the file existed at that ref and contained no issues``.
    """
    import dogcat.git as git_helpers

    raw = git_helpers.show_file(f"{ref}:{storage_rel}", cwd=cwd)
    if raw is None:
        return None

    issues: dict[str, dict[str, Any]] = {}
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            data = orjson.loads(line)
            if classify_record(data) == "issue":
                ns = data.get("namespace", DEFAULT_NAMESPACE)
                rid = data.get("id", "")
                issues[f"{ns}-{rid}"] = data
        except (orjson.JSONDecodeError, ValueError, KeyError):
            continue
    return issues


def _field_value(value: Any) -> Any:
    """Normalize a field value for comparison (delegates to _diff)."""
    from dogcat._diff import field_value

    return field_value(value)


def detect_concurrent_edits(
    cwd: Path | None = None,
    storage_rel: str = ".dogcats/issues.jsonl",
) -> list[dict[str, Any]]:
    """Detect issues modified on both sides of the latest merge.

    Returns a list of warning dicts. Every warning has ``level`` and
    ``message``; beyond that there are two shapes:

    - Concurrent-edit warnings also carry ``issue_id`` and ``fields`` (a
      field-name → per-side diff mapping).
    - The single ref-load-failure warning carries ``failed_refs`` (a list
      of ``{role, ref}``) instead of ``fields`` — emitted when the storage
      file could not be read at base/parent_1/parent_2, meaning detection
      was skipped rather than clean.
    """
    import dogcat.git as git_helpers

    warnings: list[dict[str, Any]] = []
    work_dir = cwd or Path.cwd()

    merge_commit = git_helpers.latest_merge_commit(cwd=work_dir)
    if merge_commit is None:
        return warnings

    parents = git_helpers.merge_parents(merge_commit, cwd=work_dir)
    if parents is None:
        return warnings
    parent1, parent2 = parents

    base = git_helpers.merge_base(parent1, parent2, cwd=work_dir)
    if base is None:
        return warnings

    # Load issue states at each ref. ``None`` means the ref itself loaded
    # but the storage file couldn't be read (missing path at that ref, git
    # error, permission denied). Returning [] in that case used to look
    # like ``no concurrent edits`` while actually meaning ``we have no
    # idea`` — surface the integrity gap as a warning instead.
    base_issues = _load_issues_at_ref(base, storage_rel, work_dir)
    p1_issues = _load_issues_at_ref(parent1, storage_rel, work_dir)
    p2_issues = _load_issues_at_ref(parent2, storage_rel, work_dir)

    failed_refs: list[tuple[str, str]] = []
    if base_issues is None:
        failed_refs.append(("base", base))
    if p1_issues is None:
        failed_refs.append(("parent_1", parent1))
    if p2_issues is None:
        failed_refs.append(("parent_2", parent2))
    if failed_refs:
        names = ", ".join(f"{role}={ref}" for role, ref in failed_refs)
        warnings.append(
            {
                "level": "warning",
                "message": (
                    "Concurrent-edit detection skipped: could not read"
                    f" {storage_rel} at {names}. Detection is incomplete;"
                    " investigate the missing ref(s) before trusting the"
                    " merge result."
                ),
                "failed_refs": [
                    {"role": role, "ref": ref} for role, ref in failed_refs
                ],
            },
        )
        return warnings

    # Narrow types after the integrity guard above.
    assert base_issues is not None
    assert p1_issues is not None
    assert p2_issues is not None

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
