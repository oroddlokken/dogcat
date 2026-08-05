"""Git default-branch detection for compaction safety.

Storage avoids auto-compacting on feature branches (it would create noisy
diffs). Deciding whether the working tree is on a default branch is a
self-contained responsibility extracted from ``JSONLStorage`` so the god
class shrinks toward cohesive units.
"""

from __future__ import annotations

import logging
import subprocess
from typing import TYPE_CHECKING

from dogcat.constants import DEFAULT_BRANCH_NAMES

if TYPE_CHECKING:
    from pathlib import Path


def known_default_branches(dogcats_dir: Path) -> frozenset[str]:
    """Return conventional default branches unioned with ``init.defaultBranch``.

    ``init.defaultBranch`` lets users opt their non-conventional default
    branch (e.g. ``develop``) into auto-compaction without a config flag.
    The git lookup is best-effort: if git is unreachable or the value isn't
    set, fall back to the compiled defaults.
    """
    from dogcat import git as git_helpers

    configured = git_helpers.get_config("init.defaultBranch", cwd=dogcats_dir)
    if configured:
        # init.defaultBranch is per-repo and writable by any collaborator.
        # If it points to a non-conventional name, log a one-line warning so
        # the user notices before a noisy compaction lands on a feature
        # branch.
        if configured not in DEFAULT_BRANCH_NAMES:
            logging.getLogger(__name__).warning(
                "init.defaultBranch=%r is not a conventional default "
                "(main/master); auto-compaction is enabled on this "
                "branch via the per-repo git config. Verify this is "
                "intentional — set the value in .dogcats/config.toml "
                "if you want it tracked in review.",
                configured,
            )
        return DEFAULT_BRANCH_NAMES | {configured}
    return DEFAULT_BRANCH_NAMES


def is_default_branch(dogcats_dir: Path) -> bool:
    """Check whether the working tree at ``dogcats_dir`` is on a default branch.

    ``True`` when there is genuinely no git repository (FileNotFoundError on
    the binary or git reports "not a git repo"). Any other non-zero return —
    permission denied, lock contention, internal git error — returns
    ``False`` and logs the stderr so we don't silently lose the feature-branch
    protection on a transient problem.

    The known-default-branch set is :data:`DEFAULT_BRANCH_NAMES` plus the
    user's ``init.defaultBranch`` git config when set.
    """
    # Kept inline here (not via dogcat.git.current_branch) because the
    # storage path needs the stderr to distinguish "no repo" (safe) from
    # "permission denied" (not safe); the git module's helper collapses both
    # to None.
    #
    # Force the C locale so stderr text matches the literal English match
    # below. Under non-English LC_ALL git emits localized strings and the
    # substring check would fail, disabling auto-compaction silently.
    # Time-bound the call so a stalled HOME / credential helper / LFS smudge
    # cannot wedge dcat indefinitely.
    try:
        from dogcat.git import _c_locale_env, _git_timeout

        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],  # noqa: S607  # PATH git
            capture_output=True,
            text=True,
            check=False,
            cwd=str(dogcats_dir),
            env=_c_locale_env(),
            timeout=_git_timeout(),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return True  # git not installed / hung — safe to compact
    if result.returncode == 0:
        branch = result.stdout.strip()
        return branch in known_default_branches(dogcats_dir)
    stderr = (result.stderr or "").strip().lower()
    # "not a git repository" is the only non-zero outcome we treat as
    # "no repo here, safe to compact". Permission denied / locked index /
    # internal errors should NOT bypass the protection.
    if "not a git repository" in stderr:
        return True
    logging.getLogger(__name__).warning(
        "git rev-parse failed (rc=%s) under %s: %s. Skipping compaction to be safe.",
        result.returncode,
        dogcats_dir,
        result.stderr.strip() if result.stderr else "<no stderr>",
    )
    return False
