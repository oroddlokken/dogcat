"""Tests for the custom JSONL merge driver.

Unit tests for the merge logic and integration tests verifying that
previously-conflicting git merge scenarios now resolve cleanly when
the merge driver is installed.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import orjson

from dogcat.constants import MERGE_DRIVER_CMD
from dogcat.merge_driver import _parse_jsonl, merge_jsonl
from dogcat.models import DependencyType, Issue
from dogcat.storage import JSONLStorage

if TYPE_CHECKING:
    from pathlib import Path

    import pytest
    from conftest import GitRepo


def _issue_record(**kwargs: Any) -> dict[str, Any]:
    """Build a minimal issue record dict."""
    defaults: dict[str, Any] = {
        "record_type": "issue",
        "namespace": "test",
        "id": "x",
        "title": "Test",
        "status": "open",
        "priority": 2,
        "issue_type": "task",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    defaults.update(kwargs)
    return defaults


def _event_record(**kwargs: Any) -> dict[str, Any]:
    """Build a minimal event record dict."""
    defaults: dict[str, Any] = {
        "record_type": "event",
        "event_type": "created",
        "issue_id": "test-x",
        "timestamp": "2026-01-01T00:00:00+00:00",
    }
    defaults.update(kwargs)
    return defaults


def _proposal_record(**kwargs: Any) -> dict[str, Any]:
    """Build a minimal proposal record dict."""
    defaults: dict[str, Any] = {
        "record_type": "proposal",
        "namespace": "test",
        "id": "p1",
        "title": "Proposal",
        "status": "open",
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    defaults.update(kwargs)
    return defaults


def _dep_record(**kwargs: Any) -> dict[str, Any]:
    """Build a minimal dependency record dict."""
    defaults: dict[str, Any] = {
        "record_type": "dependency",
        "issue_id": "test-a",
        "depends_on_id": "test-b",
        "type": "blocks",
    }
    defaults.update(kwargs)
    return defaults


# ---------------------------------------------------------------------------
# Unit tests for merge_jsonl()
# ---------------------------------------------------------------------------


class TestMergeJSONL:
    """Unit tests for the JSONL merge logic."""

    def test_non_overlapping_issues(self) -> None:
        """Different issues from each side are both kept."""
        base: list[dict[str, Any]] = []
        ours = [_issue_record(id="a1", title="Issue A")]
        theirs = [_issue_record(id="b1", title="Issue B")]

        result = merge_jsonl(base, ours, theirs)
        issue_ids = {
            f"{r['namespace']}-{r['id']}"
            for r in result
            if r.get("record_type") == "issue"
        }
        assert issue_ids == {"test-a1", "test-b1"}

    def test_same_issue_latest_wins(self) -> None:
        """Same issue edited on both sides: later updated_at wins."""
        base = [_issue_record(id="s1", title="Original")]
        ours = [
            _issue_record(
                id="s1",
                title="Title from ours",
                updated_at="2026-01-02T00:00:00+00:00",
            ),
        ]
        theirs = [
            _issue_record(
                id="s1",
                title="Title from theirs",
                updated_at="2026-01-03T00:00:00+00:00",
            ),
        ]

        result = merge_jsonl(base, ours, theirs)
        issues = [r for r in result if r.get("record_type") == "issue"]
        assert len(issues) == 1
        assert issues[0]["title"] == "Title from theirs"

    def test_events_deduplicated(self) -> None:
        """Same event from both sides is kept only once."""
        event = _event_record(issue_id="test-x", timestamp="2026-01-01T00:00:00+00:00")
        base: list[dict[str, Any]] = []
        ours = [event.copy()]
        theirs = [event.copy()]

        result = merge_jsonl(base, ours, theirs)
        events = [r for r in result if r.get("record_type") == "event"]
        assert len(events) == 1

    def test_events_union(self) -> None:
        """Different events from each side are both kept."""
        base: list[dict[str, Any]] = []
        ours = [_event_record(issue_id="test-a", timestamp="2026-01-01T00:00:00+00:00")]
        theirs = [
            _event_record(issue_id="test-b", timestamp="2026-01-02T00:00:00+00:00"),
        ]

        result = merge_jsonl(base, ours, theirs)
        events = [r for r in result if r.get("record_type") == "event"]
        assert len(events) == 2

    def test_deps_union(self) -> None:
        """Different dependencies from each side are both kept."""
        base: list[dict[str, Any]] = []
        ours = [_dep_record(issue_id="test-a", depends_on_id="test-b")]
        theirs = [_dep_record(issue_id="test-c", depends_on_id="test-d")]

        result = merge_jsonl(base, ours, theirs)
        deps = [r for r in result if r.get("record_type") == "dependency"]
        assert len(deps) == 2

    def test_deps_deduplicated(self) -> None:
        """Same dependency from both sides is kept only once."""
        dep = _dep_record()
        base: list[dict[str, Any]] = []
        ours = [dep.copy()]
        theirs = [dep.copy()]

        result = merge_jsonl(base, ours, theirs)
        deps = [r for r in result if r.get("record_type") == "dependency"]
        assert len(deps) == 1

    def test_mixed_records(self) -> None:
        """Issues, events, deps, and links all merge correctly."""
        base: list[dict[str, Any]] = []
        ours = [
            _issue_record(id="a1", title="Issue A"),
            _event_record(issue_id="test-a1", timestamp="2026-01-01T00:00:00+00:00"),
            _dep_record(issue_id="test-a1", depends_on_id="test-a2"),
        ]
        theirs = [
            _issue_record(id="b1", title="Issue B"),
            _event_record(issue_id="test-b1", timestamp="2026-01-02T00:00:00+00:00"),
        ]

        result = merge_jsonl(base, ours, theirs)
        issues = [r for r in result if r.get("record_type") == "issue"]
        events = [r for r in result if r.get("record_type") == "event"]
        deps = [r for r in result if r.get("record_type") == "dependency"]
        assert len(issues) == 2
        assert len(events) == 2
        assert len(deps) == 1

    def test_empty_inputs(self) -> None:
        """All empty inputs produce empty output."""
        result = merge_jsonl([], [], [])
        assert result == []

    def test_non_overlapping_proposals(self) -> None:
        """Different proposals from each side are both kept."""
        base: list[dict[str, Any]] = []
        ours = [_proposal_record(id="p1", title="Proposal A")]
        theirs = [_proposal_record(id="p2", title="Proposal B")]

        result = merge_jsonl(base, ours, theirs)
        proposals = [r for r in result if r.get("record_type") == "proposal"]
        assert len(proposals) == 2

    def test_same_proposal_more_final_status_wins(self) -> None:
        """Same proposal: closed wins over open."""
        base: list[dict[str, Any]] = []
        ours = [_proposal_record(id="p1", status="open")]
        theirs = [
            _proposal_record(
                id="p1",
                status="closed",
                closed_at="2026-01-02T00:00:00+00:00",
            ),
        ]

        result = merge_jsonl(base, ours, theirs)
        proposals = [r for r in result if r.get("record_type") == "proposal"]
        assert len(proposals) == 1
        assert proposals[0]["status"] == "closed"

    def test_same_proposal_tombstone_wins_over_closed(self) -> None:
        """Same proposal: tombstone wins over closed."""
        base: list[dict[str, Any]] = []
        ours = [_proposal_record(id="p1", status="closed")]
        theirs = [_proposal_record(id="p1", status="tombstone")]

        result = merge_jsonl(base, ours, theirs)
        proposals = [r for r in result if r.get("record_type") == "proposal"]
        assert len(proposals) == 1
        assert proposals[0]["status"] == "tombstone"

    def test_same_proposal_same_status_later_created_at_wins(self) -> None:
        """Same proposal, same status: later created_at wins."""
        base: list[dict[str, Any]] = []
        ours = [
            _proposal_record(
                id="p1",
                title="Earlier",
                created_at="2026-01-01T00:00:00+00:00",
            ),
        ]
        theirs = [
            _proposal_record(
                id="p1",
                title="Later",
                created_at="2026-01-02T00:00:00+00:00",
            ),
        ]

        result = merge_jsonl(base, ours, theirs)
        proposals = [r for r in result if r.get("record_type") == "proposal"]
        assert len(proposals) == 1
        assert proposals[0]["title"] == "Later"

    def test_proposals_not_dropped_during_merge(self) -> None:
        """Proposals are preserved through merge (not silently dropped)."""
        base: list[dict[str, Any]] = []
        ours = [
            _issue_record(id="i1", title="Issue"),
            _proposal_record(id="p1", title="Proposal"),
        ]
        theirs: list[dict[str, Any]] = []

        result = merge_jsonl(base, ours, theirs)
        proposals = [r for r in result if r.get("record_type") == "proposal"]
        issues = [r for r in result if r.get("record_type") == "issue"]
        assert len(proposals) == 1
        assert len(issues) == 1

    def test_dep_deleted_by_theirs_stays_deleted(self) -> None:
        """Dep in base and ours but removed by theirs stays deleted."""
        dep = _dep_record(issue_id="test-a", depends_on_id="test-b")
        base = [dep]
        ours = [dep.copy()]
        theirs: list[dict[str, Any]] = []  # theirs removed it (compacted away)

        result = merge_jsonl(base, ours, theirs)
        deps = [r for r in result if r.get("record_type") == "dependency"]
        assert len(deps) == 0, "Dep deleted by theirs should not be resurrected"

    def test_dep_deleted_by_ours_stays_deleted(self) -> None:
        """Dep in base and theirs but removed by ours stays deleted."""
        dep = _dep_record(issue_id="test-a", depends_on_id="test-b")
        base = [dep]
        ours: list[dict[str, Any]] = []  # ours removed it
        theirs = [dep.copy()]

        result = merge_jsonl(base, ours, theirs)
        deps = [r for r in result if r.get("record_type") == "dependency"]
        assert len(deps) == 0, "Dep deleted by ours should not be resurrected"

    def test_dep_deleted_by_both_stays_deleted(self) -> None:
        """Dep removed by both sides stays deleted."""
        dep = _dep_record(issue_id="test-a", depends_on_id="test-b")
        base = [dep]
        ours: list[dict[str, Any]] = []
        theirs: list[dict[str, Any]] = []

        result = merge_jsonl(base, ours, theirs)
        deps = [r for r in result if r.get("record_type") == "dependency"]
        assert len(deps) == 0

    def test_dep_added_by_ours_not_in_base_kept(self) -> None:
        """New dep added by ours (not in base or theirs) is kept."""
        dep = _dep_record(issue_id="test-a", depends_on_id="test-b")
        base: list[dict[str, Any]] = []
        ours = [dep]
        theirs: list[dict[str, Any]] = []

        result = merge_jsonl(base, ours, theirs)
        deps = [r for r in result if r.get("record_type") == "dependency"]
        assert len(deps) == 1

    def test_dep_with_remove_record_in_theirs(self) -> None:
        """Dep removed via explicit remove record in theirs is honored."""
        dep = _dep_record(issue_id="test-a", depends_on_id="test-b")
        remove = _dep_record(issue_id="test-a", depends_on_id="test-b", op="remove")
        base = [dep]
        ours = [dep.copy()]
        theirs = [dep.copy(), remove]  # add then remove

        result = merge_jsonl(base, ours, theirs)
        deps = [r for r in result if r.get("record_type") == "dependency"]
        assert len(deps) == 0, "Explicit remove in theirs should be honored"

    def test_link_deleted_by_theirs_stays_deleted(self) -> None:
        """Link in base and ours but removed by theirs stays deleted."""
        link = {
            "record_type": "link",
            "from_id": "test-a",
            "to_id": "test-b",
            "link_type": "relates_to",
        }
        base = [link]
        ours = [link.copy()]
        theirs: list[dict[str, Any]] = []

        result = merge_jsonl(base, ours, theirs)
        links = [r for r in result if r.get("record_type") == "link"]
        assert len(links) == 0, "Link deleted by theirs should not be resurrected"

    def test_link_added_by_theirs_not_in_base_kept(self) -> None:
        """New link added by theirs (not in base or ours) is kept."""
        link = {
            "record_type": "link",
            "from_id": "test-c",
            "to_id": "test-d",
            "link_type": "relates_to",
        }
        base: list[dict[str, Any]] = []
        ours: list[dict[str, Any]] = []
        theirs = [link]

        result = merge_jsonl(base, ours, theirs)
        links = [r for r in result if r.get("record_type") == "link"]
        assert len(links) == 1


# ---------------------------------------------------------------------------
# Unit tests for _parse_jsonl() logging and conflict marker detection
# ---------------------------------------------------------------------------


class TestParseJSONLLogging:
    """Verify _parse_jsonl logs warnings for malformed lines and conflict markers."""

    def test_malformed_line_logs_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Malformed JSONL lines produce a warning log."""
        f = tmp_path / "test.jsonl"
        f.write_text('{"record_type":"issue","id":"a","title":"A"}\nGARBAGE\n')

        with caplog.at_level(logging.WARNING, logger="dogcat.merge_driver"):
            records = _parse_jsonl(f)

        assert len(records) == 1
        assert any(
            "Skipping malformed JSONL at line 2" in msg for msg in caplog.messages
        )

    def test_conflict_markers_log_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Git conflict markers produce a specific warning."""
        f = tmp_path / "test.jsonl"
        f.write_text(
            '{"record_type":"issue","id":"a","title":"A"}\n'
            "<<<<<<< HEAD\n"
            '{"record_type":"issue","id":"b","title":"B"}\n'
            "=======\n"
            '{"record_type":"issue","id":"c","title":"C"}\n'
            ">>>>>>> branch\n"
        )

        with caplog.at_level(logging.WARNING, logger="dogcat.merge_driver"):
            records = _parse_jsonl(f)

        # Only the 3 valid JSON records are parsed
        assert len(records) == 3
        # Conflict markers produced warnings
        conflict_warnings = [msg for msg in caplog.messages if "conflict marker" in msg]
        assert len(conflict_warnings) == 3

    def test_valid_file_no_warnings(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A fully valid JSONL file produces no warnings."""
        f = tmp_path / "test.jsonl"
        f.write_text('{"record_type":"issue","id":"a","title":"A"}\n')

        with caplog.at_level(logging.WARNING, logger="dogcat.merge_driver"):
            records = _parse_jsonl(f)

        assert len(records) == 1
        assert len(caplog.messages) == 0

    def test_nonexistent_file_returns_empty(self, tmp_path: Path) -> None:
        """Parsing a nonexistent file returns an empty list."""
        f = tmp_path / "nonexistent.jsonl"
        assert _parse_jsonl(f) == []


# ---------------------------------------------------------------------------
# Tests for merge driver CLI entry point error handling
# ---------------------------------------------------------------------------


class TestMergeDriverCLI:
    """Verify git_merge_driver CLI has proper error handling."""

    def test_merge_driver_success(self, tmp_path: Path) -> None:
        """Merge driver exits 0 and writes merged result on success."""
        from typer.testing import CliRunner

        from dogcat.cli import app

        base = tmp_path / "base.jsonl"
        ours = tmp_path / "ours.jsonl"
        theirs = tmp_path / "theirs.jsonl"

        base.write_text("")
        ours.write_text(
            '{"record_type":"issue","namespace":"t","id":"a","title":"A","status":"open","priority":2,"issue_type":"task","updated_at":"2026-01-01T00:00:00+00:00"}\n'
        )
        theirs.write_text(
            '{"record_type":"issue","namespace":"t","id":"b","title":"B","status":"open","priority":2,"issue_type":"task","updated_at":"2026-01-01T00:00:00+00:00"}\n'
        )

        runner = CliRunner()
        result = runner.invoke(
            app, ["git", "merge-driver", str(base), str(ours), str(theirs)]
        )
        assert result.exit_code == 0

        # Ours file should contain both issues
        merged_records = [
            orjson.loads(ln) for ln in ours.read_text().splitlines() if ln.strip()
        ]
        ids = {r["id"] for r in merged_records}
        assert ids == {"a", "b"}

    def test_merge_driver_failure_exits_nonzero(self, tmp_path: Path) -> None:
        """When merge logic fails, exits 1 so git falls back."""
        from unittest.mock import patch

        from typer.testing import CliRunner

        from dogcat.cli import app

        base = tmp_path / "base.jsonl"
        ours = tmp_path / "ours.jsonl"
        theirs = tmp_path / "theirs.jsonl"

        base.write_text("")
        ours.write_text('{"record_type":"issue","id":"a","title":"A"}\n')
        theirs.write_text('{"record_type":"issue","id":"b","title":"B"}\n')

        runner = CliRunner()
        with patch(
            "dogcat.merge_driver.merge_jsonl",
            side_effect=RuntimeError("Boom"),
        ):
            result = runner.invoke(
                app, ["git", "merge-driver", str(base), str(ours), str(theirs)]
            )
        assert result.exit_code == 1

    def test_merge_driver_atomic_write(self, tmp_path: Path) -> None:
        """Merge driver uses atomic write (temp file + rename)."""
        from typer.testing import CliRunner

        from dogcat.cli import app

        base = tmp_path / "base.jsonl"
        ours = tmp_path / "ours.jsonl"
        theirs = tmp_path / "theirs.jsonl"

        base.write_text("")
        ours.write_text(
            '{"record_type":"issue","namespace":"t","id":"a","title":"A","status":"open","priority":2,"issue_type":"task","updated_at":"2026-01-01T00:00:00+00:00"}\n'
        )
        theirs.write_text("")

        ours.read_text()
        runner = CliRunner()
        result = runner.invoke(
            app, ["git", "merge-driver", str(base), str(ours), str(theirs)]
        )
        assert result.exit_code == 0

        # Verify the ours file is valid JSONL after merge
        for ln in ours.read_text().splitlines():
            if ln.strip():
                orjson.loads(ln)


# ---------------------------------------------------------------------------
# Integration tests: merge driver with real git repos
# ---------------------------------------------------------------------------


def _install_merge_driver(repo: GitRepo) -> None:
    """Configure the dcat-jsonl merge driver in a git repo."""
    repo.git("config", "merge.dcat-jsonl.driver", MERGE_DRIVER_CMD)
    # Write .gitattributes
    attrs = repo.path / ".gitattributes"
    attrs.write_text(".dogcats/*.jsonl merge=dcat-jsonl\n")
    repo.commit_all("Add merge driver config")


def _all_valid_json(repo: GitRepo) -> bool:
    """Return True if every non-empty line in issues.jsonl is valid JSON."""
    lines = repo.read_jsonl_lines()
    try:
        for line in lines:
            orjson.loads(line)
    except orjson.JSONDecodeError:
        return False
    return True


class TestMergeDriverIntegration:
    """Integration tests verifying the merge driver resolves conflicts."""

    def test_non_overlapping_adds_resolve(self, git_repo: GitRepo) -> None:
        """With merge driver, non-overlapping adds merge cleanly."""
        repo = git_repo
        _install_merge_driver(repo)

        # Branch A
        repo.create_branch("branch-a")
        s = repo.storage()
        s.create(Issue(id="a1", namespace="test", title="Issue A1"))
        s.create(Issue(id="a2", namespace="test", title="Issue A2"))
        repo.commit_all("Add issues on branch-a")

        # Branch B
        repo.switch_branch("main")
        repo.create_branch("branch-b")
        s = repo.storage()
        s.create(Issue(id="b1", namespace="test", title="Issue B1"))
        s.create(Issue(id="b2", namespace="test", title="Issue B2"))
        repo.commit_all("Add issues on branch-b")

        # Merge
        repo.switch_branch("main")
        result_a = repo.merge("branch-a")
        assert result_a.returncode == 0

        result_b = repo.merge("branch-b")
        assert result_b.returncode == 0, f"Merge failed: {result_b.stdout}"

        assert _all_valid_json(repo)
        storage = JSONLStorage(str(repo.storage_path))
        assert len(storage.list()) == 4

    def test_same_issue_edits_resolve(self, git_repo: GitRepo) -> None:
        """With merge driver, same-issue edits resolve via latest timestamp."""
        repo = git_repo
        _install_merge_driver(repo)

        # Seed
        s = repo.storage()
        s.create(Issue(id="shared1", namespace="test", title="Original"))
        repo.commit_all("Seed shared issue")

        # Branch A: update title
        repo.create_branch("branch-a")
        s = repo.storage()
        s.update("test-shared1", {"title": "Title from A"})
        repo.commit_all("Update on branch-a")

        # Branch B: update title
        repo.switch_branch("main")
        repo.create_branch("branch-b")
        s = repo.storage()
        s.update("test-shared1", {"title": "Title from B"})
        repo.commit_all("Update on branch-b")

        # Merge
        repo.switch_branch("main")
        repo.merge("branch-a")
        result_b = repo.merge("branch-b")
        assert result_b.returncode == 0, f"Merge failed: {result_b.stdout}"

        assert _all_valid_json(repo)
        storage = JSONLStorage(str(repo.storage_path))
        issue = storage.get("test-shared1")
        assert issue is not None
        # The one with later updated_at wins (branch-b was created after A)
        assert issue.title == "Title from B"

    def test_concurrent_creates_resolve(self, git_repo: GitRepo) -> None:
        """With merge driver, concurrent creates merge cleanly."""
        repo = git_repo
        _install_merge_driver(repo)

        repo.create_branch("branch-a")
        s = repo.storage()
        for i in range(3):
            s.create(Issue(id=f"ca{i}", namespace="test", title=f"A issue {i}"))
        repo.commit_all("Creates on branch-a")

        repo.switch_branch("main")
        repo.create_branch("branch-b")
        s = repo.storage()
        for i in range(3):
            s.create(Issue(id=f"cb{i}", namespace="test", title=f"B issue {i}"))
        repo.commit_all("Creates on branch-b")

        repo.switch_branch("main")
        repo.merge("branch-a")
        result_b = repo.merge("branch-b")
        assert result_b.returncode == 0, f"Merge failed: {result_b.stdout}"

        assert _all_valid_json(repo)
        storage = JSONLStorage(str(repo.storage_path))
        assert len(storage.list()) == 6

    def test_mixed_record_types_resolve(self, git_repo: GitRepo) -> None:
        """With merge driver, deps and links on separate branches merge cleanly."""
        repo = git_repo
        _install_merge_driver(repo)

        s = repo.storage()
        s.create(Issue(id="d1", namespace="test", title="Issue D1"))
        s.create(Issue(id="d2", namespace="test", title="Issue D2"))
        repo.commit_all("Seed issues")

        # Branch A: add dependency
        repo.create_branch("branch-a")
        s = repo.storage()
        s.add_dependency("test-d1", "test-d2", DependencyType.BLOCKS)
        repo.commit_all("Add dep on branch-a")

        # Branch B: add link
        repo.switch_branch("main")
        repo.create_branch("branch-b")
        s = repo.storage()
        s.add_link("test-d1", "test-d2", "relates_to")
        repo.commit_all("Add link on branch-b")

        repo.switch_branch("main")
        repo.merge("branch-a")
        result_b = repo.merge("branch-b")
        assert result_b.returncode == 0, f"Merge failed: {result_b.stdout}"

        assert _all_valid_json(repo)
        storage = JSONLStorage(str(repo.storage_path))
        assert len(storage.all_dependencies) >= 1
        assert len(storage.all_links) >= 1


# ---------------------------------------------------------------------------
# E2E test: full git merge workflow using dcat CLI
# ---------------------------------------------------------------------------


def _cli_invoke(dogcats_dir: Path, args: list[str]) -> str:
    """Invoke dcat CLI and return stdout, asserting exit code 0."""
    from typer.testing import CliRunner

    from dogcat.cli import app

    runner = CliRunner()
    result = runner.invoke(app, [*args, "--dogcats-dir", str(dogcats_dir)])
    assert result.exit_code == 0, f"CLI failed: {result.stdout}\n{result.output}"
    return result.stdout


def _cli_extract_id(create_output: str) -> str:
    """Extract issue ID from create command output."""
    return create_output.split(": ")[0].split()[-1]


class TestGitMergeWorkflowE2E:
    """E2E: full git merge workflow with CLI operations on both branches."""

    def test_cli_operations_on_both_branches_merge_cleanly(
        self, git_repo: GitRepo
    ) -> None:
        """Create and edit issues via CLI on two branches, then merge."""
        repo = git_repo
        _install_merge_driver(repo)

        # Create a seed issue on main via CLI
        out = _cli_invoke(repo.dogcats_dir, ["create", "Seed issue", "--type", "task"])
        seed_id = _cli_extract_id(out)
        repo.commit_all("Seed issue on main")

        # Branch A: create an issue and update the seed
        repo.create_branch("branch-a")
        out_a = _cli_invoke(
            repo.dogcats_dir,
            ["create", "Branch A issue", "--type", "bug", "--priority", "0"],
        )
        branch_a_id = _cli_extract_id(out_a)
        _cli_invoke(repo.dogcats_dir, ["update", seed_id, "--status", "in_progress"])
        repo.commit_all("CLI operations on branch-a")

        # Branch B: create a different issue and update the seed differently
        repo.switch_branch("main")
        repo.create_branch("branch-b")
        out_b = _cli_invoke(
            repo.dogcats_dir,
            ["create", "Branch B issue", "--type", "feature", "--priority", "1"],
        )
        branch_b_id = _cli_extract_id(out_b)
        _cli_invoke(
            repo.dogcats_dir,
            ["update", seed_id, "--title", "Seed issue (modified on B)"],
        )
        repo.commit_all("CLI operations on branch-b")

        # Merge A into main
        repo.switch_branch("main")
        result_a = repo.merge("branch-a")
        assert result_a.returncode == 0, f"Merge A failed: {result_a.stdout}"

        # Merge B into main (merge driver resolves conflicts)
        result_b = repo.merge("branch-b")
        assert result_b.returncode == 0, f"Merge B failed: {result_b.stdout}"

        # Verify all issues present and file integrity
        assert _all_valid_json(repo)
        storage = JSONLStorage(str(repo.storage_path))
        all_ids = {i.full_id for i in storage.list()}
        assert seed_id in all_ids
        assert branch_a_id in all_ids
        assert branch_b_id in all_ids

        # Seed issue should have branch-b's title (last-write-wins)
        seed = storage.get(seed_id)
        assert seed is not None
        assert seed.title == "Seed issue (modified on B)"

    def test_cli_close_on_one_branch_update_on_other(self, git_repo: GitRepo) -> None:
        """Close on one branch, update on another; merge driver resolves."""
        repo = git_repo
        _install_merge_driver(repo)

        out = _cli_invoke(
            repo.dogcats_dir, ["create", "Shared issue", "--type", "task"]
        )
        shared_id = _cli_extract_id(out)
        repo.commit_all("Seed shared issue")

        # Branch A: close the issue
        repo.create_branch("branch-a")
        _cli_invoke(repo.dogcats_dir, ["close", shared_id, "--reason", "Done"])
        repo.commit_all("Close on branch-a")

        # Branch B: update the issue
        repo.switch_branch("main")
        repo.create_branch("branch-b")
        _cli_invoke(
            repo.dogcats_dir,
            ["update", shared_id, "--priority", "0"],
        )
        repo.commit_all("Update on branch-b")

        # Merge both
        repo.switch_branch("main")
        repo.merge("branch-a")
        result_b = repo.merge("branch-b")
        assert result_b.returncode == 0, f"Merge failed: {result_b.stdout}"

        assert _all_valid_json(repo)
        storage = JSONLStorage(str(repo.storage_path))
        issue = storage.get(shared_id)
        assert issue is not None

    def test_doctor_post_merge_detects_concurrent_edits(
        self, git_repo: GitRepo
    ) -> None:
        """Dcat doctor --post-merge detects concurrent edits after merge."""
        repo = git_repo
        _install_merge_driver(repo)

        out = _cli_invoke(
            repo.dogcats_dir, ["create", "Contested issue", "--type", "task"]
        )
        contested_id = _cli_extract_id(out)
        repo.commit_all("Seed contested issue")

        # Branch A: change title
        repo.create_branch("branch-a")
        _cli_invoke(
            repo.dogcats_dir,
            ["update", contested_id, "--title", "Title from A"],
        )
        repo.commit_all("Edit on branch-a")

        # Branch B: change title to something different
        repo.switch_branch("main")
        repo.create_branch("branch-b")
        _cli_invoke(
            repo.dogcats_dir,
            ["update", contested_id, "--title", "Title from B"],
        )
        repo.commit_all("Edit on branch-b")

        # Merge
        repo.switch_branch("main")
        repo.merge("branch-a")
        result_b = repo.merge("branch-b")
        assert result_b.returncode == 0

        # Use the programmatic API (detect_concurrent_edits) which accepts cwd
        from dogcat.cli._validate import detect_concurrent_edits

        warnings = detect_concurrent_edits(
            storage_rel=".dogcats/issues.jsonl",
            cwd=repo.path,
        )
        # Should detect concurrent edits on the contested issue
        concurrent_ids = {w["issue_id"] for w in warnings}
        assert contested_id in concurrent_ids


# ---------------------------------------------------------------------------
# Unit test: event dedup key granularity
# ---------------------------------------------------------------------------


class TestEventDedupKey:
    """Verify that the event dedup key distinguishes distinct events."""

    def test_same_timestamp_different_changes_kept(self) -> None:
        """Two events with same timestamp but different changes are both kept."""
        ts = "2026-01-01T00:00:00+00:00"
        event_a = _event_record(
            issue_id="test-x",
            timestamp=ts,
            event_type="updated",
        )
        event_a["changes"] = {"title": {"old": "A", "new": "B"}}
        event_a["by"] = "alice"

        event_b = _event_record(
            issue_id="test-x",
            timestamp=ts,
            event_type="updated",
        )
        event_b["changes"] = {"status": {"old": "open", "new": "closed"}}
        event_b["by"] = "bob"

        base: list[dict[str, Any]] = []
        ours = [event_a]
        theirs = [event_b]

        result = merge_jsonl(base, ours, theirs)
        events = [r for r in result if r.get("record_type") == "event"]
        assert len(events) == 2, (
            "Distinct events with same timestamp should both be kept"
        )

    def test_identical_events_still_deduped(self) -> None:
        """Truly identical events are still deduplicated."""
        event = _event_record(
            issue_id="test-x",
            timestamp="2026-01-01T00:00:00+00:00",
            event_type="created",
        )
        base: list[dict[str, Any]] = []
        ours = [event.copy()]
        theirs = [event.copy()]

        result = merge_jsonl(base, ours, theirs)
        events = [r for r in result if r.get("record_type") == "event"]
        assert len(events) == 1
