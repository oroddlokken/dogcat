"""Tests for the centralized git subprocess helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dogcat import git as git_helpers

if TYPE_CHECKING:
    import pytest


def _completed(
    rc: int, stdout: object = "", stderr: str = ""
) -> subprocess.CompletedProcess[Any]:
    """Build a real ``subprocess.CompletedProcess`` for monkey-patching.

    Using the actual class (rather than a duck-typed look-alike) means
    this test fixture stays honest if ``dogcat.git`` ever inspects extra
    attributes (``args``, ``stdout`` type checks). (dogcat-3ibu)
    """
    return subprocess.CompletedProcess(
        args=[], returncode=rc, stdout=stdout, stderr=stderr
    )


def test_repo_root_returns_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """repo_root parses git output into a Path."""

    def fake_run(*_args: Any, **_kwargs: Any) -> object:  # noqa: ARG001
        return _completed(0, "/tmp/some-repo\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert git_helpers.repo_root() == Path("/tmp/some-repo")


def test_repo_root_returns_none_outside_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    """repo_root returns None when git reports failure."""

    def fake_run(*_args: Any, **_kwargs: Any) -> object:  # noqa: ARG001
        return _completed(128, "", "fatal: not a git repository\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert git_helpers.repo_root() is None


def test_repo_root_returns_none_when_git_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """repo_root returns None when the git binary is unavailable."""

    def fake_run(*_args: Any, **_kwargs: Any) -> object:  # noqa: ARG001
        msg = "git not on PATH"
        raise FileNotFoundError(msg)

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert git_helpers.repo_root() is None


def test_current_branch_strips_whitespace(monkeypatch: pytest.MonkeyPatch) -> None:
    """current_branch strips trailing whitespace from git's output."""

    def fake_run(*_args: Any, **_kwargs: Any) -> object:  # noqa: ARG001
        return _completed(0, "feature/my-thing\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert git_helpers.current_branch() == "feature/my-thing"


def test_show_file_returns_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    """show_file returns the raw bytes of git show."""

    def fake_run(*_args: Any, **_kwargs: Any) -> object:  # noqa: ARG001
        return _completed(0, b"file contents\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert git_helpers.show_file("HEAD:README.md") == b"file contents\n"


def test_show_file_returns_none_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """show_file returns None when the ref doesn't resolve."""

    def fake_run(*_args: Any, **_kwargs: Any) -> object:  # noqa: ARG001
        return _completed(128, b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert git_helpers.show_file("bogus:path") is None


def test_is_path_ignored_true(monkeypatch: pytest.MonkeyPatch) -> None:
    """is_path_ignored returns True when git check-ignore exits 0."""

    def fake_run(*_args: Any, **_kwargs: Any) -> object:  # noqa: ARG001
        return _completed(0, "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert git_helpers.is_path_ignored("ignored.txt") is True


def test_is_path_ignored_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """is_path_ignored returns False when git check-ignore exits non-zero."""

    def fake_run(*_args: Any, **_kwargs: Any) -> object:  # noqa: ARG001
        return _completed(1, "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert git_helpers.is_path_ignored("tracked.txt") is False


def test_is_path_ignored_safe_when_git_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """is_path_ignored returns False (not an error) when git is missing."""

    def fake_run(*_args: Any, **_kwargs: Any) -> object:  # noqa: ARG001
        msg = "no git"
        raise FileNotFoundError(msg)

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert git_helpers.is_path_ignored("any.txt") is False


def test_user_email_returns_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """user_email parses git config output."""

    def fake_run(*_args: Any, **_kwargs: Any) -> object:  # noqa: ARG001
        return _completed(0, "alice@example.com\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert git_helpers.user_email() == "alice@example.com"


def test_user_email_returns_none_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """user_email returns None when git config exits non-zero (key not set)."""

    def fake_run(*_args: Any, **_kwargs: Any) -> object:  # noqa: ARG001
        return _completed(1, "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert git_helpers.user_email() is None


def test_set_config_returns_true_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """set_config returns True when git config exits 0."""

    def fake_run(*_args: Any, **_kwargs: Any) -> object:  # noqa: ARG001
        return _completed(0, "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert git_helpers.set_config("merge.foo.driver", "cmd") is True


def test_latest_merge_commit_returns_sha(monkeypatch: pytest.MonkeyPatch) -> None:
    """latest_merge_commit returns the trimmed SHA on success."""

    def fake_run(*_args: Any, **_kwargs: Any) -> object:  # noqa: ARG001
        return _completed(0, "abc123def456\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert git_helpers.latest_merge_commit() == "abc123def456"


def test_latest_merge_commit_returns_none_when_no_merges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """latest_merge_commit returns None when git log returns nothing."""

    def fake_run(*_args: Any, **_kwargs: Any) -> object:  # noqa: ARG001
        return _completed(0, "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert git_helpers.latest_merge_commit() is None


def test_merge_parents_returns_pair(monkeypatch: pytest.MonkeyPatch) -> None:
    """merge_parents returns a (parent1, parent2) tuple."""

    def fake_run(*_args: Any, **_kwargs: Any) -> object:  # noqa: ARG001
        return _completed(0, "aaa\nbbb\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert git_helpers.merge_parents("merge_sha") == ("aaa", "bbb")


def test_merge_parents_returns_none_on_unexpected_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """merge_parents returns None when output doesn't have exactly 2 parents."""

    def fake_run(*_args: Any, **_kwargs: Any) -> object:  # noqa: ARG001
        return _completed(0, "only-one\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert git_helpers.merge_parents("merge_sha") is None


def test_merge_base_returns_sha(monkeypatch: pytest.MonkeyPatch) -> None:
    """merge_base returns the SHA of the common ancestor."""

    def fake_run(*_args: Any, **_kwargs: Any) -> object:  # noqa: ARG001
        return _completed(0, "common-sha\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert git_helpers.merge_base("a", "b") == "common-sha"


def test_add_paths_empty_list_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    """add_paths returns True without invoking git for an empty list."""
    called: list[bool] = []

    def fake_run(*_args: Any, **_kwargs: Any) -> object:  # noqa: ARG001
        called.append(True)
        return _completed(0, "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert git_helpers.add_paths([]) is True
    assert called == []


class TestGitTimeout:
    """git._run must time-bound subprocess calls.

    Regression for dogcat-1uq7: a stalled NFS HOME / dead credential
    helper / broken LFS smudge would wedge dcat indefinitely.
    """

    def test_run_passes_timeout_to_subprocess(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The default 10 s timeout is passed through to subprocess.run."""
        captured: dict[str, object] = {}

        def fake_run(*_args: Any, **kwargs: Any) -> object:
            captured["timeout"] = kwargs.get("timeout")
            return _completed(0, "main\n")

        monkeypatch.setattr(subprocess, "run", fake_run)
        git_helpers.current_branch()
        assert captured["timeout"] == 10.0

    def test_dcat_git_timeout_secs_env_override(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``DCAT_GIT_TIMEOUT_SECS`` overrides the default."""
        captured: dict[str, object] = {}

        def fake_run(*_args: Any, **kwargs: Any) -> object:
            captured["timeout"] = kwargs.get("timeout")
            return _completed(0, "main\n")

        monkeypatch.setenv("DCAT_GIT_TIMEOUT_SECS", "42")
        monkeypatch.setattr(subprocess, "run", fake_run)
        git_helpers.current_branch()
        assert captured["timeout"] == 42.0

    def test_run_returns_none_on_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When git hangs and TimeoutExpired raises, _run returns None."""

        def fake_run(*args: Any, **_kwargs: Any) -> object:  # noqa: ARG001
            raise subprocess.TimeoutExpired(cmd="git", timeout=10.0)

        monkeypatch.setattr(subprocess, "run", fake_run)
        # current_branch returns None when _run returns None.
        assert git_helpers.current_branch() is None


class TestCLocaleEnvOverlay:
    """git subprocess calls must run with ``LC_ALL=C, LANG=C``.

    Regression-fix dogcat-4tl1 added the overlay so localized git
    stderr/stdout doesn't break substring checks like ``"not a git
    repository"``. A refactor that drops the ``env=`` kwarg on the
    underlying ``_run`` would silently re-introduce the bug — this
    fixture pins it down. (dogcat-3ibu)
    """

    def test_repo_root_forwards_c_locale_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``repo_root`` (and every helper through ``_run``) sets LC_ALL=C, LANG=C."""
        captured: dict[str, dict[str, str] | None] = {}

        def fake_run(*_args: Any, **kwargs: Any) -> object:  # noqa: ARG001
            captured["env"] = kwargs.get("env")
            return _completed(0, "/tmp/some-repo\n")

        monkeypatch.setattr(subprocess, "run", fake_run)
        git_helpers.repo_root()

        env = captured["env"]
        assert env is not None, "env was not forwarded to subprocess.run"
        assert env.get("LC_ALL") == "C", (
            f"LC_ALL not forwarded as 'C': {env.get('LC_ALL')!r}"
        )
        assert env.get("LANG") == "C", f"LANG not forwarded as 'C': {env.get('LANG')!r}"

    def test_current_branch_forwards_c_locale_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A second helper through ``_run`` also sees the overlay.

        Two helpers are checked instead of one to catch a refactor that
        passed env to a single helper but not the shared ``_run`` path.
        """
        captured: dict[str, dict[str, str] | None] = {}

        def fake_run(*_args: Any, **kwargs: Any) -> object:  # noqa: ARG001
            captured["env"] = kwargs.get("env")
            return _completed(0, "main\n")

        monkeypatch.setattr(subprocess, "run", fake_run)
        git_helpers.current_branch()

        env = captured["env"]
        assert env is not None
        assert env.get("LC_ALL") == "C"
        assert env.get("LANG") == "C"

    def test_overlay_does_not_drop_caller_environ(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The overlay merges into ``os.environ`` rather than replacing it.

        Without the merge, dropping the rest of the environment (PATH,
        HOME, GIT_*) would break git's ability to find subcommands or
        credentials — a far more disruptive regression than localized
        stderr.
        """
        monkeypatch.setenv("DCAT_TEST_SENTINEL", "preserved")
        captured: dict[str, dict[str, str] | None] = {}

        def fake_run(*_args: Any, **kwargs: Any) -> object:  # noqa: ARG001
            captured["env"] = kwargs.get("env")
            return _completed(0, "")

        monkeypatch.setattr(subprocess, "run", fake_run)
        git_helpers.repo_root()

        env = captured["env"]
        assert env is not None
        assert env.get("DCAT_TEST_SENTINEL") == "preserved"
