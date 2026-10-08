"""Tests for dcat stage: stage one issue's records without the rest."""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING, Any

import orjson
import pytest
from conftest import _GIT_TEST_ENV
from typer.testing import CliRunner

from dogcat.cli import app
from dogcat.stage import plan_stage
from dogcat.storage import JSONLStorage

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()

STORE = ".dogcats/issues.jsonl"


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env=_GIT_TEST_ENV,
    )
    return result.stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Return a git repo whose initialized .dogcats is committed."""
    _git(tmp_path, "init")
    result = runner.invoke(app, ["init", "--dogcats-dir", str(tmp_path / ".dogcats")])
    assert result.exit_code == 0
    _git(tmp_path, "add", ".dogcats/")
    _git(tmp_path, "commit", "-m", "init")
    return tmp_path


def _dcat(repo: Path, *args: str) -> Any:
    result = runner.invoke(app, [*args, "--dogcats-dir", str(repo / ".dogcats")])
    assert result.exit_code == 0, result.output
    return result


def _create(repo: Path, title: str, *extra: str) -> str:
    data = json.loads(_dcat(repo, "create", title, "--json", *extra).stdout)
    return f"{data['namespace']}-{data['id']}"


def _stage(repo: Path, *ids: str) -> Any:
    return runner.invoke(
        app, ["stage", *ids, "--json", "--dogcats-dir", str(repo / ".dogcats")]
    )


def _commit_all(repo: Path, message: str = "commit") -> None:
    _git(repo, "add", ".dogcats/")
    _git(repo, "commit", "-m", message)


def _index_storage(repo: Path, tmp_path: Path) -> JSONLStorage:
    """Load the staged blob into a scratch store for assertions."""
    blob = subprocess.run(
        ["git", "-C", str(repo), "show", f":{STORE}"],
        check=True,
        capture_output=True,
        env=_GIT_TEST_ENV,
    ).stdout
    scratch = tmp_path / "scratch" / ".dogcats"
    scratch.mkdir(parents=True)
    (scratch / "issues.jsonl").write_bytes(blob)
    return JSONLStorage(str(scratch / "issues.jsonl"))


def _index_events(repo: Path) -> list[dict[str, Any]]:
    blob = _git(repo, "show", f":{STORE}")
    records = [orjson.loads(line) for line in blob.splitlines() if line.strip()]
    return [r for r in records if r.get("record_type") == "event"]


def _diff_ids(repo: Path, flag: str) -> set[str]:
    out = _dcat(repo, "diff", flag, "--json").stdout
    return {event["issue_id"] for event in json.loads(out)}


class TestStageIsolation:
    """Staging one issue leaves the others in the working tree."""

    def test_staged_and_unstaged_split(self, repo: Path) -> None:
        """Diff --staged lists X only and --unstaged lists Y only."""
        x = _create(repo, "Issue X")
        y = _create(repo, "Issue Y")

        result = _stage(repo, x)

        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["staged"] == {x: 2}
        assert _diff_ids(repo, "--staged") == {x}
        assert _diff_ids(repo, "--unstaged") == {y}

    def test_working_tree_untouched(self, repo: Path) -> None:
        """The working file keeps every issue's records."""
        x = _create(repo, "Issue X")
        _create(repo, "Issue Y")
        before = (repo / STORE).read_bytes()

        assert _stage(repo, x).exit_code == 0

        assert (repo / STORE).read_bytes() == before

    def test_blob_carries_events_comments_close_and_deps(
        self, repo: Path, tmp_path: Path
    ) -> None:
        """Every record naming X reaches the index, and nothing of Y's does."""
        base = _create(repo, "Committed base")
        _commit_all(repo)
        x = _create(repo, "Issue X")
        y = _create(repo, "Issue Y")
        _dcat(repo, "comment", x, "add", "-t", "a note")
        _dcat(repo, "dep", x, "add", "--depends-on", base)
        _dcat(repo, "close", x, "--reason", "done")
        _dcat(repo, "update", y, "--status", "in_progress")

        assert _stage(repo, x).exit_code == 0

        staged = _index_storage(repo, tmp_path)
        issue = staged.get(x)
        assert issue is not None
        assert issue.status.value == "closed"
        assert issue.closed_reason == "done"
        assert [c.text for c in issue.comments] == ["a note"]
        assert [d.depends_on_id for d in staged.get_dependencies(x)] == [base]
        assert staged.get(y) is None
        event_ids = {e["issue_id"] for e in _index_events(repo)}
        assert x in event_ids
        assert y not in event_ids

    def test_repeated_stage_accumulates(self, repo: Path) -> None:
        """Staging Y after X keeps X staged, the way git add does."""
        x = _create(repo, "Issue X")
        y = _create(repo, "Issue Y")
        z = _create(repo, "Issue Z")

        assert _stage(repo, x).exit_code == 0
        assert _stage(repo, y).exit_code == 0

        assert _diff_ids(repo, "--staged") == {x, y}
        assert _diff_ids(repo, "--unstaged") == {z}

    def test_commit_carries_staged_issue_only(self, repo: Path) -> None:
        """A plain git commit after stage leaves Y uncommitted."""
        x = _create(repo, "Issue X")
        y = _create(repo, "Issue Y")
        assert _stage(repo, x).exit_code == 0

        _git(repo, "commit", "-m", "x only")

        assert _diff_ids(repo, "--staged") == set()
        assert _diff_ids(repo, "--unstaged") == {y}


class TestHeldBackEdges:
    """An edge to an uncommitted, unstaged issue is left out."""

    def test_edge_to_uncommitted_issue_held_back(
        self, repo: Path, tmp_path: Path
    ) -> None:
        """The dependency stays unstaged, is named, and nothing dangles."""
        x = _create(repo, "Issue X")
        y = _create(repo, "Issue Y")
        _dcat(repo, "dep", x, "add", "--depends-on", y)

        result = _stage(repo, x)

        assert result.exit_code == 0, result.output
        held = json.loads(result.stdout)["held_back"]
        assert held == [
            {
                "kind": "dependency",
                "from_id": x,
                "to_id": y,
                "type": "blocks",
                "missing_id": y,
            }
        ]
        staged = _index_storage(repo, tmp_path)
        assert staged.get_dependencies(x) == []
        assert staged.find_dangling_dependencies() == []

    def test_held_back_edge_named_in_text_output(self, repo: Path) -> None:
        """The human output names the held-back edge and the missing id."""
        x = _create(repo, "Issue X")
        y = _create(repo, "Issue Y")
        _dcat(repo, "dep", x, "add", "--depends-on", y)

        result = _dcat(repo, "stage", x)

        assert f"Held back dependency {x} → {y}" in result.stdout
        assert f"{y} is not committed or staged" in result.stdout

    def test_restage_with_only_held_edge_left(self, repo: Path) -> None:
        """A second stage does not claim X is clean while its edge waits."""
        x = _create(repo, "Issue X")
        y = _create(repo, "Issue Y")
        _dcat(repo, "dep", x, "add", "--depends-on", y)
        _dcat(repo, "stage", x)

        result = _dcat(repo, "stage", x)

        assert f"{x}: nothing more to stage" in result.stdout
        assert f"Held back dependency {x} → {y}" in result.stdout

    def test_edge_staged_when_both_ids_staged_together(
        self, repo: Path, tmp_path: Path
    ) -> None:
        """Passing both endpoints in one call stages the edge."""
        x = _create(repo, "Issue X")
        y = _create(repo, "Issue Y")
        _dcat(repo, "dep", x, "add", "--depends-on", y)

        result = _stage(repo, x, y)

        assert json.loads(result.stdout)["held_back"] == []
        staged = _index_storage(repo, tmp_path)
        assert [d.depends_on_id for d in staged.get_dependencies(x)] == [y]

    def test_edge_staged_when_other_end_already_staged(
        self, repo: Path, tmp_path: Path
    ) -> None:
        """An endpoint staged by an earlier call counts as present."""
        x = _create(repo, "Issue X")
        y = _create(repo, "Issue Y")
        _dcat(repo, "dep", x, "add", "--depends-on", y)
        assert _stage(repo, y).exit_code == 0

        result = _stage(repo, x)

        assert json.loads(result.stdout)["held_back"] == []
        staged = _index_storage(repo, tmp_path)
        assert [d.depends_on_id for d in staged.get_dependencies(x)] == [y]

    def test_uncommitted_parent_warned(self, repo: Path) -> None:
        """A parent that is neither committed nor staged is named."""
        parent = _create(repo, "Parent")
        child = _create(repo, "Child", "--parent", parent)

        result = _stage(repo, child)

        assert json.loads(result.stdout)["unstaged_parents"] == {child: parent}


class TestRewriteSinceIndex:
    """A rewritten working file is staged from replayed state."""

    def test_compacted_store_stages_from_state(
        self, repo: Path, tmp_path: Path
    ) -> None:
        """X's changes, including a removed edge, stage; Y's stay unstaged."""
        x = _create(repo, "Issue X")
        y = _create(repo, "Issue Y")
        base = _create(repo, "Base")
        _dcat(repo, "dep", x, "add", "--depends-on", base)
        _commit_all(repo)
        _dcat(repo, "dep", x, "remove", "--depends-on", base)
        _dcat(repo, "update", x, "--title", "Issue X renamed")
        _dcat(repo, "update", y, "--title", "Issue Y renamed")
        JSONLStorage(str(repo / STORE))._save()  # pyright: ignore[reportPrivateUsage]

        result = _stage(repo, x)

        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["rewritten"] is True
        staged = _index_storage(repo, tmp_path)
        staged_x = staged.get(x)
        staged_y = staged.get(y)
        assert staged_x is not None
        assert staged_y is not None
        assert staged_x.title == "Issue X renamed"
        assert staged.get_dependencies(x) == []
        assert staged_y.title == "Issue Y"
        assert _diff_ids(repo, "--staged") == {x}
        assert _diff_ids(repo, "--unstaged") == {y}
        events = [e for e in _index_events(repo) if e["issue_id"] == x]
        assert any(
            e.get("changes", {}).get("title", {}).get("new") == "Issue X renamed"
            for e in events
        )

    def test_compacted_store_keeps_base_lines(self, repo: Path) -> None:
        """The blob starts with the index's bytes, so the commit only appends."""
        x = _create(repo, "Issue X")
        _commit_all(repo)
        committed = _git(repo, "show", f"HEAD:{STORE}")
        _dcat(repo, "update", x, "--title", "Renamed")
        JSONLStorage(str(repo / STORE))._save()  # pyright: ignore[reportPrivateUsage]

        assert _stage(repo, x).exit_code == 0

        assert _git(repo, "show", f":{STORE}").startswith(committed)


class TestStageErrors:
    """Unknown ids, no-op ids, and stores outside git."""

    def test_unknown_id_errors(self, repo: Path) -> None:
        """An id the store does not hold exits non-zero."""
        result = runner.invoke(
            app, ["stage", "nope", "--dogcats-dir", str(repo / ".dogcats")]
        )
        assert result.exit_code == 1

    def test_unchanged_id_exits_zero_with_message(self, repo: Path) -> None:
        """An already-committed issue reports no records and leaves the index."""
        x = _create(repo, "Issue X")
        _commit_all(repo)
        y = _create(repo, "Issue Y")

        result = _dcat(repo, "stage", x)

        assert f"{x}: no uncommitted records" in result.stdout
        assert _diff_ids(repo, "--staged") == set()
        assert _diff_ids(repo, "--unstaged") == {y}

    def test_store_outside_git_refused(self, tmp_path: Path) -> None:
        """A store with no enclosing repository is refused, not silently skipped."""
        dogcats = tmp_path / ".dogcats"
        assert (
            runner.invoke(app, ["init", "--dogcats-dir", str(dogcats)]).exit_code == 0
        )
        x = _create(tmp_path, "Issue X")

        result = runner.invoke(app, ["stage", x, "--dogcats-dir", str(dogcats)])

        assert result.exit_code == 1
        assert "not inside a git repository" in result.output


class TestPlanStage:
    """plan_stage over raw bytes, without git."""

    @staticmethod
    def _issue(full_id: str, title: str, **extra: Any) -> bytes:
        namespace, short = full_id.rsplit("-", 1)
        record = {
            "record_type": "issue",
            "namespace": namespace,
            "id": short,
            "title": title,
            "status": "open",
            "priority": 2,
            "issue_type": "task",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            **extra,
        }
        return orjson.dumps(record)

    def test_untracked_base_stages_onto_empty(self) -> None:
        """With nothing in the index the blob is X's lines alone."""
        x = self._issue("dc-aaaa", "X")
        y = self._issue("dc-bbbb", "Y")

        plan = plan_stage(b"", x + b"\n" + y + b"\n", ["dc-aaaa"])

        assert plan.blob == x + b"\n"
        assert plan.staged == {"dc-aaaa": 1}

    def test_no_changes_returns_base(self) -> None:
        """An id with nothing appended leaves the blob byte-identical."""
        base = self._issue("dc-aaaa", "X") + b"\n"

        plan = plan_stage(base, base, ["dc-aaaa"])

        assert plan.blob == base
        assert not plan.changed

    def test_base_without_trailing_newline(self) -> None:
        """Appended lines never fuse onto a base whose last line lacks a newline."""
        base = self._issue("dc-aaaa", "X")
        update = self._issue("dc-aaaa", "X2")

        plan = plan_stage(base, base + b"\n" + update + b"\n", ["dc-aaaa"])

        assert plan.blob == base + b"\n" + update + b"\n"

    def test_unknown_record_types_not_staged(self) -> None:
        """A record kind this dcat does not model is left in the working tree."""
        base = self._issue("dc-aaaa", "X") + b"\n"
        unknown = orjson.dumps({"record_type": "future", "issue_id": "dc-aaaa"})

        plan = plan_stage(base, base + unknown + b"\n", ["dc-aaaa"])

        assert plan.blob == base
