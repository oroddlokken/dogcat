"""Tests for the top-level ``-C`` / ``--repo`` option."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from dogcat.cli import app

if TYPE_CHECKING:
    import pytest

runner = CliRunner()


class TestRepoOption:
    """``dcat -C <path>`` mirrors ``git -C`` by chdir'ing before dispatch."""

    def test_repo_short_flag_chdirs_for_discovery(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``-C`` lets dcat find ``.dogcats/`` outside the current cwd."""
        repo = tmp_path / "repo"
        repo.mkdir()
        runner.invoke(app, ["init", "--dogcats-dir", str(repo / ".dogcats")])

        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)

        result = runner.invoke(app, ["-C", str(repo), "status"])
        assert result.exit_code == 0, result.stdout
        assert "Total issues" in result.stdout

    def test_repo_long_flag(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``--repo`` is the long form of ``-C``."""
        repo = tmp_path / "repo"
        repo.mkdir()
        runner.invoke(app, ["init", "--dogcats-dir", str(repo / ".dogcats")])
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["--repo", str(repo), "status"])
        assert result.exit_code == 0, result.stdout

    def test_repo_missing_path_errors(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A non-existent ``-C`` path fails with a clear message."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["-C", str(tmp_path / "nope"), "status"])
        assert result.exit_code == 1
        assert "does not exist" in (result.stderr or result.output)

    def test_repo_not_a_directory_errors(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A file (not a directory) passed to ``-C`` fails."""
        file_path = tmp_path / "afile"
        file_path.write_text("hello")
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["-C", str(file_path), "status"])
        assert result.exit_code == 1
        assert "not a directory" in (result.stderr or result.output)

    def test_repo_expands_user_home(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``~`` in the ``-C`` path is expanded against ``$HOME``."""
        repo = tmp_path / "repo"
        repo.mkdir()
        runner.invoke(app, ["init", "--dogcats-dir", str(repo / ".dogcats")])

        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["-C", "~/repo", "status"])
        assert result.exit_code == 0, result.stdout

    def test_repo_changes_process_cwd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``-C`` chdirs the process so later relative lookups resolve there."""
        repo = tmp_path / "repo"
        repo.mkdir()
        runner.invoke(app, ["init", "--dogcats-dir", str(repo / ".dogcats")])

        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)

        runner.invoke(app, ["-C", str(repo), "status"])
        assert Path.cwd().resolve() == repo.resolve()
