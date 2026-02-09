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

        with patch("dogcat.cli._helpers.subprocess.run", return_value=mock_result):
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

        with patch("dogcat.cli._helpers.subprocess.run", return_value=mock_result):
            result = _find_dogcats_via_worktree()

        assert result is None

    def test_returns_none_when_not_in_git_repo(self) -> None:
        """Test returns None when not in a git repository."""
        mock_result = type(
            "CompletedProcess",
            (),
            {"returncode": 128, "stdout": ""},
        )()

        with patch("dogcat.cli._helpers.subprocess.run", return_value=mock_result):
            result = _find_dogcats_via_worktree()

        assert result is None

    def test_returns_none_when_git_not_installed(self) -> None:
        """Test returns None when git is not installed."""
        with patch(
            "dogcat.cli._helpers.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            result = _find_dogcats_via_worktree()

        assert result is None

    def test_returns_none_on_os_error(self) -> None:
        """Test returns None on OSError from subprocess."""
        with patch(
            "dogcat.cli._helpers.subprocess.run",
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

        with patch("dogcat.cli._helpers.subprocess.run", return_value=mock_result):
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

        with patch("dogcat.cli._helpers.subprocess.run", return_value=mock_result):
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

        with patch("dogcat.cli._helpers.subprocess.run", return_value=mock_result):
            result = find_dogcats_dir(str(isolated))

        assert result == ".dogcats"
