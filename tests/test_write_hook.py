"""Tests for the optional ``pre_write_hook`` (dogcat.write_hook)."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from dogcat import write_hook
from dogcat.cli import app
from dogcat.global_config import get_global_config_path, load_global_config
from dogcat.inbox import InboxStorage
from dogcat.storage import JSONLStorage
from dogcat.write_hook import WriteHookRejectedError

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()

# Rejects any write whose payload contains FORBIDDEN, and records every
# payload and the target it was told about, so tests can assert on both.
_HOOK_SCRIPT = """\
import os, sys
payload = sys.stdin.read()
log = sys.argv[1]
with open(log, "a", encoding="utf-8") as f:
    f.write(os.environ.get("DCAT_WRITE_TARGET", "") + "\\t" + payload)
if "FORBIDDEN" in payload:
    print("found FORBIDDEN in the record", file=sys.stderr)
    sys.exit(1)
"""


def _set_hook(command: str) -> None:
    path = get_global_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"pre_write_hook = {json.dumps(command)}\n")


@pytest.fixture
def hook_log(tmp_path: Path) -> Path:
    """Install the recording hook and return the log it writes to."""
    script = tmp_path / "hook.py"
    script.write_text(_HOOK_SCRIPT)
    log = tmp_path / "hook.log"
    _set_hook(shlex.join([sys.executable, str(script), str(log)]))
    return log


@pytest.fixture
def storage(temp_dogcats_dir: Path) -> JSONLStorage:
    """Return an empty issue store."""
    return JSONLStorage(str(temp_dogcats_dir / "issues.jsonl"), create_dir=True)


class TestConfig:
    """Reading the hook from the global config."""

    def test_unset_by_default(self) -> None:
        """No global config means no hook."""
        assert load_global_config().pre_write_hook is None

    def test_blank_command_counts_as_unset(self) -> None:
        """A whitespace-only value must not run an empty shell command."""
        _set_hook("   ")
        assert load_global_config().pre_write_hook is None

    def test_config_set_global(self) -> None:
        """`dcat config set --global pre_write_hook` writes the global file."""
        result = runner.invoke(
            app, ["config", "set", "--global", "pre_write_hook", "true"]
        )
        assert result.exit_code == 0, result.output
        assert load_global_config().pre_write_hook == "true"

    def test_config_set_without_global_is_refused(self, temp_dogcats_dir: Path) -> None:
        """A store's config.toml is often committed, so it can't carry a hook."""
        runner.invoke(app, ["init", "--dogcats-dir", str(temp_dogcats_dir)])
        result = runner.invoke(app, ["config", "set", "pre_write_hook", "true"])
        assert result.exit_code == 2
        assert "global-only" in result.output

    def test_store_config_is_ignored(
        self, storage: JSONLStorage, temp_dogcats_dir: Path
    ) -> None:
        """A hook in a store's own config.toml never runs."""
        (temp_dogcats_dir / "config.toml").write_text('pre_write_hook = "false"\n')
        issue = storage.create_issue(namespace="test", title="harmless")
        assert storage.get(issue.full_id) is not None


class TestIssueStore:
    """The hook in front of issues.jsonl."""

    def test_allowed_write_lands_and_hook_sees_the_records(
        self, storage: JSONLStorage, hook_log: Path
    ) -> None:
        """Exit 0 lets the write through; the hook got the JSONL and target."""
        issue = storage.create_issue(
            namespace="test", title="ordinary", description="nothing here"
        )

        assert JSONLStorage(str(storage.path)).get(issue.full_id) is not None
        target, payload = hook_log.read_text().split("\t", 1)
        assert target == str(storage.path)
        records = [json.loads(line) for line in payload.splitlines()]
        assert any(r.get("title") == "ordinary" for r in records)

    def test_rejected_create_writes_nothing(
        self, storage: JSONLStorage, hook_log: Path
    ) -> None:
        """A refused create leaves the file and the in-memory store untouched."""
        storage.create_issue(namespace="test", title="first")
        before = storage.path.read_bytes()

        with pytest.raises(WriteHookRejectedError, match="exit 1"):
            storage.create_issue(
                namespace="test", title="second", description="FORBIDDEN token"
            )

        assert storage.path.read_bytes() == before
        assert [i.title for i in storage.list()] == ["first"]
        assert hook_log.exists()

    def test_rejected_update_rolls_back_memory(
        self, storage: JSONLStorage, hook_log: Path
    ) -> None:
        """A long-lived process must not keep showing the refused value."""
        issue = storage.create_issue(namespace="test", title="t", description="clean")
        assert hook_log.exists()

        with pytest.raises(WriteHookRejectedError):
            storage.update(issue.full_id, {"description": "FORBIDDEN"})

        refreshed = storage.get(issue.full_id)
        assert refreshed is not None
        assert refreshed.description == "clean"

    def test_rejected_batch_writes_nothing(
        self, storage: JSONLStorage, hook_log: Path
    ) -> None:
        """The buffered batch is vetted as one payload at flush."""
        before = storage.path.read_bytes() if storage.path.exists() else b""
        with pytest.raises(WriteHookRejectedError), storage.batch():  # noqa: PT012
            storage.create_issue(namespace="test", title="a")
            storage.create_issue(namespace="test", title="b", notes="FORBIDDEN")

        after = storage.path.read_bytes() if storage.path.exists() else b""
        assert after == before
        assert storage.list() == []
        assert hook_log.exists()

    def test_refused_record_survives_no_corrupt_tail_rewrite(
        self, storage: JSONLStorage, hook_log: Path
    ) -> None:
        """The corrupt-tail compaction runs after the hook, not before it.

        That rewrite is made from memory, where the refused record already
        sits, so running it first would write the secret to disk.
        """
        storage.create_issue(namespace="test", title="first")
        with storage.path.open("ab") as f:
            f.write(b'{"truncated')
        storage = JSONLStorage(str(storage.path))
        assert storage._needs_compaction  # pyright: ignore[reportPrivateUsage]

        with pytest.raises(WriteHookRejectedError):
            storage.create_issue(namespace="test", title="x", description="FORBIDDEN")

        assert storage.path.read_bytes().endswith(b'{"truncated')
        assert b"FORBIDDEN" not in storage.path.read_bytes()
        assert hook_log.exists()


class TestFailsClosed:
    """A hook that can't do its job blocks the write."""

    def test_missing_command_rejects(self, storage: JSONLStorage) -> None:
        """A typo in the command must not quietly disable scanning."""
        _set_hook("dcat-no-such-scanner-xyz")
        with pytest.raises(WriteHookRejectedError, match="exit 127"):
            storage.create_issue(namespace="test", title="t")
        assert not storage.path.exists() or storage.list() == []

    def test_timeout_rejects(
        self, storage: JSONLStorage, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A hung hook is cut off and the write refused."""
        monkeypatch.setattr(write_hook, "HOOK_TIMEOUT_SECS", 0.2)
        _set_hook(shlex.join([sys.executable, "-c", "import time; time.sleep(5)"]))
        with pytest.raises(WriteHookRejectedError, match="timed out"):
            storage.create_issue(namespace="test", title="t")


class TestInboxStore:
    """The hook in front of inbox.jsonl."""

    def test_rejected_proposal_writes_nothing(
        self, temp_dogcats_dir: Path, hook_log: Path
    ) -> None:
        """Proposals from `dcat propose` and the web form are vetted too."""
        inbox = InboxStorage(dogcats_dir=str(temp_dogcats_dir))
        inbox.create_proposal(title="fine")
        before = inbox.path.read_bytes()

        with pytest.raises(WriteHookRejectedError):
            inbox.create_proposal(title="leak", description="FORBIDDEN")

        assert inbox.path.read_bytes() == before
        assert [p.title for p in inbox.list()] == ["fine"]
        target = hook_log.read_text().split("\t", 1)[0]
        assert target == str(inbox.path)


class TestCli:
    """What a refused write looks like from the command line."""

    def test_create_hides_hook_output_and_exits_1(
        self, temp_dogcats_dir: Path, hook_log: Path
    ) -> None:
        """The hook's message stays private, and no issue is created."""
        runner.invoke(app, ["init", "--dogcats-dir", str(temp_dogcats_dir)])
        result = runner.invoke(
            app,
            [
                "create",
                "leaky",
                "-d",
                "FORBIDDEN",
                "--dogcats-dir",
                str(temp_dogcats_dir),
            ],
        )
        assert result.exit_code == 1
        assert "pre_write_hook rejected the write" in result.output
        assert "found FORBIDDEN" not in result.output
        assert b"leaky" not in (temp_dogcats_dir / "issues.jsonl").read_bytes()
        assert hook_log.exists()


@pytest.mark.skipif(shutil.which("gitleaks") is None, reason="gitleaks not installed")
def test_gitleaks_blocks_a_token(storage: JSONLStorage) -> None:
    """The documented gitleaks command catches a token in a description."""
    _set_hook("gitleaks stdin --no-banner --redact")
    storage.create_issue(
        namespace="test", title="no secrets", description="see the runbook"
    )

    # Assembled at runtime so this file doesn't trip secret scanners itself.
    token = "ghp_" + "Zx81Kq0LmT4vR7nB2cYw9sHd5jFg3aPe6uQi"
    with pytest.raises(WriteHookRejectedError, match="exit"):
        storage.create_issue(
            namespace="test", title="deploy", description=f"token {token}"
        )

    assert token.encode() not in storage.path.read_bytes()


class TestRuntime:
    """Exercise fail-closed behavior without relying on storage rollback."""

    @pytest.mark.parametrize(
        "contents", [b"pre_write_hook = [", b"pre_write_hook = 42", b"\xff"]
    )
    def test_invalid_config_rejects_but_read_config_is_forgiving(
        self, contents: bytes, tmp_path: Path
    ) -> None:
        """Check the runtime contract for this case."""
        path = get_global_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
        assert load_global_config().pre_write_hook is None
        with pytest.raises(WriteHookRejectedError, match="Invalid global config"):
            write_hook.run_pre_write_hook(b"data", tmp_path / "issues.jsonl")

    def test_unreadable_config_rejects(self, tmp_path: Path) -> None:
        """Check the runtime contract for this case."""
        path = get_global_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.mkdir()
        with pytest.raises(WriteHookRejectedError, match="Invalid global config"):
            write_hook.run_pre_write_hook(b"data", tmp_path / "issues.jsonl")

    @pytest.mark.parametrize("command", [None, "", "   "])
    def test_no_hook_starts_no_process(
        self, command: str | None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Check the runtime contract for this case."""
        if command is not None:
            _set_hook(command)

        def unexpected(*_args: object, **_kwargs: object) -> None:
            pytest.fail("started a process without a hook")

        monkeypatch.setattr(subprocess, "Popen", unexpected)
        write_hook.run_pre_write_hook(b"data", tmp_path / "issues.jsonl")

    def test_start_failure_and_invalid_command_reject(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Check the runtime contract for this case."""
        target = tmp_path / "issues.jsonl"
        _set_hook("bad\x00command")
        with pytest.raises(WriteHookRejectedError, match="could not start"):
            write_hook.run_pre_write_hook(b"data", target)
        _set_hook("true")

        def fail(*_args: object, **_kwargs: object) -> None:
            msg = "private detail"
            raise OSError(msg)

        monkeypatch.setattr(subprocess, "Popen", fail)
        with pytest.raises(WriteHookRejectedError, match="could not start") as exc:
            write_hook.run_pre_write_hook(b"data", target)
        assert "private detail" not in str(exc.value)

    def test_exact_bytes_and_target(
        self, tmp_path: Path, capfd: pytest.CaptureFixture[str]
    ) -> None:
        """Check the runtime contract for this case."""
        script = tmp_path / "record.py"
        payload_file = tmp_path / "payload"
        target_file = tmp_path / "target"
        script.write_text(
            "import os, pathlib, sys\n"
            "pathlib.Path(sys.argv[1]).write_bytes(sys.stdin.buffer.read())\n"
            "pathlib.Path(sys.argv[2]).write_text(os.environ['DCAT_WRITE_TARGET'])\n"
            "print('private stdout')\n"
            "print('private stderr', file=sys.stderr)\n"
        )
        _set_hook(
            shlex.join(
                [sys.executable, str(script), str(payload_file), str(target_file)]
            )
        )
        target = tmp_path / "a target.jsonl"
        payload = b'\x00\xff{"x":1}\n{"x":2}\n'
        write_hook.run_pre_write_hook(payload, target)
        assert payload_file.read_bytes() == payload
        assert target_file.read_text() == str(target)
        captured = capfd.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    @pytest.mark.skipif(os.name != "posix", reason="POSIX process groups")
    def test_timeout_kills_descendant(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Check the runtime contract for this case."""
        marker = tmp_path / "descendant-survived"
        started = tmp_path / "started"
        script = tmp_path / "child.py"
        script.write_text(
            "import pathlib, sys, time\n"
            "pathlib.Path(sys.argv[1]).write_text('ready')\n"
            "time.sleep(1.5)\n"
            "pathlib.Path(sys.argv[2]).write_text('alive')\n"
        )
        _set_hook(shlex.join([sys.executable, str(script), str(started), str(marker)]))
        monkeypatch.setattr(write_hook, "HOOK_TIMEOUT_SECS", 0.5)
        start = time.monotonic()
        with pytest.raises(WriteHookRejectedError, match="timed out"):
            write_hook.run_pre_write_hook(b"data", tmp_path / "issues")
        assert time.monotonic() - start < 1.5
        assert started.exists()
        time.sleep(max(0, 1.8 - (time.monotonic() - start)))
        assert not marker.exists()


def test_rejected_first_writes_then_clean(
    temp_dogcats_dir: Path, hook_log: Path
) -> None:
    store = JSONLStorage(str(temp_dogcats_dir / "issues.jsonl"), create_dir=True)
    inbox = InboxStorage(dogcats_dir=str(temp_dogcats_dir))
    with pytest.raises(WriteHookRejectedError):
        store.create_issue(namespace="test", title="FORBIDDEN")
    with pytest.raises(WriteHookRejectedError):
        inbox.create_proposal(title="FORBIDDEN")
    assert not store.path.exists()
    assert not inbox.path.exists()
    store.create_issue(namespace="test", title="clean")
    inbox.create_proposal(title="clean")
    assert b"FORBIDDEN" not in store.path.read_bytes()
    assert b"FORBIDDEN" not in inbox.path.read_bytes()
    assert hook_log.exists()


def test_namespace_preflight_rolls_back_and_checks_once(
    storage: JSONLStorage, hook_log: Path
) -> None:
    issue = storage.create_issue(namespace="test", title="clean")
    before = storage.path.read_bytes()
    with pytest.raises(WriteHookRejectedError):
        storage.change_namespace(issue.full_id, "other", updated_by="FORBIDDEN")
    assert storage.path.read_bytes() == before
    assert storage.get(issue.full_id) is not None
    hook_log.unlink()
    renamed = storage.change_namespace(issue.full_id, "other")
    assert renamed.namespace == "other"
    events = [json.loads(line) for line in storage.path.read_text().splitlines()]
    events = [event for event in events if event.get("record_type") == "event"]
    assert {event["issue_id"] for event in events} == {renamed.full_id}
    assert any(
        event.get("changes", {}).get("namespace") == {"old": "test", "new": "other"}
        for event in events
    )
    assert hook_log.read_text().count(str(storage.path) + "\t") == 1


def test_inbox_namespace_rejection_restores_memory(
    temp_dogcats_dir: Path, hook_log: Path
) -> None:
    inbox = InboxStorage(dogcats_dir=str(temp_dogcats_dir))
    proposal = inbox.create_proposal(title="clean", namespace="test")
    before = inbox.path.read_bytes()
    with pytest.raises(WriteHookRejectedError):
        inbox.rename_namespace("test", "FORBIDDEN")
    assert inbox.path.read_bytes() == before
    assert inbox.get(proposal.full_id) is not None
    assert hook_log.exists()


@pytest.mark.parametrize("log_class", ["EventLog", "InboxEventLog"])
def test_direct_events_rejected(
    temp_dogcats_dir: Path, hook_log: Path, log_class: str
) -> None:
    from dogcat import event_log

    log = getattr(event_log, log_class)(temp_dogcats_dir)
    event = event_log.EventRecord("updated", "test-1", "2026-01-01", title="FORBIDDEN")
    with pytest.raises(WriteHookRejectedError):
        log.append(event)
    with pytest.raises(WriteHookRejectedError):
        log.try_emit("updated", "test-1", "2026-01-01", "FORBIDDEN", {"x": {"new": 1}})
    assert not log.path.exists()
    assert hook_log.exists()


def test_bulk_namespace_preflight(storage: JSONLStorage, hook_log: Path) -> None:
    first = storage.create_issue(namespace="test", title="first")
    storage.create_issue(namespace="test", title="second")
    before = storage.path.read_bytes()
    with pytest.raises(WriteHookRejectedError):
        storage.rename_namespace("test", "other", updated_by="FORBIDDEN")
    assert storage.path.read_bytes() == before
    assert storage.get(first.full_id) is not None
    hook_log.unlink()
    renamed = storage.rename_namespace("test", "other")
    assert len(renamed) == 2
    events = [json.loads(line) for line in storage.path.read_text().splitlines()]
    events = [event for event in events if event.get("record_type") == "event"]
    assert {event["issue_id"] for event in events} == {
        issue.full_id for issue in renamed
    }
    namespace_events = [
        event
        for event in events
        if event.get("changes", {}).get("namespace") == {"old": "test", "new": "other"}
    ]
    assert {event["issue_id"] for event in namespace_events} == {
        issue.full_id for issue in renamed
    }
    assert hook_log.read_text().count(str(storage.path) + "\t") == 1


def test_inbox_batch_rejection(temp_dogcats_dir: Path, hook_log: Path) -> None:
    inbox = InboxStorage(dogcats_dir=str(temp_dogcats_dir))
    with pytest.raises(WriteHookRejectedError), inbox.batch():  # noqa: PT012
        inbox.create_proposal(title="clean")
        inbox.create_proposal(title="FORBIDDEN")
    assert not inbox.path.exists()
    assert inbox.list() == []
    inbox.create_proposal(title="later")
    assert b"FORBIDDEN" not in inbox.path.read_bytes()
    assert hook_log.exists()


def test_web_proposal_rejection(temp_dogcats_dir: Path, hook_log: Path) -> None:
    from fastapi.testclient import TestClient

    from dogcat.config import DogcatConfig, save_config
    from dogcat.web.propose import create_app
    from tests.test_web_propose import _csrf

    (temp_dogcats_dir / "issues.jsonl").touch()
    (temp_dogcats_dir / "inbox.jsonl").touch()
    save_config(str(temp_dogcats_dir), DogcatConfig.from_dict({"namespace": "test"}))
    client = TestClient(create_app(dogcats_dir=str(temp_dogcats_dir)))
    token = _csrf(client)
    response = client.post(
        "/", data={"csrf_token": token, "namespace": "test", "title": "FORBIDDEN"}
    )
    assert "Could not save the proposal" in response.text
    assert "Proposal submitted" not in response.text
    assert (temp_dogcats_dir / "inbox.jsonl").read_bytes() == b""
    response = client.post(
        "/", data={"csrf_token": _csrf(client), "namespace": "test", "title": "clean"}
    )
    assert "Proposal submitted" in response.text
    assert b"FORBIDDEN" not in (temp_dogcats_dir / "inbox.jsonl").read_bytes()
    assert hook_log.exists()


def test_acceptance_policy_example(storage: JSONLStorage) -> None:
    from pathlib import Path

    script = (
        Path(__file__).resolve().parents[1] / "examples/hooks/require_acceptance.py"
    )
    _set_hook(shlex.join([sys.executable, str(script)]))
    issue = storage.create_issue(namespace="test", title="draft")
    before = storage.path.read_bytes()
    with pytest.raises(WriteHookRejectedError, match="exit 10"):
        storage.update(issue.full_id, {"status": "in_progress"})
    assert storage.path.read_bytes() == before
    storage.update(issue.full_id, {"acceptance": "It works"})
    assert (
        storage.update(issue.full_id, {"status": "in_progress"}).status == "in_progress"
    )


def test_relative_target_is_absolute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    target_file = tmp_path / "target"
    script = tmp_path / "target.py"
    script.write_text(
        "import os, pathlib, sys\n"
        "pathlib.Path(sys.argv[1]).write_text(os.environ['DCAT_WRITE_TARGET'])\n"
    )
    _set_hook(shlex.join([sys.executable, str(script), str(target_file)]))
    from pathlib import Path

    write_hook.run_pre_write_hook(b"data", Path("relative.jsonl"))
    assert target_file.read_text() == str(tmp_path / "relative.jsonl")
