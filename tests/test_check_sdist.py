"""Tests for scripts/check-sdist against synthetic tarballs.

The script guards what reaches PyPI, so the cases here are the two ways a
release goes wrong: a swept-in cache directory and a tarball that grew past
its ceiling (dogcat-sin0). Building a real sdist would cost seconds per case
and pin the test to hatchling's behaviour rather than the script's, so each
tarball is assembled by hand instead.
"""

from __future__ import annotations

import subprocess
import tarfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check-sdist"

ROOT = "dogcat-1.2.3"

# Mirrors the sdist hatchling actually produces: the include-list's own paths
# plus the three files hatchling adds unasked.
CLEAN_MEMBERS = (
    ".gitignore",
    "CHANGELOG.md",
    "LICENSE",
    "PKG-INFO",
    "README.md",
    "docs/releasing.md",
    "pyproject.toml",
    "src/dogcat/__init__.py",
)


def _make_tarball(
    path: Path,
    members: tuple[str, ...] = CLEAN_MEMBERS,
    payload: bytes = b"x",
) -> Path:
    """Write a gzipped tarball whose members sit under a single root dir."""
    src = path.parent / "build"
    with tarfile.open(path, "w:gz") as tar:
        for member in members:
            f = src / member
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(payload)
            tar.add(f, arcname=f"{ROOT}/{member}")
    return path


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    """Run check-sdist and capture both streams."""
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def tarball(tmp_path: Path) -> Path:
    return _make_tarball(tmp_path / "dogcat-1.2.3.tar.gz")


class TestAccepts:
    """A tarball shaped like the one hatchling ships."""

    def test_clean_tarball_passes(self, tarball: Path) -> None:
        """The include-list's own entries clear every check."""
        result = _run(str(tarball))
        assert result.returncode == 0, result.stderr
        assert "Package present" in result.stdout

    def test_entry_count_matches_the_tarball(self, tarball: Path) -> None:
        """The reported count matches the tarball's distinct top-level names.

        `$(...)` strips the trailing newline, so counting with a bare
        `printf '%s'` reported one entry fewer than the tarball held.
        """
        expected = len({m.split("/")[0] for m in CLEAN_MEMBERS})
        result = _run(str(tarball))
        assert f"({expected})" in result.stdout, result.stdout


class TestRejects:
    """Tarballs carrying what the include-list exists to keep out."""

    def test_swept_in_cache_directory_fails(self, tmp_path: Path) -> None:
        """The .hypothesis case: gitignored from inside, invisible to git."""
        path = _make_tarball(
            tmp_path / "dogcat-1.2.3.tar.gz",
            (*CLEAN_MEMBERS, ".hypothesis/examples/deadbeef"),
        )
        result = _run(str(path))
        assert result.returncode != 0
        assert ".hypothesis" in result.stderr

    def test_tests_directory_fails(self, tmp_path: Path) -> None:
        """A directory outside the allowlist is named in the failure."""
        path = _make_tarball(
            tmp_path / "dogcat-1.2.3.tar.gz",
            (*CLEAN_MEMBERS, "tests/test_storage.py"),
        )
        result = _run(str(path))
        assert result.returncode != 0
        assert "tests" in result.stderr

    def test_oversized_tarball_fails(self, tmp_path: Path) -> None:
        """Size is the first gate, so it fails before the entry check runs."""
        path = _make_tarball(tmp_path / "dogcat-1.2.3.tar.gz")
        result = _run("--max-bytes", "10", str(path))
        assert result.returncode != 0
        assert "ceiling" in result.stderr

    def test_tarball_without_the_package_fails(self, tmp_path: Path) -> None:
        """An sdist holding no src/ passes size and entries while being useless."""
        path = _make_tarball(
            tmp_path / "dogcat-1.2.3.tar.gz",
            tuple(m for m in CLEAN_MEMBERS if not m.startswith("src/")),
        )
        result = _run(str(path))
        assert result.returncode != 0
        assert "no package" in result.stderr

    def test_missing_file_fails(self, tmp_path: Path) -> None:
        """A path that does not exist fails before any tar is read."""
        result = _run(str(tmp_path / "absent.tar.gz"))
        assert result.returncode != 0
        assert "Not a file" in result.stderr


class TestDistDiscovery:
    """The no-argument form, which resolves dist/*.tar.gz itself."""

    def test_finds_the_single_dist_tarball(self, tmp_path: Path) -> None:
        """One tarball in dist/ is checked without being named."""
        dist = tmp_path / "dist"
        dist.mkdir()
        _make_tarball(dist / "dogcat-1.2.3.tar.gz")
        result = subprocess.run(
            ["bash", str(SCRIPT)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr

    def test_ambiguous_dist_fails(self, tmp_path: Path) -> None:
        """Two tarballs leave no basis to pick, so the guard refuses."""
        dist = tmp_path / "dist"
        dist.mkdir()
        _make_tarball(dist / "dogcat-1.2.3.tar.gz")
        _make_tarball(dist / "dogcat-1.2.4.tar.gz")
        result = subprocess.run(
            ["bash", str(SCRIPT)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0
        assert "Name one" in result.stderr

    def test_empty_dist_fails(self, tmp_path: Path) -> None:
        """An empty dist/ points at the build command instead of passing."""
        (tmp_path / "dist").mkdir()
        result = subprocess.run(
            ["bash", str(SCRIPT)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0
        assert "uv build" in result.stderr
