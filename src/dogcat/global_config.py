"""User-global dogcat config at $XDG_CONFIG_HOME/dogcat/config.toml.

This file is opt-in. When present, it provides a fallback `.dogcats`
directory and an auto-namespace policy for repos that have no local
.dogcats/, no walk-up .dogcatrc, and no other configuration.

Without this file dogcat behaves exactly as before.
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

import contextlib

import tomli_w

_logger = logging.getLogger(__name__)

GLOBAL_CONFIG_DIRNAME = "dogcat"
GLOBAL_CONFIG_FILENAME = "config.toml"


@dataclass
class GlobalConfig:
    """Parsed user-global config. All fields are optional."""

    default_storage: Path | None = None
    visible_namespaces: list[str] = field(default_factory=list[str])


def get_global_config_path() -> Path:
    """Return the path to the user-global config file.

    Honors ``$XDG_CONFIG_HOME`` per the XDG Base Directory spec; falls
    back to ``~/.config`` when unset.
    """
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / GLOBAL_CONFIG_DIRNAME / GLOBAL_CONFIG_FILENAME


def _expand_path(value: str) -> Path:
    """Expand ``~`` and ``$VAR`` in a path string."""
    return Path(os.path.expandvars(value)).expanduser()


def _load_raw() -> dict[str, Any]:
    """Load the raw TOML as a dict. Empty dict on missing/malformed file."""
    path = get_global_config_path()
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except (tomllib.TOMLDecodeError, OSError) as e:
        _logger.warning("Failed to read global config at %s: %s", path, e)
        return {}


def load_global_config() -> GlobalConfig:
    """Load the user-global config. Returns defaults if missing or malformed."""
    data = _load_raw()
    if not data:
        return GlobalConfig()

    storage_raw = data.get("default_storage")
    storage = _expand_path(storage_raw) if isinstance(storage_raw, str) else None

    visible_raw: object = data.get("visible_namespaces")
    visible: list[str] = (
        [str(v) for v in visible_raw]  # type: ignore[reportUnknownVariableType]
        if isinstance(visible_raw, list)
        else []
    )

    return GlobalConfig(
        default_storage=storage,
        visible_namespaces=visible,
    )


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    """Write TOML atomically via write-tmp + fsync + replace."""
    import tempfile

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "wb") as f:
            tomli_w.dump(data, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)  # noqa: PTH105
    except BaseException:
        with contextlib.suppress(OSError):
            Path(tmp_name).unlink()
        raise


def save_global_config_value(key: str, value: Any) -> None:
    """Set a single key in the global config. Creates dir + file if needed."""
    data = _load_raw()
    data[key] = value
    _atomic_write(get_global_config_path(), data)


def unset_global_config_value(key: str) -> None:
    """Remove a key from the global config. No-op if file or key is missing."""
    path = get_global_config_path()
    if not path.is_file():
        return
    data = _load_raw()
    if key in data:
        del data[key]
        _atomic_write(path, data)
