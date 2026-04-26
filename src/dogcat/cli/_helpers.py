"""Shared infrastructure for dogcat CLI commands."""

from __future__ import annotations

import functools
import getpass
import inspect
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import typer
from typer.core import TyperGroup

from dogcat.config import parse_dogcatrc
from dogcat.constants import (
    ALL_SHORTHANDS,
    DOGCATRC_FILENAME,
    PRIORITY_NAMES,
    PRIORITY_SHORTHANDS,
    STATUS_SHORTHANDS,
    TYPE_SHORTHANDS,
)
from dogcat.models import Issue, Proposal, is_manual_issue
from dogcat.storage import JSONLStorage

if TYPE_CHECKING:
    from collections.abc import Callable

    import click


_type_keys = "/".join(sorted(TYPE_SHORTHANDS.keys()))
_status_keys = "/".join(sorted(STATUS_SHORTHANDS.keys()))
_ARG_HELP = "Issue title"
_ARG_HELP_SHORTHAND = (
    f"Title or shorthand (0-4 for priority,"
    f" {_type_keys} for type, {_status_keys} for status)"
)


def with_ns_shim(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorate a Typer command with hidden --namespace / --all-namespaces options.

    Why: these flags are owned by the global Typer callback, but Typer parses
    options at the level they appear on the command line. Without per-command
    shim params, ``dcat close ISSUE --namespace ns`` errors out because
    ``close`` doesn't declare them. The shim accepts and discards the values;
    the actual filter is applied by ``get_namespace_filter()`` reading the
    process state set by the global callback.
    """
    sig = inspect.signature(func)
    shim_params = [
        inspect.Parameter(
            "all_namespaces",
            inspect.Parameter.KEYWORD_ONLY,
            default=typer.Option(
                False,
                "--all-namespaces",
                "--all-ns",
                "-A",
                hidden=True,
            ),
            annotation="bool",
        ),
        inspect.Parameter(
            "namespace",
            inspect.Parameter.KEYWORD_ONLY,
            default=typer.Option(None, "--namespace", hidden=True),
            annotation="str | None",
        ),
    ]
    new_params = list(sig.parameters.values()) + shim_params

    @functools.wraps(func)
    def wrapper(**kwargs: Any) -> Any:
        kwargs.pop("all_namespaces", None)
        kwargs.pop("namespace", None)
        return func(**kwargs)

    wrapper.__signature__ = sig.replace(parameters=new_params)  # type: ignore[attr-defined]
    wrapper.__annotations__ = {
        **func.__annotations__,
        "all_namespaces": "bool",
        "namespace": "str | None",
    }
    return wrapper


def _make_alias(
    source_fn: Callable[..., Any],
    *,
    doc: str,
    exclude_params: frozenset[str] = frozenset(),
    param_defaults: dict[str, Any] | None = None,
    param_help: dict[str, str] | None = None,
) -> Callable[..., Any]:
    """Create a CLI command alias by cloning a source function's signature.

    Typer infers CLI parameters from function signatures. This creates a thin
    wrapper that shares the source function's signature (minus any excluded
    params) so parameter declarations aren't duplicated across aliases.

    ``param_help`` overrides the help text on specific parameters (useful when
    the alias presents an argument differently, e.g. "Issue title" instead of
    the shorthand-aware help string).
    """
    import copy

    defaults = param_defaults or {}
    sig = inspect.signature(source_fn)
    new_params = [p for name, p in sig.parameters.items() if name not in exclude_params]

    if param_help:
        updated: list[inspect.Parameter] = []
        for p in new_params:
            if p.name in param_help:
                new_default = copy.copy(p.default)
                new_default.help = param_help[p.name]
                updated.append(p.replace(default=new_default))
            else:
                updated.append(p)
        new_params = updated

    def wrapper(**kwargs: Any) -> Any:
        kwargs.update(defaults)
        return source_fn(**kwargs)

    wrapper.__signature__ = sig.replace(parameters=new_params)  # type: ignore[attr-defined]
    wrapper.__doc__ = doc
    wrapper.__module__ = source_fn.__module__
    # Copy string annotations so typing.get_type_hints() resolves them
    # correctly (required when using `from __future__ import annotations`).
    wrapper.__annotations__ = {
        name: ann
        for name, ann in source_fn.__annotations__.items()
        if name not in exclude_params
    }
    return wrapper


def require_resolved_id(
    storage: JSONLStorage, raw_id: str, *, label: str = "Issue"
) -> str:
    """Resolve a partial id or echo+exit with a clear error.

    Replaces the six-line ``if foo: resolved = storage.resolve_id(foo); if
    resolved is None: echo_error(...); raise typer.Exit(1); foo = resolved``
    pattern in CLI commands that accept reference flags (``--depends-on``,
    ``--blocks``, ``--duplicate-of``, ``--parent``). ``label`` lets each
    call site surface the role (``"Parent issue"``, ``"Duplicate target"``)
    in the error message.
    """
    from ._json_state import echo_error

    resolved = storage.resolve_id(raw_id)
    if resolved is None:
        echo_error(f"{label} {raw_id} not found")
        raise typer.Exit(1)
    return resolved


def cli_command(func: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap a Typer command body in the standard try/except envelope.

    Most CLI commands wrap their body in::

        try:
            ...
        except typer.Exit:
            raise
        except Exception as e:
            echo_error(str(e))
            raise typer.Exit(1)

    This decorator handles that uniform envelope so command bodies can
    focus on the work. ``typer.BadParameter`` is also re-raised so Typer
    can surface its own usage message; everything else flows through
    :func:`echo_error` and exits with rc=1.
    """
    from ._json_state import echo_error

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except (typer.Exit, typer.BadParameter):
            raise
        except Exception as e:  # noqa: BLE001
            echo_error(str(e))
            raise typer.Exit(1) from e

    return wrapper


def apply_to_each(
    ids: list[str],
    op: Callable[[str], None],
    *,
    verb: str,
) -> bool:
    """Apply ``op`` to each id, recording errors with a verb prefix.

    Returns True if any iteration raised. Each error is reported via
    :func:`echo_error` as ``"{verb} {id}: {exc}"``. The caller typically
    raises ``typer.Exit(1)`` when this returns True.
    """
    from ._json_state import echo_error

    has_errors = False
    for id_ in ids:
        try:
            op(id_)
        except Exception as e:  # noqa: BLE001, PERF203
            echo_error(f"{verb} {id_}: {e}")
            has_errors = True
    return has_errors


class SortedGroup(TyperGroup):
    """Typer group that lists commands in alphabetical order."""

    def list_commands(self, ctx: click.Context) -> list[str]:
        """Return commands sorted alphabetically."""
        return sorted(super().list_commands(ctx))


@functools.lru_cache(maxsize=1)
def get_default_operator() -> str:
    """Get the default operator (user identifier) for issue operations.

    Tries to get the git config user.email first, falls back to machine username.

    Returns:
        User email from git config, or machine username as fallback.
    """
    import dogcat.git as git_helpers

    email = git_helpers.user_email()
    if email:
        return email
    return getpass.getuser()


def is_gitignored(path: str) -> bool:
    """Check if a path is covered by .gitignore.

    Returns True if the path is gitignored, False otherwise (including
    when not in a git repo or git is not available).
    """
    import dogcat.git as git_helpers

    return git_helpers.is_path_ignored(path)


def find_dogcats_dir(start_dir: str | None = None) -> str:
    """Find .dogcats directory by searching upward from start_dir.

    Checks for .dogcatrc first (external directory reference), then falls back
    to searching for .dogcats/ directly. If the upward walk fails, checks the
    main git worktree root (via ``git rev-parse --git-common-dir``) so that
    linked worktrees transparently share the main tree's .dogcats directory.

    The walk is bounded by :func:`dogcat.config.get_rc_walkup_boundary`
    (git toplevel by default, or ``$HOME``) to prevent a planted
    ``/tmp/.dogcatrc`` from silently re-rooting commands. Set
    ``DCAT_RC_WALKUP_UNRESTRICTED=1`` to fall back to legacy behavior.
    (dogcat-4107)

    Args:
        start_dir: Directory to start searching from (default: current directory)

    Returns:
        Path to .dogcats directory, or ".dogcats" if not found
    """
    from dogcat.config import (
        get_rc_walkup_boundary,
        warn_if_rc_target_foreign,
    )

    current = Path.cwd() if start_dir is None else Path(start_dir).resolve()
    boundary = get_rc_walkup_boundary(current)

    while True:
        # Check for .dogcatrc first
        rc_candidate = current / DOGCATRC_FILENAME
        if rc_candidate.is_file():
            try:
                target = parse_dogcatrc(rc_candidate)
                warn_if_rc_target_foreign(rc_candidate, target)
            except ValueError as e:
                typer.echo(f"Error: {e}", err=True)
                raise SystemExit(1) from e
            if not target.is_dir():
                typer.echo(
                    f"Error: {DOGCATRC_FILENAME} points to "
                    f"nonexistent directory: {target}",
                    err=True,
                )
                raise SystemExit(1)
            return str(target)

        # Fall back to .dogcats/ directory
        candidate = current / ".dogcats"
        if candidate.is_dir():
            return str(candidate)

        parent = current.parent
        if parent == current:
            # Reached filesystem root — try git worktree fallback
            return _find_dogcats_via_worktree() or ".dogcats"
        if boundary is not None and current == boundary:
            # Stop at the boundary; do not trust ancestors above it.
            return _find_dogcats_via_worktree() or ".dogcats"
        current = parent


def _find_dogcats_via_worktree() -> str | None:
    """Check the main git worktree root for a .dogcats directory.

    In a linked worktree, ``git rev-parse --git-common-dir`` points back to
    the main worktree's ``.git`` directory.  We resolve the main worktree root
    from that and look for ``.dogcats`` there.

    Returns:
        Path to .dogcats directory, or None if not found or not in a git repo.
    """
    import dogcat.git as git_helpers

    common_git_dir = git_helpers.common_dir()
    if common_git_dir is None:
        return None

    # --git-common-dir returns the path to the shared .git directory.
    # The main worktree root is its parent.
    main_worktree_root = common_git_dir.resolve().parent
    candidate = main_worktree_root / ".dogcats"
    if candidate.is_dir():
        return str(candidate)
    return None


def resolve_dogcats_dir(dogcats_dir: str) -> str:
    """Return ``dogcats_dir`` if it exists, otherwise walk up to find one.

    Thin wrapper around :func:`find_dogcats_dir` for callers that have a
    pre-resolved candidate dir and only want to walk up when it's missing.
    """
    if Path(dogcats_dir).is_dir():
        return dogcats_dir
    return find_dogcats_dir()


def get_storage(
    dogcats_dir: str = ".dogcats",
    create_dir: bool = False,
) -> JSONLStorage:
    """Get or create storage instance.

    If dogcats_dir doesn't exist in current directory, searches upward
    to find it (similar to how git finds .git).

    Args:
        dogcats_dir: Path to .dogcats directory.
        create_dir: If True, create the directory if it doesn't exist.

    Returns:
        JSONLStorage instance
    """
    # Always resolve via find_dogcats_dir() to respect .dogcatrc priority
    # over a local .dogcats/ directory (which may only contain config.local.toml)
    if not create_dir and dogcats_dir == ".dogcats":
        dogcats_dir = find_dogcats_dir()
    return JSONLStorage(f"{dogcats_dir}/issues.jsonl", create_dir=create_dir)


def check_agent_manual_exclusive(*, agent_only: bool, manual_only: bool) -> None:
    """Reject --agent-only combined with --manual."""
    if agent_only and manual_only:
        msg = "--agent-only and --manual are mutually exclusive"
        raise typer.BadParameter(
            msg,
        )


def resolve_limit(
    limit_arg: int | None,
    limit_opt: int | None,
    default: int | None = None,
) -> int | None:
    """Coalesce positional ``LIMIT`` and ``--limit`` and reject negatives.

    ``limit_arg or limit_opt`` (the previous pattern) treats ``0`` as
    falsy, silently skipping truncation, and lets ``-1`` slip through to
    ``issues[:-1]`` which drops the last item. (dogcat-26a4)
    """
    value = limit_arg if limit_arg is not None else limit_opt
    if value is None:
        return default
    if value < 0:
        msg = f"--limit must be >= 0 (got {value})"
        raise typer.BadParameter(msg)
    return value


def check_comments_exclusive(*, has_comments: bool, without_comments: bool) -> None:
    """Reject --has-comments combined with --without-comments."""
    if has_comments and without_comments:
        msg = "--has-comments and --without-comments are mutually exclusive"
        raise typer.BadParameter(
            msg,
        )


def apply_comment_filter(
    issues: list[Issue],
    *,
    has_comments: bool = False,
    without_comments: bool = False,
) -> list[Issue]:
    """Filter issues by presence/absence of comments.

    Comments are hard-deleted from issue.comments, so 'has comments' is
    just bool(issue.comments).
    """
    check_comments_exclusive(
        has_comments=has_comments, without_comments=without_comments
    )
    if has_comments:
        return [i for i in issues if i.comments]
    if without_comments:
        return [i for i in issues if not i.comments]
    return issues


def apply_common_filters(
    issues: list[Issue],
    *,
    issue_type: str | None = None,
    priority: int | None = None,
    label: str | None = None,
    owner: str | None = None,
    parent: str | None = None,
    no_parent: bool = False,
    namespace: str | None = None,
    agent_only: bool = False,
    manual_only: bool = False,
    has_comments: bool = False,
    without_comments: bool = False,
    all_namespaces: bool = False,
    dogcats_dir: str | None = None,
    storage: JSONLStorage | None = None,
) -> list[Issue]:
    """Apply common filters to a list of issues.

    This is a shared helper to avoid duplicating filter logic across
    shortcut commands (ready, blocked, in-progress, etc.), search, and export.
    """
    from dogcat.config import get_namespace_filter
    from dogcat.constants import parse_labels

    check_agent_manual_exclusive(agent_only=agent_only, manual_only=manual_only)
    check_comments_exclusive(
        has_comments=has_comments, without_comments=without_comments
    )

    if issue_type:
        issues = [i for i in issues if i.issue_type.value == issue_type]
    if priority is not None:
        issues = [i for i in issues if i.priority == priority]
    if label:
        labels_filter = set(parse_labels(label))
        issues = [i for i in issues if labels_filter.issubset(set(i.labels or []))]
    if owner:
        issues = [i for i in issues if i.owner == owner]
    if parent and storage:
        resolved_parent = storage.resolve_id(parent)
        if resolved_parent:
            child_ids = {c.full_id for c in storage.get_children(resolved_parent)}
            issues = [
                i
                for i in issues
                if i.full_id == resolved_parent or i.full_id in child_ids
            ]
    if no_parent:
        issues = [i for i in issues if i.parent is None]
    if agent_only:
        issues = [i for i in issues if not is_manual_issue(i.metadata)]
    if manual_only:
        issues = [i for i in issues if is_manual_issue(i.metadata)]
    if has_comments:
        issues = [i for i in issues if i.comments]
    if without_comments:
        issues = [i for i in issues if not i.comments]

    # Namespace filtering (skip if --all-namespaces)
    if not all_namespaces and dogcats_dir:
        ns_filter = get_namespace_filter(dogcats_dir, namespace)
        if ns_filter is not None:
            issues = [i for i in issues if ns_filter(i.namespace)]

    return issues


def parse_duration(value: str) -> datetime:
    """Parse a relative duration string into an absolute datetime.

    Accepted formats: Nd (days), Nw (weeks), Nm (months as 30d).
    Also accepts ISO8601 date strings directly.

    Returns:
        Absolute datetime (timezone-aware) representing the snooze expiry.

    Raises:
        ValueError: If the format is not recognized.
    """
    import re
    from datetime import timedelta

    stripped = value.strip()
    # Relative regex matches case-insensitively (7d / 7D both work),
    # but ISO parsing must use the original-case string because
    # ``datetime.fromisoformat`` only accepts uppercase ``Z``. Without
    # this, ``dcat snooze 2026-04-25T00:00:00Z`` was rejected.
    # (dogcat-3x9q)
    match = re.fullmatch(r"(\d+)([dwmDWM])", stripped)
    if match:
        amount = int(match.group(1))
        unit = match.group(2).lower()
        if unit == "d":
            days = amount
        elif unit == "w":
            days = amount * 7
        else:  # unit == "m"
            days = amount * 30
        # Cap snooze duration at ~100 years (dogcat-dfn9): a typo
        # like 999999999999d would otherwise OverflowError inside
        # timedelta, and a far-future snooze permanently orphans the
        # issue from list views.
        max_days = 365 * 100
        if days > max_days:
            msg = (
                f"Duration too far in the future ({amount}{unit} > "
                f"{max_days}d / 100y). Use a shorter span or "
                f"`dcat update <id> --status deferred` instead."
            )
            raise ValueError(msg)
        return datetime.now().astimezone() + timedelta(days=days)

    # Try ISO8601 date/datetime — accept trailing ``Z`` as +00:00.
    iso = stripped[:-1] + "+00:00" if stripped.endswith("Z") else stripped
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        pass
    else:
        if dt.tzinfo is None:
            # Use the local zoneinfo (DST-aware) rather than the fixed
            # offset of ``datetime.now()``: a snooze a few months out
            # would otherwise stamp the wrong offset across a DST
            # transition. (dogcat-3x9q)
            try:
                from zoneinfo import ZoneInfo

                local_tz_name = (
                    datetime.now().astimezone().tzname()  # e.g. "CEST"
                )
                # tzname() values like "CEST" are unparseable by
                # ZoneInfo. Fall back to the system tz on error.
                local_tz = ZoneInfo(local_tz_name) if local_tz_name else None
            except (ImportError, Exception):  # noqa: BLE001
                local_tz = None
            if local_tz is None:
                local_tz = datetime.now().astimezone().tzinfo
            dt = dt.replace(tzinfo=local_tz)
        return dt

    msg = (
        f"Invalid duration '{value}'. "
        "Use relative (e.g. 7d, 2w, 1m) or ISO8601 date (e.g. 2026-04-01)."
    )
    raise ValueError(msg)


def _parse_priority_value(value: str) -> int:
    """Parse a priority value that can be an int (0-4), pINT (p0-p4), or a name.

    Accepted names: critical (0), high (1), medium (2), low (3), minimal (4).

    Returns the priority as an integer.
    Raises ValueError if the format is invalid.
    """
    raw = value.strip().lower()
    if raw in PRIORITY_NAMES:
        return PRIORITY_NAMES[raw]
    raw = raw.removeprefix("p")
    try:
        priority = int(raw)
    except ValueError:
        names = ", ".join(PRIORITY_NAMES)
        msg = f"Invalid priority '{value}'. Use 0-4, p0-p4, or a name ({names})."
        raise ValueError(msg) from None
    if priority < 0 or priority > 4:
        msg = f"Invalid priority '{value}'. Must be 0-4."
        raise ValueError(msg)
    return priority


# (shorthand-kind, lookup-set, case-sensitive). Order matters for resolution
# precedence in `_classify_shorthand`: priority is checked first.
_SHORTHAND_KINDS: tuple[tuple[str, frozenset[str], bool], ...] = (
    ("priority", frozenset(PRIORITY_SHORTHANDS), True),
    ("type", frozenset(TYPE_SHORTHANDS), False),
    ("status", frozenset(STATUS_SHORTHANDS), False),
)


def _classify_shorthand(value: str) -> str | None:
    """Return the shorthand kind ("priority"/"type"/"status") or None.

    Replaces the older quartet (``_is_priority_shorthand``,
    ``_is_type_shorthand``, ``_is_status_shorthand``, ``_is_shorthand``) with
    a single dictionary-driven lookup; callers compare the returned kind.
    """
    if len(value) != 1:
        return None
    for kind, lookup, case_sensitive in _SHORTHAND_KINDS:
        key = value if case_sensitive else value.lower()
        if key in lookup:
            return kind
    return None


def _is_shorthand(value: str) -> bool:
    """Check if a string is any shorthand (priority, type, or status)."""
    return _classify_shorthand(value) is not None


def _is_invalid_single_char(value: str) -> bool:
    """Check if a value is a single char that's not a valid shorthand."""
    return len(value) == 1 and value.lower() not in ALL_SHORTHANDS


def _parse_args_for_create(
    args: list[str | None],
    *,
    allow_shorthands: bool = True,
) -> tuple[str, int | None, str | None, str | None]:
    """Parse positional args for title, priority, type, and status.

    Args:
        args: Positional arguments from the CLI.
        allow_shorthands: If False, valid shorthands raise ValueError directing
            the user to ``dcat c``.

    Returns:
        (title, priority_shorthand, type_shorthand, status_shorthand)
    Raises: ValueError if arguments are ambiguous or invalid.
    """
    title_parts: list[str] = []
    priority_sh = None
    type_sh = None
    status_sh = None

    for arg in args:
        if arg is None:
            continue
        kind = _classify_shorthand(arg)
        if not allow_shorthands and kind is not None:
            msg = (
                "Shorthands are only available with 'dcat c'. "
                "Use --type/--priority/--status flags instead."
            )
            raise ValueError(msg)
        if kind == "priority" and priority_sh is None:
            priority_sh = int(arg)
        elif kind == "type" and type_sh is None:
            type_sh = TYPE_SHORTHANDS[arg.lower()]
        elif kind == "status" and status_sh is None:
            status_sh = STATUS_SHORTHANDS[arg.lower()]
        elif _is_invalid_single_char(arg):
            valid_types = ", ".join(sorted(TYPE_SHORTHANDS.keys()))
            valid_statuses = ", ".join(sorted(STATUS_SHORTHANDS.keys()))
            msg = (
                f"Invalid shorthand '{arg}'. "
                f"Valid priority: 0-4, valid type: {valid_types}, "
                f"valid status: {valid_statuses}"
            )
            raise ValueError(
                msg,
            )
        else:
            title_parts.append(arg)

    title = " ".join(title_parts) if title_parts else ""

    # Validate: title must not be a single-char shorthand (ambiguous)
    # e.g., "dcat c b 0 b" would make second "b" the title, which is confusing
    if title and len(title) == 1 and _is_shorthand(title):
        msg = (
            f"Ambiguous arguments: '{title}' looks like a shorthand "
            "but was used as title. Use a longer title or explicit "
            "--type/--priority/--status options."
        )
        raise ValueError(msg)

    return title, priority_sh, type_sh, status_sh


def load_open_inbox_proposals(
    dogcats_dir: str,
    namespace: str | None,
    *,
    all_namespaces: bool,
) -> list[Proposal]:
    """Load open (non-closed) inbox proposals from ``dogcats_dir``.

    Filters by namespace using the same precedence as issue listings:
    explicit ``namespace`` > config visibility > primary namespace.
    Returns an empty list if the inbox file is missing or unreadable so
    callers can call this unconditionally inside list-style commands.
    """
    from dogcat.config import get_issue_prefix, get_namespace_filter
    from dogcat.inbox import InboxStorage

    try:
        inbox = InboxStorage(dogcats_dir=dogcats_dir)
    except (ValueError, RuntimeError):
        return []

    proposals: list[Proposal] = [p for p in inbox.list() if not p.is_closed()]
    if all_namespaces:
        return proposals

    ns_filter = get_namespace_filter(dogcats_dir, namespace)
    if ns_filter is not None:
        return [p for p in proposals if ns_filter(p.namespace)]
    primary = get_issue_prefix(dogcats_dir)
    return [p for p in proposals if p.namespace == primary]


def load_remote_inbox_proposals(
    dogcats_dir: str,
    namespace: str | None,
    *,
    all_namespaces: bool,
    show_all: bool = False,
) -> tuple[list[Proposal], str | None]:
    """Load proposals from the remote inbox configured in ``inbox_remote``.

    Returns ``(proposals, remote_path)``. When no remote is configured or
    the remote dir is missing/unreadable, returns ``([], None)``. Filters
    closed/tombstone unless ``show_all`` is True.
    """
    from pathlib import Path

    from dogcat.config import get_issue_prefix, load_config
    from dogcat.inbox import InboxStorage
    from dogcat.models import ProposalStatus

    try:
        config = load_config(dogcats_dir)
    except (ValueError, RuntimeError):
        return [], None
    remote_path = config.get("inbox_remote")
    if not remote_path:
        return [], None

    remote_dogcats = Path(remote_path).expanduser()
    if remote_dogcats.name != ".dogcats":
        candidate = remote_dogcats / ".dogcats"
        if candidate.is_dir():
            remote_dogcats = candidate
    if not remote_dogcats.is_dir():
        return [], remote_path

    ns_filter_value = (
        None if all_namespaces else (namespace or get_issue_prefix(dogcats_dir))
    )
    try:
        remote_inbox = InboxStorage(dogcats_dir=str(remote_dogcats))
        proposals: list[Proposal] = remote_inbox.list(
            include_tombstones=show_all,
            namespace=ns_filter_value,
        )
    except (ValueError, RuntimeError):
        return [], remote_path
    if not show_all:
        proposals = [
            p
            for p in proposals
            if p.status not in (ProposalStatus.CLOSED, ProposalStatus.TOMBSTONE)
        ]
    return proposals, remote_path
