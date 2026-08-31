"""Tests for scripts/release-prep against a local bare-repo remote.

Both cases here are the v0.14.2 failure: a release branch that exists on
the remote but not in the clone, and a rejected branch push that had
already published its RC tag (dogcat-43d6).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Sequence

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "release-prep"

_GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@test.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@test.com",
    "GIT_TERMINAL_PROMPT": "0",
}

CHANGELOG = "# Changelog\n\n## [Unreleased]\n\n### Fixed\n\n- Something\n"


def _git(cwd: Path, *args: str, check: bool = True) -> str:
    """Run git in cwd and return stdout."""
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=check,
        env=_GIT_ENV,
    )
    return result.stdout.strip()


def _make_gh_stub(bin_dir: Path) -> None:
    """Put a `gh` on PATH that reports no PR and creates a fake one.

    release-prep calls gh for PR discovery and creation; neither is under
    test here, and a real gh would try to reach GitHub.
    """
    bin_dir.mkdir(parents=True, exist_ok=True)
    stub = bin_dir / "gh"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        'if [[ "$1 $2" == "pr create" ]]; then\n'
        '    echo "https://example.invalid/pr/1"\n'
        "    exit 0\n"
        "fi\n"
        "exit 1\n",
    )
    stub.chmod(0o755)


def _run_script(
    repo: Path, bin_dir: Path, args: Sequence[str]
) -> subprocess.CompletedProcess[str]:
    """Run release-prep in repo with the gh stub ahead of the real PATH."""
    env = {**_GIT_ENV, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


@pytest.fixture
def remote_and_clone(tmp_path: Path) -> tuple[Path, Path]:
    """Build a bare remote plus a clone on main with a CHANGELOG."""
    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "--bare", "--initial-branch=main", str(remote))

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--initial-branch=main")
    _git(repo, "remote", "add", "origin", str(remote))
    (repo / "CHANGELOG.md").write_text(CHANGELOG)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "Initial")
    _git(repo, "push", "-u", "origin", "main")
    return remote, repo


class TestRemoteOnlyBranch:
    """A release branch on the remote that the clone does not have."""

    def test_reuses_remote_branch_instead_of_forking(
        self,
        tmp_path: Path,
        remote_and_clone: tuple[Path, Path],
    ) -> None:
        """The rerun builds on the remote tip and pushes without a conflict.

        Checking only `refs/heads/<branch>` sent this case down the
        `worktree add -b` path, which branched off main and produced a
        sibling of the remote tip that no push could fast-forward.
        """
        remote, repo = remote_and_clone

        # Previous RC, cut elsewhere: branch and tag exist only on the remote.
        _git(repo, "checkout", "-b", "release/v9.9.9")
        (repo / "CHANGELOG.md").write_text(
            CHANGELOG.replace(
                "## [Unreleased]", "## [Unreleased]\n\n## 9.9.9 (2026-01-01)"
            ),
        )
        _git(repo, "commit", "-am", "Prepare changelog for v9.9.9")
        _git(repo, "tag", "-a", "v9.9.9-rc.1", "-m", "rc1")
        _git(repo, "push", "origin", "release/v9.9.9", "--tags")
        _git(repo, "checkout", "main")
        _git(repo, "branch", "-D", "release/v9.9.9")
        _git(repo, "tag", "-d", "v9.9.9-rc.1")

        # A fix lands on main after that RC, which is why we cut another.
        (repo / "fix.txt").write_text("fix\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "Fix something")
        _git(repo, "push", "origin", "main")

        bin_dir = tmp_path / "bin"
        _make_gh_stub(bin_dir)
        result = _run_script(repo, bin_dir, ["-W", "--skip-checks", "9.9.9"])

        assert result.returncode == 0, result.stdout + result.stderr

        remote_tip = _git(remote, "rev-parse", "release/v9.9.9")
        assert _git(repo, "rev-parse", "release/v9.9.9") == remote_tip
        # The branch carries the fix, so it was re-cut from main rather than
        # left at the previous RC.
        assert "fix.txt" in _git(repo, "ls-tree", "--name-only", remote_tip)
        assert _git(remote, "rev-parse", "v9.9.9-rc.2^{}") == remote_tip


class TestRejectedBranchPush:
    """A branch push the remote refuses must not leave a tag behind."""

    def test_rejected_push_publishes_no_tag(
        self,
        tmp_path: Path,
        remote_and_clone: tuple[Path, Path],
    ) -> None:
        """`push --tags` used to send the RC tag even when the branch failed."""
        remote, repo = remote_and_clone

        # The remote branch holds a commit this clone's branch does not, so
        # the non-fast-forward push is rejected.
        _git(repo, "checkout", "-b", "release/v9.9.8")
        (repo / "theirs.txt").write_text("theirs\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "Their release work")
        _git(repo, "push", "origin", "release/v9.9.8")
        _git(repo, "checkout", "main")
        # Rewind the local branch so it no longer contains the remote tip.
        _git(repo, "branch", "-f", "release/v9.9.8", "main")

        bin_dir = tmp_path / "bin"
        _make_gh_stub(bin_dir)
        result = _run_script(repo, bin_dir, ["-W", "--skip-checks", "9.9.8"])

        assert result.returncode != 0, result.stdout
        assert _git(remote, "tag", "-l", "v9.9.8-rc.1") == ""
        assert _git(repo, "tag", "-l", "v9.9.8-rc.1") == ""
