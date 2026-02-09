"""Shell completion callbacks for dogcat CLI."""

from __future__ import annotations

from dogcat.constants import PRIORITY_NAMES, STATUS_OPTIONS, TYPE_OPTIONS

from ._helpers import get_storage

# Return (value, help_text) tuples so Typer generates "value":"description"
# pairs in the zsh completion output. Bare strings without descriptions cause
# zsh's _arguments (()) parser to emit "number expected" errors.


def complete_issue_ids(incomplete: str) -> list[tuple[str, str]]:
    """Complete issue IDs from storage."""
    try:
        storage = get_storage()
        issues = {i.full_id: i.title for i in storage.list()}
        return sorted(
            (fid, title) for fid, title in issues.items() if fid.startswith(incomplete)
        )
    except Exception:
        return []


def complete_statuses(incomplete: str) -> list[tuple[str, str]]:
    """Complete status values."""
    return [
        (value, label)
        for label, value in STATUS_OPTIONS
        if value.startswith(incomplete)
    ]


def complete_types(incomplete: str) -> list[tuple[str, str]]:
    """Complete issue type values."""
    return [
        (value, label) for label, value in TYPE_OPTIONS if value.startswith(incomplete)
    ]


def complete_priorities(incomplete: str) -> list[tuple[str, str]]:
    """Complete priority values (integers and names)."""
    items: list[tuple[str, str]] = [
        ("0", "Critical"),
        ("1", "High"),
        ("2", "Medium"),
        ("3", "Low"),
        ("4", "Minimal"),
    ]
    items.extend(
        sorted((name, f"Priority {val}") for name, val in PRIORITY_NAMES.items()),
    )
    return [(v, h) for v, h in items if v.startswith(incomplete)]


def complete_labels(incomplete: str) -> list[tuple[str, str]]:
    """Complete label values from existing issues."""
    try:
        storage = get_storage()
        labels: set[str] = set()
        for issue in storage.list():
            labels.update(issue.labels)
        return [(lbl, "label") for lbl in sorted(labels) if lbl.startswith(incomplete)]
    except Exception:
        return []
