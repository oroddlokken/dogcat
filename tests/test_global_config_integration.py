"""End-to-end tests for global config fallback in storage resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

from dogcat.cli import find_dogcats_dir
from dogcat.global_config import save_global_config_value

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

runner = CliRunner()


def _isolate_global_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Point XDG_CONFIG_HOME at tmp_path so global config writes are sandboxed."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))


class TestGlobalConfigStorageFallback:
    """Tests for testglobalconfigstoragefallback."""

    def test_local_dogcats_wins_over_global(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A local .dogcats/ in cwd is preferred over global default_storage."""
        _isolate_global_config(tmp_path, monkeypatch)

        global_store = tmp_path / "shared" / ".dogcats"
        global_store.mkdir(parents=True)
        save_global_config_value("default_storage", str(global_store))

        repo = tmp_path / "repo"
        local_store = repo / ".dogcats"
        local_store.mkdir(parents=True)

        monkeypatch.chdir(repo)
        assert find_dogcats_dir() == str(local_store)

    def test_rc_wins_over_global(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A walk-up .dogcatrc is preferred over global default_storage."""
        from dogcat.constants import DOGCATRC_FILENAME

        _isolate_global_config(tmp_path, monkeypatch)

        global_store = tmp_path / "global" / ".dogcats"
        global_store.mkdir(parents=True)
        save_global_config_value("default_storage", str(global_store))

        rc_target = tmp_path / "rc" / ".dogcats"
        rc_target.mkdir(parents=True)
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / DOGCATRC_FILENAME).write_text(str(rc_target) + "\n")

        monkeypatch.chdir(repo)
        assert find_dogcats_dir() == str(rc_target)

    def test_global_used_when_nothing_local(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """No local .dogcats and no .dogcatrc → fall back to global default_storage."""
        _isolate_global_config(tmp_path, monkeypatch)

        global_store = tmp_path / "shared" / ".dogcats"
        global_store.mkdir(parents=True)
        save_global_config_value("default_storage", str(global_store))

        repo = tmp_path / "repo"
        repo.mkdir()
        monkeypatch.chdir(repo)

        assert find_dogcats_dir() == str(global_store)

    def test_global_ignored_when_path_does_not_exist(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """default_storage points to missing dir → fall through to .dogcats default."""
        _isolate_global_config(tmp_path, monkeypatch)
        save_global_config_value("default_storage", str(tmp_path / "does-not-exist"))

        repo = tmp_path / "repo"
        repo.mkdir()
        monkeypatch.chdir(repo)
        assert find_dogcats_dir() == ".dogcats"

    def test_global_ignored_when_path_is_a_file(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """default_storage points to a regular file, fall through to .dogcats."""
        _isolate_global_config(tmp_path, monkeypatch)
        not_a_dir = tmp_path / "shared-as-file"
        not_a_dir.write_text("not a directory")
        save_global_config_value("default_storage", str(not_a_dir))

        repo = tmp_path / "repo"
        repo.mkdir()
        monkeypatch.chdir(repo)
        assert find_dogcats_dir() == ".dogcats"

    def test_no_global_config_is_unchanged(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When no global config file exists, behavior matches current dcat."""
        _isolate_global_config(tmp_path, monkeypatch)
        repo = tmp_path / "repo"
        repo.mkdir()
        monkeypatch.chdir(repo)
        assert find_dogcats_dir() == ".dogcats"


class TestGlobalConfigNamespace:
    """Tests for testglobalconfignamespace."""

    def test_namespace_uses_cwd_dir_slug(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """In global-store mode, namespace is the slug of the cwd folder name."""
        from dogcat.config import get_issue_prefix

        _isolate_global_config(tmp_path, monkeypatch)
        global_store = tmp_path / "shared" / ".dogcats"
        global_store.mkdir(parents=True)
        save_global_config_value("default_storage", str(global_store))

        repo = tmp_path / "læring"
        repo.mkdir()
        monkeypatch.chdir(repo)

        assert get_issue_prefix(str(global_store)) == "laering"

    def test_local_config_overrides_cwd_slug(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A repo-local config.local.toml namespace wins over cwd slug."""
        from dogcat.config import get_issue_prefix
        from dogcat.constants import DOGCATRC_FILENAME

        _isolate_global_config(tmp_path, monkeypatch)
        global_store = tmp_path / "shared" / ".dogcats"
        global_store.mkdir(parents=True)
        (global_store / "config.toml").write_text('namespace = "shared"\n')
        save_global_config_value("default_storage", str(global_store))

        repo = tmp_path / "læring"
        repo.mkdir()
        (repo / DOGCATRC_FILENAME).write_text(str(global_store) + "\n")
        (repo / ".dogcats").mkdir()
        (repo / ".dogcats" / "config.local.toml").write_text('namespace = "custom"\n')

        monkeypatch.chdir(repo)
        assert get_issue_prefix(str(global_store)) == "custom"

    def test_cwd_slug_beats_shared_store_config_namespace(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Shared store's own namespace must not leak into cwd-derived mode."""
        from dogcat.config import get_issue_prefix

        _isolate_global_config(tmp_path, monkeypatch)
        global_store = tmp_path / "shared" / ".dogcats"
        global_store.mkdir(parents=True)
        (global_store / "config.toml").write_text('namespace = "shared"\n')
        save_global_config_value("default_storage", str(global_store))

        repo = tmp_path / "læring"
        repo.mkdir()
        monkeypatch.chdir(repo)

        assert get_issue_prefix(str(global_store)) == "laering"

    def test_unsluggable_cwd_falls_back_to_shared_store_namespace(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When cwd is not sluggable, fall through to the shared store's namespace."""
        from dogcat.config import get_issue_prefix

        _isolate_global_config(tmp_path, monkeypatch)
        global_store = tmp_path / "shared" / ".dogcats"
        global_store.mkdir(parents=True)
        (global_store / "config.toml").write_text('namespace = "shared"\n')
        save_global_config_value("default_storage", str(global_store))

        repo = tmp_path / "测试"
        repo.mkdir()
        monkeypatch.chdir(repo)

        assert get_issue_prefix(str(global_store)) == "shared"
