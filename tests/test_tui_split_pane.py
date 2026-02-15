"""Tests for the split-pane TUI layout."""

from __future__ import annotations

from typing import Any
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
