"""Pytest configuration and shared fixtures."""

import subprocess
import tempfile
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path

import pytest

from dogcat.storage import JSONLStorage


@pytest.fixture
def temp_dogcats_dir() -> Generator[Path]:
    """Create a temporary .dogcats directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        dogcats_path = Path(tmpdir) / ".dogcats"
        dogcats_path.mkdir()
        yield dogcats_path


@pytest.fixture
def temp_workspace() -> Generator[Path]:
    """Create a temporary workspace directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@dataclass
class GitRepo:
    """A temporary git repository with dogcats initialized."""

    path: Path
    dogcats_dir: Path
    storage_path: Path

    def git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        """Run a git command in this repo."""
        return subprocess.run(
            ["git", *args],
            cwd=self.path,
            capture_output=True,
            text=True,
            check=check,
        )

    def storage(self) -> JSONLStorage:
        """Create a fresh JSONLStorage instance pointing at this repo's JSONL file."""
        return JSONLStorage(str(self.storage_path))

    def commit_all(self, message: str) -> None:
        """Stage all changes and commit."""
        self.git("add", "-A")
        self.git("commit", "-m", message)

    def create_branch(self, name: str) -> None:
        """Create and switch to a new branch from current HEAD."""
        self.git("checkout", "-b", name)

    def switch_branch(self, name: str) -> None:
        """Switch to an existing branch."""
        self.git("checkout", name)

    def merge(self, branch: str) -> subprocess.CompletedProcess[str]:
        """Merge a branch. Returns the CompletedProcess (does not raise on conflict)."""
        return self.git("merge", branch, check=False)

    def read_jsonl_lines(self) -> list[str]:
        """Read all non-empty lines from issues.jsonl."""
        return [
            line for line in self.storage_path.read_text().splitlines() if line.strip()
        ]


@pytest.fixture
def git_repo() -> Generator[GitRepo]:
    """Create a temporary git repository with dogcats initialized."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        dogcats_dir = repo_path / ".dogcats"
        storage_path = dogcats_dir / "issues.jsonl"

        # Initialize git repo with per-repo config
        subprocess.run(["git", "init", str(repo_path)], check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Initialize dogcats directory with empty JSONL
        dogcats_dir.mkdir()
        storage_path.touch()

        # Initial commit so branches can diverge
        subprocess.run(
            ["git", "add", "-A"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit with empty .dogcats"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        yield GitRepo(
            path=repo_path,
            dogcats_dir=dogcats_dir,
            storage_path=storage_path,
        )
