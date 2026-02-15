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
