"""Centralized helpers for git subprocess calls.

Every ``git`` subprocess in the tree goes through here, which gives one place
to harden behavior (capturing stderr, normalizing missing-binary handling,
the timeout) and one mock target for tests. Spelling out a
``subprocess.run(["git", ...])`` elsewhere forfeits both.

Each helper returns ``None`` (or an empty result) when git is unavailable or
the operation legitimately has no answer (e.g. ``repo_root`` outside a
repository). Callers shouldn't have to reinvent the missing-binary check.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any


def _c_locale_env() -> dict[str, str]:
    """Return the current environment with LC_ALL=C, LANG=C overlaid.

    Forces git to emit C-locale stdout/stderr so substring checks ("not
    a git repository", "fatal: ...") match regardless of the user's
    locale.
    """
    return {**os.environ, "LC_ALL": "C", "LANG": "C"}


# Default timeout (seconds) for every ``git`` subprocess. Without a
# timeout, a stalled NFS ``$HOME``, a dead credential helper, or a
# broken LFS smudge wedges every dcat invocation indefinitely. Override
# via ``DCAT_GIT_TIMEOUT_SECS`` for slow networks.
_GIT_TIMEOUT_DEFAULT = 10.0


def _git_timeout() -> float:
    raw = os.environ.get("DCAT_GIT_TIMEOUT_SECS")
    if not raw:
        return _GIT_TIMEOUT_DEFAULT
    try:
        value = float(raw)
    except ValueError:
        return _GIT_TIMEOUT_DEFAULT
    return value if value > 0 else _GIT_TIMEOUT_DEFAULT


def _run(
    args: list[str],
    *,
    cwd: str | Path | None = None,
    capture_text: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes] | None:
    """Run ``git <args>`` and return the CompletedProcess (or None if missing).

    ``capture_text=True`` decodes stdout/stderr as text. When False (used for
    ``git show`` of binary blobs) raw bytes are returned. We never set
    ``check=True`` — callers inspect the returncode themselves so they can
    distinguish "no repo" from real failures. The call is bounded by
    :func:`_git_timeout` (default 10 s, overridable via
    ``DCAT_GIT_TIMEOUT_SECS``); on TimeoutExpired we return None like a
    missing binary so callers degrade gracefully. ``env`` is overlaid on
    the C-locale environment (e.g. ``GIT_INDEX_FILE`` for a scratch index).

    S603/S607 are silenced throughout: argv is a fixed list (never a shell
    string), and resolving "git" off PATH is the point — dcat must use whichever
    git the user's environment provides, not one pinned at install time.
    """
    env = {**_c_locale_env(), **(env or {})}
    timeout = _git_timeout()
    try:
        if capture_text:
            return subprocess.run(  # noqa: S603
                ["git", *args],  # noqa: S607
                capture_output=True,
                text=True,
                check=False,
                cwd=str(cwd) if cwd else None,
                env=env,
                timeout=timeout,
            )
        return subprocess.run(  # noqa: S603
            ["git", *args],  # noqa: S607
            capture_output=True,
            check=False,
            cwd=str(cwd) if cwd else None,
            env=env,
            timeout=timeout,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
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


def check_attr(
    attr: str,
    paths: list[str],
    *,
    cwd: str | Path | None = None,
) -> dict[str, str] | None:
    """Return ``attr``'s effective value per path, or None when git can't answer.

    ``paths`` are resolved relative to ``cwd``, so pass the repo root to get
    repo-root-relative matching — the same relative path resolves differently
    from a subdirectory. A path need not exist: ``git check-attr`` applies the
    .gitattributes rules to any name, which is what lets a caller probe a
    directory holding no files yet.

    Values are git's own spelling, so a path with no rule reads
    ``"unspecified"`` rather than being absent from the mapping.
    """
    if not paths:
        return {}
    result = _run(["check-attr", "-z", attr, "--", *paths], cwd=cwd)
    if result is None or result.returncode != 0:
        return None
    out = result.stdout
    if not isinstance(out, str):
        return None
    # -z emits NUL-separated (path, attr, value) triples, trailing NUL included,
    # which keeps paths containing colons or newlines parseable.
    fields = out.split("\0")
    return {
        fields[i]: fields[i + 2]
        for i in range(0, len(fields) - 2, 3)  # -2: a trailing partial is padding
    }


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


def _stdout_line(result: subprocess.CompletedProcess[Any] | None) -> str | None:
    """Return stripped text stdout of a successful run, or None."""
    if result is None or result.returncode != 0:
        return None
    out = result.stdout
    if not isinstance(out, str):
        return None
    return out.strip() or None


def resolve_branch(branch: str, *, cwd: str | Path | None = None) -> str | None:
    """Return the commit SHA of local branch ``branch``, or None if it doesn't exist."""
    return _stdout_line(
        _run(
            ["rev-parse", "--verify", "--quiet", f"refs/heads/{branch}^{{commit}}"],
            cwd=cwd,
        )
    )


def local_branches(cwd: str | Path | None = None) -> list[str]:
    """Return the names of all local branches (empty outside a repo)."""
    out = _stdout_line(
        _run(["for-each-ref", "--format=%(refname:short)", "refs/heads/"], cwd=cwd)
    )
    return out.splitlines() if out else []


def checked_out_branches(cwd: str | Path | None = None) -> set[str]:
    """Return the branches checked out in any worktree of this repository."""
    out = _stdout_line(_run(["worktree", "list", "--porcelain"], cwd=cwd))
    if out is None:
        return set()
    prefix = "branch refs/heads/"
    return {line[len(prefix) :] for line in out.splitlines() if line.startswith(prefix)}


def hash_object(path: str | Path, *, cwd: str | Path | None = None) -> str | None:
    """Write ``path``'s contents to the object store and return the blob SHA."""
    return _stdout_line(_run(["hash-object", "-w", "--", str(path)], cwd=cwd))


def stage_blob(blob: str, repo_path: str, *, cwd: str | Path | None = None) -> bool:
    """Point the index entry for ``repo_path`` at ``blob``, leaving the worktree.

    ``repo_path`` is repo-root-relative with forward slashes. The entry is
    written as a regular non-executable file (mode 100644).
    """
    result = _run(
        ["update-index", "--add", "--cacheinfo", f"100644,{blob},{repo_path}"],
        cwd=cwd,
    )
    return result is not None and result.returncode == 0


def commit_file_to_branch(
    branch: str,
    *,
    parent: str,
    repo_path: str,
    blob: str,
    message: str,
    scratch_index: str | Path,
    cwd: str | Path | None = None,
) -> str | None:
    """Commit ``blob`` at ``repo_path`` on top of ``parent`` and move ``branch`` to it.

    Builds the tree in ``scratch_index`` (a path that must not exist yet),
    so the user's index and working tree are never touched. The ref moves
    with ``update-ref <new> <parent>``, a compare-and-swap: when ``branch``
    no longer points at ``parent`` nothing moves and None is returned.

    Returns:
        The new commit SHA, or None when any step failed.
    """
    env = {"GIT_INDEX_FILE": str(scratch_index)}
    steps: list[list[str]] = [
        ["read-tree", parent],
        ["update-index", "--add", "--cacheinfo", f"100644,{blob},{repo_path}"],
    ]
    for args in steps:
        result = _run(args, cwd=cwd, env=env)
        if result is None or result.returncode != 0:
            return None
    tree = _stdout_line(_run(["write-tree"], cwd=cwd, env=env))
    if tree is None:
        return None
    commit = _stdout_line(
        _run(["commit-tree", tree, "-p", parent, "-m", message], cwd=cwd)
    )
    if commit is None:
        return None
    moved = _run(["update-ref", f"refs/heads/{branch}", commit, parent], cwd=cwd)
    if moved is None or moved.returncode != 0:
        return None
    return commit
