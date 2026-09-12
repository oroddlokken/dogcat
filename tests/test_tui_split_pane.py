"""Tests for the split-pane TUI layout."""

from __future__ import annotations

import asyncio
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from textual.widgets import OptionList

from dogcat.models import Issue
from dogcat.tui.dashboard import DogcatTUI


def _make_issue(**kwargs: object) -> Issue:
    """Create a test issue with sensible defaults."""
    defaults: dict[str, Any] = {
        "id": "test",
        "title": "Test issue",
        "namespace": "dc",
    }
    defaults.update(kwargs)
    return Issue(**defaults)  # type: ignore[arg-type]


def _make_storage(issues: list[Issue] | None = None) -> MagicMock:
    """Create a mock storage backend with optional issues."""
    storage = MagicMock()
    issue_list = issues or []
    storage.list.return_value = issue_list

    def _get_by_id(fid: str) -> Issue | None:
        return next((i for i in issue_list if i.full_id == fid), None)

    storage.get.side_effect = _get_by_id
    storage.get_children.return_value = []
    storage.get_dependencies.return_value = []
    storage.get_issue_ids.return_value = {i.full_id for i in issue_list}
    storage.dogcats_dir = MagicMock()
    storage.dogcats_dir.__str__ = MagicMock(return_value="/tmp/_nonexistent_dogcats")
    return storage


class TestSplitModeActivation:
    """Test that split mode activates/deactivates at the right thresholds."""

    @pytest.mark.asyncio
    async def test_split_mode_activates_at_threshold(self) -> None:
        """Split mode should activate when terminal is >= 200x40."""
        storage = _make_storage()
        app = DogcatTUI(storage)

        async with app.run_test(size=(200, 40)) as _pilot:
            assert app._split_mode is True

    @pytest.mark.asyncio
    async def test_split_mode_inactive_at_default_size(self) -> None:
        """Split mode should be inactive at default 80x24 size."""
        storage = _make_storage()
        app = DogcatTUI(storage)

        async with app.run_test(size=(80, 24)) as _pilot:
            assert app._split_mode is False

    @pytest.mark.asyncio
    async def test_split_mode_inactive_below_width_threshold(self) -> None:
        """Split mode should be inactive when width < 200."""
        storage = _make_storage()
        app = DogcatTUI(storage)

        async with app.run_test(size=(199, 40)) as _pilot:
            assert app._split_mode is False

    @pytest.mark.asyncio
    async def test_split_mode_inactive_below_height_threshold(self) -> None:
        """Split mode should be inactive when height < 40."""
        storage = _make_storage()
        app = DogcatTUI(storage)

        async with app.run_test(size=(200, 39)) as _pilot:
            assert app._split_mode is False

    @pytest.mark.asyncio
    async def test_split_active_class_applied(self) -> None:
        """The split-active CSS class is applied to main-pane."""
        storage = _make_storage()
        app = DogcatTUI(storage)

        async with app.run_test(size=(200, 40)) as _pilot:
            main_pane = app.query_one("#main-pane")
            assert main_pane.has_class("split-active")

    @pytest.mark.asyncio
    async def test_split_active_class_not_applied_at_small_size(self) -> None:
        """The split-active CSS class is NOT applied at small sizes."""
        storage = _make_storage()
        app = DogcatTUI(storage)

        async with app.run_test(size=(80, 24)) as _pilot:
            main_pane = app.query_one("#main-pane")
            assert not main_pane.has_class("split-active")


class TestDetailPanelInSplitMode:
    """Test that the detail panel populates on highlight in split mode."""

    @pytest.mark.asyncio
    async def test_detail_panel_shows_on_highlight(self) -> None:
        """Highlighting an issue in split mode shows the detail panel."""
        issue = _make_issue(id="abc1", title="Test issue")
        storage = _make_storage([issue])
        app = DogcatTUI(storage)

        async with app.run_test(size=(200, 40)) as pilot:
            await pilot.pause()

            # A detail panel should be mounted since an issue is highlighted
            panels = app.query("#detail-panel")
            assert len(panels) > 0

    @pytest.mark.asyncio
    async def test_no_detail_panel_at_small_size(self) -> None:
        """No detail panel should be mounted at small terminal sizes."""
        issue = _make_issue(id="abc1", title="Test issue")
        storage = _make_storage([issue])
        app = DogcatTUI(storage)

        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()

            panels = app.query("#detail-panel")
            assert len(panels) == 0


class TestInlineEditing:
    """Test inline editing via 'e' key in split mode."""

    @pytest.mark.asyncio
    async def test_edit_key_triggers_inline_editing(self) -> None:
        """Pressing 'e' in split mode triggers inline editing."""
        issue = _make_issue(id="abc1", title="Editable")
        storage = _make_storage([issue])
        app = DogcatTUI(storage)

        async with app.run_test(size=(200, 40)) as pilot:
            await pilot.pause()

            # Trigger edit action
            app.action_edit_issue()
            await pilot.pause()

            # Should NOT push a modal editor screen
            from dogcat.tui.editor import IssueEditorScreen

            assert not any(isinstance(s, IssueEditorScreen) for s in app.screen_stack)

    @pytest.mark.asyncio
    async def test_edit_key_pushes_modal_at_small_size(self) -> None:
        """Pressing 'e' at small sizes pushes the modal editor."""
        from dogcat.tui.editor import IssueEditorScreen

        issue = _make_issue(id="abc1", title="Editable")
        storage = _make_storage([issue])
        app = DogcatTUI(storage)

        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()

            app.action_edit_issue()
            await pilot.pause()

            assert any(isinstance(s, IssueEditorScreen) for s in app.screen_stack)


class TestEnterKeyBehavior:
    """Test Enter key behavior in split vs narrow mode."""

    @pytest.mark.asyncio
    async def test_enter_in_split_mode_no_modal(self) -> None:
        """Enter in split mode should NOT push a modal editor."""
        issue = _make_issue(id="abc1", title="Test")
        storage = _make_storage([issue])
        app = DogcatTUI(storage)

        async with app.run_test(size=(200, 40)) as pilot:
            option_list = app.query_one("#issue-list", OptionList)
            assert option_list.option_count > 0

            # Simulate pressing Enter
            await pilot.press("enter")
            await pilot.pause()

            from dogcat.tui.editor import IssueEditorScreen

            assert not any(isinstance(s, IssueEditorScreen) for s in app.screen_stack)

    @pytest.mark.asyncio
    async def test_enter_in_narrow_mode_pushes_modal(self) -> None:
        """Enter in narrow mode should push a modal editor."""
        issue = _make_issue(id="abc1", title="Test")
        storage = _make_storage([issue])
        app = DogcatTUI(storage)

        async with app.run_test(size=(80, 24)) as pilot:
            option_list = app.query_one("#issue-list", OptionList)
            assert option_list.option_count > 0

            # Simulate pressing Enter
            await pilot.press("enter")
            await pilot.pause()

            from dogcat.tui.editor import IssueEditorScreen

            assert any(isinstance(s, IssueEditorScreen) for s in app.screen_stack)


class TestSplitPaneSaveCancel:
    """Test save and cancel from inline detail panel."""

    @pytest.mark.asyncio
    async def test_cancel_reloads_view_mode(self) -> None:
        """Cancelling inline edit reverts to view mode and focuses list."""
        issue = _make_issue(id="abc1", title="Test")
        storage = _make_storage([issue])
        app = DogcatTUI(storage)

        async with app.run_test(size=(200, 40)) as pilot:
            await pilot.pause()

            # Enter edit mode
            app.action_edit_issue()
            await pilot.pause()

            # Simulate cancel
            from dogcat.tui.detail_panel import IssueDetailPanel

            panel = app.query_one("#detail-panel", IssueDetailPanel)
            panel.cancel_edit()
            await pilot.pause()

            # Title should be restored
            assert app.title == "dogcat"


class TestConcurrentPanelSwap:
    """Test that overlapping detail-panel swaps do not tear down a mount."""

    @pytest.mark.asyncio
    async def test_overlapping_shows_do_not_crash(self) -> None:
        """Concurrent _show_issue_in_panel calls leave one working panel.

        Each swap removes the panel and mounts a replacement. Before the
        swap lock, a second swap starting mid-mount removed widgets whose
        Mount message was still queued, and Textual's Select answers Mount
        by querying its own children — so it raised NoMatches into the app
        (dogcat-xur2, seen as a Python 3.10 CI failure).
        """
        issue = _make_issue(id="abc1", title="Test")
        storage = _make_storage([issue])
        app = DogcatTUI(storage)

        async with app.run_test(size=(200, 40)) as pilot:
            await pilot.pause()

            await asyncio.gather(
                *(app._show_issue_in_panel("dc-abc1") for _ in range(4)),
            )
            await pilot.pause()

            from dogcat.tui.detail_panel import IssueDetailPanel

            panels = app.query(IssueDetailPanel)
            assert len(panels) == 1
            # The surviving panel finished mounting: type, status and
            # priority are the three Selects that compose the meta row.
            assert len(panels.first().query("Select")) == 3

    @pytest.mark.asyncio
    async def test_overlapping_show_and_clear_do_not_crash(self) -> None:
        """A clear racing a show still ends with a consistent right pane."""
        issue = _make_issue(id="abc1", title="Test")
        storage = _make_storage([issue])
        app = DogcatTUI(storage)

        async with app.run_test(size=(200, 40)) as pilot:
            await pilot.pause()

            await asyncio.gather(
                app._show_issue_in_panel("dc-abc1"),
                app._clear_detail_panel(),
                app._show_issue_in_panel("dc-abc1"),
            )
            await pilot.pause()

            from dogcat.tui.detail_panel import IssueDetailPanel

            assert len(app.query(IssueDetailPanel)) == 1


class TestEscapeInEditMode:
    """Test that escape does not quit the app during inline editing."""

    @pytest.mark.asyncio
    async def test_escape_blocked_during_inline_edit(self) -> None:
        """Pressing escape while editing in split mode should not quit."""
        issue = _make_issue(id="abc1", title="Test")
        storage = _make_storage([issue])
        app = DogcatTUI(storage)

        async with app.run_test(size=(200, 40)) as pilot:
            await pilot.pause()

            # Enter edit mode
            app.action_edit_issue()
            await pilot.pause()

            # check_action should block quit
            assert app.check_action("quit", ()) is False

    @pytest.mark.asyncio
    async def test_escape_allowed_in_view_mode(self) -> None:
        """Pressing escape in view mode (not editing) should be allowed."""
        issue = _make_issue(id="abc1", title="Test")
        storage = _make_storage([issue])
        app = DogcatTUI(storage)

        async with app.run_test(size=(200, 40)) as pilot:
            await pilot.pause()

            # In view mode, quit should be allowed
            assert app.check_action("quit", ()) is True

    @pytest.mark.asyncio
    async def test_escape_allowed_without_split_mode(self) -> None:
        """Pressing escape at small sizes should always be allowed."""
        storage = _make_storage()
        app = DogcatTUI(storage)

        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            assert app.check_action("quit", ()) is True


class TestSplitModeBeforeMount:
    """Test that a resize arriving ahead of compose() is not lost."""

    @pytest.mark.asyncio
    async def test_split_mode_applied_without_pane_does_not_raise(self) -> None:
        """The watcher returns quietly when #main-pane is not in the DOM.

        on_resize assigns _split_mode, and Textual can deliver a resize
        before compose() has built the pane. The watcher used to query
        #main-pane unguarded and raise NoMatches into the app (dogcat-1mvy).
        """
        issue = _make_issue(id="abc1", title="Test")
        storage = _make_storage([issue])
        app = DogcatTUI(storage)

        async with app.run_test(size=(200, 40)) as pilot:
            await pilot.pause()
            await app.query_one("#main-pane").remove()

            await app.watch__split_mode(True)

            assert not app.query("#main-pane")

    @pytest.mark.asyncio
    async def test_mount_replays_split_mode_set_before_compose(self) -> None:
        """State set while the pane was missing lands once it exists.

        set_reactive writes _split_mode without running the watcher, which
        is the state a dropped pre-mount toggle leaves behind.
        """
        issue = _make_issue(id="abc1", title="Test")
        storage = _make_storage([issue])
        app = DogcatTUI(storage)
        app.set_reactive(DogcatTUI._split_mode, True)

        async with app.run_test(size=(200, 40)) as pilot:
            await pilot.pause()

            assert app.query_one("#main-pane").has_class("split-active")


class TestMountSafeSelect:
    """Test the Select guard against children vanishing mid-mount."""

    @pytest.mark.asyncio
    async def test_value_set_with_label_removed_does_not_raise(self) -> None:
        """A value applied to a torn-down select is absorbed.

        Textual's Select answers Mount by pushing the value through
        SelectCurrent.update, which queries #label. A panel swap that
        removes the subtree mid-mount made that raise into the app
        (dogcat-5obm).
        """
        from textual.widgets import Select
        from textual.widgets._select import SelectCurrent

        issue = _make_issue(id="abc1", title="Test")
        storage = _make_storage([issue])
        app = DogcatTUI(storage)

        async with app.run_test(size=(200, 40)) as pilot:
            await pilot.pause()
            await app._show_issue_in_panel("dc-abc1")
            await pilot.pause()

            select = cast("Select[str]", app.query_one("#status-input", Select))
            await select.query_one(SelectCurrent).query("#label").remove()

            select.value = "closed"
            await pilot.pause()

            assert select.value == "closed"

    @pytest.mark.asyncio
    async def test_value_reaches_label_that_comes_back(self) -> None:
        """A swallowed update is re-applied once the child exists again."""
        from textual.widgets import Select, Static
        from textual.widgets._select import SelectCurrent

        issue = _make_issue(id="abc1", title="Test")
        storage = _make_storage([issue])
        app = DogcatTUI(storage)

        async with app.run_test(size=(200, 40)) as pilot:
            await pilot.pause()
            await app._show_issue_in_panel("dc-abc1")
            await pilot.pause()

            select = cast("Select[str]", app.query_one("#status-input", Select))
            current = select.query_one(SelectCurrent)
            await current.query("#label").remove()

            select.value = "closed"
            await current.mount(Static(id="label"))
            await pilot.pause()

            label = current.query_one("#label", Static)
            assert "Closed" in str(label.render())
