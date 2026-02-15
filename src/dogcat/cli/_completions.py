"""Shell completion callbacks for dogcat CLI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dogcat.config import get_namespace_filter
from dogcat.constants import PRIORITY_NAMES, STATUS_OPTIONS, TYPE_OPTIONS

from ._helpers import get_storage

if TYPE_CHECKING:
    from collections.abc import Callable

# Return (value, help_text) tuples so Typer generates "value":"description"
# pairs in the zsh completion output. Bare strings without descriptions cause
# zsh's _arguments (()) parser to emit "number expected" errors.


def _ns_filter_from_ctx(
    ctx: Any,
    dogcats_dir: str,
) -> Callable[[str], bool] | None:
    """Build a namespace filter from the Click context.

    Reads ctx.params for all_namespaces and namespace options.
    Commands must define hidden -A / --namespace options for this to work.
    """
    params = getattr(ctx, "params", None) or {}

    if params.get("all_namespaces", False):
        return None

    return get_namespace_filter(dogcats_dir, params.get("namespace"))


def complete_issue_ids(
    ctx: Any,
    args: list[str],  # noqa: ARG001 (always [] from Typer, kept for signature compat)
    incomplete: str,
) -> list[tuple[str, str]]:
    """Complete issue IDs from storage, respecting namespace visibility."""
    try:
        storage = get_storage()
        ns_filter = _ns_filter_from_ctx(ctx, str(storage.dogcats_dir))
        results: list[tuple[str, str]] = []
        for i in storage.list():
            if i.status.value in ("closed", "tombstone"):
                continue
            if ns_filter is not None and not ns_filter(i.namespace):
                continue
            fid = i.full_id
            short_id = i.id  # part after namespace prefix
            if fid.startswith(incomplete):
                results.append((fid, i.title))
            elif short_id.startswith(incomplete):
                results.append((short_id, i.title))
        return sorted(results)
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


def complete_subcommands(incomplete: str) -> list[tuple[str, str]]:
    """Complete subcommand values for dep, link, and label commands."""
    options = [
        ("add", "Add a new entry"),
        ("remove", "Remove an entry"),
        ("list", "List all entries"),
    ]
    return [(v, h) for v, h in options if v.startswith(incomplete)]


def complete_comment_actions(incomplete: str) -> list[tuple[str, str]]:
    """Complete action values for the comment command."""
    options = [
        ("add", "Add a comment"),
        ("list", "List all comments"),
        ("delete", "Delete a comment"),
    ]
    return [(v, h) for v, h in options if v.startswith(incomplete)]


def complete_labels(
    ctx: Any,
    args: list[str],  # noqa: ARG001 (always [] from Typer, kept for signature compat)
    incomplete: str,
) -> list[tuple[str, str]]:
    """Complete label values from existing issues, respecting namespace visibility."""
    try:
        storage = get_storage()
        ns_filter = _ns_filter_from_ctx(ctx, str(storage.dogcats_dir))
        labels: set[str] = set()
        for issue in storage.list():
            if ns_filter is None or ns_filter(issue.namespace):
                labels.update(issue.labels)
        return [(lbl, "label") for lbl in sorted(labels) if lbl.startswith(incomplete)]
    except Exception:
        return []
