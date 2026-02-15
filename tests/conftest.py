"""Pytest configuration and shared fixtures."""

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from dogcat.storage import JSONLStorage

# Environment variables that eliminate per-repo git config calls and skip
# system/global config lookups, saving 2 subprocess calls per git_repo fixture
# and speeding up every subsequent git operation.
_GIT_TEST_ENV = {
    **os.environ,
    "GIT_CONFIG_NOSYSTEM": "1",
    "HOME": "/dev/null",
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@test.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@test.com",
    "GIT_TERMINAL_PROMPT": "0",
}


@pytest.fixture
def temp_dogcats_dir(tmp_path: Path) -> Path:
    """Create a temporary .dogcats directory for testing."""
    dogcats_path = tmp_path / ".dogcats"
    dogcats_path.mkdir()
    return dogcats_path


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    """Create a temporary workspace directory for testing."""
    return tmp_path


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
            env=_GIT_TEST_ENV,
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


@pytest.fixture(scope="session")
def _git_template_dir(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Empty template dir to skip copying sample hooks during git init."""
    return str(tmp_path_factory.mktemp("git-tpl"))


@pytest.fixture
def git_repo(tmp_path: Path, _git_template_dir: str) -> GitRepo:
    """Create a temporary git repository with dogcats initialized."""
    repo_path = tmp_path
    dogcats_dir = repo_path / ".dogcats"
    storage_path = dogcats_dir / "issues.jsonl"

    # Initialize dogcats directory with empty JSONL
    dogcats_dir.mkdir()
    storage_path.touch()

    # Initialize git repo (3 subprocess calls instead of 5:
    # no git config needed thanks to _GIT_TEST_ENV, faster init via --template)
    subprocess.run(
        ["git", "init", "-b", "main", "--template", _git_template_dir, str(repo_path)],
        check=True,
        capture_output=True,
        env=_GIT_TEST_ENV,
    )
    subprocess.run(
        ["git", "add", "-A"],
        cwd=repo_path,
        check=True,
        capture_output=True,
        env=_GIT_TEST_ENV,
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial commit with empty .dogcats"],
        cwd=repo_path,
        check=True,
        capture_output=True,
        env=_GIT_TEST_ENV,
    )

    return GitRepo(
        path=repo_path,
        dogcats_dir=dogcats_dir,
        storage_path=storage_path,
    )
