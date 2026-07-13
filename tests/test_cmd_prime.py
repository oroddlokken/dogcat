"""Tests for `dcat prime` output paths."""

from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

from dogcat.cli import app
from dogcat.global_config import save_global_config_value

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

runner = CliRunner()


class TestPrimeNoLocalNoGlobal:
    """Tests for testprimenolocalnoglobal."""

    def test_message_when_no_dogcats_and_no_global(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify message when no dogcats and no global."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        repo = tmp_path / "repo"
        repo.mkdir()
        monkeypatch.chdir(repo)

        result = runner.invoke(app, ["prime"])
        assert result.exit_code == 0
        assert "No .dogcats/ found" in result.output


class TestPrimeWithGlobalConfig:
    """Tests for testprimewithglobalconfig."""

    def test_uses_global_when_no_local(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify uses global when no local."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        global_store = tmp_path / "shared" / ".dogcats"
        global_store.mkdir(parents=True)
        save_global_config_value("default_storage", str(global_store))

        repo = tmp_path / "læring"
        repo.mkdir()
        monkeypatch.chdir(repo)

        result = runner.invoke(app, ["prime"])
        assert result.exit_code == 0
        assert "DOGCAT WORKFLOW GUIDE" in result.output

    def test_message_when_global_storage_missing(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """default_storage points to missing dir → message points at fix-up command."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        save_global_config_value("default_storage", str(tmp_path / "missing"))

        repo = tmp_path / "repo"
        repo.mkdir()
        monkeypatch.chdir(repo)

        result = runner.invoke(app, ["prime"])
        assert result.exit_code == 0
        assert "global" in result.output.lower()
        assert "default_storage" in result.output


class TestPrimeGlobalFallbackSection:
    """prime names the active store and namespace in global-fallback mode.

    (dogcat-mbk1) An agent primed in a directory with no visible store
    must learn where its issues actually go and how to opt out.
    """

    def test_names_store_and_namespace(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Fallback mode: guide opens with store path, namespace, overrides."""
        global_store = tmp_path / "shared" / ".dogcats"
        global_store.mkdir(parents=True)
        save_global_config_value("default_storage", str(global_store))

        repo = tmp_path / "myrepo"
        repo.mkdir()
        monkeypatch.chdir(repo)

        result = runner.invoke(app, ["prime"])
        assert result.exit_code == 0
        assert "Active Storage (global fallback)" in result.output
        assert str(global_store.resolve()) in result.output
        assert "Namespace: myrepo" in result.output
        assert "dcat init --use-existing-folder" in result.output

    def test_absent_with_local_store(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A locally resolved store keeps the guide unchanged."""
        global_store = tmp_path / "shared" / ".dogcats"
        global_store.mkdir(parents=True)
        save_global_config_value("default_storage", str(global_store))

        repo = tmp_path / "repo"
        (repo / ".dogcats").mkdir(parents=True)
        monkeypatch.chdir(repo)

        result = runner.invoke(app, ["prime"])
        assert result.exit_code == 0
        assert "Active Storage" not in result.output
