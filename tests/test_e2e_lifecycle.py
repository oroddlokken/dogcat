"""E2E tests for full issue lifecycle and concurrent process access."""

from __future__ import annotations

import json
import subprocess
import sys
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from dogcat.cli import app
from dogcat.storage import JSONLStorage

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()


def _invoke(dogcats_dir: Path, args: list[str]) -> str:
    """Invoke CLI and return stdout, asserting exit code 0."""
    result = runner.invoke(app, [*args, "--dogcats-dir", str(dogcats_dir)])
    assert result.exit_code == 0, f"CLI failed: {result.stdout}\n{result.output}"
    return result.stdout


def _extract_id(create_output: str) -> str:
    """Extract issue ID from create command output."""
    return create_output.split(": ")[0].split()[-1]


class TestFullLifecycleWithReopen:
    """E2E test: create -> update -> close -> reopen -> close via CLI."""

    def test_complete_lifecycle(self, tmp_path: Path) -> None:
        """Full lifecycle: create, update, close, reopen, update, close."""
        dd = tmp_path / ".dogcats"
        _invoke(dd, ["init"])

        # Create
        out = _invoke(
            dd, ["create", "Lifecycle bug", "--type", "bug", "--priority", "1"]
        )
        issue_id = _extract_id(out)

        # Update to in_progress
        _invoke(dd, ["update", issue_id, "--status", "in_progress"])
        show = _invoke(dd, ["show", issue_id])
        assert "in_progress" in show

        # Close
        _invoke(dd, ["close", issue_id, "--reason", "Fixed"])
        show = _invoke(dd, ["show", issue_id])
        assert "closed" in show.lower()

        # Verify it appears in recently-closed
        rc = _invoke(dd, ["recently-closed"])
        assert issue_id in rc

        # Reopen
        _invoke(dd, ["reopen", issue_id, "--reason", "Bug returned"])
        show = _invoke(dd, ["show", issue_id])
        assert "open" in show.lower()

        # Verify it shows as open in list (not filtered to closed)
        list_out = _invoke(dd, ["list"])
        assert issue_id in list_out

        # Update again
        _invoke(dd, ["update", issue_id, "--status", "in_progress"])
        _invoke(dd, ["update", issue_id, "--title", "Lifecycle bug (confirmed)"])

        # Close again
        _invoke(dd, ["close", issue_id, "--reason", "Actually fixed this time"])

        # Verify final state via JSON
        result = runner.invoke(
            app,
            ["show", issue_id, "--json", "--dogcats-dir", str(dd)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["status"] == "closed"
        assert data["title"] == "Lifecycle bug (confirmed)"

    def test_reopen_non_closed_fails(self, tmp_path: Path) -> None:
        """Reopening an open issue should fail."""
        dd = tmp_path / ".dogcats"
        _invoke(dd, ["init"])
        out = _invoke(dd, ["create", "Open issue", "--type", "task"])
        issue_id = _extract_id(out)

        result = runner.invoke(
            app,
            ["reopen", issue_id, "--dogcats-dir", str(dd)],
        )
        assert result.exit_code != 0

    def test_lifecycle_with_dependencies(self, tmp_path: Path) -> None:
        """Lifecycle with dependency chain: create deps, close blocker, verify ready."""
        dd = tmp_path / ".dogcats"
        _invoke(dd, ["init"])

        # Create parent and child
        out_a = _invoke(dd, ["create", "Blocker task", "--type", "task"])
        id_a = _extract_id(out_a)
        out_b = _invoke(dd, ["create", "Blocked task", "--type", "task"])
        id_b = _extract_id(out_b)

        # Add dependency: B depends on A
        _invoke(dd, ["dep", id_b, "add", "--depends-on", id_a])

        # B should be blocked
        blocked = _invoke(dd, ["blocked"])
        assert id_b in blocked

        # Close A
        _invoke(dd, ["close", id_a, "--reason", "Done"])

        # B should now be ready
        ready = _invoke(dd, ["ready"])
        assert id_b in ready

    def test_history_reflects_all_operations(self, tmp_path: Path) -> None:
        """History command shows all lifecycle events."""
        dd = tmp_path / ".dogcats"
        _invoke(dd, ["init"])

        out = _invoke(dd, ["create", "History test", "--type", "task"])
        issue_id = _extract_id(out)

        _invoke(dd, ["update", issue_id, "--status", "in_progress"])
        _invoke(dd, ["close", issue_id, "--reason", "Done"])
        _invoke(dd, ["reopen", issue_id, "--reason", "Not done"])

        history = _invoke(dd, ["history", "-i", issue_id])
        assert "created" in history.lower()
        assert "closed" in history.lower()
        assert "reopen_reason" in history.lower()


class TestConcurrentProcessAccess:
    """E2E test: concurrent subprocess access to the same JSONL file."""

    def test_concurrent_creates_via_subprocess(self, tmp_path: Path) -> None:
        """Two subprocesses creating issues simultaneously both succeed."""
        dd = tmp_path / ".dogcats"
        dd.mkdir()
        storage_path = dd / "issues.jsonl"
        storage_path.touch()

        # Spawn two dcat processes in parallel
        procs = []
        for i in range(2):
            proc = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    f"""
import sys
sys.path.insert(0, 'src')
from dogcat.models import Issue
from dogcat.storage import JSONLStorage
s = JSONLStorage('{storage_path}')
for j in range(5):
    s.create(Issue(id=f'proc{i}-{{j}}', title=f'Issue from proc {i} #{{j}}'))
""",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            procs.append(proc)

        # Wait for both
        for proc in procs:
            _stdout, stderr = proc.communicate(timeout=30)
            assert proc.returncode == 0, f"Process failed: {stderr.decode()}"

        # Verify all 10 issues exist
        s = JSONLStorage(str(storage_path))
        issues = s.list()
        assert len(issues) == 10

        # Verify file is valid JSONL
        import orjson

        for line in storage_path.read_text().splitlines():
            if line.strip():
                orjson.loads(line)

    def test_concurrent_updates_via_subprocess(self, tmp_path: Path) -> None:
        """Two subprocesses updating the same issue don't corrupt the file."""
        dd = tmp_path / ".dogcats"
        dd.mkdir()
        storage_path = dd / "issues.jsonl"
        storage_path.touch()

        # Seed an issue
        s = JSONLStorage(str(storage_path))
        from dogcat.models import Issue

        s.create(Issue(id="shared", title="Shared issue"))

        # Spawn two processes that update the same issue
        procs = []
        for i in range(2):
            proc = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    f"""
import sys
sys.path.insert(0, 'src')
from dogcat.storage import JSONLStorage
s = JSONLStorage('{storage_path}')
for j in range(5):
    s.update('dc-shared', {{'title': f'Updated by proc {i} round {{j}}'}})
""",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            procs.append(proc)

        for proc in procs:
            _stdout, stderr = proc.communicate(timeout=30)
            assert proc.returncode == 0, f"Process failed: {stderr.decode()}"

        # File should be valid and issue should exist
        s2 = JSONLStorage(str(storage_path))
        issue = s2.get("shared")
        assert issue is not None
        assert "Updated by proc" in issue.title

        # Verify file integrity
        import orjson

        for line in storage_path.read_text().splitlines():
            if line.strip():
                orjson.loads(line)
