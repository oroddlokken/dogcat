"""Tests for global dogcat config (~/.config/dogcat/config.toml)."""

from __future__ import annotations

from pathlib import Path

import pytest

from dogcat.global_config import (
    GlobalConfig,
    get_global_config_path,
    load_global_config,
)


class TestGlobalConfigPath:
    """Tests for testglobalconfigpath."""

    def test_uses_xdg_config_home_when_set(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify uses xdg config home when set."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        assert get_global_config_path() == tmp_path / "dogcat" / "config.toml"

    def test_falls_back_to_home_dot_config(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify falls back to home dot config."""
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        assert (
            get_global_config_path() == tmp_path / ".config" / "dogcat" / "config.toml"
        )


class TestLoadGlobalConfig:
    """Tests for testloadglobalconfig."""

    def test_returns_empty_when_no_file(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify returns empty when no file."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        cfg = load_global_config()
        assert cfg.default_storage is None
        assert cfg.visible_namespaces == []

    def test_reads_all_fields(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify reads all fields."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        path = tmp_path / "dogcat" / "config.toml"
        path.parent.mkdir(parents=True)
        path.write_text(
            'default_storage = "/tmp/shared/.dogcats"\n'
            'visible_namespaces = ["misc", "foo"]\n'
        )
        cfg = load_global_config()
        assert cfg.default_storage == Path("/tmp/shared/.dogcats")
        assert cfg.visible_namespaces == ["misc", "foo"]

    def test_expands_tilde_in_default_storage(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify expands tilde in default storage."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        monkeypatch.setenv("HOME", "/home/testuser")
        path = tmp_path / "dogcat" / "config.toml"
        path.parent.mkdir(parents=True)
        path.write_text('default_storage = "~/dev/issues/.dogcats"\n')
        cfg = load_global_config()
        assert cfg.default_storage == Path("/home/testuser/dev/issues/.dogcats")

    def test_expands_env_vars_in_default_storage(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify expands env vars in default storage."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        monkeypatch.setenv("MY_DOGCATS", "/var/dogcats")
        path = tmp_path / "dogcat" / "config.toml"
        path.parent.mkdir(parents=True)
        path.write_text('default_storage = "$MY_DOGCATS/.dogcats"\n')
        cfg = load_global_config()
        assert cfg.default_storage == Path("/var/dogcats/.dogcats")

    def test_malformed_toml_returns_empty(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify malformed toml returns empty."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        path = tmp_path / "dogcat" / "config.toml"
        path.parent.mkdir(parents=True)
        path.write_text("this is not [[ valid toml")
        cfg = load_global_config()
        assert cfg.default_storage is None

    def test_non_string_default_storage_is_ignored(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A non-string default_storage in TOML is ignored, not crashed on."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        path = tmp_path / "dogcat" / "config.toml"
        path.parent.mkdir(parents=True)
        path.write_text("default_storage = 42\n")
        cfg = load_global_config()
        assert cfg.default_storage is None


class TestGlobalConfigDataclass:
    """Tests for testglobalconfigdataclass."""

    def test_defaults(self) -> None:
        """Verify defaults."""
        cfg = GlobalConfig()
        assert cfg.default_storage is None
        assert cfg.visible_namespaces == []


class TestSaveGlobalConfigValue:
    """Tests for testsaveglobalconfigvalue."""

    def test_creates_dir_and_file_if_missing(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify creates dir and file if missing."""
        from dogcat.global_config import save_global_config_value

        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        save_global_config_value("default_storage", "/tmp/shared/.dogcats")
        path = tmp_path / "dogcat" / "config.toml"
        assert path.is_file()
        content = path.read_text()
        assert 'default_storage = "/tmp/shared/.dogcats"' in content

    def test_updates_existing_value(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify updates existing value."""
        from dogcat.global_config import save_global_config_value

        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        save_global_config_value("default_storage", "/old/.dogcats")
        save_global_config_value("default_storage", "/new/.dogcats")
        cfg = load_global_config()
        assert cfg.default_storage == Path("/new/.dogcats")

    def test_preserves_other_keys(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify preserves other keys."""
        from dogcat.global_config import save_global_config_value

        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        save_global_config_value("default_storage", "/foo/.dogcats")
        save_global_config_value("visible_namespaces", ["foo"])
        cfg = load_global_config()
        assert cfg.default_storage == Path("/foo/.dogcats")
        assert cfg.visible_namespaces == ["foo"]

    def test_save_list_value(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify save list value."""
        from dogcat.global_config import save_global_config_value

        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        save_global_config_value("visible_namespaces", ["a", "b"])
        cfg = load_global_config()
        assert cfg.visible_namespaces == ["a", "b"]


class TestUnsetGlobalConfigValue:
    """Tests for testunsetglobalconfigvalue."""

    def test_removes_key(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify removes key."""
        from dogcat.global_config import (
            save_global_config_value,
            unset_global_config_value,
        )

        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        save_global_config_value("default_storage", "/foo/.dogcats")
        save_global_config_value("visible_namespaces", ["misc"])
        unset_global_config_value("default_storage")
        cfg = load_global_config()
        assert cfg.default_storage is None
        assert cfg.visible_namespaces == ["misc"]

    def test_unset_missing_key_is_noop(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify unset missing key is noop."""
        from dogcat.global_config import unset_global_config_value

        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        unset_global_config_value("default_storage")
        assert load_global_config().default_storage is None


class TestSaveGlobalConfigPermissionError:
    """save_global_config_value handles a non-writable directory."""

    def test_readonly_dir_raises_oserror(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Read-only XDG dir surfaces PermissionError, not a cryptic traceback."""
        from dogcat.global_config import save_global_config_value

        xdg = tmp_path / "xdg"
        xdg.mkdir()
        xdg.chmod(0o500)

        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
        try:
            with pytest.raises(PermissionError):
                save_global_config_value("default_storage", "/foo/.dogcats")
        finally:
            xdg.chmod(0o700)
