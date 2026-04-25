"""Tests for inbox proposal edge cases during merges.

Exercises the merge driver on .dogcats/inbox.jsonl across git branches
that mutate local proposals concurrently. Uses CLI commands that operate
on the LOCAL inbox (propose --to, inbox close, inbox delete); accept/reject
require a configured remote inbox and are out of scope here — see
test_cmd_inbox.py and test_merge_driver.py for those paths.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from dogcat.cli import app
from dogcat.constants import MERGE_DRIVER_CMD
from dogcat.models import Issue
from dogcat.storage import JSONLStorage

if TYPE_CHECKING:
    from conftest import GitRepo


def _install_merge_driver(repo: GitRepo) -> None:
    """Configure the dcat-jsonl merge driver in a git repo."""
    repo.git("config", "merge.dcat-jsonl.driver", MERGE_DRIVER_CMD)
    attrs = repo.path / ".gitattributes"
    attrs.write_text(".dogcats/*.jsonl merge=dcat-jsonl\n")
    repo.commit_all("Add merge driver config")


def _propose(repo: GitRepo, title: str) -> str:
    """Create a proposal in the test repo's local inbox. Returns full proposal id."""
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["propose", title, "--to", str(repo.path), "--json"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, f"propose failed: {result.stdout}\n{result.stderr}"
    data = json.loads(result.stdout)
    return f"{data['namespace']}-inbox-{data['id']}"


def _inbox_close(repo: GitRepo, proposal_id: str, reason: str | None = None) -> None:
    """Close a local proposal."""
    runner = CliRunner()
    args = ["inbox", "close", proposal_id, "--dogcats-dir", str(repo.dogcats_dir)]
    if reason is not None:
        args.extend(["--reason", reason])
    result = runner.invoke(app, args, catch_exceptions=False)
    assert result.exit_code == 0, (
        f"inbox close failed: {result.stdout}\n{result.stderr}"
    )


def _inbox_delete(repo: GitRepo, proposal_id: str) -> None:
    """Tombstone a local proposal."""
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["inbox", "delete", proposal_id, "--dogcats-dir", str(repo.dogcats_dir)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, (
        f"inbox delete failed: {result.stdout}\n{result.stderr}"
    )


class TestInboxMergeEdgeCases:
    """Edge cases for inbox proposals during git merges."""

    def test_concurrent_close_same_proposal(self, git_repo: GitRepo) -> None:
        """Both branches close the same proposal: final state is closed once."""
        repo = git_repo
        _install_merge_driver(repo)

        proposal_id = _propose(repo, "Build feature X")
        repo.commit_all("Create proposal")

        # Branch A: close with reason "out of scope"
        repo.create_branch("branch-a")
        _inbox_close(repo, proposal_id, reason="out of scope")
        repo.commit_all("Close on A")

        # Branch B: close with a different reason
        repo.switch_branch("main")
        repo.create_branch("branch-b")
        _inbox_close(repo, proposal_id, reason="duplicate of Y")
        repo.commit_all("Close on B")

        # Merge both branches into main
        repo.switch_branch("main")
        repo.merge("branch-a")
        result_b = repo.merge("branch-b")
        assert result_b.returncode == 0, f"Merge failed: {result_b.stdout}"

        inbox = JSONLStorage(str(repo.dogcats_dir / "inbox.jsonl"))
        proposals = [p for p in inbox.list() if getattr(p, "id", None) is not None]
        # Same proposal id on both sides — LWW collapses to one record
        matching = [p for p in proposals if proposal_id.endswith(f"-inbox-{p.id}")]
        assert len(matching) == 1, f"Expected one record, got {len(matching)}"
        assert matching[0].status == "closed"

    def test_close_vs_delete_same_proposal(self, git_repo: GitRepo) -> None:
        """One branch closes, other tombstones — tombstone wins (absorbing)."""
        repo = git_repo
        _install_merge_driver(repo)

        proposal_id = _propose(repo, "Cleanup deprecated API")
        repo.commit_all("Create proposal")

        # Branch A: close
        repo.create_branch("branch-a")
        _inbox_close(repo, proposal_id, reason="defer to next quarter")
        repo.commit_all("Close on A")

        # Branch B: delete (tombstone)
        repo.switch_branch("main")
        repo.create_branch("branch-b")
        _inbox_delete(repo, proposal_id)
        repo.commit_all("Delete on B")

        # Merge
        repo.switch_branch("main")
        repo.merge("branch-a")
        result_b = repo.merge("branch-b")
        assert result_b.returncode == 0, f"Merge failed: {result_b.stdout}"

        inbox = JSONLStorage(str(repo.dogcats_dir / "inbox.jsonl"))
        proposals = inbox.list()
        matching = [p for p in proposals if proposal_id.endswith(f"-inbox-{p.id}")]
        assert len(matching) == 1
        assert matching[0].status == "tombstone", (
            "tombstone is absorbing — must win over closed"
        )

    def test_concurrent_create_different_proposals(self, git_repo: GitRepo) -> None:
        """Each branch creates a different proposal — both survive merge."""
        repo = git_repo
        _install_merge_driver(repo)

        # Branch A: create proposal A
        repo.create_branch("branch-a")
        proposal_a = _propose(repo, "Proposal from A")
        repo.commit_all("Create proposal on A")

        # Branch B: create proposal B
        repo.switch_branch("main")
        repo.create_branch("branch-b")
        proposal_b = _propose(repo, "Proposal from B")
        repo.commit_all("Create proposal on B")

        # Merge
        repo.switch_branch("main")
        repo.merge("branch-a")
        result_b = repo.merge("branch-b")
        assert result_b.returncode == 0, f"Merge failed: {result_b.stdout}"

        inbox = JSONLStorage(str(repo.dogcats_dir / "inbox.jsonl"))
        proposals = inbox.list()
        ids = {f"{p.namespace}-inbox-{p.id}" for p in proposals}
        assert proposal_a in ids
        assert proposal_b in ids

    def test_cross_file_integrity_after_merge(self, git_repo: GitRepo) -> None:
        """issues.jsonl and inbox.jsonl merge independently and stay valid."""
        repo = git_repo
        _install_merge_driver(repo)

        # Seed an issue and a proposal on main
        s = repo.storage()
        s.create(Issue(id="task1", namespace="test", title="Task 1"))
        proposal_id = _propose(repo, "Related feature")
        repo.commit_all("Seed issue and proposal")

        # Branch A: create another issue (mutates issues.jsonl)
        repo.create_branch("branch-a")
        s = repo.storage()
        s.create(Issue(id="task2", namespace="test", title="Task 2"))
        repo.commit_all("Create task2 on A")

        # Branch B: close the proposal (mutates inbox.jsonl)
        repo.switch_branch("main")
        repo.create_branch("branch-b")
        _inbox_close(repo, proposal_id, reason="superseded")
        repo.commit_all("Close proposal on B")

        # Merge
        repo.switch_branch("main")
        repo.merge("branch-a")
        result_b = repo.merge("branch-b")
        assert result_b.returncode == 0, f"Merge failed: {result_b.stdout}"

        issues = JSONLStorage(str(repo.dogcats_dir / "issues.jsonl")).list()
        issue_ids = {f"{i.namespace}-{i.id}" for i in issues}
        assert "test-task1" in issue_ids
        assert "test-task2" in issue_ids

        proposals = JSONLStorage(str(repo.dogcats_dir / "inbox.jsonl")).list()
        matching = [p for p in proposals if proposal_id.endswith(f"-inbox-{p.id}")]
        assert len(matching) == 1
        assert matching[0].status == "closed"
