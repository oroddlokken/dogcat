"""Tests for Dogcat CLI commands."""

import json
from pathlib import Path

import pytest
from cli_test_helpers import _init_with_namespace, _set_ns_config
from typer.testing import CliRunner

from dogcat.cli import app
from dogcat.config import load_config

runner = CliRunner()


class TestFindDogcatsDirWithRc:
    """Test find_dogcats_dir() with .dogcatrc support."""

    def test_dogcatrc_in_current_dir(
        self,
        tmp_path: Path,
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """find_dogcats_dir() finds .dogcatrc in current directory."""
        from dogcat.cli import find_dogcats_dir
        from dogcat.constants import DOGCATRC_FILENAME

        external_dir = tmp_path / "external" / ".dogcats"
        external_dir.mkdir(parents=True)

        rc_file = tmp_path / DOGCATRC_FILENAME
        rc_file.write_text(str(external_dir) + "\n")

        monkeypatch.chdir(tmp_path)
        result = find_dogcats_dir()
        assert result == str(external_dir)

    def test_dogcatrc_in_parent_dir(
        self,
        tmp_path: Path,
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """find_dogcats_dir() finds .dogcatrc in parent directory."""
        from dogcat.cli import find_dogcats_dir
        from dogcat.constants import DOGCATRC_FILENAME

        external_dir = tmp_path / "external" / ".dogcats"
        external_dir.mkdir(parents=True)

        rc_file = tmp_path / DOGCATRC_FILENAME
        rc_file.write_text(str(external_dir) + "\n")

        child_dir = tmp_path / "subdir"
        child_dir.mkdir()

        monkeypatch.chdir(child_dir)
        result = find_dogcats_dir()
        assert result == str(external_dir)

    def test_dogcatrc_preferred_over_dogcats_dir(
        self,
        tmp_path: Path,
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """find_dogcats_dir() prefers .dogcatrc over .dogcats/ in same directory."""
        from dogcat.cli import find_dogcats_dir
        from dogcat.constants import DOGCATRC_FILENAME

        # Create both .dogcats/ and .dogcatrc pointing elsewhere
        local_dogcats = tmp_path / ".dogcats"
        local_dogcats.mkdir()

        external_dir = tmp_path / "external" / ".dogcats"
        external_dir.mkdir(parents=True)

        rc_file = tmp_path / DOGCATRC_FILENAME
        rc_file.write_text(str(external_dir) + "\n")

        monkeypatch.chdir(tmp_path)
        result = find_dogcats_dir()
        assert result == str(external_dir)

    def test_no_dogcatrc_falls_back_to_dogcats(
        self,
        tmp_path: Path,
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """find_dogcats_dir() falls back to .dogcats/ when no .dogcatrc exists."""
        from dogcat.cli import find_dogcats_dir

        dogcats_dir = tmp_path / ".dogcats"
        dogcats_dir.mkdir()

        monkeypatch.chdir(tmp_path)
        result = find_dogcats_dir()
        assert result == str(dogcats_dir)

    def test_dogcatrc_nonexistent_target_exits(
        self,
        tmp_path: Path,
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """Exits with error when .dogcatrc points to nonexistent dir."""
        from dogcat.cli import find_dogcats_dir
        from dogcat.constants import DOGCATRC_FILENAME

        rc_file = tmp_path / DOGCATRC_FILENAME
        rc_file.write_text("/nonexistent/path/.dogcats\n")

        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit):
            find_dogcats_dir()

    def test_dogcatrc_empty_file_exits(
        self,
        tmp_path: Path,
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """find_dogcats_dir() exits with error when .dogcatrc is empty."""
        from dogcat.cli import find_dogcats_dir
        from dogcat.constants import DOGCATRC_FILENAME

        rc_file = tmp_path / DOGCATRC_FILENAME
        rc_file.write_text("")

        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit):
            find_dogcats_dir()

    def test_dogcatrc_with_relative_path(
        self,
        tmp_path: Path,
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """find_dogcats_dir() resolves relative paths in .dogcatrc."""
        from dogcat.cli import find_dogcats_dir
        from dogcat.constants import DOGCATRC_FILENAME

        external_dir = tmp_path / "external" / ".dogcats"
        external_dir.mkdir(parents=True)

        rc_file = tmp_path / DOGCATRC_FILENAME
        rc_file.write_text("external/.dogcats\n")

        monkeypatch.chdir(tmp_path)
        result = find_dogcats_dir()
        assert result == str(external_dir.resolve())


class TestGetStorageWithDogcatrc:
    """Test get_storage() respects .dogcatrc over local .dogcats/."""

    def test_get_storage_uses_dogcatrc_when_local_dogcats_exists(
        self,
        tmp_path: Path,
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """get_storage() should use .dogcatrc even when local .dogcats/ dir exists."""
        from dogcat.cli._helpers import get_storage
        from dogcat.constants import DOGCATRC_FILENAME

        # Create shared .dogcats with issues
        shared_dir = tmp_path / "shared" / ".dogcats"
        shared_dir.mkdir(parents=True)
        (shared_dir / "issues.jsonl").write_text("")
        (shared_dir / "config.toml").write_text('namespace = "shared"\n')

        # Create repo dir with .dogcatrc + local .dogcats/config.local.toml
        repo_dir = tmp_path / "myrepo"
        repo_dir.mkdir()
        (repo_dir / DOGCATRC_FILENAME).write_text(str(shared_dir) + "\n")

        local_dogcats = repo_dir / ".dogcats"
        local_dogcats.mkdir()
        (local_dogcats / "config.local.toml").write_text(
            'namespace = "myrepo"\nvisible_namespaces = ["myrepo"]\n'
        )

        monkeypatch.chdir(repo_dir)
        storage = get_storage()

        # Storage should point to shared, not local
        assert str(shared_dir) in str(storage.path)


class TestCLIConfig:
    """Test dcat config commands."""

    def test_config_set_and_get(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test setting and getting a config value."""
        monkeypatch.chdir(tmp_path)
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            ["config", "set", "namespace", "myproject"],
        )
        assert result.exit_code == 0
        assert "Set namespace = myproject" in result.stdout

        result = runner.invoke(app, ["config", "get", "namespace"])
        assert result.exit_code == 0
        assert "myproject" in result.stdout

    def test_config_set_bool_true(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test setting a boolean config value to true."""
        monkeypatch.chdir(tmp_path)
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            ["config", "set", "git_tracking", "true"],
        )
        assert result.exit_code == 0
        assert "Set git_tracking = True" in result.stdout

        config = load_config(str(dogcats_dir))
        assert config["git_tracking"] is True

    def test_config_set_bool_false(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test setting a boolean config value to false."""
        monkeypatch.chdir(tmp_path)
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            ["config", "set", "git_tracking", "false"],
        )
        assert result.exit_code == 0
        assert "Set git_tracking = False" in result.stdout

        config = load_config(str(dogcats_dir))
        assert config["git_tracking"] is False

    def test_config_set_bool_invalid(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test setting a boolean key with an invalid value."""
        monkeypatch.chdir(tmp_path)
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            ["config", "set", "git_tracking", "maybe"],
        )
        assert result.exit_code != 0

    def test_config_get_missing_key(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test getting a key that doesn't exist."""
        monkeypatch.chdir(tmp_path)
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(app, ["config", "get", "nonexistent"])
        assert result.exit_code == 1

    def test_config_get_json(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test getting a config value as JSON."""
        monkeypatch.chdir(tmp_path)
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            ["config", "get", "namespace", "--json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "namespace" in data

    def test_config_list(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test listing all config values."""
        monkeypatch.chdir(tmp_path)
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(app, ["config", "list"])
        assert result.exit_code == 0
        assert "namespace" in result.stdout

    def test_config_list_json(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test listing all config values as JSON."""
        monkeypatch.chdir(tmp_path)
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(app, ["config", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "namespace" in data

    def test_config_list_empty(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test listing config when no values are set."""
        monkeypatch.chdir(tmp_path)
        dogcats_dir = tmp_path / ".dogcats"
        dogcats_dir.mkdir(parents=True)
        (dogcats_dir / "issues.jsonl").touch()

        result = runner.invoke(app, ["config", "list"])
        assert result.exit_code == 0
        assert "No configuration values set" in result.stdout


class TestConfigLocal:
    """Test config --local flag and config.local.toml support."""

    def test_config_set_local(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test setting a config value with --local."""
        monkeypatch.chdir(tmp_path)
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            ["config", "set", "inbox_remote", "~/git/inbox", "--local"],
        )
        assert result.exit_code == 0
        assert "(local)" in result.stdout

        from dogcat.config import load_local_config, load_shared_config

        local = load_local_config(str(dogcats_dir))
        assert local["inbox_remote"] == "~/git/inbox"

        shared = load_shared_config(str(dogcats_dir))
        assert "inbox_remote" not in shared

    def test_config_set_local_only_key_auto_redirects(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Setting a local_only key without --local auto-redirects to local."""
        monkeypatch.chdir(tmp_path)
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            ["config", "set", "inbox_remote", "~/git/inbox"],
        )
        assert result.exit_code == 0
        assert "machine-specific" in result.stdout
        assert "(local)" in result.stdout

        from dogcat.config import load_local_config

        local = load_local_config(str(dogcats_dir))
        assert local["inbox_remote"] == "~/git/inbox"

    def test_config_list_shows_local_indicator(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Config list shows (local) for values from config.local.toml."""
        monkeypatch.chdir(tmp_path)
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        runner.invoke(
            app,
            ["config", "set", "inbox_remote", "~/git/inbox", "--local"],
        )

        result = runner.invoke(app, ["config", "list"])
        assert result.exit_code == 0
        assert "inbox_remote = ~/git/inbox (local)" in result.stdout
        # namespace should NOT have (local)
        for line in result.stdout.splitlines():
            if line.startswith("namespace"):
                assert "(local)" not in line

    def test_config_get_reads_local_value(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Config get reads merged values including local."""
        monkeypatch.chdir(tmp_path)
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        runner.invoke(
            app,
            ["config", "set", "inbox_remote", "~/git/inbox", "--local"],
        )

        result = runner.invoke(app, ["config", "get", "inbox_remote"])
        assert result.exit_code == 0
        assert "~/git/inbox" in result.stdout

    def test_config_set_local_warns_when_not_gitignored(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Config set --local warns when config.local.toml is not gitignored."""
        import subprocess

        monkeypatch.chdir(tmp_path)
        subprocess.run(
            ["git", "init"], cwd=str(tmp_path), capture_output=True, check=True
        )

        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        # Remove config.local.toml from .gitignore
        gitignore = tmp_path / ".gitignore"
        if gitignore.exists():
            lines = gitignore.read_text().splitlines()
            lines = [ln for ln in lines if "config.local.toml" not in ln]
            gitignore.write_text("\n".join(lines) + "\n" if lines else "")

        result = runner.invoke(
            app,
            ["config", "set", "inbox_remote", "~/git/inbox", "--local"],
        )
        assert result.exit_code == 0
        output = result.stdout + (result.stderr or "")
        assert "not in .gitignore" in output


class TestConfigArrayKeys:
    """Test config array key handling."""

    def test_set_visible_namespaces_stores_as_list(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Dcat config set visible_namespaces "a,b,c" → stores as list."""
        monkeypatch.chdir(tmp_path)
        dogcats_dir = tmp_path / ".dogcats"
        _init_with_namespace(dogcats_dir, "proj")

        result = runner.invoke(
            app,
            ["config", "set", "visible_namespaces", "a,b,c"],
        )
        assert result.exit_code == 0

        from dogcat.config import load_config

        config = load_config(str(dogcats_dir))
        assert config["visible_namespaces"] == ["a", "b", "c"]

    def test_get_visible_namespaces_displays(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Dcat config get visible_namespaces → displays correctly."""
        monkeypatch.chdir(tmp_path)
        dogcats_dir = tmp_path / ".dogcats"
        _init_with_namespace(dogcats_dir, "proj")
        _set_ns_config(dogcats_dir, "visible_namespaces", ["a", "b"])

        result = runner.invoke(
            app,
            ["config", "get", "visible_namespaces"],
        )
        assert result.exit_code == 0
        assert "a, b" in result.stdout

    def test_config_list_shows_arrays(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Dcat config list → shows array values."""
        monkeypatch.chdir(tmp_path)
        dogcats_dir = tmp_path / ".dogcats"
        _init_with_namespace(dogcats_dir, "proj")
        _set_ns_config(dogcats_dir, "visible_namespaces", ["x", "y"])

        result = runner.invoke(app, ["config", "list"])
        assert result.exit_code == 0
        assert "visible_namespaces = x, y" in result.stdout

    def test_config_list_json_shows_array(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Dcat config list --json → JSON array."""
        monkeypatch.chdir(tmp_path)
        dogcats_dir = tmp_path / ".dogcats"
        _init_with_namespace(dogcats_dir, "proj")
        _set_ns_config(dogcats_dir, "visible_namespaces", ["a", "b"])

        result = runner.invoke(app, ["config", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["visible_namespaces"] == ["a", "b"]


class TestConfigKeys:
    """Test config keys subcommand."""

    def test_config_keys(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Dcat config keys → lists all known keys with descriptions."""
        monkeypatch.chdir(tmp_path)
        dogcats_dir = tmp_path / ".dogcats"
        _init_with_namespace(dogcats_dir, "proj")

        result = runner.invoke(app, ["config", "keys"])
        assert result.exit_code == 0
        for key in (
            "namespace",
            "git_tracking",
            "visible_namespaces",
            "hidden_namespaces",
        ):
            assert key in result.stdout
        assert "Key" in result.stdout
        assert "Type" in result.stdout
        assert "Default" in result.stdout
        assert "Description" in result.stdout

    def test_config_keys_bool_defaults_match_resolution(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Each declared bool default must match what an unset store resolves to.

        `dcat config keys` is the only surface that states a default —
        `dcat config get` errors on an unset key (dogcat-1w21) — so a wrong
        row here is the only thing an operator reads. The
        allow_creating_namespaces row printed `true` while every consumer
        resolved it to False.

        The three bool keys each resolve through their own idiom, and they
        do not agree: git_tracking treats unset as *enabled*. So this pins
        them one at a time rather than assuming a shared rule. (dogcat-2l8k)
        """
        from dogcat.cli._cmd_config import _KNOWN_KEYS

        monkeypatch.chdir(tmp_path)
        dogcats_dir = tmp_path / ".dogcats"
        _init_with_namespace(dogcats_dir, "proj")
        config = load_config(str(dogcats_dir))

        # _cmd_web.py — `config.allow_creating_namespaces is True`
        assert _KNOWN_KEYS["allow_creating_namespaces"]["default"] == (
            config.allow_creating_namespaces is True
        )
        # _cmd_docs.py, `if config.git_tracking is False` — unset means enabled
        assert _KNOWN_KEYS["git_tracking"]["default"] == (
            config.git_tracking if config.git_tracking is not None else True
        )
        # _cmd_read.py — `not config.disable_legend_colors`
        assert _KNOWN_KEYS["disable_legend_colors"]["default"] == bool(
            config.disable_legend_colors
        )

        # And the value actually rendered to the operator.
        result = runner.invoke(app, ["config", "keys", "--json"])
        assert result.exit_code == 0
        assert (
            json.loads(result.stdout)["allow_creating_namespaces"]["default"] is False
        )

    def test_config_keys_json(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Dcat config keys --json → JSON with all known keys."""
        monkeypatch.chdir(tmp_path)
        dogcats_dir = tmp_path / ".dogcats"
        _init_with_namespace(dogcats_dir, "proj")

        result = runner.invoke(app, ["config", "keys", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "namespace" in data
        assert "git_tracking" in data
        assert "visible_namespaces" in data
        assert "hidden_namespaces" in data
        assert data["namespace"]["type"] == "str"
        assert "description" in data["namespace"]
        assert "default" in data["git_tracking"]
        assert "values" in data["git_tracking"]


class TestConfigGlobalFlag:
    """`dcat config --global` writes to the user-global config file."""

    def test_set_global_writes_xdg_file(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify set global writes xdg file."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".dogcats").mkdir()
        monkeypatch.chdir(repo)

        result = runner.invoke(
            app,
            [
                "config",
                "set",
                "--global",
                "default_storage",
                str(tmp_path / "shared" / ".dogcats"),
            ],
        )
        assert result.exit_code == 0, result.output
        cfg_path = tmp_path / "xdg" / "dogcat" / "config.toml"
        assert cfg_path.is_file()
        assert "default_storage" in cfg_path.read_text()

    def test_get_global_reads_xdg_file(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify get global reads xdg file."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".dogcats").mkdir()
        monkeypatch.chdir(repo)

        runner.invoke(
            app,
            ["config", "set", "--global", "default_storage", "/tmp/shared/.dogcats"],
        )
        result = runner.invoke(
            app,
            ["config", "get", "--global", "default_storage"],
        )
        assert result.exit_code == 0
        assert result.output.strip() == "/tmp/shared/.dogcats"

    def test_unset_global(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify unset global."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".dogcats").mkdir()
        monkeypatch.chdir(repo)

        runner.invoke(
            app,
            ["config", "set", "--global", "default_storage", "/tmp/shared/.dogcats"],
        )
        result = runner.invoke(app, ["config", "unset", "--global", "default_storage"])
        assert result.exit_code == 0
        result = runner.invoke(app, ["config", "get", "--global", "default_storage"])
        assert result.exit_code != 0

    def test_list_shows_global_source(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify list shows global source."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".dogcats").mkdir()
        monkeypatch.chdir(repo)

        runner.invoke(
            app,
            ["config", "set", "--global", "default_storage", "/tmp/shared/.dogcats"],
        )
        result = runner.invoke(app, ["config", "list"])
        assert result.exit_code == 0
        assert "(global)" in result.output
        assert "default_storage" in result.output

    def test_set_local_and_global_are_mutually_exclusive(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify set local and global are mutually exclusive."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".dogcats").mkdir()
        monkeypatch.chdir(repo)

        result = runner.invoke(
            app,
            [
                "config",
                "set",
                "--local",
                "--global",
                "default_storage",
                "/tmp/shared/.dogcats",
            ],
        )
        assert result.exit_code == 2
        assert "mutually exclusive" in result.output

    def test_set_global_rejects_non_global_key(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Keys the runtime never reads globally are rejected by set --global."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".dogcats").mkdir()
        monkeypatch.chdir(repo)

        result = runner.invoke(
            app,
            ["config", "set", "--global", "git_tracking", "false"],
        )
        assert result.exit_code == 2
        assert "not a global config key" in result.output
        assert not (tmp_path / "xdg" / "dogcat" / "config.toml").exists()

    def test_set_global_only_key_without_global_flag_errors(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """default_storage in repo config would never be read; refuse to save it."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".dogcats").mkdir()
        monkeypatch.chdir(repo)

        result = runner.invoke(
            app,
            ["config", "set", "default_storage", "/tmp/shared/.dogcats"],
        )
        assert result.exit_code == 2
        assert "--global" in result.output
        assert not (repo / ".dogcats" / "config.toml").exists()

    def test_list_ignores_stray_global_keys(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Keys in the global file that the runtime never reads stay hidden."""
        from dogcat.global_config import get_global_config_path

        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        cfg_path = get_global_config_path()
        cfg_path.parent.mkdir(parents=True)
        cfg_path.write_text('git_tracking = false\nnamespace = "stray"\n')

        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".dogcats").mkdir()
        monkeypatch.chdir(repo)

        result = runner.invoke(app, ["config", "list"])
        assert result.exit_code == 0
        assert "stray" not in result.output
        assert "git_tracking" not in result.output


class TestConfigUnsetLocalShared:
    """`dcat config unset` (without --global) removes keys from local/shared."""

    def test_unset_shared_removes_key(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify unset shared removes key from config.toml."""
        monkeypatch.chdir(tmp_path)
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])
        runner.invoke(app, ["config", "set", "git_tracking", "false"])

        result = runner.invoke(app, ["config", "unset", "git_tracking"])
        assert result.exit_code == 0

        # A known-but-unset key now reports its documented default and
        # says it is unset, rather than erroring like an unknown key.
        # (dogcat-1w21)
        result = runner.invoke(app, ["config", "get", "git_tracking"])
        assert result.exit_code == 0
        assert "true" in result.stdout
        assert "unset" in result.stdout

    def test_unset_local_removes_key(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify unset --local removes key from config.local.toml."""
        monkeypatch.chdir(tmp_path)
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])
        runner.invoke(app, ["config", "set", "--local", "namespace", "mylocal"])

        result = runner.invoke(app, ["config", "unset", "--local", "namespace"])
        assert result.exit_code == 0

        local_file = dogcats_dir / "config.local.toml"
        if local_file.exists():
            assert "mylocal" not in local_file.read_text()


class TestConfigGetUnsetKnownKey:
    """`dcat config get` on a known-but-unset key reports its default.

    It used to exit 1 with "not found in config", treating a documented
    key the same as a typo — which left `dcat config keys` as the only
    surface stating a default. (dogcat-1w21)
    """

    def test_unset_known_key_reports_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Exit 0, print the default, and mark it unset."""
        monkeypatch.chdir(tmp_path)
        _init_with_namespace(tmp_path / ".dogcats", "proj")

        result = runner.invoke(app, ["config", "get", "allow_creating_namespaces"])
        assert result.exit_code == 0
        assert "false" in result.stdout
        assert "unset" in result.stdout

    def test_unset_known_key_json_marks_it_unset(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--json distinguishes "unset, default X" from "set to X"."""
        monkeypatch.chdir(tmp_path)
        _init_with_namespace(tmp_path / ".dogcats", "proj")

        result = runner.invoke(
            app, ["config", "get", "allow_creating_namespaces", "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["set"] is False
        assert data["default"] == "false"
        assert data["allow_creating_namespaces"] is None

    def test_unknown_key_still_errors(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A typo must not silently succeed."""
        monkeypatch.chdir(tmp_path)
        _init_with_namespace(tmp_path / ".dogcats", "proj")

        result = runner.invoke(app, ["config", "get", "no_such_key"])
        assert result.exit_code != 0
