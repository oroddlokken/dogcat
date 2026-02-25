"""Tests for Dogcat CLI commands."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dogcat.cli import app
from dogcat.config import load_config

runner = CliRunner()


class TestCLIInit:
    """Test init command."""

    def test_init_creates_directory(self, tmp_path: Path) -> None:
        """Test that init creates .dogcats directory."""
        dogcats_dir = tmp_path / ".dogcats"
        result = runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert dogcats_dir.exists()
        assert (dogcats_dir / "issues.jsonl").exists()

    def test_init_output(self, tmp_path: Path) -> None:
        """Test init output."""
        dogcats_dir = tmp_path / ".dogcats"
        result = runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )
        assert "Dogcat repository initialized" in result.stdout

    def test_init_adds_gitignore_entries(
        self,
        tmp_path: Path,
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """Init adds config.local.toml and .issues.lock to .gitignore."""
        monkeypatch.chdir(tmp_path)
        dogcats_dir = tmp_path / ".dogcats"

        result = runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0

        gitignore = tmp_path / ".gitignore"
        assert gitignore.exists()
        content = gitignore.read_text()
        assert ".dogcats/config.local.toml" in content
        assert ".dogcats/.issues.lock" in content


class TestCLIInitPrefix:
    """Test init command with --prefix flag."""

    def test_init_with_explicit_prefix(self, tmp_path: Path) -> None:
        """Test init with --prefix flag sets the prefix."""
        dogcats_dir = tmp_path / ".dogcats"
        result = runner.invoke(
            app,
            [
                "init",
                "--namespace",
                "myapp",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Set namespace: myapp" in result.stdout
        assert "myapp-<hash>" in result.stdout

    def test_init_creates_config_file(self, tmp_path: Path) -> None:
        """Test init creates config.toml with prefix."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            [
                "init",
                "--namespace",
                "testprefix",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        config_file = dogcats_dir / "config.toml"
        assert config_file.exists()
        content = config_file.read_text()
        assert "namespace" in content
        assert "testprefix" in content

    def test_init_auto_detects_prefix_from_directory(self, tmp_path: Path) -> None:
        """Test init auto-detects prefix from parent directory name."""
        project_dir = tmp_path / "my-cool-project"
        project_dir.mkdir()
        dogcats_dir = project_dir / ".dogcats"

        result = runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Set namespace: my-cool-project" in result.stdout

    def test_init_prefix_strips_trailing_hyphens(self, tmp_path: Path) -> None:
        """Test init strips trailing hyphens from prefix."""
        dogcats_dir = tmp_path / ".dogcats"
        result = runner.invoke(
            app,
            [
                "init",
                "--namespace",
                "myapp-",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Set namespace: myapp" in result.stdout

    def test_create_uses_config_prefix(self, tmp_path: Path) -> None:
        """Test that create uses prefix from config."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            [
                "init",
                "--namespace",
                "custom",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["create", "Test issue", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "custom-" in result.stdout

    def test_create_uses_directory_prefix_when_no_config(self, tmp_path: Path) -> None:
        """Test that create uses directory-detected prefix when no config."""
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()
        dogcats_dir = project_dir / ".dogcats"

        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["create", "Test issue", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "myproject-" in result.stdout

    def test_multiple_creates_use_same_prefix(self, tmp_path: Path) -> None:
        """Test that multiple creates use consistent prefix."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            [
                "init",
                "--namespace",
                "proj",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result1 = runner.invoke(
            app,
            ["create", "Issue 1", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        result2 = runner.invoke(
            app,
            ["create", "Issue 2", "--json", "--dogcats-dir", str(dogcats_dir)],
        )

        issue1 = json.loads(result1.stdout)
        issue2 = json.loads(result2.stdout)

        assert issue1["namespace"] == "proj"
        assert issue2["namespace"] == "proj"


class TestCLIInitWithDir:
    """Test init --dir command for .dogcatrc support."""

    def test_init_with_dir_creates_dogcatrc(
        self,
        tmp_path: Path,
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """Init --dir creates .dogcatrc file in current directory."""
        from dogcat.constants import DOGCATRC_FILENAME

        monkeypatch.chdir(tmp_path)
        external_dir = tmp_path / "external" / ".dogcats"

        result = runner.invoke(
            app,
            ["init", "--dir", str(external_dir)],
        )
        assert result.exit_code == 0

        rc_file = tmp_path / DOGCATRC_FILENAME
        assert rc_file.exists()
        assert str(external_dir) in rc_file.read_text()

    def test_init_with_dir_creates_external_directory(
        self,
        tmp_path: Path,
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """Init --dir creates the .dogcats directory at the external path."""
        monkeypatch.chdir(tmp_path)
        external_dir = tmp_path / "external" / ".dogcats"

        result = runner.invoke(
            app,
            ["init", "--dir", str(external_dir)],
        )
        assert result.exit_code == 0
        assert external_dir.exists()
        assert (external_dir / "issues.jsonl").exists()


class TestCLIInitUseExistingFolder:
    """Test init --use-existing-folder command."""

    def test_creates_dogcatrc_for_existing_dir(
        self,
        tmp_path: Path,
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """Creates .dogcatrc pointing to an existing .dogcats directory."""
        from dogcat.constants import DOGCATRC_FILENAME

        # Set up an existing .dogcats directory
        existing = tmp_path / "shared" / ".dogcats"
        existing.mkdir(parents=True)
        (existing / "issues.jsonl").touch()

        project = tmp_path / "myproject"
        project.mkdir()
        monkeypatch.chdir(project)

        result = runner.invoke(
            app,
            ["init", "--use-existing-folder", str(existing)],
        )
        assert result.exit_code == 0
        assert "Linked to existing" in result.stdout

        rc_file = project / DOGCATRC_FILENAME
        assert rc_file.exists()
        assert str(existing) in rc_file.read_text()

    def test_does_not_reinitialize(
        self,
        tmp_path: Path,
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """Does not modify the existing .dogcats directory."""
        existing = tmp_path / "shared" / ".dogcats"
        existing.mkdir(parents=True)
        issues = existing / "issues.jsonl"
        issues.write_text('{"id": "test-abc", "title": "Existing"}\n')

        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            app,
            ["init", "--use-existing-folder", str(existing)],
        )
        assert result.exit_code == 0
        # Original content preserved
        assert "Existing" in issues.read_text()

    def test_errors_on_nonexistent_dir(
        self,
        tmp_path: Path,
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """Errors when the specified directory doesn't exist."""
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            app,
            ["init", "--use-existing-folder", "/nonexistent/path"],
        )
        assert result.exit_code != 0
        assert "does not exist" in result.output

    def test_errors_on_invalid_dogcat_dir(
        self,
        tmp_path: Path,
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """Errors when directory exists but is not a valid dogcat dir."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            app,
            ["init", "--use-existing-folder", str(empty_dir)],
        )
        assert result.exit_code != 0
        assert "missing issues.jsonl" in result.output

    def test_mutually_exclusive_with_dir(
        self,
        tmp_path: Path,
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """--dir and --use-existing-folder are mutually exclusive."""
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            app,
            [
                "init",
                "--dir",
                "/some/path",
                "--use-existing-folder",
                "/other/path",
            ],
        )
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output


class TestCLIInitNoGit:
    """Test dcat init --no-git flag."""

    def test_init_no_git_sets_config(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--no-git sets git_tracking=false in config."""
        monkeypatch.chdir(tmp_path)
        dogcats_dir = tmp_path / ".dogcats"

        result = runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir), "--no-git"],
        )
        assert result.exit_code == 0
        assert (
            "git_tracking = false" in result.stdout.lower()
            or "Disabled git tracking" in result.stdout
        )

        config = load_config(str(dogcats_dir))
        assert config["git_tracking"] is False

    def test_init_no_git_creates_gitignore(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--no-git creates .gitignore with .dogcats/ entry."""
        monkeypatch.chdir(tmp_path)
        dogcats_dir = tmp_path / ".dogcats"

        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir), "--no-git"],
        )

        gitignore = tmp_path / ".gitignore"
        assert gitignore.exists()
        assert ".dogcats/" in gitignore.read_text()

    def test_init_no_git_appends_to_existing_gitignore(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--no-git appends to existing .gitignore without overwriting."""
        monkeypatch.chdir(tmp_path)
        dogcats_dir = tmp_path / ".dogcats"
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.pyc\n")

        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir), "--no-git"],
        )

        content = gitignore.read_text()
        assert "*.pyc" in content
        assert ".dogcats/" in content

    def test_init_no_git_skips_if_already_in_gitignore(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--no-git skips if .dogcats/ is already in .gitignore."""
        monkeypatch.chdir(tmp_path)
        dogcats_dir = tmp_path / ".dogcats"
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text(".dogcats/\n")

        result = runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir), "--no-git"],
        )
        assert result.exit_code == 0
        assert "already in .gitignore" in result.stdout
