"""Shared infrastructure for dogcat CLI commands."""

from __future__ import annotations

import functools
import getpass
import inspect
import subprocess
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
    TYPE_SHORTHANDS,
)
from dogcat.storage import JSONLStorage

if TYPE_CHECKING:
    from collections.abc import Callable

    import click

_type_keys = "/".join(sorted(TYPE_SHORTHANDS.keys()))
_ARG_HELP = f"Title or shorthand (0-4 for priority, {_type_keys} for type)"


def _make_alias(
    source_fn: Callable[..., Any],
    *,
    doc: str,
    exclude_params: frozenset[str] = frozenset(),
    param_defaults: dict[str, Any] | None = None,
) -> Callable[..., Any]:
    """Create a CLI command alias by cloning a source function's signature.

    Typer infers CLI parameters from function signatures. This creates a thin
    wrapper that shares the source function's signature (minus any excluded
    params) so parameter declarations aren't duplicated across aliases.
    """
    defaults = param_defaults or {}
    sig = inspect.signature(source_fn)
    new_params = [p for name, p in sig.parameters.items() if name not in exclude_params]

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
    try:
        result = subprocess.run(
            ["git", "config", "user.email"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, OSError):
        # git not installed or other OS error
        pass

    return getpass.getuser()


def find_dogcats_dir(start_dir: str | None = None) -> str:
    """Find .dogcats directory by searching upward from start_dir.

    Checks for .dogcatrc first (external directory reference), then falls back
    to searching for .dogcats/ directly. If the upward walk fails, checks the
    main git worktree root (via ``git rev-parse --git-common-dir``) so that
    linked worktrees transparently share the main tree's .dogcats directory.

    Args:
        start_dir: Directory to start searching from (default: current directory)

    Returns:
        Path to .dogcats directory, or ".dogcats" if not found
    """
    current = Path.cwd() if start_dir is None else Path(start_dir).resolve()

    while True:
        # Check for .dogcatrc first
        rc_candidate = current / DOGCATRC_FILENAME
        if rc_candidate.is_file():
            try:
                target = parse_dogcatrc(rc_candidate)
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
        current = parent


def _find_dogcats_via_worktree() -> str | None:
    """Check the main git worktree root for a .dogcats directory.

    In a linked worktree, ``git rev-parse --git-common-dir`` points back to
    the main worktree's ``.git`` directory.  We resolve the main worktree root
    from that and look for ``.dogcats`` there.

    Returns:
        Path to .dogcats directory, or None if not found or not in a git repo.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None

        # --git-common-dir returns the path to the shared .git directory.
        # The main worktree root is its parent.
        common_git_dir = Path(result.stdout.strip()).resolve()
        main_worktree_root = common_git_dir.parent

        candidate = main_worktree_root / ".dogcats"
        if candidate.is_dir():
            return str(candidate)
    except (FileNotFoundError, OSError):
        pass

    return None


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
    # If not creating and the path doesn't exist locally, search upward
    if not create_dir and not Path(dogcats_dir).is_dir():
        dogcats_dir = find_dogcats_dir()
    return JSONLStorage(f"{dogcats_dir}/issues.jsonl", create_dir=create_dir)


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


def _is_priority_shorthand(value: str) -> bool:
    """Check if a string is a priority shorthand (single char: 0-4)."""
    return len(value) == 1 and value in PRIORITY_SHORTHANDS


def _is_type_shorthand(value: str) -> bool:
    """Check if a string is a type shorthand (single char: b/f/e/s)."""
    return len(value) == 1 and value.lower() in TYPE_SHORTHANDS


def _is_shorthand(value: str) -> bool:
    """Check if a string is any shorthand (priority or type)."""
    return _is_priority_shorthand(value) or _is_type_shorthand(value)


def _is_invalid_single_char(value: str) -> bool:
    """Check if a value is a single char that's not a valid shorthand."""
    return len(value) == 1 and value.lower() not in ALL_SHORTHANDS


def _parse_args_for_create(
    args: list[str | None],
) -> tuple[str, int | None, str | None]:
    """Parse positional arguments to extract title, priority, and type shorthand.

    Returns:
        (title, priority_shorthand, type_shorthand)
    Raises: ValueError if arguments are ambiguous or invalid.
    """
    title_parts: list[str] = []
    priority_sh = None
    type_sh = None

    for arg in args:
        if arg is None:
            continue
        if _is_priority_shorthand(arg) and priority_sh is None:
            priority_sh = int(arg)
        elif _is_type_shorthand(arg) and type_sh is None:
            type_sh = TYPE_SHORTHANDS[arg.lower()]
        elif _is_invalid_single_char(arg):
            valid_types = ", ".join(sorted(TYPE_SHORTHANDS.keys()))
            msg = (
                f"Invalid shorthand '{arg}'. "
                f"Valid priority: 0-4, valid type: {valid_types}"
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
            "--type/--priority options."
        )
        raise ValueError(msg)

    return title, priority_sh, type_sh
