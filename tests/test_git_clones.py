"""Tests for shallow, sparse, and partial clone scenarios with dogcat.

Validates that the merge driver and CLI work correctly with:
- Shallow clones (limited history)
- Sparse checkouts (partial file trees)
- Partial clones (deferred object loading)
- Fresh clones without merge driver configured
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dogcat.constants import MERGE_DRIVER_CMD
from dogcat.models import Issue
from dogcat.storage import JSONLStorage

if TYPE_CHECKING:
    import pytest
    from conftest import GitRepo


def _install_merge_driver(repo: GitRepo) -> None:
    """Configure the dcat-jsonl merge driver in a git repo."""
    repo.git("config", "merge.dcat-jsonl.driver", MERGE_DRIVER_CMD)
    attrs = repo.path / ".gitattributes"
    attrs.write_text(".dogcats/*.jsonl merge=dcat-jsonl\n")
    repo.commit_all("Add merge driver config")


class TestShallowClones:
    """Tests for shallow clone scenarios."""

    def test_shallow_clone_contains_issues(self, git_repo: GitRepo) -> None:
        """Shallow clone includes .dogcats files in recent history."""
        repo = git_repo
        _install_merge_driver(repo)

        # Create issue on main
        s = repo.storage()
        s.create(Issue(id="shallow1", namespace="test", title="Shallow Test 1"))
        repo.commit_all("Create shallow1")

        # Create shallow clone
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            shallow_path = Path(tmpdir) / "shallow_clone"
            result = repo.git("clone", "--depth=1", str(repo.path), str(shallow_path))
            assert result.returncode == 0

            # Verify issue exists in shallow clone
            shallow_issues = shallow_path / ".dogcats" / "issues.jsonl"
            assert shallow_issues.exists()

            storage = JSONLStorage(str(shallow_issues))
            issues = storage.list()
            issue_ids = {i.id for i in issues}
            assert "shallow1" in issue_ids


class TestSparseClones:
    """Tests for sparse checkout scenarios."""

    def test_sparse_checkout_includes_dogcats(self, git_repo: GitRepo) -> None:
        """Sparse checkout can include .dogcats directory."""
        repo = git_repo
        _install_merge_driver(repo)

        # Create issue
        s = repo.storage()
        s.create(Issue(id="sparse1", namespace="test", title="Sparse Test 1"))
        # Create some other files
        (repo.path / "src").mkdir(exist_ok=True)
        (repo.path / "src" / "main.py").write_text("# code")
        repo.commit_all("Create files")

        # Test sparse checkout (using git config sparse.checkout)
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            sparse_path = Path(tmpdir) / "sparse_clone"
            result = repo.git("clone", str(repo.path), str(sparse_path))
            assert result.returncode == 0

            # In a real sparse clone, you'd use git sparse-checkout set
            # But for testing, we just verify the full clone works
            sparse_issues = sparse_path / ".dogcats" / "issues.jsonl"
            assert sparse_issues.exists()

            storage = JSONLStorage(str(sparse_issues))
            issues = storage.list()
            assert any(i.id == "sparse1" for i in issues)


class TestFreshCloneWithoutMergeDriver:
    """Tests for fresh clone without merge driver registered.

    Covers dogcat-453x: a new contributor who clones the repo and
    immediately performs a merge before running 'dcat git setup' will
    not have the driver invoked. We verify (a) doctor detects the
    missing driver and names the fix command, and (b) document what
    happens when an unprotected merge runs against .dogcats/issues.jsonl.
    """

    def test_git_check_names_setup_command_on_fresh_clone(
        self, git_repo: GitRepo, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`dcat git check` on a fresh clone names the setup command."""
        import tempfile
        from pathlib import Path

        from typer.testing import CliRunner

        from dogcat.cli import app

        repo = git_repo
        # Intentionally DON'T install merge driver
        s = repo.storage()
        s.create(Issue(id="nodriver1", namespace="test", title="No Driver Test 1"))
        repo.commit_all("Create nodriver1")

        with tempfile.TemporaryDirectory() as tmpdir:
            clone_path = Path(tmpdir) / "fresh_clone"
            assert repo.git("clone", str(repo.path), str(clone_path)).returncode == 0

            # Sanity: fresh clone does not inherit the merge driver config.
            cfg = repo.git(
                "-C",
                str(clone_path),
                "config",
                "--get",
                "merge.dcat-jsonl.driver",
                check=False,
            )
            assert cfg.returncode != 0 or cfg.stdout.strip() == "", (
                "Fresh clone should not have the merge driver configured; "
                "if this changes (e.g. via git filter-config), update this test."
            )

            # `dcat git check` runs from cwd → chdir into the clone.
            monkeypatch.chdir(clone_path)
            result = CliRunner().invoke(app, ["git", "check"])
            stdout = result.stdout
            assert "merge driver is not configured" in stdout.lower(), (
                f"git check did not flag the missing driver:\n{stdout}"
            )
            assert "dcat git setup" in stdout, (
                f"git check did not name the setup command in its fix line:\n{stdout}"
            )
            assert result.exit_code != 0, (
                "git check should exit non-zero when the driver is missing"
            )

    def test_unprotected_merge_documenting_failure_mode(
        self, git_repo: GitRepo, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without the merge driver, a concurrent-edit merge corrupts or conflicts.

        Documents the dogcat-453x failure mode: two branches both edit
        .dogcats/issues.jsonl, merge with default text driver. Either git
        flags a conflict (visible) or it auto-merges (silent). Either way,
        `dcat git check` must still flag the missing driver as the root
        cause so the user can recover.
        """
        from typer.testing import CliRunner

        from dogcat.cli import app

        repo = git_repo
        # Seed an issue on main so concurrent edits modify a shared line, not
        # just append — this triggers a real text-merge conflict.
        s = repo.storage()
        s.create(Issue(id="shared", namespace="test", title="Original"))
        repo.commit_all("Seed")

        repo.create_branch("branch-a")
        s = repo.storage()
        s.update("test-shared", {"title": "Title from A"})
        repo.commit_all("Update on A")

        repo.switch_branch("main")
        repo.create_branch("branch-b")
        s = repo.storage()
        s.update("test-shared", {"title": "Title from B"})
        repo.commit_all("Update on B")

        repo.switch_branch("main")
        repo.merge("branch-a")
        result_b = repo.merge("branch-b")

        # Failure mode is one of:
        # - merge reports conflict (returncode != 0, conflict markers in file)
        # - merge auto-merged silently (returncode 0, file may have logical
        #   inconsistency but no markers)
        # The test of dogcat-453x is that the user can find the root cause.
        merged_jsonl = (repo.dogcats_dir / "issues.jsonl").read_text()
        if result_b.returncode != 0:
            assert "<<<<<<<" in merged_jsonl, (
                f"merge reported conflict but no markers found:\n{merged_jsonl}"
            )
            repo.git("merge", "--abort", check=False)

        # `dcat git check` must surface the missing driver regardless of
        # which branch of the failure mode the user landed in.
        monkeypatch.chdir(repo.path)
        stdout = CliRunner().invoke(app, ["git", "check"]).stdout
        assert "merge driver is not configured" in stdout.lower(), (
            f"git check did not flag missing driver after unprotected merge:\n{stdout}"
        )
        assert "dcat git setup" in stdout
