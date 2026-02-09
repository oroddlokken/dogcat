"""Tests for config module."""

from pathlib import Path

import pytest

from dogcat.config import (
    CONFIG_FILENAME,
    DEFAULT_PREFIX,
    _detect_prefix_from_directory,
    _detect_prefix_from_issues,
    extract_prefix,
    get_config_path,
    get_issue_prefix,
    load_config,
    parse_dogcatrc,
    save_config,
    set_issue_prefix,
)
from dogcat.constants import DOGCATRC_FILENAME


class TestExtractPrefix:
    """Tests for extract_prefix function."""

    def test_extract_simple_prefix(self) -> None:
        """Extract prefix from standard issue ID."""
        assert extract_prefix("search-8qx") == "search"

    def test_extract_prefix_with_numbers(self) -> None:
        """Extract prefix containing numbers."""
        assert extract_prefix("proj123-abc") == "proj123"

    def test_extract_multi_hyphen_prefix(self) -> None:
        """Extract prefix with multiple hyphens (before last hyphen)."""
        assert extract_prefix("my-cool-project-xyz") == "my-cool-project"

    def test_extract_prefix_no_hyphen(self) -> None:
        """Return None if no hyphen in ID."""
        assert extract_prefix("nohyphen") is None

    def test_extract_prefix_empty_string(self) -> None:
        """Return None for empty string."""
        assert extract_prefix("") is None

    def test_extract_prefix_single_char_prefix(self) -> None:
        """Extract single character prefix."""
        assert extract_prefix("x-123") == "x"

    def test_extract_prefix_long_hash(self) -> None:
        """Extract prefix with longer hash portion."""
        assert extract_prefix("myapp-a1b2c3d4") == "myapp"

    def test_extract_prefix_hyphen_only(self) -> None:
        """Return None for hyphen-only string."""
        assert extract_prefix("-") is None

    def test_extract_prefix_trailing_hyphen(self) -> None:
        """Handle trailing hyphen."""
        assert extract_prefix("prefix-") == "prefix"

    def test_extract_prefix_leading_hyphen(self) -> None:
        """Handle leading hyphen."""
        assert extract_prefix("-suffix") is None  # Empty prefix before hyphen


class TestGetConfigPath:
    """Tests for get_config_path function."""

    def test_returns_path_object(self, tmp_path: Path) -> None:
        """Returns a Path object."""
        result = get_config_path(str(tmp_path))
        assert isinstance(result, Path)

    def test_appends_config_filename(self, tmp_path: Path) -> None:
        """Appends config filename to directory."""
        result = get_config_path(str(tmp_path))
        assert result == tmp_path / CONFIG_FILENAME

    def test_handles_trailing_slash(self, tmp_path: Path) -> None:
        """Handles directory with trailing slash."""
        result = get_config_path(str(tmp_path) + "/")
        assert result.name == CONFIG_FILENAME


class TestLoadSaveConfig:
    """Tests for load_config and save_config functions."""

    def test_load_nonexistent_config(self, tmp_path: Path) -> None:
        """Loading nonexistent config returns empty dict."""
        config = load_config(str(tmp_path / ".dogcats"))
        assert config == {}

    def test_save_and_load_config(self, tmp_path: Path) -> None:
        """Save and load config roundtrip."""
        dogcats_dir = tmp_path / ".dogcats"
        dogcats_dir.mkdir()

        config = {"issue_prefix": "myproject", "other": "value"}
        save_config(str(dogcats_dir), config)

        loaded = load_config(str(dogcats_dir))
        assert loaded == config

    def test_save_creates_directory(self, tmp_path: Path) -> None:
        """Save creates directory if it doesn't exist."""
        dogcats_dir = tmp_path / ".dogcats"
        assert not dogcats_dir.exists()

        save_config(str(dogcats_dir), {"issue_prefix": "test"})

        assert dogcats_dir.exists()
        assert (dogcats_dir / CONFIG_FILENAME).exists()

    def test_save_creates_nested_directory(self, tmp_path: Path) -> None:
        """Save creates nested directories if needed."""
        dogcats_dir = tmp_path / "a" / "b" / ".dogcats"
        assert not dogcats_dir.exists()

        save_config(str(dogcats_dir), {"issue_prefix": "test"})

        assert dogcats_dir.exists()

    def test_load_empty_config_file(self, tmp_path: Path) -> None:
        """Loading empty config file returns empty dict."""
        dogcats_dir = tmp_path / ".dogcats"
        dogcats_dir.mkdir()
        (dogcats_dir / CONFIG_FILENAME).write_text("")

        config = load_config(str(dogcats_dir))
        assert config == {}

    def test_load_invalid_toml(self, tmp_path: Path) -> None:
        """Loading invalid TOML returns empty dict."""
        dogcats_dir = tmp_path / ".dogcats"
        dogcats_dir.mkdir()
        (dogcats_dir / CONFIG_FILENAME).write_text("this is [not valid toml")

        config = load_config(str(dogcats_dir))
        assert config == {}

    def test_save_overwrites_existing(self, tmp_path: Path) -> None:
        """Save overwrites existing config file."""
        dogcats_dir = tmp_path / ".dogcats"
        dogcats_dir.mkdir()

        save_config(str(dogcats_dir), {"issue_prefix": "first"})
        save_config(str(dogcats_dir), {"issue_prefix": "second"})

        loaded = load_config(str(dogcats_dir))
        assert loaded["issue_prefix"] == "second"

    def test_save_preserves_other_keys(self, tmp_path: Path) -> None:
        """Save preserves other configuration keys."""
        dogcats_dir = tmp_path / ".dogcats"
        dogcats_dir.mkdir()

        config = {
            "issue_prefix": "myapp",
            "custom_setting": "value",
            "nested": {"key": "value"},
        }
        save_config(str(dogcats_dir), config)

        loaded = load_config(str(dogcats_dir))
        assert loaded == config

    def test_config_file_is_valid_toml(self, tmp_path: Path) -> None:
        """Saved config file is valid TOML."""
        import sys

        if sys.version_info >= (3, 11):
            import tomllib
        else:
            import tomli as tomllib

        dogcats_dir = tmp_path / ".dogcats"
        dogcats_dir.mkdir()

        save_config(str(dogcats_dir), {"issue_prefix": "test"})

        # Should not raise
        with (dogcats_dir / CONFIG_FILENAME).open("rb") as f:
            parsed = tomllib.load(f)
        assert parsed["issue_prefix"] == "test"


class TestSetGetIssuePrefix:
    """Tests for set_issue_prefix and get_issue_prefix functions."""

    def test_set_and_get_prefix(self, tmp_path: Path) -> None:
        """Set and get prefix roundtrip."""
        dogcats_dir = tmp_path / ".dogcats"
        dogcats_dir.mkdir()

        set_issue_prefix(str(dogcats_dir), "myprefix")
        assert get_issue_prefix(str(dogcats_dir)) == "myprefix"

    def test_set_prefix_creates_config(self, tmp_path: Path) -> None:
        """Setting prefix creates config file if needed."""
        dogcats_dir = tmp_path / ".dogcats"
        dogcats_dir.mkdir()

        set_issue_prefix(str(dogcats_dir), "newprefix")

        assert (dogcats_dir / CONFIG_FILENAME).exists()

    def test_set_prefix_preserves_other_config(self, tmp_path: Path) -> None:
        """Setting prefix preserves other config values."""
        dogcats_dir = tmp_path / ".dogcats"
        dogcats_dir.mkdir()

        # Save initial config with extra key
        save_config(str(dogcats_dir), {"issue_prefix": "old", "other_key": "value"})

        # Update just the prefix
        set_issue_prefix(str(dogcats_dir), "new")

        loaded = load_config(str(dogcats_dir))
        assert loaded["issue_prefix"] == "new"
        assert loaded["other_key"] == "value"

    def test_get_prefix_no_config(self, tmp_path: Path) -> None:
        """Get prefix without config falls back to directory name detection."""
        dogcats_dir = tmp_path / ".dogcats"
        dogcats_dir.mkdir()

        # Should detect from parent directory name
        prefix = get_issue_prefix(str(dogcats_dir))
        # The prefix should be the tmp directory name (sanitized)
        assert prefix is not None
        assert len(prefix) > 0

    def test_get_prefix_returns_default_for_root(self, tmp_path: Path) -> None:
        """Get prefix returns default if directory name detection fails."""
        # Create a .dogcats in a directory with an unusable name
        dogcats_dir = tmp_path / "---" / ".dogcats"
        dogcats_dir.mkdir(parents=True)

        prefix = get_issue_prefix(str(dogcats_dir))
        # Should fall back to default since "---" sanitizes to empty
        assert prefix == DEFAULT_PREFIX

    def test_get_prefix_config_takes_precedence(self, tmp_path: Path) -> None:
        """Config prefix takes precedence over auto-detection."""
        dogcats_dir = tmp_path / "myproject" / ".dogcats"
        dogcats_dir.mkdir(parents=True)

        # Set a different prefix than directory name
        set_issue_prefix(str(dogcats_dir), "custom")

        prefix = get_issue_prefix(str(dogcats_dir))
        assert prefix == "custom"  # Not "myproject"


class TestDetectPrefixFromDirectory:
    """Tests for _detect_prefix_from_directory function."""

    def test_detect_from_simple_directory(self, tmp_path: Path) -> None:
        """Detect prefix from simple directory name."""
        dogcats_dir = tmp_path / "myproject" / ".dogcats"
        dogcats_dir.mkdir(parents=True)

        prefix = _detect_prefix_from_directory(str(dogcats_dir))
        assert prefix == "myproject"

    def test_detect_sanitizes_special_chars(self, tmp_path: Path) -> None:
        """Special characters are sanitized to hyphens."""
        dogcats_dir = tmp_path / "my project!" / ".dogcats"
        dogcats_dir.mkdir(parents=True)

        prefix = _detect_prefix_from_directory(str(dogcats_dir))
        # Trailing hyphen is stripped
        assert prefix == "my-project"

    def test_detect_preserves_hyphens(self, tmp_path: Path) -> None:
        """Hyphens in directory name are preserved."""
        dogcats_dir = tmp_path / "my-cool-project" / ".dogcats"
        dogcats_dir.mkdir(parents=True)

        prefix = _detect_prefix_from_directory(str(dogcats_dir))
        assert prefix == "my-cool-project"

    def test_detect_lowercases(self, tmp_path: Path) -> None:
        """Directory name is lowercased."""
        dogcats_dir = tmp_path / "MyProject" / ".dogcats"
        dogcats_dir.mkdir(parents=True)

        prefix = _detect_prefix_from_directory(str(dogcats_dir))
        assert prefix == "myproject"

    def test_detect_strips_leading_trailing_hyphens(self, tmp_path: Path) -> None:
        """Leading/trailing hyphens are stripped."""
        dogcats_dir = tmp_path / "-project-" / ".dogcats"
        dogcats_dir.mkdir(parents=True)

        prefix = _detect_prefix_from_directory(str(dogcats_dir))
        assert prefix == "project"

    def test_detect_returns_none_for_empty(self, tmp_path: Path) -> None:
        """Returns None if sanitization results in empty string."""
        dogcats_dir = tmp_path / "!!!" / ".dogcats"
        dogcats_dir.mkdir(parents=True)

        prefix = _detect_prefix_from_directory(str(dogcats_dir))
        assert prefix is None


class TestDetectPrefixFromIssues:
    """Tests for _detect_prefix_from_issues function."""

    def test_detect_prefix_from_issues(self, tmp_path: Path) -> None:
        """Detect prefix from existing issues in storage."""
        dogcats_dir = tmp_path / ".dogcats"
        dogcats_dir.mkdir()

        # Create issues.jsonl with some issues
        issues_file = dogcats_dir / "issues.jsonl"
        issues_file.write_text(
            '{"id": "search-abc", "title": "Issue 1"}\n'
            '{"id": "search-def", "title": "Issue 2"}\n'
            '{"id": "search-ghi", "title": "Issue 3"}\n',
        )

        prefix = _detect_prefix_from_issues(str(dogcats_dir))
        assert prefix == "search"

    def test_detect_most_common_prefix(self, tmp_path: Path) -> None:
        """Detect most common prefix when issues have mixed prefixes."""
        dogcats_dir = tmp_path / ".dogcats"
        dogcats_dir.mkdir()

        # Create issues.jsonl with mixed prefixes
        issues_file = dogcats_dir / "issues.jsonl"
        issues_file.write_text(
            '{"id": "proj-abc", "title": "Issue 1"}\n'
            '{"id": "proj-def", "title": "Issue 2"}\n'
            '{"id": "proj-ghi", "title": "Issue 3"}\n'
            '{"id": "other-xyz", "title": "Issue 4"}\n',
        )

        prefix = _detect_prefix_from_issues(str(dogcats_dir))
        assert prefix == "proj"

    def test_detect_no_issues_file(self, tmp_path: Path) -> None:
        """Returns None if no issues file exists."""
        dogcats_dir = tmp_path / ".dogcats"
        dogcats_dir.mkdir()

        prefix = _detect_prefix_from_issues(str(dogcats_dir))
        assert prefix is None

    def test_detect_empty_issues_file(self, tmp_path: Path) -> None:
        """Returns None if issues file is empty."""
        dogcats_dir = tmp_path / ".dogcats"
        dogcats_dir.mkdir()
        (dogcats_dir / "issues.jsonl").write_text("")

        prefix = _detect_prefix_from_issues(str(dogcats_dir))
        assert prefix is None

    def test_detect_skips_invalid_json(self, tmp_path: Path) -> None:
        """Skips invalid JSON lines."""
        dogcats_dir = tmp_path / ".dogcats"
        dogcats_dir.mkdir()

        issues_file = dogcats_dir / "issues.jsonl"
        issues_file.write_text(
            '{"id": "valid-abc", "title": "Issue 1"}\n'
            "not valid json\n"
            '{"id": "valid-def", "title": "Issue 2"}\n',
        )

        prefix = _detect_prefix_from_issues(str(dogcats_dir))
        assert prefix == "valid"

    def test_detect_skips_issues_without_id(self, tmp_path: Path) -> None:
        """Skips issues without id field."""
        dogcats_dir = tmp_path / ".dogcats"
        dogcats_dir.mkdir()

        issues_file = dogcats_dir / "issues.jsonl"
        issues_file.write_text(
            '{"id": "myapp-abc", "title": "Issue 1"}\n'
            '{"title": "Issue without id"}\n'
            '{"id": "myapp-def", "title": "Issue 2"}\n',
        )

        prefix = _detect_prefix_from_issues(str(dogcats_dir))
        assert prefix == "myapp"

    def test_detect_skips_issues_without_hyphen(self, tmp_path: Path) -> None:
        """Skips issues with IDs that have no hyphen."""
        dogcats_dir = tmp_path / ".dogcats"
        dogcats_dir.mkdir()

        issues_file = dogcats_dir / "issues.jsonl"
        issues_file.write_text(
            '{"id": "nohyphen", "title": "Issue 1"}\n'
            '{"id": "valid-abc", "title": "Issue 2"}\n',
        )

        prefix = _detect_prefix_from_issues(str(dogcats_dir))
        assert prefix == "valid"


class TestPrefixPrecedence:
    """Tests for prefix resolution precedence."""

    def test_config_over_issues(self, tmp_path: Path) -> None:
        """Config prefix takes precedence over issues detection."""
        dogcats_dir = tmp_path / ".dogcats"
        dogcats_dir.mkdir()

        # Create issues with different prefix
        issues_file = dogcats_dir / "issues.jsonl"
        issues_file.write_text('{"id": "issues-prefix-abc", "title": "Issue 1"}\n')

        # Set different prefix in config
        set_issue_prefix(str(dogcats_dir), "config-prefix")

        prefix = get_issue_prefix(str(dogcats_dir))
        assert prefix == "config-prefix"

    def test_issues_over_directory(self, tmp_path: Path) -> None:
        """Issues prefix takes precedence over directory name."""
        dogcats_dir = tmp_path / "directory-name" / ".dogcats"
        dogcats_dir.mkdir(parents=True)

        # Create issues with different prefix
        issues_file = dogcats_dir / "issues.jsonl"
        issues_file.write_text('{"id": "from-issues-abc", "title": "Issue 1"}\n')

        prefix = get_issue_prefix(str(dogcats_dir))
        assert prefix == "from-issues"

    def test_directory_over_default(self, tmp_path: Path) -> None:
        """Directory name takes precedence over default."""
        dogcats_dir = tmp_path / "custom-dir" / ".dogcats"
        dogcats_dir.mkdir(parents=True)

        prefix = get_issue_prefix(str(dogcats_dir))
        assert prefix == "custom-dir"
        assert prefix != DEFAULT_PREFIX

    def test_full_precedence_chain(self, tmp_path: Path) -> None:
        """Test full precedence: config > issues > directory > default."""
        dogcats_dir = tmp_path / "dir-prefix" / ".dogcats"
        dogcats_dir.mkdir(parents=True)

        # Step 1: No config, no issues -> directory name
        assert get_issue_prefix(str(dogcats_dir)) == "dir-prefix"

        # Step 2: Add issues -> issues prefix
        issues_file = dogcats_dir / "issues.jsonl"
        issues_file.write_text('{"id": "issues-prefix-abc", "title": "Issue"}\n')
        assert get_issue_prefix(str(dogcats_dir)) == "issues-prefix"

        # Step 3: Add config -> config prefix
        set_issue_prefix(str(dogcats_dir), "config-prefix")
        assert get_issue_prefix(str(dogcats_dir)) == "config-prefix"


class TestParseDogcatrc:
    """Tests for parse_dogcatrc function."""

    def test_absolute_path(self, tmp_path: Path) -> None:
        """Parse .dogcatrc with absolute path."""
        target = tmp_path / "external" / ".dogcats"
        rc_file = tmp_path / DOGCATRC_FILENAME
        rc_file.write_text(str(target) + "\n")

        result = parse_dogcatrc(rc_file)
        assert result == target

    def test_relative_path(self, tmp_path: Path) -> None:
        """Parse .dogcatrc with relative path resolves relative to rc file location."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        rc_file = project_dir / DOGCATRC_FILENAME
        rc_file.write_text("subdir/.dogcats\n")

        result = parse_dogcatrc(rc_file)
        assert result == (project_dir / "subdir" / ".dogcats").resolve()

    def test_relative_path_same_dir(self, tmp_path: Path) -> None:
        """Parse .dogcatrc with relative path in same directory."""
        rc_file = tmp_path / DOGCATRC_FILENAME
        rc_file.write_text(".dogcats\n")

        result = parse_dogcatrc(rc_file)
        assert result == (tmp_path / ".dogcats").resolve()

    def test_strips_whitespace(self, tmp_path: Path) -> None:
        """Parse .dogcatrc strips leading/trailing whitespace."""
        target = tmp_path / ".dogcats"
        rc_file = tmp_path / DOGCATRC_FILENAME
        rc_file.write_text(f"  {target}  \n\n")

        result = parse_dogcatrc(rc_file)
        assert result == target

    def test_empty_file_raises(self, tmp_path: Path) -> None:
        """Empty .dogcatrc raises ValueError."""
        rc_file = tmp_path / DOGCATRC_FILENAME
        rc_file.write_text("")

        with pytest.raises(ValueError, match="empty"):
            parse_dogcatrc(rc_file)

    def test_whitespace_only_raises(self, tmp_path: Path) -> None:
        """Whitespace-only .dogcatrc raises ValueError."""
        rc_file = tmp_path / DOGCATRC_FILENAME
        rc_file.write_text("   \n\n  ")

        with pytest.raises(ValueError, match="empty"):
            parse_dogcatrc(rc_file)

    def test_path_traversal_raises(self, tmp_path: Path) -> None:
        """Path traversal escaping project boundary raises ValueError."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        rc_file = project_dir / DOGCATRC_FILENAME
        rc_file.write_text("../../../../etc/something")

        with pytest.raises(ValueError, match="escapes project boundary"):
            parse_dogcatrc(rc_file)

    def test_absolute_path_outside_project_raises(self, tmp_path: Path) -> None:
        """Absolute path outside project boundary raises ValueError."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        rc_file = project_dir / DOGCATRC_FILENAME
        rc_file.write_text("/tmp/evil/.dogcats")

        with pytest.raises(ValueError, match="escapes project boundary"):
            parse_dogcatrc(rc_file)

    def test_relative_path_within_project_works(self, tmp_path: Path) -> None:
        """Relative path within project boundary succeeds."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        rc_file = project_dir / DOGCATRC_FILENAME
        rc_file.write_text("subdir/.dogcats")

        result = parse_dogcatrc(rc_file)
        assert result == (project_dir / "subdir" / ".dogcats").resolve()
