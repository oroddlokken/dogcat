"""Configuration file handling for Dogcat."""

from __future__ import annotations

import copy
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

import orjson

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

import tomli_w

from dogcat.constants import DEFAULT_NAMESPACE, DOGCATRC_FILENAME
from dogcat.models import classify_record

_logger = logging.getLogger(__name__)

# Default prefix for issue IDs. Canonical value lives in constants as
# DEFAULT_NAMESPACE; this module-level name is kept as a back-compat alias.
DEFAULT_PREFIX = DEFAULT_NAMESPACE

CONFIG_FILENAME = "config.toml"
LOCAL_CONFIG_FILENAME = "config.local.toml"

# Directory name for repo-local config (next to .dogcatrc)
DOGCATS_DIR_NAME = ".dogcats"


# --- Per-process memos -------------------------------------------------
#
# One `dcat list` reaches get_rc_walkup_boundary and load_config 4-5 times
# each, and a Tab press pays the same again; the boundary forks git and each
# load re-parses 2-3 TOML files (dogcat-2s9r). The memos below are keyed on a
# stat signature rather than on the path alone, so a config edit made by
# another process is picked up by the next read — that matters for `dcat tui`
# and `dcat web`, which live long enough to outlast an edit.
#
# Path -> (stat signature, value). One entry per path, so a long-running
# process holds a bounded number of them.
_toml_cache: dict[str, tuple[tuple[int, int, int] | None, dict[str, Any]]] = {}
_detected_namespace_cache: dict[
    str, tuple[tuple[int, int, int] | None, str | None]
] = {}
# (start dir, HOME) -> boundary. Not stat-keyed: the git toplevel of a fixed
# directory does not move within a process.
_boundary_cache: dict[tuple[str, str | None], Path | None] = {}


def _stat_signature(path: Path) -> tuple[int, int, int] | None:
    """Return (mtime_ns, size, inode) for ``path``, or None when unreadable.

    None is a valid cache key: it means "absent", and a file that appears
    later gets a signature, so the memo misses and reloads.
    """
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size, st.st_ino)


def clear_caches() -> None:
    """Drop every per-process memo in this module.

    Writes invalidate their own entry, so this is for tests and for callers
    that mutate config through a route this module cannot see.
    """
    _toml_cache.clear()
    _detected_namespace_cache.clear()
    _boundary_cache.clear()


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
            control byte or embedded newline.
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
    "walk to filesystem root" behavior.

    The result is memoized per process, keyed on the start directory and on
    ``$HOME`` (the fallback), because the rev-parse fork otherwise runs 4-5
    times per command (dogcat-2s9r). Call :func:`clear_caches` if a
    repository is created underneath a directory already queried.
    """
    import os

    if os.environ.get("DCAT_RC_WALKUP_UNRESTRICTED"):
        return None

    cwd = start if start is not None else Path.cwd()
    home = os.environ.get("HOME")
    cache_key = (str(cwd), home)
    if cache_key in _boundary_cache:
        return _boundary_cache[cache_key]
    boundary = _compute_rc_walkup_boundary(cwd, home)
    _boundary_cache[cache_key] = boundary
    return boundary


def _compute_rc_walkup_boundary(cwd: Path, home: str | None) -> Path | None:
    """Ask git for the toplevel above ``cwd``, falling back to ``$HOME``."""
    import subprocess

    try:
        result = subprocess.run(  # noqa: S603  # fixed argv, no shell
            ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],  # noqa: S607
            check=False,
            capture_output=True,
            text=True,
            # Tighter than the 10s _git_timeout() default (dogcat.git):
            # this rev-parse bounds the .dogcatrc walkup on the CLI startup
            # hot path, so a hung git must not stall every command. Kept
            # inline rather than routed through git._run.
            timeout=5,
        )
        if result.returncode == 0:
            top = result.stdout.strip()
            if top:
                return Path(top).resolve()
    except (OSError, subprocess.SubprocessError):
        pass
    if home:
        return Path(home).resolve()
    return None


def refuse_if_rc_target_cross_user(rc_path: Path, target: Path) -> None:
    """Refuse the rc when its target is owned by a different user.

    Raises ``ValueError`` when the rc file's owner uid and the target's
    owner uid differ (a cross-user re-root, e.g. a ``.dogcatrc`` planted by
    another account silently redirecting reads and writes). Set
    ``DCAT_UNSAFE_CROSS_USER=1`` to override (e.g. shared CI).

    A same-user target outside the rc's own directory is allowed silently:
    it is the documented shared-store setup (see docs/sharing-a-database.md).
    The walk-up boundary (``get_rc_walkup_boundary``) still bounds which
    ancestors are trusted.
    """
    import os

    rc_resolved = rc_path.resolve()
    target_resolved = target.resolve()

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
    """Get the path to the shared config file.

    Args:
        dogcats_dir: Path to .dogcats directory

    Returns:
        Path to config.toml. Pure path arithmetic — the file is not checked
        for existence, and an absent config is normal (``load_config``
        returns an empty :class:`DogcatConfig`).
    """
    return Path(dogcats_dir) / CONFIG_FILENAME


def get_local_config_path(dogcats_dir: str) -> Path:
    """Get the path to the gitignored local-override config file.

    Args:
        dogcats_dir: Path to .dogcats directory

    Returns:
        Path to config.local.toml, unchecked for existence as in
        :func:`get_config_path`. Absent is the common case — this file is
        gitignored, so a fresh clone never has one.
    """
    return Path(dogcats_dir) / LOCAL_CONFIG_FILENAME


# Keys whose value MUST be a list of strings. A scalar string here
# would silently iterate per-character ("frontend" → {'f','r','o','n',
# 't','e','d'}), which the rename-namespace path turns into a hard
# crash and the visibility filter into a stealthy bug.
_LIST_OF_STR_CONFIG_KEYS = (
    "visible_namespaces",
    "hidden_namespaces",
    "pinned_namespaces",
)
# Keys whose value MUST be a string.
_STR_CONFIG_KEYS = ("namespace", "issue_prefix", "inbox_remote")
# Keys whose value MUST be a bool. A string here ("false" / "no" /
# "0") would be truthy under ``bool(...)`` and silently flip a
# security-sensitive toggle.
_BOOL_CONFIG_KEYS = ("allow_creating_namespaces", "git_tracking")

# Every config key the runtime reads, in a stable order. Drives the typed
# DogcatConfig fields below; anything outside this set is forward-compat data
# preserved verbatim in ``DogcatConfig.extra``.
_KNOWN_CONFIG_KEYS: tuple[str, ...] = (
    *_STR_CONFIG_KEYS,
    *_BOOL_CONFIG_KEYS,
    *_LIST_OF_STR_CONFIG_KEYS,
    "disable_legend_colors",
)


@dataclass
class DogcatConfig:
    """Typed view of a merged dogcat config with forward-compat passthrough.

    Known keys are exposed as attributes; any other key a newer dcat (or a
    hand-edit) wrote is preserved verbatim in :attr:`extra` so a
    load -> mutate -> save round-trip never drops it.

    The mapping dunders (``__getitem__`` etc.) back the dynamic-key
    ``dcat config`` command and dict-unpacking (``{**cfg}``); they route known
    keys to their attribute and everything else to :attr:`extra`. A key whose
    attribute is ``None`` is treated as absent — so ``to_dict`` never writes a
    defaulted key the user did not set, and ``key in cfg`` matches the old
    dict semantics.
    """

    namespace: str | None = None
    issue_prefix: str | None = None
    inbox_remote: str | None = None
    allow_creating_namespaces: bool | None = None
    git_tracking: bool | None = None
    visible_namespaces: list[str] | None = None
    hidden_namespaces: list[str] | None = None
    pinned_namespaces: list[str] | None = None
    disable_legend_colors: bool | None = None
    extra: dict[str, Any] = field(default_factory=dict[str, Any])

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DogcatConfig:
        """Build from a raw config dict, routing unknown keys to :attr:`extra`."""
        known: dict[str, Any] = {}
        extra: dict[str, Any] = {}
        for key, value in data.items():
            if key in _KNOWN_CONFIG_KEYS:
                known[key] = value
            else:
                extra[key] = value
        return cls(**known, extra=extra)

    def to_dict(self) -> dict[str, Any]:
        """Serialize back to a plain dict, emitting only keys that are set.

        A known key whose attribute is ``None`` is omitted so writing back
        never adds a defaulted key to the user's TOML; unknown keys in
        :attr:`extra` are preserved.
        """
        result: dict[str, Any] = {}
        for key in _KNOWN_CONFIG_KEYS:
            value = getattr(self, key)
            if value is not None:
                result[key] = value
        result.update(self.extra)
        return result

    def __getitem__(self, key: str) -> Any:
        if key in _KNOWN_CONFIG_KEYS:
            value = getattr(self, key)
            if value is None:
                raise KeyError(key)
            return value
        return self.extra[key]

    def __setitem__(self, key: str, value: Any) -> None:
        if key in _KNOWN_CONFIG_KEYS:
            setattr(self, key, value)
        else:
            self.extra[key] = value

    def __delitem__(self, key: str) -> None:
        if key in _KNOWN_CONFIG_KEYS:
            if getattr(self, key) is None:
                raise KeyError(key)
            setattr(self, key, None)
        else:
            del self.extra[key]

    def __contains__(self, key: str) -> bool:
        if key in _KNOWN_CONFIG_KEYS:
            return getattr(self, key) is not None
        return key in self.extra

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-style read used by dynamic-key callers; prefer attributes."""
        try:
            return self[key]
        except KeyError:
            return default

    def keys(self) -> list[str]:
        """Set keys, for ``{**cfg}`` unpacking and the config command."""
        return list(self.to_dict().keys())

    def items(self) -> list[tuple[str, Any]]:
        """Set (key, value) pairs, for the config command."""
        return list(self.to_dict().items())

    def __iter__(self) -> Iterator[str]:
        return iter(self.to_dict())


def _validate_config_shape(payload: dict[str, Any], source: str) -> dict[str, Any]:
    """Drop shape-violating values from a config dict, logging each drop.

    Coercing here keeps callers (which previously did
    ``list(config.get('pinned_namespaces', []))`` etc.) from silently
    iterating a wrongly-typed scalar.
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

    Memoized on the file's (mtime_ns, size, inode), so repeated reads within
    one command parse once while an edit from another process still lands on
    the next call. The result is deep-copied out: callers merge into it and
    hand its lists to :class:`DogcatConfig`, and a mutation reaching the
    stored dict would poison every later read.
    """
    key = str(path)
    signature = _stat_signature(path)
    cached = _toml_cache.get(key)
    if cached is not None and cached[0] == signature:
        return copy.deepcopy(cached[1])
    payload = _parse_toml(path)
    _toml_cache[key] = (signature, payload)
    return copy.deepcopy(payload)


def _parse_toml(path: Path) -> dict[str, Any]:
    """Read and validate one TOML file, uncached.

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
    ``/tmp/.dogcatrc`` planted by another user.

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


def load_config(dogcats_dir: str) -> DogcatConfig:
    """Load configuration from .dogcats/config.toml, merged with config.local.toml.

    Values in config.local.toml override those in config.toml (shallow merge).
    When using .dogcatrc, a repo-local config.local.toml (in .dogcats/ next to
    the .dogcatrc) takes highest precedence.

    Args:
        dogcats_dir: Path to .dogcats directory

    Returns:
        Typed :class:`DogcatConfig` (empty when no config exists)
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

    return DogcatConfig.from_dict(config)


def load_shared_config(dogcats_dir: str) -> DogcatConfig:
    """Load only the shared config.toml (ignoring config.local.toml).

    Use this when you need to write back to config.toml without
    accidentally persisting local-only values.

    Args:
        dogcats_dir: Path to .dogcats directory

    Returns:
        Typed :class:`DogcatConfig` from config.toml only
    """
    return DogcatConfig.from_dict(_load_toml(get_config_path(dogcats_dir)))


def load_local_config(dogcats_dir: str) -> DogcatConfig:
    """Load the local config.local.toml.

    When using .dogcatrc, reads from the repo-local .dogcats/config.local.toml
    (next to the .dogcatrc) instead of the shared directory.

    Args:
        dogcats_dir: Path to .dogcats directory

    Returns:
        Typed :class:`DogcatConfig` from config.local.toml only
    """
    repo_local_path = _get_repo_local_config_path()
    if repo_local_path is not None:
        return DogcatConfig.from_dict(_load_toml(repo_local_path))
    return DogcatConfig.from_dict(_load_toml(get_local_config_path(dogcats_dir)))


def atomic_write_toml(path: Path, payload: dict[str, Any]) -> None:
    """Write TOML to ``path`` atomically (write-tmp + fsync + replace).

    Without this, a kill / power-loss / ENOSPC mid-write leaves a
    truncated config that ``_load_toml`` silently treats as ``{}`` —
    every configured setting (namespace, visible_namespaces, etc.)
    is lost without a signal. The pattern mirrors
    ``_atomic_write_json`` in :mod:`dogcat.cli._cmd_doctor`.
    Also used by :mod:`dogcat.global_config` for the user-global file.
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
        # Drop the memo here rather than in save_config / save_local_config:
        # this is the single choke point every config write passes through,
        # and a rewrite landing inside one mtime tick would otherwise leave
        # the caller reading its own pre-write value (dogcat-2s9r).
        _toml_cache.pop(str(path), None)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp_path.unlink()
        raise


def save_local_config(dogcats_dir: str, config: DogcatConfig) -> None:
    """Save configuration to config.local.toml.

    When using .dogcatrc, saves to the repo-local .dogcats/config.local.toml
    (next to the .dogcatrc) instead of the shared directory.

    Args:
        dogcats_dir: Path to .dogcats directory
        config: Configuration to save
    """
    repo_local_path = _get_repo_local_config_path()
    if repo_local_path is not None:
        config_path = repo_local_path
    else:
        config_path = get_local_config_path(dogcats_dir)
    atomic_write_toml(config_path, config.to_dict())


def save_config(dogcats_dir: str, config: DogcatConfig) -> None:
    """Save configuration to .dogcats/config.toml.

    Args:
        dogcats_dir: Path to .dogcats directory
        config: Configuration to save
    """
    atomic_write_toml(get_config_path(dogcats_dir), config.to_dict())


def _resolve_dogcats_path(dogcats_dir: str) -> str:
    """Resolve the .dogcats directory path, walking up from CWD if needed.

    When commands are run from a subdirectory, ``dogcats_dir`` may be the
    default ``".dogcats"`` which doesn't exist locally, so this walks up
    from CWD for callers in ``config.py`` (which can't import from ``cli``).

    This is the *unhardened* walk. It is not a copy of
    ``cli._helpers.walkup_find_store`` or of :func:`_find_rc_parent`, both of
    which stop at :func:`get_rc_walkup_boundary` and run
    :func:`refuse_if_rc_target_cross_user`. This one climbs to the
    filesystem root, applies no cross-user refusal, and swallows a malformed
    ``.dogcatrc`` instead of exiting. A planted ``/tmp/.dogcatrc`` can
    therefore steer resolution here where it could not there. Why the guards
    were left off is not recorded — treat the gap as unexplained rather than
    as a reviewed exemption, and prefer the hardened walk-ups when a caller
    can reach them.

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
            # Filesystem root reached. Try global config before falling back.
            from dogcat.global_config import resolve_global_fallback

            return resolve_global_fallback() or dogcats_dir
        current = parent


def get_namespace(dogcats_dir: str) -> str:
    """Get the issue prefix from config or return default.

    Precedence:
    1. When storage was resolved via the global fallback: slug of the
       project root name — git toplevel when inside a repo, else cwd
       (a .dogcatrc or local .dogcats would have resolved first, so
       repo-level config cannot apply here)
    2. Namespace from local/shared config.toml in the storage dir
    3. Auto-detect from existing issues (most common prefix)
    4. Auto-detect from directory name
    5. Default prefix ("dc")

    Args:
        dogcats_dir: Path to .dogcats directory

    Returns:
        Issue prefix string
    """
    from dogcat.global_config import (
        derive_fallback_namespace,
        was_resolved_via_global,
    )

    # Resolve the actual .dogcats path (handles subdirectory invocations)
    dogcats_dir = _resolve_dogcats_path(dogcats_dir)

    # When the store was reached via the global fallback, prefer the
    # project-root-derived namespace over the shared store's primary prefix.
    if was_resolved_via_global(dogcats_dir):
        slug = derive_fallback_namespace()
        if slug:
            return slug
        # Fall through if the project root is not sluggable (CJK, emoji, etc.).

    # Try config file ("namespace" key, with "issue_prefix" fallback)
    config = load_config(dogcats_dir)
    if config.namespace is not None:
        return config.namespace
    if config.issue_prefix is not None:
        return config.issue_prefix

    # Try to auto-detect from existing issues
    prefix = _detect_namespace_from_issues(dogcats_dir)
    if prefix:
        return prefix

    # Try directory name (parent of .dogcats)
    prefix = _detect_namespace_from_directory(dogcats_dir)
    if prefix:
        return prefix

    return DEFAULT_PREFIX


def set_namespace(dogcats_dir: str, namespace: str) -> None:
    """Set the issue namespace in config.

    Args:
        dogcats_dir: Path to .dogcats directory
        namespace: Namespace to set
    """
    config = load_shared_config(dogcats_dir)
    config.namespace = namespace
    config.issue_prefix = None
    save_config(dogcats_dir, config)


def _detect_namespace_from_issues(dogcats_dir: str) -> str | None:
    """Detect prefix from existing issues in storage.

    Runs on every ``get_namespace`` call for a store whose config sets no
    namespace, and reads every line of issues.jsonl to do it — a second full
    parse on top of the one storage already did, 1-2 times per command
    (dogcat-48ti). Memoized on the file's (mtime_ns, size, inode), so an
    append re-detects and a repeated call inside one command does not.

    Args:
        dogcats_dir: Path to .dogcats directory

    Returns:
        Most common prefix, or None if no issues exist
    """
    issues_path = Path(dogcats_dir) / "issues.jsonl"
    key = str(issues_path)
    signature = _stat_signature(issues_path)
    cached = _detected_namespace_cache.get(key)
    if cached is not None and cached[0] == signature:
        return cached[1]
    detected = _scan_namespace_from_issues(issues_path)
    _detected_namespace_cache[key] = (signature, detected)
    return detected


def _scan_namespace_from_issues(issues_path: Path) -> str | None:
    """Count id prefixes across issues.jsonl and return the most common."""
    if not issues_path.exists():
        return None

    try:
        prefix_counts: dict[str, int] = {}

        with issues_path.open("rb") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    data = orjson.loads(line)
                    if classify_record(data) != "issue":
                        continue
                    issue_id = data.get("id", "")
                    prefix = extract_namespace(issue_id)
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


def _detect_namespace_from_directory(dogcats_dir: str) -> str | None:
    """Detect prefix from directory name.

    Args:
        dogcats_dir: Path to .dogcats directory

    Returns:
        Directory name as prefix, or None
    """
    from dogcat.namespace_slug import slug_from_dir

    dogcats_path = Path(dogcats_dir).resolve()

    # Get the parent directory (the project directory)
    project_dir = dogcats_path.parent

    # Same slug policy as the global-fallback namespace derivation, so
    # one folder name never yields two different namespaces.
    return slug_from_dir(project_dir.name)


def extract_namespace(issue_id: str) -> str | None:
    """Extract the namespace from an issue ID.

    Args:
        issue_id: Issue ID like "search-8qx" or "dc-abc"

    Returns:
        Namespace part, or None if no hyphen found
    """
    if "-" not in issue_id:
        return None

    # Find the last hyphen and take everything before it
    last_hyphen = issue_id.rfind("-")
    return issue_id[:last_hyphen] if last_hyphen > 0 else None


# Deprecated aliases — the canonical names are the ``*_namespace`` helpers
# above. These shims kept the old ``*_prefix`` names importable for out-of-tree
# callers through v0.13.1, the one release they were promised. Remove them in
# v0.14.0: nothing in-tree imports them except tests/test_config.py, so the
# deletion is these four lines plus that test. (dogcat-1tzm)
get_issue_prefix = get_namespace
set_issue_prefix = set_namespace
extract_prefix = extract_namespace


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
    from dogcat.global_config import load_global_config, was_resolved_via_global

    if explicit_namespace is not None:
        return lambda ns: ns == explicit_namespace

    config = load_config(dogcats_dir)
    visible = config.visible_namespaces
    hidden = config.hidden_namespaces

    primary = get_namespace(dogcats_dir)

    # If we resolved via the global fallback, layer global
    # visible_namespaces under local config. When cwd has a slug (so
    # namespace was cwd-derived), filter to that namespace alone.
    if was_resolved_via_global(dogcats_dir) and not visible and not hidden:
        gcfg = load_global_config()
        if gcfg.visible_namespaces:
            allowed = set(gcfg.visible_namespaces)
            allowed.add(primary)
            return lambda ns: ns in allowed
        return lambda ns: ns == primary

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


def migrate_config_keys(config: DogcatConfig) -> bool:
    """Rename deprecated config keys to their current names.

    Renames ``issue_prefix`` → ``namespace`` in-place.

    Returns:
        True if any keys were migrated, False otherwise.
    """
    changed = False
    if config.issue_prefix is not None:
        if config.namespace is None:
            config.namespace = config.issue_prefix
        config.issue_prefix = None
        changed = True
    return changed
