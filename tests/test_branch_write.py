"""Tests for ``--branch``: mutations committed onto another branch (dogcat-1fvb)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import orjson
import pytest
from typer.testing import CliRunner

import dogcat.branch_store as branch_store_mod
from dogcat.cli import app
from dogcat.config import DogcatConfig, save_config
from dogcat.constants import MERGE_DRIVER_CMD
from dogcat.models import Issue, Status
from dogcat.storage import JSONLStorage

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from conftest import GitRepo

runner = CliRunner()

ISSUES = ".dogcats/issues.jsonl"


@pytest.fixture
def repo(git_repo: GitRepo, monkeypatch: pytest.MonkeyPatch) -> GitRepo:
    """Repo with one committed issue (test-seed) on main, checked out on feature-x."""
    # dcat's own git calls (commit-tree) need an identity; the fixture only
    # passes one to its own subprocesses.
    for key in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{key}_NAME", "Test")
        monkeypatch.setenv(f"GIT_{key}_EMAIL", "test@test.com")
    save_config(str(git_repo.dogcats_dir), DogcatConfig(namespace="test"))
    git_repo.storage().create(Issue(id="seed", namespace="test", title="Seed"))
    git_repo.commit_all("Seed issue")
    git_repo.create_branch("feature-x")
    return git_repo


def _dcat(repo: GitRepo, *args: str) -> Any:
    return runner.invoke(app, [*args, "--dogcats-dir", str(repo.dogcats_dir)])


def _branch_storage(repo: GitRepo, branch: str, tmp_path: Path) -> JSONLStorage:
    """Load ``branch``'s committed issues.jsonl into a fresh storage."""
    out = tmp_path / f"read-{branch}" / ".dogcats"
    out.mkdir(parents=True)
    (out / "issues.jsonl").write_text(repo.git("show", f"{branch}:{ISSUES}").stdout)
    return JSONLStorage(str(out / "issues.jsonl"))


def _sha(repo: GitRepo, ref: str) -> str:
    return repo.git("rev-parse", ref).stdout.strip()


class TestCreateOnBranch:
    """``dcat create --branch`` commits onto the target and touches nothing else."""

    def test_create_commits_to_target_only(self, repo: GitRepo, tmp_path: Path) -> None:
        """The issue lands on main as a child commit; feature-x is untouched."""
        old_main = _sha(repo, "main")
        before = repo.storage_path.read_bytes()

        result = _dcat(repo, "create", "Fix X", "--type", "bug", "--branch", "main")

        assert result.exit_code == 0, result.output
        assert repo.storage_path.read_bytes() == before
        assert repo.git("status", "--porcelain").stdout == ""
        assert _sha(repo, "HEAD") != _sha(repo, "main")
        assert _sha(repo, "main^") == old_main
        main = _branch_storage(repo, "main", tmp_path)
        created = next(i for i in main.list() if i.title == "Fix X")
        assert created.issue_type.value == "bug"
        subject = repo.git("log", "-1", "--format=%s", "main").stdout.strip()
        assert subject == f"dcat create {created.full_id}"
        assert "Committed to main" in result.output

    def test_event_record_lands_with_issue(self, repo: GitRepo) -> None:
        """The created event is committed alongside the issue record."""
        result = _dcat(repo, "create", "Fix Y", "--branch", "main")
        assert result.exit_code == 0, result.output
        lines = [
            orjson.loads(line)
            for line in repo.git("show", f"main:{ISSUES}").stdout.splitlines()
        ]
        assert any(
            r["record_type"] == "event" and r["event_type"] == "created" for r in lines
        )

    def test_namespace_follows_target_config(
        self, repo: GitRepo, tmp_path: Path
    ) -> None:
        """The target branch's config.toml decides the new issue's namespace."""
        save_config(str(repo.dogcats_dir), DogcatConfig(namespace="local"))
        repo.commit_all("Local namespace")

        result = _dcat(repo, "create", "Where", "--branch", "main")

        assert result.exit_code == 0, result.output
        created = next(
            i
            for i in _branch_storage(repo, "main", tmp_path).list()
            if i.title == "Where"
        )
        assert created.namespace == "test"

    def test_json_stdout_stays_parseable(self, repo: GitRepo) -> None:
        """The commit notice goes to stderr so --json stdout stays one object."""
        result = runner.invoke(
            app,
            [
                "create",
                "Fix Z",
                "--json",
                "--branch",
                "main",
                "--dogcats-dir",
                str(repo.dogcats_dir),
            ],
        )
        assert result.exit_code == 0, result.output
        assert orjson.loads(result.stdout)["title"] == "Fix Z"

    def test_new_id_avoids_current_branch_ids(
        self, repo: GitRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A new id skips ids that exist only on the current branch."""

        # Every first attempt hashes to "aaaa", every retry to "bbbb", so the
        # second create collides unless the current branch's ids are reserved.
        def fake_hash(_data: str, nonce: str = "", length: int = 4) -> str:  # noqa: ARG001
            return "aaaa" if nonce == "" else "bbbb"

        monkeypatch.setattr("dogcat.idgen.generate_hash_id", fake_hash)
        assert _dcat(repo, "create", "Local").exit_code == 0
        assert repo.storage().get("test-aaaa") is not None

        result = _dcat(repo, "create", "Remote", "--branch", "main")

        assert result.exit_code == 0, result.output
        main = _branch_storage(repo, "main", tmp_path)
        assert main.get("test-aaaa") is None
        remote = main.get("test-bbbb")
        assert remote is not None
        assert remote.title == "Remote"


def _is_p0(issue: Issue) -> bool:
    return issue.priority == 0


def _is_closed(issue: Issue) -> bool:
    return issue.status == Status.CLOSED


def _is_deferred(issue: Issue) -> bool:
    return issue.status == Status.DEFERRED


def _is_tombstone(issue: Issue) -> bool:
    return issue.status == Status.TOMBSTONE


def _has_comment(issue: Issue) -> bool:
    return issue.comments[-1].text == "hello"


def _has_label(issue: Issue) -> bool:
    return "ux" in issue.labels


class TestOtherMutations:
    """Every mutating command honours ``--branch`` against an issue on the target."""

    @pytest.mark.parametrize(
        ("args", "check"),
        [
            (["update", "test-seed", "--priority", "0"], _is_p0),
            (["close", "test-seed"], _is_closed),
            (["comment", "test-seed", "add", "-t", "hello"], _has_comment),
            (["label", "test-seed", "add", "-l", "ux"], _has_label),
            (["defer", "test-seed"], _is_deferred),
            (["remove", "test-seed"], _is_tombstone),
        ],
    )
    def test_mutation_lands_on_target(
        self,
        repo: GitRepo,
        tmp_path: Path,
        args: list[str],
        check: Callable[[Issue], bool],
    ) -> None:
        """Each command's change lands on main and not in the working tree."""
        before = repo.storage_path.read_bytes()

        result = _dcat(repo, *args, "--branch", "main")

        assert result.exit_code == 0, result.output
        assert repo.storage_path.read_bytes() == before
        seed = _branch_storage(repo, "main", tmp_path).get("test-seed")
        assert seed is not None
        assert check(seed)

    def test_dep_and_link_land_on_target(self, repo: GitRepo, tmp_path: Path) -> None:
        """Dependency and link records are committed onto the target."""
        repo.switch_branch("main")
        repo.storage().create(Issue(id="other", namespace="test", title="Other"))
        repo.commit_all("Other issue")
        repo.switch_branch("feature-x")

        dep = _dcat(
            repo, "dep", "test-seed", "add", "--depends-on", "test-other",
            "--branch", "main",
        )  # fmt: skip
        link = _dcat(
            repo, "link", "test-seed", "add", "--related", "test-other",
            "--branch", "main",
        )  # fmt: skip

        assert dep.exit_code == 0, dep.output
        assert link.exit_code == 0, link.output
        main = _branch_storage(repo, "main", tmp_path)
        assert [d.depends_on_id for d in main.get_dependencies("test-seed")] == [
            "test-other"
        ]
        assert [lk.to_id for lk in main.get_links("test-seed")] == ["test-other"]

    def test_issue_missing_on_target_errors_without_commit(self, repo: GitRepo) -> None:
        """An id that exists only on feature-x errors and moves nothing."""
        assert _dcat(repo, "create", "Only here").exit_code == 0
        local_id = next(
            i.full_id for i in repo.storage().list() if i.title == "Only here"
        )
        old_main = _sha(repo, "main")

        result = _dcat(repo, "close", local_id, "--branch", "main")

        assert result.exit_code != 0
        assert _sha(repo, "main") == old_main


class TestStoreIntegrity:
    """The target file is appended to, never rewritten."""

    def test_no_compaction_on_target(
        self, repo: GitRepo, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Past the compaction threshold the target is still only appended to."""
        # From the default branch, normal writes would compact; the target
        # (a non-checked-out branch) must still only be appended to.
        repo.switch_branch("main")
        repo.git("branch", "release")

        def always(*_counts: int) -> bool:
            return True

        monkeypatch.setattr("dogcat.storage.should_compact", always)
        before = repo.git("show", f"release:{ISSUES}").stdout

        result = _dcat(repo, "create", "Hotfix", "--branch", "release")

        assert result.exit_code == 0, result.output
        after = repo.git("show", f"release:{ISSUES}").stdout
        assert after.startswith(before)
        assert len(after) > len(before)

    def test_unknown_records_preserved(self, repo: GitRepo) -> None:
        """A record type this dcat doesn't model survives the write."""
        repo.switch_branch("main")
        unknown = '{"record_type":"from_the_future","x":1}\n'
        with repo.storage_path.open("a") as f:
            f.write(unknown)
        repo.commit_all("Future record")
        repo.switch_branch("feature-x")

        result = _dcat(repo, "create", "Fix", "--branch", "main")

        assert result.exit_code == 0, result.output
        assert unknown.strip() in repo.git("show", f"main:{ISSUES}").stdout

    def test_branch_moved_meanwhile_commits_nothing(
        self, repo: GitRepo, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A concurrent ref move fails the compare-and-swap cleanly."""
        real_hash = branch_store_mod.git_helpers.hash_object

        def racing_hash(path: Any, **kw: Any) -> str | None:
            # Another writer moves main between our read and our ref update.
            sha = repo.git(
                "commit-tree", "-m", "race", "-p", "main", "main^{tree}"
            ).stdout.strip()
            repo.git("update-ref", "refs/heads/main", sha)
            return real_hash(path, **kw)

        monkeypatch.setattr(branch_store_mod.git_helpers, "hash_object", racing_hash)

        result = _dcat(repo, "create", "Lost", "--branch", "main")

        assert result.exit_code == 1
        assert "moved" in result.output
        assert repo.git("log", "-1", "--format=%s", "main").stdout.strip() == "race"


class TestRefusals:
    """Targets that can't be written fail before anything is committed."""

    def test_unknown_branch(self, repo: GitRepo) -> None:
        """A branch that doesn't exist is refused."""
        result = _dcat(repo, "create", "X", "--branch", "nope")
        assert result.exit_code == 1
        assert "No local branch named 'nope'" in result.output

    def test_current_branch(self, repo: GitRepo) -> None:
        """Targeting the checked-out branch is refused."""
        result = _dcat(repo, "create", "X", "--branch", "feature-x")
        assert result.exit_code == 1
        assert "current branch" in result.output

    def test_branch_checked_out_in_other_worktree(
        self, repo: GitRepo, tmp_path: Path
    ) -> None:
        """A branch checked out in another worktree is refused."""
        repo.git("worktree", "add", str(tmp_path.parent / "wt-main"), "main")
        result = _dcat(repo, "create", "X", "--branch", "main")
        assert result.exit_code == 1
        assert "another worktree" in result.output

    def test_branch_without_store(self, repo: GitRepo) -> None:
        """A branch without the store file is refused."""
        empty_tree = repo.git("hash-object", "-t", "tree", "/dev/null").stdout.strip()
        orphan = repo.git("commit-tree", "-m", "empty", empty_tree).stdout.strip()
        repo.git("branch", "bare", orphan)

        result = _dcat(repo, "create", "X", "--branch", "bare")

        assert result.exit_code == 1
        assert "has no .dogcats/issues.jsonl" in result.output

    def test_store_in_another_repo(
        self, repo: GitRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A store tracked by a different repo than the cwd's is refused."""
        other = tmp_path.parent / f"{tmp_path.name}-other"
        other.mkdir()
        repo.git("init", "-q", "-b", "main", str(other))
        monkeypatch.chdir(other)
        old_main = _sha(repo, "main")

        result = _dcat(repo, "create", "X", "--branch", "main")

        assert result.exit_code == 1
        assert "not the one you are in" in result.output
        assert _sha(repo, "main") == old_main

    def test_no_change_makes_no_commit(self, repo: GitRepo) -> None:
        """A read-only subcommand under --branch makes no commit."""
        old_main = _sha(repo, "main")
        result = _dcat(repo, "comment", "test-seed", "list", "--branch", "main")
        assert result.exit_code == 0, result.output
        assert _sha(repo, "main") == old_main
        assert "no commit made" in result.output


def test_merge_brings_issue_back(repo: GitRepo) -> None:
    """Merging the target into the current branch carries the new issue across."""
    repo.git("config", "merge.dcat-jsonl.driver", MERGE_DRIVER_CMD)
    (repo.path / ".gitattributes").write_text(".dogcats/*.jsonl merge=dcat-jsonl\n")
    repo.commit_all("Merge driver")
    assert _dcat(repo, "create", "Local work").exit_code == 0
    repo.commit_all("Local issue")
    assert _dcat(repo, "create", "Main bug", "--branch", "main").exit_code == 0

    merged = repo.merge("main")

    assert merged.returncode == 0, merged.stdout + merged.stderr
    titles = {i.title for i in repo.storage().list()}
    assert {"Local work", "Main bug", "Seed"} <= titles
