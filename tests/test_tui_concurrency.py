"""TUI storage mutations run off the Textual event loop (dogcat-46i8).

The write path takes an advisory flock that a concurrent ``dcat`` process can
hold for up to the lock timeout. These tests hold that lock from the test
process and assert the app still handles input while the write waits.
"""

from __future__ import annotations

import asyncio
import fcntl
import threading
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Button, Input
from tui_test_helpers import wait_for_workers

from dogcat.constants import LOCK_FILENAME
from dogcat.locking import LOCK_TIMEOUT_ENV_VAR
from dogcat.models import Issue
from dogcat.storage import JSONLStorage
from dogcat.tui.dashboard import ConfirmDeleteScreen, DogcatTUI
from dogcat.tui.detail_panel import IssueDetailPanel

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

# A held lock must not stall the loop, so every await below is bounded. The
# waits are for a message round trip, not for the lock: 2s is orders of
# magnitude above that and still well under the 5s lock timeout the tests set.
_RESPONSE_TIMEOUT = 2.0


@contextmanager
def _hold_store_lock(dogcats_dir: Path) -> Generator[None]:
    """Hold the store's advisory lock the way a concurrent dcat process does.

    ``flock`` conflicts between open file descriptions, not processes, so a
    second fd opened here blocks the writer even in the same process.
    """
    lock_fd = (dogcats_dir / LOCK_FILENAME).open("w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()


class _PanelApp(App[None]):
    """Host app that records what the panel posts."""

    def __init__(self, issue: Issue, storage: Any) -> None:
        super().__init__()
        self._issue = issue
        self._storage = storage
        self.saved: list[Issue] = []
        self.cancelled = 0

    def compose(self) -> ComposeResult:
        yield IssueDetailPanel(self._issue, self._storage, id="panel")

    def on_issue_detail_panel_saved(self, event: IssueDetailPanel.Saved) -> None:
        self.saved.append(event.issue)

    def on_issue_detail_panel_cancelled(
        self,
        event: IssueDetailPanel.Cancelled,  # noqa: ARG002
    ) -> None:
        self.cancelled += 1


def _make_store(tmp_path: Path) -> JSONLStorage:
    """Build a real JSONLStorage in a temp dir (the flock has to be real)."""
    return JSONLStorage(str(tmp_path / ".dogcats" / "issues.jsonl"), create_dir=True)


def _reread(storage: JSONLStorage, full_id: str) -> Issue:
    """Read an issue back from disk, bypassing the in-memory copy."""
    fresh = JSONLStorage(str(storage.path))
    issue = fresh.get(full_id)
    assert issue is not None, full_id
    return issue


class TestContendedSave:
    """The acceptance criterion: responsive during a save that waits on the lock."""

    @pytest.mark.asyncio
    async def test_app_handles_input_while_save_waits_for_the_lock(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Keystrokes are handled while the write is queued behind the lock."""
        monkeypatch.setenv(LOCK_TIMEOUT_ENV_VAR, "5")
        storage = _make_store(tmp_path)
        issue = storage.create(Issue(id="lock1", title="Original"))

        app = _PanelApp(issue, storage)
        async with app.run_test() as pilot:
            panel = app.query_one("#panel", IssueDetailPanel)
            panel.query_one("#title-input", Input).value = "Renamed"

            with _hold_store_lock(storage.dogcats_dir):
                await asyncio.wait_for(pilot.press("ctrl+s"), timeout=_RESPONSE_TIMEOUT)
                assert panel._save_in_flight is True

                # The loop is still dispatching keys while the worker waits.
                panel.query_one("#owner-input", Input).focus()
                await asyncio.wait_for(pilot.press("z"), timeout=_RESPONSE_TIMEOUT)
                assert panel.query_one("#owner-input", Input).value == "z"

                # And the write has not landed: the lock holder still has it.
                assert _reread(storage, issue.full_id).title == "Original"
                assert app.saved == []

            await asyncio.wait_for(wait_for_workers(app), timeout=10)
            await pilot.pause()

        assert [i.title for i in app.saved] == ["Renamed"]
        stored = _reread(storage, issue.full_id)
        assert stored.title == "Renamed"
        # The form was snapshotted at dispatch, so the keystroke typed during
        # the wait is not part of the write.
        assert stored.owner is None

    @pytest.mark.asyncio
    async def test_second_save_is_refused_while_one_is_in_flight(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A second Ctrl+S during a queued write does not queue a second one."""
        monkeypatch.setenv(LOCK_TIMEOUT_ENV_VAR, "5")
        storage = _make_store(tmp_path)
        issue = storage.create(Issue(id="lock2", title="Original"))

        app = _PanelApp(issue, storage)
        async with app.run_test() as pilot:
            panel = app.query_one("#panel", IssueDetailPanel)
            title = panel.query_one("#title-input", Input)
            title.value = "First"

            with (
                _hold_store_lock(storage.dogcats_dir),
                patch.object(panel, "notify") as notify_spy,
            ):
                await asyncio.wait_for(pilot.press("ctrl+s"), timeout=_RESPONSE_TIMEOUT)
                title.value = "Second"
                await asyncio.wait_for(pilot.press("ctrl+s"), timeout=_RESPONSE_TIMEOUT)
                messages = [str(c.args[0]) for c in notify_spy.call_args_list]
                assert any("Save in progress" in m for m in messages), messages

            await asyncio.wait_for(wait_for_workers(app), timeout=10)
            await pilot.pause()

        assert [i.title for i in app.saved] == ["First"]
        assert _reread(storage, issue.full_id).title == "First"

    @pytest.mark.asyncio
    async def test_cancel_is_refused_while_a_save_is_in_flight(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Cancel cannot recall a dispatched write, so it waits for the outcome."""
        monkeypatch.setenv(LOCK_TIMEOUT_ENV_VAR, "5")
        storage = _make_store(tmp_path)
        issue = storage.create(Issue(id="lock3", title="Original"))

        app = _PanelApp(issue, storage)
        async with app.run_test() as pilot:
            panel = app.query_one("#panel", IssueDetailPanel)
            panel.query_one("#title-input", Input).value = "Renamed"

            with _hold_store_lock(storage.dogcats_dir):
                await asyncio.wait_for(pilot.press("ctrl+s"), timeout=_RESPONSE_TIMEOUT)
                panel.query_one("#cancel-btn", Button).press()
                await asyncio.wait_for(pilot.pause(), timeout=_RESPONSE_TIMEOUT)
                assert app.cancelled == 0

            await asyncio.wait_for(wait_for_workers(app), timeout=10)
            await pilot.pause()

        assert [i.title for i in app.saved] == ["Renamed"]
        assert app.cancelled == 0


class TestLateResultHandling:
    """A result that arrives after the panel moved on must not move it back."""

    @pytest.mark.asyncio
    async def test_result_for_a_replaced_issue_does_not_post_saved(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """load_issue during a write keeps the new issue on screen."""
        monkeypatch.setenv(LOCK_TIMEOUT_ENV_VAR, "5")
        storage = _make_store(tmp_path)
        edited = storage.create(Issue(id="stale1", title="Original"))
        other = storage.create(Issue(id="other2", title="Other issue"))

        app = _PanelApp(edited, storage)
        async with app.run_test() as pilot:
            panel = app.query_one("#panel", IssueDetailPanel)
            panel.query_one("#title-input", Input).value = "Renamed"

            with _hold_store_lock(storage.dogcats_dir):
                await asyncio.wait_for(pilot.press("ctrl+s"), timeout=_RESPONSE_TIMEOUT)
                await asyncio.wait_for(
                    panel.load_issue(other), timeout=_RESPONSE_TIMEOUT
                )

            await asyncio.wait_for(wait_for_workers(app), timeout=10)
            await pilot.pause()

            # The panel keeps showing the issue the user navigated to.
            assert panel.issue.full_id == other.full_id
            assert panel.query_one("#title-input", Input).value == "Other issue"

        # No Saved for the issue that is no longer on screen ...
        assert app.saved == []
        # ... but the write itself committed.
        assert _reread(storage, edited.full_id).title == "Renamed"


class TestWorkerErrorsSurface:
    """Errors raised on the worker thread reach the UI, as the sync path did."""

    @pytest.mark.asyncio
    async def test_save_failure_notifies(self, tmp_path: Path) -> None:
        """A storage.update failure inside the worker is reported."""
        storage = MagicMock(spec=JSONLStorage)
        storage.get.return_value = None
        storage.get_dependencies.return_value = []
        storage.get_dependents.return_value = []
        storage.get_children.return_value = []
        storage.dogcats_dir = tmp_path
        storage.update.side_effect = RuntimeError("disk on fire")

        issue = Issue(id="err1", title="Original", namespace="dc")
        app = _PanelApp(issue, storage)
        async with app.run_test() as pilot:
            panel = app.query_one("#panel", IssueDetailPanel)
            panel.query_one("#title-input", Input).value = "Renamed"

            with patch.object(panel, "notify") as notify_spy:
                panel.do_save()
                await asyncio.wait_for(wait_for_workers(app), timeout=10)
                await pilot.pause()

                messages = [str(c.args[0]) for c in notify_spy.call_args_list]
                assert any("disk on fire" in m for m in messages), messages

            assert app.saved == []
            # The panel is usable again, so the user can retry.
            assert panel._save_in_flight is False

    @pytest.mark.asyncio
    async def test_delete_failure_notifies(self, tmp_path: Path) -> None:
        """A storage.delete failure inside the worker is reported."""
        issue = Issue(id="err2", title="Doomed", namespace="dc")
        storage = MagicMock(spec=JSONLStorage)
        storage.list.return_value = [issue]
        storage.get.return_value = issue
        storage.get_children.return_value = []
        storage.get_dependencies.return_value = []
        storage.get_issue_ids.return_value = {issue.full_id}
        dogcats = tmp_path / ".dogcats"
        dogcats.mkdir(parents=True, exist_ok=True)
        storage.dogcats_dir = dogcats
        storage.delete.side_effect = RuntimeError("read-only store")

        app = DogcatTUI(storage)
        async with app.run_test() as pilot:
            with patch.object(app, "notify") as notify_spy:
                app.action_delete_issue()
                await pilot.pause()
                confirm = next(
                    s for s in app.screen_stack if isinstance(s, ConfirmDeleteScreen)
                )
                confirm.action_confirm()
                await pilot.pause()
                await asyncio.wait_for(wait_for_workers(app), timeout=10)
                await pilot.pause()

                messages = [str(c.args[0]) for c in notify_spy.call_args_list]
                assert any("read-only store" in m for m in messages), messages


class TestDashboardWorkOffLoop:
    """Delete and reload run on a worker thread, not the loop."""

    @pytest.mark.asyncio
    async def test_delete_runs_on_a_worker_thread(self, tmp_path: Path) -> None:
        """storage.delete is called off the main thread."""
        issue = Issue(id="thr1", title="Doomed", namespace="dc")
        storage = MagicMock(spec=JSONLStorage)
        storage.list.return_value = [issue]
        storage.get.return_value = issue
        storage.get_children.return_value = []
        storage.get_dependencies.return_value = []
        storage.get_issue_ids.return_value = {issue.full_id}
        dogcats = tmp_path / ".dogcats"
        dogcats.mkdir(parents=True, exist_ok=True)
        storage.dogcats_dir = dogcats

        seen: list[int] = []

        def _record_thread(_id: str) -> None:
            seen.append(threading.get_ident())

        storage.delete.side_effect = _record_thread

        app = DogcatTUI(storage)
        async with app.run_test() as pilot:
            app.action_delete_issue()
            await pilot.pause()
            confirm = next(
                s for s in app.screen_stack if isinstance(s, ConfirmDeleteScreen)
            )
            confirm.action_confirm()
            await pilot.pause()
            await asyncio.wait_for(wait_for_workers(app), timeout=10)
            await pilot.pause()

        assert seen
        assert seen[0] != threading.get_ident()

    @pytest.mark.asyncio
    async def test_refresh_reloads_on_a_worker_thread(self, tmp_path: Path) -> None:
        """storage.reload is called off the main thread, and the list rebuilds."""
        storage = _make_store(tmp_path)
        storage.create(Issue(id="ref1", title="First"))

        seen: list[int] = []
        real_reload = storage.reload

        def _tracking_reload() -> None:
            seen.append(threading.get_ident())
            real_reload()

        app = DogcatTUI(storage)
        async with app.run_test() as pilot:
            await pilot.pause()
            other = JSONLStorage(str(storage.path))
            other.create(Issue(id="ref2", title="Added by another process"))

            with patch.object(storage, "reload", _tracking_reload):
                await asyncio.wait_for(app.action_refresh(), timeout=10)
            await pilot.pause()

            from textual.widgets import OptionList

            assert app.query_one("#issue-list", OptionList).option_count == 2

        assert seen
        assert seen[0] != threading.get_ident()
