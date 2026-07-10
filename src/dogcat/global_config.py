"""User-global dogcat config at $XDG_CONFIG_HOME/dogcat/config.toml.

This file is opt-in. When present, it provides a fallback `.dogcats`
directory and an auto-namespace policy for repos that have no local
.dogcats/, no walk-up .dogcatrc, and no other configuration.

Without this file dogcat behaves exactly as before.

Only the keys in :data:`GLOBAL_CONFIG_KEYS` are read from this file;
`dcat config set --global` rejects anything else so the file can't
accumulate settings that look configured but are never honored.
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

from dogcat.constants import GLOBAL_CONFIG_DIRNAME, GLOBAL_CONFIG_FILENAME

_logger = logging.getLogger(__name__)

# Keys the runtime actually reads from the global config file.
GLOBAL_CONFIG_KEYS: frozenset[str] = frozenset(
    {"default_storage", "visible_namespaces"}
)


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


def load_global_config_raw() -> dict[str, Any]:
    """Load the raw TOML as a dict. Empty dict on missing/malformed file.

    Parse errors are logged rather than raised, matching
    :func:`dogcat.config._load_toml`; ``dcat doctor`` surfaces them via
    :func:`dogcat.config.check_toml_parseable`.
    """
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
    data = load_global_config_raw()
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


def save_global_config_value(key: str, value: Any) -> None:
    """Set a single key in the global config. Creates dir + file if needed."""
    from dogcat.config import atomic_write_toml

    data = load_global_config_raw()
    data[key] = value
    atomic_write_toml(get_global_config_path(), data)


def unset_global_config_value(key: str) -> None:
    """Remove a key from the global config. No-op if file or key is missing."""
    from dogcat.config import atomic_write_toml

    path = get_global_config_path()
    if not path.is_file():
        return
    data = load_global_config_raw()
    if key in data:
        del data[key]
        atomic_write_toml(path, data)


# --- Resolution state -------------------------------------------------
#
# Namespace derivation and default filtering behave differently when the
# storage directory was reached via the global fallback (no local
# .dogcats, no .dogcatrc). That fact is recorded here at the resolution
# site instead of being re-derived later by path comparison — a repo
# whose .dogcatrc points at the same store, or the store's own home
# repo, must NOT get fallback semantics. Process-global state is fine
# for a one-shot CLI (same pattern as cli._json_state).

_global_fallback_path: Path | None = None


def resolve_global_fallback() -> str | None:
    """Return ``default_storage`` if configured and an existing directory.

    Records that resolution went through the global fallback (see
    :func:`was_resolved_via_global`) and prints a one-time stderr notice
    so issue writes never land in the shared store silently.
    """
    global _global_fallback_path

    cfg = load_global_config()
    if cfg.default_storage is None or not cfg.default_storage.is_dir():
        return None

    if _global_fallback_path is None:
        _global_fallback_path = cfg.default_storage.resolve()
        from dogcat.namespace_slug import slug_from_dir

        slug = slug_from_dir(Path.cwd().name)
        namespace_note = (
            f" (namespace '{slug}' from folder name)"
            if slug
            else " (namespace from store config)"
        )
        print(
            f"dcat: no local .dogcats or .dogcatrc found, using global "
            f"default_storage at {_global_fallback_path}{namespace_note}",
            file=sys.stderr,
        )

    return str(cfg.default_storage)


def was_resolved_via_global(dogcats_dir: str | Path) -> bool:
    """Return True if ``dogcats_dir`` was resolved via the global fallback."""
    if _global_fallback_path is None:
        return False
    try:
        return Path(dogcats_dir).resolve() == _global_fallback_path
    except OSError:
        return False


def reset_resolution_state() -> None:
    """Forget any recorded global-fallback resolution (test isolation)."""
    global _global_fallback_path
    _global_fallback_path = None
