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
    params: dict[str, object] = getattr(ctx, "params", None) or {}

    if params.get("all_namespaces", False):
        return None

    ns = params.get("namespace")
    explicit_ns: str | None = str(ns) if isinstance(ns, str) else None
    return get_namespace_filter(dogcats_dir, explicit_ns)


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


def complete_closed_issue_ids(
    ctx: Any,
    args: list[str],  # noqa: ARG001 (always [] from Typer, kept for signature compat)
    incomplete: str,
) -> list[tuple[str, str]]:
    """Complete closed issue IDs from storage (for reopen command)."""
    try:
        storage = get_storage()
        ns_filter = _ns_filter_from_ctx(ctx, str(storage.dogcats_dir))
        results: list[tuple[str, str]] = []
        for i in storage.list():
            if i.status.value != "closed":
                continue
            if ns_filter is not None and not ns_filter(i.namespace):
                continue
            fid = i.full_id
            short_id = i.id
            if fid.startswith(incomplete):
                results.append((fid, i.title))
            elif short_id.startswith(incomplete):
                results.append((short_id, i.title))
        return sorted(results)
    except Exception:
        return []


def complete_proposal_ids(
    ctx: Any,
    args: list[str],  # noqa: ARG001 (always [] from Typer, kept for signature compat)
    incomplete: str,
) -> list[tuple[str, str]]:
    """Complete proposal IDs from local and remote inbox."""
    try:
        from pathlib import Path

        from dogcat.config import get_issue_prefix, load_config
        from dogcat.inbox import InboxStorage

        from ._helpers import find_dogcats_dir

        dogcats_dir = find_dogcats_dir()
        ns_filter = _ns_filter_from_ctx(ctx, dogcats_dir)
        results: list[tuple[str, str]] = []
        seen: set[str] = set()

        # Local proposals
        inbox = InboxStorage(dogcats_dir=dogcats_dir)
        for p in inbox.list(include_tombstones=False):
            if ns_filter is not None and not ns_filter(p.namespace):
                continue
            desc = f"{p.title} [{p.status.value}]" if p.is_closed() else p.title
            fid = p.full_id
            if fid.startswith(incomplete):
                results.append((fid, desc))
                seen.add(fid)
            elif p.id.startswith(incomplete):
                results.append((p.id, desc))
                seen.add(fid)

        # Remote proposals
        config = load_config(dogcats_dir)
        remote_path = config.get("inbox_remote")
        if remote_path:
            remote_dogcats = Path(remote_path).expanduser()
            if remote_dogcats.name != ".dogcats":
                candidate = remote_dogcats / ".dogcats"
                if candidate.is_dir():
                    remote_dogcats = candidate
            if remote_dogcats.is_dir():
                current_ns = get_issue_prefix(dogcats_dir)
                remote_inbox = InboxStorage(dogcats_dir=str(remote_dogcats))
                for p in remote_inbox.list(
                    include_tombstones=False,
                    namespace=current_ns,
                ):
                    if p.is_closed():
                        continue
                    fid = p.full_id
                    if fid in seen:
                        continue
                    desc = f"{p.title} (remote)"
                    if fid.startswith(incomplete):
                        results.append((fid, desc))
                    elif p.id.startswith(incomplete):
                        results.append((p.id, desc))

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


def complete_namespaces(
    ctx: Any,  # noqa: ARG001
    args: list[str],  # noqa: ARG001
    incomplete: str,
) -> list[tuple[str, str]]:
    """Complete namespace values from existing issues and proposals."""
    try:
        from dogcat.storage import get_namespaces

        storage = get_storage()
        ns_counts = get_namespaces(storage)

        return [
            (ns, f"{counts.total} item(s)")
            for ns, counts in sorted(ns_counts.items())
            if ns.startswith(incomplete)
        ]
    except Exception:
        return []


def complete_owners(
    ctx: Any,  # noqa: ARG001
    args: list[str],  # noqa: ARG001
    incomplete: str,
) -> list[tuple[str, str]]:
    """Complete owner values from existing issues."""
    try:
        storage = get_storage()
        owners: set[str] = set()
        for issue in storage.list():
            if issue.owner:
                owners.add(issue.owner)
        return [
            (owner, "owner") for owner in sorted(owners) if owner.startswith(incomplete)
        ]
    except Exception:
        return []


def complete_config_keys(incomplete: str) -> list[tuple[str, str]]:
    """Complete configuration key names."""
    from dogcat.cli._cmd_config import _KNOWN_KEYS

    return [
        (key, info["description"])
        for key, info in _KNOWN_KEYS.items()
        if key.startswith(incomplete)
    ]


def complete_export_formats(incomplete: str) -> list[tuple[str, str]]:
    """Complete export format values."""
    options = [
        ("json", "JSON object with issues, dependencies, and links"),
        ("jsonl", "JSON Lines (one record per line)"),
    ]
    return [(v, h) for v, h in options if v.startswith(incomplete)]


def complete_durations(incomplete: str) -> list[tuple[str, str]]:
    """Complete common duration values for --older-than."""
    options = [
        ("7d", "1 week"),
        ("14d", "2 weeks"),
        ("30d", "1 month"),
        ("60d", "2 months"),
        ("90d", "3 months"),
    ]
    return [(v, h) for v, h in options if v.startswith(incomplete)]


def complete_dates(incomplete: str) -> list[tuple[str, str]]:
    """Complete recent date values for --closed-after / --closed-before."""
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    suggestions: list[tuple[str, str]] = []
    for label, delta in [
        ("today", timedelta(days=0)),
        ("1 week ago", timedelta(days=7)),
        ("2 weeks ago", timedelta(days=14)),
        ("1 month ago", timedelta(days=30)),
        ("3 months ago", timedelta(days=90)),
        ("6 months ago", timedelta(days=180)),
        ("1 year ago", timedelta(days=365)),
    ]:
        date_str = (now - delta).strftime("%Y-%m-%d")
        if date_str.startswith(incomplete):
            suggestions.append((date_str, label))
    return suggestions


def complete_config_values(
    ctx: Any,
    args: list[str],  # noqa: ARG001
    incomplete: str,
) -> list[tuple[str, str]]:
    """Complete config values based on the key being set."""
    from dogcat.cli._cmd_config import _ARRAY_KEYS, _BOOL_KEYS, _KNOWN_KEYS

    # The key is the first positional arg (args is always [] from Typer,
    # so read from ctx.params instead).
    params: dict[str, Any] = getattr(ctx, "params", None) or {}
    key: str = params.get("key", "")

    if key in _BOOL_KEYS:
        options = [
            ("true", "Enable"),
            ("false", "Disable"),
        ]
        return [(v, h) for v, h in options if v.startswith(incomplete)]

    if key in _ARRAY_KEYS and key in ("visible_namespaces", "hidden_namespaces"):
        try:
            storage = get_storage()
            ns_set: set[str] = set()
            for issue in storage.list():
                ns_set.add(issue.namespace)
            return [
                (ns, "namespace") for ns in sorted(ns_set) if ns.startswith(incomplete)
            ]
        except Exception:
            return []

    # For keys with documented values, show them from _KNOWN_KEYS
    info = _KNOWN_KEYS.get(key, {})
    if "values" in info:
        return [(info["values"], "allowed values")]

    return []


def complete_dep_types(incomplete: str) -> list[tuple[str, str]]:
    """Complete dependency type values."""
    options = [
        ("blocks", "Blocking dependency"),
    ]
    return [(v, h) for v, h in options if v.startswith(incomplete)]


def complete_link_types(incomplete: str) -> list[tuple[str, str]]:
    """Complete link type values."""
    options = [
        ("relates_to", "General relationship"),
        ("duplicates", "Duplicate issue"),
    ]
    return [(v, h) for v, h in options if v.startswith(incomplete)]
