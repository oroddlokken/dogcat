"""Configuration file handling for Dogcat."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

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
        ValueError: If the file is empty or contains only whitespace
    """
    rc_path = Path(rc_path)
    content = rc_path.read_text().strip()

    if not content:
        msg = f"{DOGCATRC_FILENAME} file is empty: {rc_path}"
        raise ValueError(msg)

    target = Path(content)

    if not target.is_absolute():
        target = rc_path.parent / target

    return target.resolve()


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
            return tomllib.load(f)
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

    Returns:
        The parent directory containing .dogcatrc, or None if not found.
    """
    current = Path.cwd()
    while True:
        if (current / DOGCATRC_FILENAME).is_file():
            return current
        parent = current.parent
        if parent == current:
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
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("wb") as f:
        tomli_w.dump(config, f)


def save_config(dogcats_dir: str, config: dict[str, Any]) -> None:
    """Save configuration to .dogcats/config.toml.

    Args:
        dogcats_dir: Path to .dogcats directory
        config: Configuration dictionary to save
    """
    config_path = get_config_path(dogcats_dir)

    # Ensure directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)

    with config_path.open("wb") as f:
        tomli_w.dump(config, f)


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
