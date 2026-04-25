"""Centralized helpers for git subprocess calls.

Multiple modules used to spell out their own ``subprocess.run(["git", ...])``
incantations, which made test mocking awkward (you had to patch the right
module's ``subprocess`` import) and led to subtle inconsistencies in error
handling. This module concentrates the calls so there's one place to harden
behavior (e.g. capturing stderr, normalizing missing-binary handling) and a
single mock target for tests.

Each helper returns ``None`` (or an empty result) when git is unavailable or
the operation legitimately has no answer (e.g. ``repo_root`` outside a
repository). Callers shouldn't have to reinvent the missing-binary check.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def _run(
    args: list[str],
    *,
    cwd: str | Path | None = None,
    capture_text: bool = True,
) -> subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes] | None:
    """Run ``git <args>`` and return the CompletedProcess (or None if missing).

    ``capture_text=True`` decodes stdout/stderr as text. When False (used for
    ``git show`` of binary blobs) raw bytes are returned. We never set
    ``check=True`` — callers inspect the returncode themselves so they can
    distinguish "no repo" from real failures.
    """
    try:
        if capture_text:
            return subprocess.run(
                ["git", *args],
                capture_output=True,
                text=True,
                check=False,
                cwd=str(cwd) if cwd else None,
            )
        return subprocess.run(
            ["git", *args],
            capture_output=True,
            check=False,
            cwd=str(cwd) if cwd else None,
        )
    except (FileNotFoundError, OSError):
        return None


def repo_root(cwd: str | Path | None = None) -> Path | None:
    """Return the working tree root for ``cwd``, or ``None`` outside a repo."""
    result = _run(["rev-parse", "--show-toplevel"], cwd=cwd)
    if result is None or result.returncode != 0:
        return None
    out = result.stdout
    if not isinstance(out, str):
        return None
    out = out.strip()
    if not out:
        return None
    return Path(out)


def common_dir(cwd: str | Path | None = None) -> Path | None:
    """Return the shared ``.git`` directory (main worktree's git dir).

    In a linked worktree, this points back to the main worktree's ``.git``
    directory; the main worktree root is the parent of that path.
    """
    result = _run(["rev-parse", "--git-common-dir"], cwd=cwd)
    if result is None or result.returncode != 0:
        return None
    out = result.stdout
    if not isinstance(out, str):
        return None
    out = out.strip()
    if not out:
        return None
    return Path(out)


def current_branch(cwd: str | Path | None = None) -> str | None:
    """Return the current branch name, or None if HEAD can't be parsed."""
    result = _run(["rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)
    if result is None or result.returncode != 0:
        return None
    out = result.stdout
    if not isinstance(out, str):
        return None
    return out.strip() or None


def show_file(
    git_ref: str,
    *,
    cwd: str | Path | None = None,
) -> bytes | None:
    """Return the raw contents of ``git show <ref>:<path>``, or None on failure.

    ``git_ref`` is the full ``ref:path`` form (e.g. ``HEAD:.dogcats/issues.jsonl``
    or ``:.dogcats/issues.jsonl`` for the index). Callers compose the ref
    so the helper stays format-agnostic.
    """
    result = _run(["show", git_ref], cwd=cwd, capture_text=False)
    if result is None or result.returncode != 0:
        return None
    out = result.stdout
    if not isinstance(out, bytes):
        return None
    return out


def is_path_ignored(path: str, *, cwd: str | Path | None = None) -> bool:
    """Return True if ``path`` is matched by a .gitignore rule.

    Returns False outside a repo or when git is unavailable; the caller's
    expectation in those cases is "treat as not ignored" rather than "fail".
    """
    result = _run(["check-ignore", "-q", path], cwd=cwd)
    if result is None:
        return False
    return result.returncode == 0


def user_email(cwd: str | Path | None = None) -> str | None:
    """Return ``git config user.email``, or None when unset / unavailable."""
    result = _run(["config", "user.email"], cwd=cwd)
    if result is None or result.returncode != 0:
        return None
    out = result.stdout
    if not isinstance(out, str):
        return None
    return out.strip() or None


def get_config(key: str, *, cwd: str | Path | None = None) -> str | None:
    """Return the value of a git config ``key``, or None when missing."""
    result = _run(["config", key], cwd=cwd)
    if result is None or result.returncode != 0:
        return None
    out = result.stdout
    if not isinstance(out, str):
        return None
    return out.strip() or None


def set_config(key: str, value: str, *, cwd: str | Path | None = None) -> bool:
    """Set a git config ``key`` to ``value``. Returns True on success."""
    result = _run(["config", key, value], cwd=cwd)
    return result is not None and result.returncode == 0


def add_paths(paths: list[str], *, cwd: str | Path | None = None) -> bool:
    """Run ``git add`` over the given paths. Returns True on success."""
    if not paths:
        return True
    result = _run(["add", *paths], cwd=cwd)
    return result is not None and result.returncode == 0


def latest_merge_commit(cwd: str | Path | None = None) -> str | None:
    """Return the SHA of the most recent merge commit, or None if there are none."""
    result = _run(
        ["log", "--merges", "-1", "--format=%H"],
        cwd=cwd,
    )
    if result is None or result.returncode != 0:
        return None
    out = result.stdout
    if not isinstance(out, str):
        return None
    return out.strip() or None


def merge_parents(
    merge_commit: str, *, cwd: str | Path | None = None
) -> tuple[str, str] | None:
    """Return the two parent SHAs of a merge commit, or None on failure."""
    result = _run(
        ["rev-parse", f"{merge_commit}^1", f"{merge_commit}^2"],
        cwd=cwd,
    )
    if result is None or result.returncode != 0:
        return None
    out = result.stdout
    if not isinstance(out, str):
        return None
    parents = out.strip().splitlines()
    if len(parents) != 2:
        return None
    return parents[0], parents[1]


def merge_base(
    parent1: str, parent2: str, *, cwd: str | Path | None = None
) -> str | None:
    """Return the merge base SHA of two commits, or None on failure."""
    result = _run(["merge-base", parent1, parent2], cwd=cwd)
    if result is None or result.returncode != 0:
        return None
    out = result.stdout
    if not isinstance(out, str):
        return None
    return out.strip() or None
