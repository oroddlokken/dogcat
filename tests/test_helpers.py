"""Tests for CLI helper functions."""

from pathlib import Path
from unittest.mock import patch

import pytest

from dogcat.cli._helpers import _find_dogcats_via_worktree, find_dogcats_dir


class TestFindDogcatsViaWorktree:
    """Test the git worktree fallback in _find_dogcats_via_worktree()."""

    def test_finds_dogcats_in_main_worktree(self, tmp_path: Path) -> None:
        """Test finding .dogcats via the main worktree root."""
        # Simulate: main worktree root has .dogcats, and git returns its .git dir
        main_root = tmp_path / "main-repo"
        main_root.mkdir()
        git_dir = main_root / ".git"
        git_dir.mkdir()
        dogcats_dir = main_root / ".dogcats"
        dogcats_dir.mkdir()

        mock_result = type(
            "CompletedProcess",
            (),
            {"returncode": 0, "stdout": str(git_dir) + "\n"},
        )()

        with patch("dogcat.git.subprocess.run", return_value=mock_result):
            result = _find_dogcats_via_worktree()

        assert result == str(dogcats_dir)

    def test_returns_none_when_no_dogcats(self, tmp_path: Path) -> None:
        """Test returns None when main worktree has no .dogcats directory."""
        main_root = tmp_path / "main-repo"
        main_root.mkdir()
        git_dir = main_root / ".git"
        git_dir.mkdir()
        # No .dogcats directory

        mock_result = type(
            "CompletedProcess",
            (),
            {"returncode": 0, "stdout": str(git_dir) + "\n"},
        )()

        with patch("dogcat.git.subprocess.run", return_value=mock_result):
            result = _find_dogcats_via_worktree()

        assert result is None

    def test_returns_none_when_not_in_git_repo(self) -> None:
        """Test returns None when not in a git repository."""
        mock_result = type(
            "CompletedProcess",
            (),
            {"returncode": 128, "stdout": ""},
        )()

        with patch("dogcat.git.subprocess.run", return_value=mock_result):
            result = _find_dogcats_via_worktree()

        assert result is None

    def test_returns_none_when_git_not_installed(self) -> None:
        """Test returns None when git is not installed."""
        with patch(
            "dogcat.git.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            result = _find_dogcats_via_worktree()

        assert result is None

    def test_returns_none_on_os_error(self) -> None:
        """Test returns None on OSError from subprocess."""
        with patch(
            "dogcat.git.subprocess.run",
            side_effect=OSError("permission denied"),
        ):
            result = _find_dogcats_via_worktree()

        assert result is None

    def test_returns_none_when_empty_stdout(self) -> None:
        """Test returns None when git returns empty stdout."""
        mock_result = type(
            "CompletedProcess",
            (),
            {"returncode": 0, "stdout": "  \n"},
        )()

        with patch("dogcat.git.subprocess.run", return_value=mock_result):
            result = _find_dogcats_via_worktree()

        assert result is None


class TestFindDogcatsDirWorktreeFallback:
    """Test that find_dogcats_dir() falls back to worktree check."""

    def test_falls_back_to_worktree_when_no_dogcats_found(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that find_dogcats_dir uses worktree fallback at filesystem root."""
        # Use a directory with no .dogcats anywhere up the tree
        isolated = tmp_path / "isolated"
        isolated.mkdir()
        monkeypatch.chdir(isolated)

        main_root = tmp_path / "main-repo"
        main_root.mkdir()
        git_dir = main_root / ".git"
        git_dir.mkdir()
        dogcats = main_root / ".dogcats"
        dogcats.mkdir()

        mock_result = type(
            "CompletedProcess",
            (),
            {"returncode": 0, "stdout": str(git_dir) + "\n"},
        )()

        with patch("dogcat.git.subprocess.run", return_value=mock_result):
            result = find_dogcats_dir(str(isolated))

        assert result == str(dogcats)

    def test_returns_default_when_worktree_also_fails(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test returns '.dogcats' when worktree fallback also has no .dogcats."""
        isolated = tmp_path / "isolated"
        isolated.mkdir()
        monkeypatch.chdir(isolated)

        mock_result = type(
            "CompletedProcess",
            (),
            {"returncode": 128, "stdout": ""},
        )()

        with patch("dogcat.git.subprocess.run", return_value=mock_result):
            result = find_dogcats_dir(str(isolated))

        assert result == ".dogcats"


class TestRcWalkupBoundary:
    """Walk-up must not trust ancestors above git toplevel / $HOME.

    Regression for dogcat-4107: a planted ``/tmp/.dogcatrc`` could
    silently re-root every dcat command running in a child workspace.
    """

    def test_walkup_stops_at_git_toplevel(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A .dogcatrc above the git toplevel is not picked up."""
        # Set up a fake git repo with no .dogcatrc, and an ancestor
        # .dogcatrc that should be ignored.
        attacker_dir = tmp_path / "attacker_dogcats"
        attacker_dir.mkdir()
        ancestor_rc = tmp_path / ".dogcatrc"
        ancestor_rc.write_text(str(attacker_dir))

        repo = tmp_path / "victim_repo"
        repo.mkdir()
        (repo / ".git").mkdir()  # marks toplevel
        sub = repo / "sub"
        sub.mkdir()
        monkeypatch.chdir(sub)

        # Pretend the git toplevel is the repo dir (so the boundary stops here).
        from dogcat.config import get_rc_walkup_boundary

        # Force the boundary to be the repo root by mocking subprocess
        mock_result = type(
            "CompletedProcess",
            (),
            {"returncode": 0, "stdout": str(repo) + "\n"},
        )()
        with patch("subprocess.run", return_value=mock_result):
            boundary = get_rc_walkup_boundary(sub)
        assert boundary == repo.resolve()

    def test_dcat_rc_walkup_unrestricted_disables_boundary(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Setting DCAT_RC_WALKUP_UNRESTRICTED=1 lets walk-up reach root."""
        from dogcat.config import get_rc_walkup_boundary

        monkeypatch.setenv("DCAT_RC_WALKUP_UNRESTRICTED", "1")
        assert get_rc_walkup_boundary(tmp_path) is None

    def test_warn_if_rc_target_outside_rc_dir(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """An rc target outside its own directory emits a stderr warning."""
        from dogcat.config import warn_if_rc_target_foreign

        rc_dir = tmp_path / "rc_dir"
        rc_dir.mkdir()
        rc = rc_dir / ".dogcatrc"
        rc.write_text("ignored")

        external = tmp_path / "elsewhere"
        external.mkdir()

        warn_if_rc_target_foreign(rc, external)
        err = capsys.readouterr().err
        assert "outside the rc's directory" in err
