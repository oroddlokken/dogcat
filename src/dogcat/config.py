"""Configuration file handling for Dogcat."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Callable

import orjson

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

import tomli_w

from dogcat.constants import DOGCATRC_FILENAME
from dogcat.models import classify_record

_logger = logging.getLogger(__name__)

# Default prefix for issue IDs
DEFAULT_PREFIX = "dc"

# Config filename
CONFIG_FILENAME = "config.toml"
LOCAL_CONFIG_FILENAME = "config.local.toml"

# Directory name for repo-local config (next to .dogcatrc)
DOGCATS_DIR_NAME = ".dogcats"


def parse_dogcatrc(rc_path: str | Path) -> Path:
    """Parse a .dogcatrc file and return the resolved .dogcats directory path.

    The file contains a single line: the path to the .dogcats directory.
    Relative paths are resolved relative to the .dogcatrc file's parent directory.

    Args:
        rc_path: Path to the .dogcatrc file

    Returns:
        Resolved absolute Path to the .dogcats directory

    Raises:
        ValueError: If the file is empty / unreadable / contains a
            control byte or embedded newline. (dogcat-2o1f)
            ``OSError`` from ``read_text`` is wrapped here so callers
            don't need to catch both exception types — the rc file
            being unreadable should surface as a clear "cannot read
            .dogcatrc" message, not a raw PermissionError traceback.
    """
    rc_path = Path(rc_path)
    try:
        text = rc_path.read_text()
    except OSError as e:
        msg = f"Failed to read {DOGCATRC_FILENAME} at {rc_path}: {e}"
        raise ValueError(msg) from e
    # Take the first physical line, ignoring blank trailing lines.
    # ``splitlines()`` handles \n, \r, \r\n uniformly. ``\x00`` (NUL)
    # is rejected explicitly because it can't appear in a valid path
    # and would silently confuse the resolver.
    if "\x00" in text:
        msg = f"{DOGCATRC_FILENAME} at {rc_path} contains a NUL byte"
        raise ValueError(msg)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        msg = f"{DOGCATRC_FILENAME} file is empty: {rc_path}"
        raise ValueError(msg)
    content = lines[0].strip()

    if not content:
        msg = f"{DOGCATRC_FILENAME} file is empty: {rc_path}"
        raise ValueError(msg)

    target = Path(content)

    if not target.is_absolute():
        target = rc_path.parent / target

    return target.resolve()


def get_rc_walkup_boundary(start: Path | None = None) -> Path | None:
    """Return the directory above which .dogcatrc walk-up should stop.

    On a multi-tenant or shared host, an attacker who can write
    ``/tmp/.dogcatrc`` (or a sibling ancestor) could silently re-root
    every dcat command running in that subtree. We bound the upward
    walk to the current git toplevel by default. ``$HOME`` is the
    fallback so a user outside any repo still keeps their writes within
    their own home directory.

    Set ``DCAT_RC_WALKUP_UNRESTRICTED=1`` to opt back into the legacy
    "walk to filesystem root" behavior. (dogcat-4107)
    """
    import os
    import subprocess

    if os.environ.get("DCAT_RC_WALKUP_UNRESTRICTED"):
        return None

    cwd = start if start is not None else Path.cwd()
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            top = result.stdout.strip()
            if top:
                return Path(top).resolve()
    except (OSError, subprocess.SubprocessError):
        pass
    home = os.environ.get("HOME")
    if home:
        return Path(home).resolve()
    return None


def is_within(path: Path, boundary: Path) -> bool:
    """Return True if ``path`` is at or below ``boundary``."""
    try:
        path.resolve().relative_to(boundary.resolve())
    except ValueError:
        return False
    return True


def warn_if_rc_target_foreign(rc_path: Path, target: Path) -> None:
    """Warn (or refuse) when the rc target is unsafe.

    - Logs a stderr warning when the target is outside the rc file's
      ancestor chain (e.g. ``/tmp`` re-rooting your repo to ``$HOME``).
    - Refuses the rc with a clear error when the rc file's owner and the
      target's owner differ (cross-user re-root). Set
      ``DCAT_UNSAFE_CROSS_USER=1`` to override (e.g. shared CI).
    """
    import os
    import sys as _sys

    rc_resolved = rc_path.resolve()
    target_resolved = target.resolve()

    # Out-of-tree warning.
    rc_parent = rc_resolved.parent
    if not is_within(target_resolved, rc_parent):
        print(
            f"warning: {DOGCATRC_FILENAME} at {rc_resolved} points to "
            f"{target_resolved} which is outside the rc's directory; "
            f"set DCAT_RC_WALKUP_UNRESTRICTED=1 to silence this warning.",
            file=_sys.stderr,
        )

    if os.environ.get("DCAT_UNSAFE_CROSS_USER"):
        return

    # Cross-user ownership refusal (POSIX only).
    try:
        rc_uid = rc_resolved.stat().st_uid
        target_uid = target_resolved.stat().st_uid
    except OSError:
        return
    if rc_uid != target_uid:
        msg = (
            f"refusing to use {DOGCATRC_FILENAME} at {rc_resolved} "
            f"(owned by uid={rc_uid}) — its target {target_resolved} "
            f"is owned by a different uid={target_uid}. Set "
            f"DCAT_UNSAFE_CROSS_USER=1 to override."
        )
        raise ValueError(msg)


def get_config_path(dogcats_dir: str) -> Path:
    """Get the path to the config file.

    Args:
        dogcats_dir: Path to .dogcats directory

    Returns:
        Path to config.toml
    """
    return Path(dogcats_dir) / CONFIG_FILENAME


def get_local_config_path(dogcats_dir: str) -> Path:
    """Get the path to the local config file.

    Args:
        dogcats_dir: Path to .dogcats directory

    Returns:
        Path to config.local.toml
    """
    return Path(dogcats_dir) / LOCAL_CONFIG_FILENAME


# Keys whose value MUST be a list of strings. A scalar string here
# would silently iterate per-character ("frontend" → {'f','r','o','n',
# 't','e','d'}), which the rename-namespace path turns into a hard
# crash and the visibility filter into a stealthy bug. (dogcat-4o1p)
_LIST_OF_STR_CONFIG_KEYS = (
    "visible_namespaces",
    "hidden_namespaces",
    "pinned_namespaces",
)
# Keys whose value MUST be a string.
_STR_CONFIG_KEYS = ("namespace", "issue_prefix", "inbox_remote")
# Keys whose value MUST be a bool. A string here ("false" / "no" /
# "0") would be truthy under ``bool(...)`` and silently flip a
# security-sensitive toggle. (dogcat-22t5)
_BOOL_CONFIG_KEYS = ("allow_creating_namespaces", "git_tracking")


def _validate_config_shape(payload: dict[str, Any], source: str) -> dict[str, Any]:
    """Drop shape-violating values from a config dict, logging each drop.

    Coercing here keeps callers (which previously did
    ``list(config.get('pinned_namespaces', []))`` etc.) from silently
    iterating a wrongly-typed scalar. (dogcat-4o1p)
    """
    cleaned: dict[str, Any] = dict(payload)
    for key in _LIST_OF_STR_CONFIG_KEYS:
        if key not in cleaned:
            continue
        raw: Any = cleaned[key]
        if isinstance(raw, list):
            items = cast("list[Any]", raw)
            is_list_of_str = all(isinstance(i, str) for i in items)
        else:
            is_list_of_str = False
        if not is_list_of_str:
            repr_value: str = repr(cast("object", raw))
            _logger.warning(
                "%s: %s must be a list of strings (got %s); ignoring.",
                source,
                key,
                repr_value,
            )
            cleaned.pop(key, None)
    for key in _STR_CONFIG_KEYS:
        if key not in cleaned:
            continue
        raw_str: Any = cleaned[key]
        if not isinstance(raw_str, str):
            repr_value = repr(cast("object", raw_str))
            _logger.warning(
                "%s: %s must be a string (got %s); ignoring.",
                source,
                key,
                repr_value,
            )
            cleaned.pop(key, None)
    for key in _BOOL_CONFIG_KEYS:
        if key not in cleaned:
            continue
        raw_bool: Any = cleaned[key]
        # ``bool`` is a subclass of int, so we accept both. Reject
        # strings here so ``"false"`` / ``"no"`` / ``"0"`` cannot
        # silently flip the toggle to True via ``bool(...)``.
        if not isinstance(raw_bool, bool):
            repr_value = repr(cast("object", raw_bool))
            _logger.warning(
                "%s: %s must be a boolean (got %s); ignoring.",
                source,
                key,
                repr_value,
            )
            cleaned.pop(key, None)
    return cleaned


def _load_toml(path: Path) -> dict[str, Any]:
    """Load a single TOML file, returning empty dict on missing/invalid.

    Parse errors are surfaced as a logger warning so that a typo in
    config.toml doesn't silently degrade to "all defaults" — the user
    needs a signal that their settings aren't being honored. ``dcat
    doctor`` also re-runs this via :func:`check_toml_parseable` and
    reports parse failure as a separate check.
    """
    if not path.exists():
        return {}
    try:
        with path.open("rb") as f:
            payload = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        _logger.warning(
            "Failed to parse %s: %s. Falling back to defaults — fix the "
            "TOML to restore configured values.",
            path,
            e,
        )
        return {}
    except OSError as e:
        _logger.warning("Failed to read %s: %s", path, e)
        return {}
    return _validate_config_shape(payload, str(path))


def check_toml_parseable(path: Path) -> str | None:
    """Try to parse a TOML file and return an error string on failure.

    Used by ``dcat doctor`` to distinguish "config exists" from "config
    parses". Returns ``None`` for missing files (the existence check is a
    separate concern) and for files that parse cleanly.
    """
    if not path.exists():
        return None
    try:
        with path.open("rb") as f:
            tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        return str(e)
    except OSError as e:
        return str(e)
    return None


def _find_rc_parent() -> Path | None:
    """Walk up from CWD to find a .dogcatrc file.

    The walk is bounded by :func:`get_rc_walkup_boundary` (git toplevel
    or ``$HOME``) so we don't trust an arbitrary ancestor like
    ``/tmp/.dogcatrc`` planted by another user. (dogcat-4107)

    Returns:
        The parent directory containing .dogcatrc, or None if not found.
    """
    current = Path.cwd()
    boundary = get_rc_walkup_boundary(current)
    while True:
        if (current / DOGCATRC_FILENAME).is_file():
            return current
        parent = current.parent
        if parent == current:
            return None
        if boundary is not None and current == boundary:
            # Stop at the boundary; do not trust ancestors above it.
            return None
        current = parent


def _get_repo_local_config_path() -> Path | None:
    """Get the repo-local config.local.toml path when using .dogcatrc.

    When a repo uses .dogcatrc to point to a shared .dogcats directory,
    the repo can have its own .dogcats/config.local.toml for per-repo
    settings like namespace and visible_namespaces.

    Returns:
        Path to repo-local config.local.toml, or None if not in a .dogcatrc context.
    """
    rc_parent = _find_rc_parent()
    if rc_parent is None:
        return None
    return rc_parent / DOGCATS_DIR_NAME / LOCAL_CONFIG_FILENAME


def load_config(dogcats_dir: str) -> dict[str, Any]:
    """Load configuration from .dogcats/config.toml, merged with config.local.toml.

    Values in config.local.toml override those in config.toml (shallow merge).
    When using .dogcatrc, a repo-local config.local.toml (in .dogcats/ next to
    the .dogcatrc) takes highest precedence.

    Args:
        dogcats_dir: Path to .dogcats directory

    Returns:
        Merged configuration dictionary, or empty dict if no config exists
    """
    config = _load_toml(get_config_path(dogcats_dir))
    local = _load_toml(get_local_config_path(dogcats_dir))
    if local:
        config.update(local)

    # Repo-local config takes highest precedence
    repo_local_path = _get_repo_local_config_path()
    if repo_local_path is not None:
        repo_local = _load_toml(repo_local_path)
        if repo_local:
            config.update(repo_local)

    return config


def load_shared_config(dogcats_dir: str) -> dict[str, Any]:
    """Load only the shared config.toml (ignoring config.local.toml).

    Use this when you need to write back to config.toml without
    accidentally persisting local-only values.

    Args:
        dogcats_dir: Path to .dogcats directory

    Returns:
        Configuration dictionary from config.toml only
    """
    return _load_toml(get_config_path(dogcats_dir))


def load_local_config(dogcats_dir: str) -> dict[str, Any]:
    """Load the local config.local.toml.

    When using .dogcatrc, reads from the repo-local .dogcats/config.local.toml
    (next to the .dogcatrc) instead of the shared directory.

    Args:
        dogcats_dir: Path to .dogcats directory

    Returns:
        Configuration dictionary from config.local.toml only
    """
    repo_local_path = _get_repo_local_config_path()
    if repo_local_path is not None:
        return _load_toml(repo_local_path)
    return _load_toml(get_local_config_path(dogcats_dir))


def _atomic_write_toml(path: Path, payload: dict[str, Any]) -> None:
    """Write TOML to ``path`` atomically (write-tmp + fsync + replace).

    Without this, a kill / power-loss / ENOSPC mid-write leaves a
    truncated config that ``_load_toml`` silently treats as ``{}`` —
    every configured setting (namespace, visible_namespaces, etc.)
    is lost without a signal. The pattern mirrors
    ``_atomic_write_json`` in :mod:`dogcat.cli._cmd_doctor`. (dogcat-1s7e)
    """
    import os
    import tempfile

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    import contextlib

    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as f:
            tomli_w.dump(payload, f)
            f.flush()
            os.fsync(f.fileno())
        # ``os.replace`` is the atomic primitive on POSIX; the tests
        # patch it directly, so we keep the call site intentional.
        os.replace(tmp_name, path)  # noqa: PTH105
    except BaseException:
        with contextlib.suppress(OSError):
            tmp_path.unlink()
        raise


def save_local_config(dogcats_dir: str, config: dict[str, Any]) -> None:
    """Save configuration to config.local.toml.

    When using .dogcatrc, saves to the repo-local .dogcats/config.local.toml
    (next to the .dogcatrc) instead of the shared directory.

    Args:
        dogcats_dir: Path to .dogcats directory
        config: Configuration dictionary to save
    """
    repo_local_path = _get_repo_local_config_path()
    if repo_local_path is not None:
        config_path = repo_local_path
    else:
        config_path = get_local_config_path(dogcats_dir)
    _atomic_write_toml(config_path, config)


def save_config(dogcats_dir: str, config: dict[str, Any]) -> None:
    """Save configuration to .dogcats/config.toml.

    Args:
        dogcats_dir: Path to .dogcats directory
        config: Configuration dictionary to save
    """
    _atomic_write_toml(get_config_path(dogcats_dir), config)


def _resolve_dogcats_path(dogcats_dir: str) -> str:
    """Resolve the .dogcats directory path, walking up from CWD if needed.

    When commands are run from a subdirectory, ``dogcats_dir`` may be the
    default ``".dogcats"`` which doesn't exist locally.  This mirrors the
    walk-up logic in ``cli._helpers.find_dogcats_dir`` so that callers in
    ``config.py`` (which can't import from ``cli``) get the correct path.

    Args:
        dogcats_dir: Path to .dogcats directory (may be relative/unresolved)

    Returns:
        Resolved path to the .dogcats directory, or the original value if
        no directory is found during the walk-up.
    """
    if Path(dogcats_dir).is_dir():
        return dogcats_dir

    current = Path.cwd()
    while True:
        # Check for .dogcatrc first
        rc_candidate = current / DOGCATRC_FILENAME
        if rc_candidate.is_file():
            try:
                target = parse_dogcatrc(rc_candidate)
                if target.is_dir():
                    return str(target)
            except ValueError:
                pass

        candidate = current / ".dogcats"
        if candidate.is_dir():
            return str(candidate)

        parent = current.parent
        if parent == current:
            return dogcats_dir  # Filesystem root — fall back to original
        current = parent


def get_issue_prefix(dogcats_dir: str) -> str:
    """Get the issue prefix from config or return default.

    Precedence:
    1. issue_prefix from config.toml
    2. Auto-detect from existing issues (most common prefix)
    3. Auto-detect from directory name
    4. Default prefix ("dc")

    Args:
        dogcats_dir: Path to .dogcats directory

    Returns:
        Issue prefix string
    """
    # Resolve the actual .dogcats path (handles subdirectory invocations)
    dogcats_dir = _resolve_dogcats_path(dogcats_dir)

    # Try config file first ("namespace" key, with "issue_prefix" fallback)
    config = load_config(dogcats_dir)
    if "namespace" in config:
        return config["namespace"]
    if "issue_prefix" in config:
        return config["issue_prefix"]

    # Try to auto-detect from existing issues
    prefix = _detect_prefix_from_issues(dogcats_dir)
    if prefix:
        return prefix

    # Try directory name (parent of .dogcats)
    prefix = _detect_prefix_from_directory(dogcats_dir)
    if prefix:
        return prefix

    return DEFAULT_PREFIX


def set_issue_prefix(dogcats_dir: str, prefix: str) -> None:
    """Set the issue prefix in config.

    Args:
        dogcats_dir: Path to .dogcats directory
        prefix: Prefix to set
    """
    config = load_shared_config(dogcats_dir)
    config["namespace"] = prefix
    config.pop("issue_prefix", None)
    save_config(dogcats_dir, config)


def _detect_prefix_from_issues(dogcats_dir: str) -> str | None:
    """Detect prefix from existing issues in storage.

    Args:
        dogcats_dir: Path to .dogcats directory

    Returns:
        Most common prefix, or None if no issues exist
    """
    issues_path = Path(dogcats_dir) / "issues.jsonl"
    if not issues_path.exists():
        return None

    try:
        prefix_counts: dict[str, int] = {}

        with issues_path.open("rb") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = orjson.loads(line)
                    if classify_record(data) != "issue":
                        continue
                    issue_id = data.get("id", "")
                    prefix = extract_prefix(issue_id)
                    if prefix:
                        prefix_counts[prefix] = prefix_counts.get(prefix, 0) + 1
                except orjson.JSONDecodeError:
                    continue

        if not prefix_counts:
            return None

        # Return most common prefix
        return max(prefix_counts, key=prefix_counts.get)  # type: ignore[arg-type]

    except OSError:
        return None


def _detect_prefix_from_directory(dogcats_dir: str) -> str | None:
    """Detect prefix from directory name.

    Args:
        dogcats_dir: Path to .dogcats directory

    Returns:
        Directory name as prefix, or None
    """
    dogcats_path = Path(dogcats_dir).resolve()

    # Get the parent directory (the project directory)
    project_dir = dogcats_path.parent

    # Use the directory name as prefix
    dir_name = project_dir.name

    # Sanitize: only allow alphanumeric and hyphens
    sanitized = "".join(c if c.isalnum() or c == "-" else "-" for c in dir_name.lower())
    sanitized = sanitized.strip("-")

    return sanitized or None


def extract_prefix(issue_id: str) -> str | None:
    """Extract prefix from an issue ID.

    Args:
        issue_id: Issue ID like "search-8qx" or "dc-abc"

    Returns:
        Prefix part, or None if no hyphen found
    """
    if "-" not in issue_id:
        return None

    # Find the last hyphen and take everything before it
    last_hyphen = issue_id.rfind("-")
    return issue_id[:last_hyphen] if last_hyphen > 0 else None


def get_namespace_filter(
    dogcats_dir: str,
    explicit_namespace: str | None = None,
) -> Callable[[str], bool] | None:
    """Return a predicate that tests whether a namespace is visible.

    Args:
        dogcats_dir: Path to .dogcats directory.
        explicit_namespace: If set, filter to only this namespace.

    Returns:
        A callable taking a namespace string and returning True if visible,
        or None when no filtering is needed.
    """
    if explicit_namespace is not None:
        return lambda ns: ns == explicit_namespace

    config = load_config(dogcats_dir)
    visible: list[str] | None = config.get("visible_namespaces")
    hidden: list[str] | None = config.get("hidden_namespaces")

    primary = get_issue_prefix(dogcats_dir)

    if not visible and not hidden:
        # In .dogcatrc context (shared database), default to primary namespace
        if _find_rc_parent() is not None:
            return lambda ns: ns == primary
        return None

    if visible:
        allowed = set(visible)
        allowed.add(primary)
        return lambda ns: ns in allowed

    if hidden:
        blocked = set(hidden)
        blocked.discard(primary)
        return lambda ns: ns not in blocked

    return None


def migrate_config_keys(config: dict[str, Any]) -> bool:
    """Rename deprecated config keys to their current names.

    Renames ``issue_prefix`` → ``namespace`` in-place.

    Returns:
        True if any keys were migrated, False otherwise.
    """
    changed = False
    if "issue_prefix" in config:
        if "namespace" not in config:
            config["namespace"] = config["issue_prefix"]
        del config["issue_prefix"]
        changed = True
    return changed
