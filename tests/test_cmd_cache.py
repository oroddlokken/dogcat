"""Tests for dcat cache commands."""

from pathlib import Path

from typer.testing import CliRunner

from dogcat.cli import app

runner = CliRunner()


class TestCacheList:
    """Test cache list command."""

    def test_empty_cache(self) -> None:
        """List with empty cache prints message."""
        result = runner.invoke(app, ["cache", "list"])
        assert result.exit_code == 0
        assert (
            "empty" in result.stdout.lower()
            or "does not exist" in result.stdout.lower()
        )

    def test_lists_entries_with_origin(self, tmp_path: Path) -> None:
        """List shows entries with origin paths."""
        cache_dir = tmp_path / "xdg-cache" / "dogcat"
        entry = cache_dir / "abc123"
        entry.mkdir(parents=True)
        (entry / ".origin").write_text(str(tmp_path))

        result = runner.invoke(app, ["cache", "list"])
        assert result.exit_code == 0
        assert "abc123" in result.stdout
        assert str(tmp_path) in result.stdout

    def test_lists_stale_entries(self, tmp_path: Path) -> None:
        """List marks stale entries."""
        cache_dir = tmp_path / "xdg-cache" / "dogcat"
        entry = cache_dir / "abc123"
        entry.mkdir(parents=True)
        (entry / ".origin").write_text("/nonexistent/path/.dogcats")

        result = runner.invoke(app, ["cache", "list"])
        assert result.exit_code == 0
        assert "(stale)" in result.stdout

    def test_lists_unknown_origin(self, tmp_path: Path) -> None:
        """List marks entries without origin file."""
        cache_dir = tmp_path / "xdg-cache" / "dogcat"
        entry = cache_dir / "abc123"
        entry.mkdir(parents=True)

        result = runner.invoke(app, ["cache", "list"])
        assert result.exit_code == 0
        assert "(unknown origin)" in result.stdout


class TestCacheClean:
    """Test cache clean command."""

    def test_clean_removes_stale(self, tmp_path: Path) -> None:
        """Clean removes stale entries by default."""
        cache_dir = tmp_path / "xdg-cache" / "dogcat"

        # Stale entry (nonexistent origin)
        stale = cache_dir / "stale1"
        stale.mkdir(parents=True)
        (stale / ".origin").write_text("/nonexistent/.dogcats")
        (stale / "prime-flags.json").write_text("{}")

        # Valid entry (existing origin)
        valid = cache_dir / "valid1"
        valid.mkdir(parents=True)
        (valid / ".origin").write_text(str(tmp_path))

        result = runner.invoke(app, ["cache", "clean"])
        assert result.exit_code == 0
        assert "Removed 1 cache entry." in result.stdout
        assert not stale.exists()
        assert valid.exists()

    def test_clean_removes_unknown_origin(self, tmp_path: Path) -> None:
        """Clean removes entries without an origin marker."""
        cache_dir = tmp_path / "xdg-cache" / "dogcat"
        entry = cache_dir / "orphan"
        entry.mkdir(parents=True)

        result = runner.invoke(app, ["cache", "clean"])
        assert result.exit_code == 0
        assert "Removed 1" in result.stdout
        assert not entry.exists()

    def test_clean_all(self, tmp_path: Path) -> None:
        """Clean --all removes everything."""
        cache_dir = tmp_path / "xdg-cache" / "dogcat"

        for name in ("a", "b", "c"):
            entry = cache_dir / name
            entry.mkdir(parents=True)
            (entry / ".origin").write_text(str(tmp_path))

        result = runner.invoke(app, ["cache", "clean", "--all"])
        assert result.exit_code == 0
        assert "Removed 3 cache entries." in result.stdout
        assert not list(cache_dir.iterdir())

    def test_clean_nothing_to_remove(self, tmp_path: Path) -> None:
        """Clean with no stale entries reports nothing."""
        cache_dir = tmp_path / "xdg-cache" / "dogcat"
        valid = cache_dir / "valid"
        valid.mkdir(parents=True)
        (valid / ".origin").write_text(str(tmp_path))

        result = runner.invoke(app, ["cache", "clean"])
        assert result.exit_code == 0
        assert "No stale cache entries found." in result.stdout

    def test_clean_empty_cache(self) -> None:
        """Clean with empty/missing cache dir."""
        result = runner.invoke(app, ["cache", "clean"])
        assert result.exit_code == 0
