"""Tests for the TUI dashboard keybindings."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest
from textual.widgets import Button, OptionList

from dogcat.models import Issue
from dogcat.tui.dashboard import ConfirmDeleteScreen, DogcatTUI

if TYPE_CHECKING:
    from pathlib import Path


def _make_issue(**kwargs: object) -> Issue:
    """Create a test issue with sensible defaults."""
    defaults: dict[str, Any] = {
        "id": "test",
        "title": "Test issue",
        "namespace": "dc",
    }
    defaults.update(kwargs)
    return Issue(**defaults)  # type: ignore[arg-type]


def _make_storage(
    issues: list[Issue] | None = None,
    *,
    tmp_path: Path | None = None,
) -> MagicMock:
    """Create a mock storage backend bound to ``JSONLStorage``.

    ``spec=JSONLStorage`` makes MagicMock raise ``AttributeError`` on
    references to methods the real class does not have, so a TUI/storage
    rename surfaces here instead of silently passing.

    ``dogcats_dir`` is pointed at a real on-disk path (an empty
    ``.dogcats`` directory) when ``tmp_path`` is provided. Without this,
    the dashboard's namespace/prefix config silently falls back to
    defaults because the path lookup short-circuits on a missing dir.
    (dogcat-wgjf)
    """
    from dogcat.storage import JSONLStorage

    storage = MagicMock(spec=JSONLStorage)
    issue_list = issues or []
    storage.list.return_value = issue_list
    storage.get.return_value = issue_list[0] if issue_list else None
    storage.get_children.return_value = []
    storage.get_dependencies.return_value = []
    storage.get_issue_ids.return_value = {i.full_id for i in issue_list}
    if tmp_path is not None:
        dogcats = tmp_path / ".dogcats"
        dogcats.mkdir(parents=True, exist_ok=True)
        storage.dogcats_dir = dogcats
    else:
        # Backwards-compatible fallback: tests that have not yet been
        # migrated still get a stringifiable dogcats_dir, but they
        # should pass tmp_path going forward.
        fallback = MagicMock()
        fallback.__str__ = MagicMock(return_value="/tmp/_nonexistent_dogcats")
        storage.dogcats_dir = fallback
    return storage


class TestDashboardKeybindings:
    """Test that n and e keybindings are registered."""

    @pytest.mark.asyncio
    async def test_bindings_registered(self) -> None:
        """Dashboard has n (New) and e (Edit) keybindings."""
        storage = _make_storage()
        app = DogcatTUI(storage)

        async with app.run_test() as _pilot:
            binding_keys = set(app.active_bindings.keys())
            assert "n" in binding_keys
            assert "e" in binding_keys

    @pytest.mark.asyncio
    async def test_refresh_binding_still_works(self) -> None:
        """Refresh keybinding (r) still present."""
        storage = _make_storage()
        app = DogcatTUI(storage)

        async with app.run_test() as _pilot:
            binding_keys = set(app.active_bindings.keys())
            assert "r" in binding_keys


class TestDashboardEditAction:
    """Test the edit (e) keybinding functionality."""

    @pytest.mark.asyncio
    async def test_edit_no_selection_notifies(self) -> None:
        """Pressing e with no issues shows warning notification."""
        storage = _make_storage()
        app = DogcatTUI(storage)

        async with app.run_test() as pilot:
            # No issues loaded, pressing e should notify
            app.action_edit_issue()
            await pilot.pause()
            # The app should still be on the main screen (no crash)
            assert app.screen is not None

    @pytest.mark.asyncio
    async def test_edit_pushes_editor_screen(self) -> None:
        """Pressing e with a selected issue pushes the editor screen."""
        from dogcat.tui.editor import IssueEditorScreen

        issue = _make_issue(id="abc1", title="Editable issue")
        storage = _make_storage([issue])

        app = DogcatTUI(storage)

        async with app.run_test() as pilot:
            # Ensure the issue list is populated and an item is highlighted
            option_list = app.query_one("#issue-list", OptionList)
            assert option_list.option_count > 0

            # Trigger edit action
            app.action_edit_issue()
            await pilot.pause()

            # Check that the editor screen was pushed
            assert any(isinstance(s, IssueEditorScreen) for s in app.screen_stack)

    @pytest.mark.asyncio
    async def test_edit_issue_not_found_notifies(self) -> None:
        """Pressing e when storage.get returns None shows error."""
        issue = _make_issue(id="abc1", title="Ghost issue")
        storage = _make_storage([issue])
        # Make get return None to simulate issue not found
        storage.get.return_value = None

        app = DogcatTUI(storage)

        async with app.run_test() as pilot:
            app.action_edit_issue()
            await pilot.pause()
            # Should not crash, editor screen should not be pushed
            from dogcat.tui.editor import IssueEditorScreen

            assert not any(isinstance(s, IssueEditorScreen) for s in app.screen_stack)


class TestDashboardNewAction:
    """Test the new (n) keybinding functionality."""

    @pytest.mark.asyncio
    async def test_new_pushes_editor_screen(self) -> None:
        """Pressing n pushes the editor screen in create mode."""
        from dogcat.tui.editor import IssueEditorScreen

        storage = _make_storage()
        app = DogcatTUI(storage)

        async with app.run_test() as pilot:
            with (
                patch("dogcat.config.get_issue_prefix", return_value="dc"),
                patch(
                    "dogcat.cli._helpers.get_default_operator",
                    return_value="test@example.com",
                ),
            ):
                app.action_new_issue()
            await pilot.pause()

            # Check that the editor screen was pushed
            editor_screens = [
                s for s in app.screen_stack if isinstance(s, IssueEditorScreen)
            ]
            assert len(editor_screens) == 1
            assert editor_screens[0]._create_mode is True

    @pytest.mark.asyncio
    async def test_new_uses_correct_namespace(self) -> None:
        """New issue editor uses the configured namespace."""
        from dogcat.tui.editor import IssueEditorScreen

        storage = _make_storage()
        app = DogcatTUI(storage)

        async with app.run_test() as pilot:
            with (
                patch("dogcat.config.get_issue_prefix", return_value="myns"),
                patch(
                    "dogcat.cli._helpers.get_default_operator",
                    return_value="alice@test.com",
                ),
            ):
                app.action_new_issue()
            await pilot.pause()

            editor_screens = [
                s for s in app.screen_stack if isinstance(s, IssueEditorScreen)
            ]
            assert len(editor_screens) == 1
            assert editor_screens[0]._namespace == "myns"


class TestDashboardEditorCallback:
    """Test that the editor callback properly refreshes the dashboard."""

    @pytest.mark.asyncio
    async def test_editor_done_refreshes_list(self) -> None:
        """After editor dismissal with result, the issue list is reloaded."""
        issue = _make_issue(id="abc1", title="Original")
        storage = _make_storage([issue])

        app = DogcatTUI(storage)

        async with app.run_test() as pilot:
            # Simulate editor callback with a result
            updated = _make_issue(id="abc1", title="Updated")
            app._on_editor_done(updated)
            await pilot.pause()

            # Storage.list should be called again (refresh)
            assert storage.list.call_count >= 2  # initial + refresh

    @pytest.mark.asyncio
    async def test_editor_done_with_none_preserves_selection(self) -> None:
        """After editor cancel, the previously selected issue stays highlighted."""
        issue = _make_issue(id="abc1", title="Test")
        storage = _make_storage([issue])

        app = DogcatTUI(storage)

        async with app.run_test() as pilot:
            # Set last selected ID and trigger cancel callback
            app._last_selected_id = "dc-abc1"
            app._on_editor_done(None)
            await pilot.pause()

            # Should still be on the dashboard
            assert app.title == "dogcat"

    @pytest.mark.asyncio
    async def test_editor_done_restores_title(self) -> None:
        """After editor dismissal, dashboard title is restored."""
        storage = _make_storage()
        app = DogcatTUI(storage)

        async with app.run_test() as pilot:
            # Simulate title being changed by editor
            app.title = "Edit: dc-abc1 - Some Issue"
            app._on_editor_done(None)
            await pilot.pause()

            assert app.title == "dogcat"


class TestGetSelectedIssueId:
    """Test the _get_selected_issue_id helper."""

    @pytest.mark.asyncio
    async def test_returns_none_when_empty(self) -> None:
        """Returns None when no issues are loaded."""
        storage = _make_storage()
        app = DogcatTUI(storage)

        async with app.run_test() as _pilot:
            assert app._get_selected_issue_id() is None

    @pytest.mark.asyncio
    async def test_returns_id_when_issue_highlighted(self) -> None:
        """Returns the full_id of the highlighted issue."""
        issue = _make_issue(id="abc1", title="Test")
        storage = _make_storage([issue])
        app = DogcatTUI(storage)

        async with app.run_test() as _pilot:
            result = app._get_selected_issue_id()
            assert result == "dc-abc1"


class TestDashboardDeleteBindings:
    """Test that d keybinding is registered."""

    @pytest.mark.asyncio
    async def test_delete_bindings_registered(self) -> None:
        """Dashboard has d (Delete) keybinding."""
        storage = _make_storage()
        app = DogcatTUI(storage)

        async with app.run_test() as _pilot:
            binding_keys = set(app.active_bindings.keys())
            assert "d" in binding_keys


class TestDashboardActionsDisabledInEditor:
    """Test that n/d/D actions are disabled when editor screen is pushed."""

    @pytest.mark.asyncio
    async def test_actions_disabled_when_editor_open(self) -> None:
        """n/d/D/e should be disabled when the editor screen is active."""
        from dogcat.tui.editor import IssueEditorScreen

        issue = _make_issue(id="abc1", title="Test issue")
        storage = _make_storage([issue])
        app = DogcatTUI(storage)

        async with app.run_test() as pilot:
            # Push editor screen (view mode)
            app.action_edit_issue()
            await pilot.pause()

            # Verify editor is active
            assert any(isinstance(s, IssueEditorScreen) for s in app.screen_stack)

            # check_action should return False for dashboard-only actions
            assert app.check_action("new_issue", ()) is False
            assert app.check_action("delete_issue", ()) is False
            assert app.check_action("edit_issue", ()) is False

    @pytest.mark.asyncio
    async def test_actions_enabled_on_dashboard(self) -> None:
        """n/d/e should be enabled when on the dashboard screen."""
        storage = _make_storage()
        app = DogcatTUI(storage)

        async with app.run_test() as _pilot:
            assert app.check_action("new_issue", ()) is True
            assert app.check_action("delete_issue", ()) is True
            assert app.check_action("edit_issue", ()) is True


class TestDashboardDeleteAction:
    """Test the delete (d) keybinding with confirmation."""

    @pytest.mark.asyncio
    async def test_delete_no_selection_notifies(self) -> None:
        """Pressing d with no issues shows warning notification."""
        storage = _make_storage()
        app = DogcatTUI(storage)

        async with app.run_test() as pilot:
            app.action_delete_issue()
            await pilot.pause()
            # Should not crash, no confirm screen pushed
            assert not any(isinstance(s, ConfirmDeleteScreen) for s in app.screen_stack)

    @pytest.mark.asyncio
    async def test_delete_pushes_confirm_screen(self) -> None:
        """Pressing d with a selected issue pushes the confirmation screen."""
        issue = _make_issue(id="abc1", title="Deletable issue")
        storage = _make_storage([issue])
        app = DogcatTUI(storage)

        async with app.run_test() as pilot:
            app.action_delete_issue()
            await pilot.pause()

            assert any(isinstance(s, ConfirmDeleteScreen) for s in app.screen_stack)

    @pytest.mark.asyncio
    async def test_confirm_yes_deletes(self) -> None:
        """Confirming Yes on the dialog calls storage.delete."""
        issue = _make_issue(id="abc1", title="To delete")
        storage = _make_storage([issue])
        app = DogcatTUI(storage)

        async with app.run_test() as pilot:
            app.action_delete_issue()
            await pilot.pause()

            # Find the Delete button and click it
            confirm_screen = next(
                s for s in app.screen_stack if isinstance(s, ConfirmDeleteScreen)
            )
            delete_btn = confirm_screen.query_one("#confirm-delete", Button)
            delete_btn.press()
            await pilot.pause()

            storage.delete.assert_called_once_with("dc-abc1")

    @pytest.mark.asyncio
    async def test_confirm_cancel_does_not_delete(self) -> None:
        """Pressing Escape on the dialog does not delete."""
        issue = _make_issue(id="abc1", title="Keep this")
        storage = _make_storage([issue])
        app = DogcatTUI(storage)

        async with app.run_test() as pilot:
            app.action_delete_issue()
            await pilot.pause()

            # Cancel the dialog
            confirm_screen = next(
                s for s in app.screen_stack if isinstance(s, ConfirmDeleteScreen)
            )
            confirm_screen.action_cancel()
            await pilot.pause()

            storage.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_issue_not_found_notifies(self) -> None:
        """Pressing d when storage.get returns None shows error."""
        issue = _make_issue(id="abc1", title="Ghost")
        storage = _make_storage([issue])
        storage.get.return_value = None
        app = DogcatTUI(storage)

        async with app.run_test() as pilot:
            app.action_delete_issue()
            await pilot.pause()
            assert not any(isinstance(s, ConfirmDeleteScreen) for s in app.screen_stack)

    @pytest.mark.asyncio
    async def test_confirm_default_focus_is_cancel(self) -> None:
        """Cancel must own initial focus so reflexive Enter does not delete."""
        issue = _make_issue(id="abc1", title="Safe default")
        storage = _make_storage([issue])
        app = DogcatTUI(storage)

        async with app.run_test() as pilot:
            app.action_delete_issue()
            await pilot.pause()

            confirm_screen = next(
                s for s in app.screen_stack if isinstance(s, ConfirmDeleteScreen)
            )
            cancel_btn = confirm_screen.query_one("#confirm-cancel", Button)
            assert cancel_btn.has_focus

    @pytest.mark.asyncio
    async def test_confirm_y_key_deletes(self) -> None:
        """Pressing y on the dialog confirms the delete."""
        issue = _make_issue(id="abc1", title="Y to delete")
        storage = _make_storage([issue])
        app = DogcatTUI(storage)

        async with app.run_test() as pilot:
            app.action_delete_issue()
            await pilot.pause()

            await pilot.press("y")
            await pilot.pause()

            storage.delete.assert_called_once_with("dc-abc1")

    @pytest.mark.asyncio
    async def test_confirm_n_key_cancels(self) -> None:
        """Pressing n on the dialog cancels the delete."""
        issue = _make_issue(id="abc1", title="N keeps")
        storage = _make_storage([issue])
        app = DogcatTUI(storage)

        async with app.run_test() as pilot:
            app.action_delete_issue()
            await pilot.pause()

            await pilot.press("n")
            await pilot.pause()

            storage.delete.assert_not_called()
            assert not any(isinstance(s, ConfirmDeleteScreen) for s in app.screen_stack)


# ---------------------------------------------------------------------------
# E2E test: TUI with real storage backend
# ---------------------------------------------------------------------------


class TestTUIWithRealStorage:
    """E2E: TUI operations with real JSONLStorage instead of mocks."""

    @pytest.mark.asyncio
    async def test_dashboard_loads_real_issues(self, tmp_path: Path) -> None:
        """Dashboard displays issues from real JSONLStorage."""
        from dogcat.storage import JSONLStorage

        storage_path = tmp_path / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)
        storage.create(Issue(id="real1", title="Real issue one"))
        storage.create(Issue(id="real2", title="Real issue two"))

        app = DogcatTUI(storage)
        async with app.run_test() as pilot:
            await pilot.pause()

            option_list = app.query_one("#issue-list", OptionList)
            assert option_list.option_count == 2

    @pytest.mark.asyncio
    async def test_issue_list_does_not_overflow_terminal_height(
        self,
        tmp_path: Path,
    ) -> None:
        """OptionList stays within terminal bounds when issues exceed visible rows.

        Regression for dogcat-1ygm: with default OptionList sizing
        (height: auto, max-height: 100%), many issues caused the list to render
        past the footer with no scrollbar. An explicit height: 1fr fixes it.
        """
        from dogcat.storage import JSONLStorage

        storage_path = tmp_path / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)
        for i in range(40):
            storage.create(Issue(id=f"r{i:03d}", title=f"Issue {i}"))

        app = DogcatTUI(storage)
        # Small terminal: 80 cols x 24 rows. 40 issues cannot fit.
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()

            option_list = app.query_one("#issue-list", OptionList)
            assert option_list.option_count == 40

            # The OptionList must not extend past the terminal height (24).
            assert option_list.region.bottom <= 24, (
                f"OptionList bottom {option_list.region.bottom} exceeds "
                f"terminal height 24 — items will be clipped without a scrollbar"
            )

    @pytest.mark.asyncio
    async def test_refresh_reloads_from_disk(self, tmp_path: Path) -> None:
        """Pressing refresh reloads issues from the real JSONL file."""
        from dogcat.storage import JSONLStorage

        storage_path = tmp_path / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)
        storage.create(Issue(id="r1", title="First"))

        app = DogcatTUI(storage)
        async with app.run_test() as pilot:
            await pilot.pause()
            option_list = app.query_one("#issue-list", OptionList)
            assert option_list.option_count == 1

            # Simulate external process adding an issue directly to the file
            import orjson

            from dogcat.models import issue_to_dict

            external = issue_to_dict(Issue(id="r2", title="External"))
            with storage_path.open("ab") as f:
                f.write(orjson.dumps(external) + b"\n")

            # Refresh should pick up the new issue
            await app.action_refresh()
            await pilot.pause()
            assert option_list.option_count == 2


class TestStaleDataRevalidation:
    """Surface deleted-out-from-under-us issues (dogcat-4g9i).

    Refresh and panel re-mount must not silently re-show stale data when
    the issue was tombstoned by another process.
    """

    @pytest.mark.asyncio
    async def test_refresh_notifies_when_selected_issue_was_tombstoned(
        self,
        tmp_path: Path,
    ) -> None:
        """If the highlighted issue is gone after reload, surface a warning."""
        from dogcat.storage import JSONLStorage

        storage_path = tmp_path / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)
        storage.create(Issue(id="keep1", title="Keep"))
        storage.create(Issue(id="kill2", title="Kill me"))

        app = DogcatTUI(storage)
        async with app.run_test(size=(220, 50)) as pilot:
            await pilot.pause()

            # Select the issue we'll tombstone
            option_list = app.query_one("#issue-list", OptionList)
            app._highlight_issue(option_list, "dc-kill2")
            await pilot.pause()
            assert app._get_selected_issue_id() == "dc-kill2"

            # Simulate an external delete by writing the tombstone directly
            # then triggering refresh.
            storage.delete("dc-kill2")

            with patch.object(app, "notify") as notify_spy:
                await app.action_refresh()
                await pilot.pause()
                messages = [
                    str(call.args[0]) if call.args else str(call.kwargs)
                    for call in notify_spy.call_args_list
                ]
                assert any(
                    "dc-kill2" in m and "no longer exists" in m for m in messages
                ), f"got: {messages}"

    @pytest.mark.asyncio
    async def test_orphan_child_stays_in_list_when_parent_tombstoned(
        self,
        tmp_path: Path,
    ) -> None:
        """A child whose parent was tombstoned must stay in the list at root."""
        from dogcat.storage import JSONLStorage

        storage_path = tmp_path / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)
        parent = storage.create(Issue(id="dad", title="Parent"))
        storage.create(Issue(id="kid", title="Child", parent=parent.full_id))
        storage.delete(parent.full_id)

        app = DogcatTUI(storage)
        async with app.run_test() as pilot:
            await pilot.pause()
            option_list = app.query_one("#issue-list", OptionList)
            # The orphaned child must still appear (filed at root)
            assert option_list.option_count == 1
            assert "kid" in str(option_list.get_option_at_index(0).prompt)

    @pytest.mark.asyncio
    async def test_show_panel_for_missing_issue_clears_panel(
        self,
        tmp_path: Path,
    ) -> None:
        """Clear the panel when storage.get returns None.

        Without this guard the previous issue's content stays visible.
        """
        from dogcat.storage import JSONLStorage
        from dogcat.tui.detail_panel import IssueDetailPanel

        storage_path = tmp_path / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)
        storage.create(Issue(id="alive1", title="Alive"))

        app = DogcatTUI(storage)
        async with app.run_test(size=(220, 50)) as pilot:
            await pilot.pause()
            assert app._is_panel_editing() is False
            # Sanity: a panel exists for the live issue
            assert app.query(IssueDetailPanel)

            # Simulate the highlighted issue being deleted externally
            # then triggering a re-show with the now-missing id.
            await app._show_issue_in_panel("dc-ghost404")
            await pilot.pause()

            # Panel must be cleared; placeholder should be back
            assert not app.query(IssueDetailPanel)


class TestInlineEditDataLossGuards:
    """Refresh and resize must not wipe an open inline edit (dogcat-3r9z)."""

    @pytest.mark.asyncio
    async def test_refresh_blocked_during_inline_edit(
        self,
        tmp_path: Path,
    ) -> None:
        """action_refresh must not reload storage while the panel is editing."""
        from dogcat.storage import JSONLStorage
        from dogcat.tui.detail_panel import IssueDetailPanel

        storage_path = tmp_path / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)
        storage.create(Issue(id="edit1", title="Editable"))

        app = DogcatTUI(storage)
        async with app.run_test(size=(220, 50)) as pilot:
            await pilot.pause()

            # Drop into inline edit mode
            panel = app.query_one("#detail-panel", IssueDetailPanel)
            panel.enter_edit()
            await pilot.pause()
            assert app._is_panel_editing()

            # Spy on storage.reload — should NOT be called while editing
            with patch.object(storage, "reload") as reload_spy:
                await app.action_refresh()
                await pilot.pause()
                reload_spy.assert_not_called()

            # Panel must still exist in edit mode
            assert app._is_panel_editing()

    @pytest.mark.asyncio
    async def test_resize_below_threshold_preserves_inline_edit(
        self,
        tmp_path: Path,
    ) -> None:
        """Shrinking below split threshold mid-edit must not clear the panel."""
        from textual.events import Resize
        from textual.geometry import Size
        from textual.widgets import Input

        from dogcat.storage import JSONLStorage
        from dogcat.tui.detail_panel import IssueDetailPanel

        storage_path = tmp_path / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)
        storage.create(Issue(id="edit2", title="Editable"))

        app = DogcatTUI(storage)
        async with app.run_test(size=(220, 50)) as pilot:
            await pilot.pause()

            panel = app.query_one("#detail-panel", IssueDetailPanel)
            panel.enter_edit()
            await pilot.pause()

            # Type into the title field — the buffer we must preserve
            title_input = panel.query_one("#title-input", Input)
            title_input.value = "Edited title — do not lose me"
            await pilot.pause()

            # Send a resize event below the split threshold (200 cols / 40 rows)
            shrunk = Size(80, 24)
            app.post_message(Resize(shrunk, shrunk))
            await pilot.pause()

            # Panel must still be present and still hold the typed text
            still_editing = app._is_panel_editing()
            assert still_editing, "panel was cleared by sub-threshold resize"
            assert (
                panel.query_one("#title-input", Input).value
                == "Edited title — do not lose me"
            )

    @pytest.mark.asyncio
    async def test_save_recollapses_split_when_below_threshold(
        self,
        tmp_path: Path,
    ) -> None:
        """After save, a sub-threshold terminal collapses out of split mode."""
        from textual.events import Resize
        from textual.geometry import Size

        from dogcat.storage import JSONLStorage
        from dogcat.tui.detail_panel import IssueDetailPanel

        storage_path = tmp_path / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)
        storage.create(Issue(id="edit3", title="Editable"))

        app = DogcatTUI(storage)
        async with app.run_test(size=(220, 50)) as pilot:
            await pilot.pause()
            assert app._split_mode

            panel = app.query_one("#detail-panel", IssueDetailPanel)
            panel.enter_edit()
            await pilot.pause()

            # Shrink — the guard preserves split mode mid-edit
            shrunk = Size(80, 24)
            app.post_message(Resize(shrunk, shrunk))
            await pilot.pause()
            assert app._split_mode

            # Save — the post-save reapply must now collapse split mode
            panel.do_save()
            await pilot.pause()
            assert not app._split_mode
