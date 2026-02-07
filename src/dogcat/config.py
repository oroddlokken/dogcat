"""Configuration file handling for Dogcat."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import toml

from dogcat.constants import DOGCATRC_FILENAME

# Default prefix for issue IDs
DEFAULT_PREFIX = "dc"

# Config filename
CONFIG_FILENAME = "config.toml"


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


def load_config(dogcats_dir: str) -> dict[str, Any]:
    """Load configuration from .dogcats/config.toml.

    Args:
        dogcats_dir: Path to .dogcats directory

    Returns:
        Configuration dictionary, or empty dict if no config exists
    """
    config_path = get_config_path(dogcats_dir)
    if not config_path.exists():
        return {}

    try:
        with config_path.open() as f:
            return toml.load(f)
    except (toml.TomlDecodeError, OSError):
        return {}


def save_config(dogcats_dir: str, config: dict[str, Any]) -> None:
    """Save configuration to .dogcats/config.toml.

    Args:
        dogcats_dir: Path to .dogcats directory
        config: Configuration dictionary to save
    """
    config_path = get_config_path(dogcats_dir)

    # Ensure directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)

    with config_path.open("w") as f:
        toml.dump(config, f)


def get_issue_prefix(dogcats_dir: str) -> str:
    """Get the issue prefix from config or return default.

    Precedence:
    1. issue_prefix from config.yaml
    2. Auto-detect from existing issues (most common prefix)
    3. Auto-detect from directory name
    4. Default prefix ("dc")

    Args:
        dogcats_dir: Path to .dogcats directory

    Returns:
        Issue prefix string
    """
    # Try config file first
    config = load_config(dogcats_dir)
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
    config = load_config(dogcats_dir)
    config["issue_prefix"] = prefix
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
        import json

        prefix_counts: dict[str, int] = {}

        with issues_path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    issue_id = data.get("id", "")
                    prefix = extract_prefix(issue_id)
                    if prefix:
                        prefix_counts[prefix] = prefix_counts.get(prefix, 0) + 1
                except json.JSONDecodeError:
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

    return sanitized if sanitized else None


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
