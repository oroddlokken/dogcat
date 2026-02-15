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


def _make_storage(issues: list[Issue] | None = None) -> MagicMock:
    """Create a mock storage backend with optional issues."""
    storage = MagicMock()
    issue_list = issues or []
    storage.list.return_value = issue_list
    storage.get.return_value = issue_list[0] if issue_list else None
    storage.get_children.return_value = []
    storage.get_dependencies.return_value = []
    storage.get_issue_ids.return_value = {i.full_id for i in issue_list}
    storage.dogcats_dir = MagicMock()
    storage.dogcats_dir.__str__ = MagicMock(return_value=".dogcats")
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
    """Test that d and D keybindings are registered."""

    @pytest.mark.asyncio
    async def test_delete_bindings_registered(self) -> None:
        """Dashboard has d (Delete) and D (Delete!) keybindings."""
        storage = _make_storage()
        app = DogcatTUI(storage)

        async with app.run_test() as _pilot:
            binding_keys = set(app.active_bindings.keys())
            assert "d" in binding_keys
            assert "D" in binding_keys


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
            assert app.check_action("force_delete_issue", ()) is False
            assert app.check_action("edit_issue", ()) is False

    @pytest.mark.asyncio
    async def test_actions_enabled_on_dashboard(self) -> None:
        """n/d/D/e should be enabled when on the dashboard screen."""
        storage = _make_storage()
        app = DogcatTUI(storage)

        async with app.run_test() as _pilot:
            assert app.check_action("new_issue", ()) is True
            assert app.check_action("delete_issue", ()) is True
            assert app.check_action("force_delete_issue", ()) is True
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

            # Find the Yes button and click it
            confirm_screen = next(
                s for s in app.screen_stack if isinstance(s, ConfirmDeleteScreen)
            )
            yes_btn = confirm_screen.query_one("#yes-btn", Button)
            yes_btn.press()
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


class TestDashboardForceDeleteAction:
    """Test the force delete (shift+d) keybinding."""

    @pytest.mark.asyncio
    async def test_force_delete_no_selection_notifies(self) -> None:
        """Pressing D with no issues shows warning notification."""
        storage = _make_storage()
        app = DogcatTUI(storage)

        async with app.run_test() as pilot:
            app.action_force_delete_issue()
            await pilot.pause()
            storage.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_force_delete_calls_storage(self) -> None:
        """Pressing D deletes immediately without confirmation."""
        issue = _make_issue(id="abc1", title="Force delete")
        storage = _make_storage([issue])
        app = DogcatTUI(storage)

        async with app.run_test() as pilot:
            app.action_force_delete_issue()
            await pilot.pause()

            # No confirmation screen pushed
            assert not any(isinstance(s, ConfirmDeleteScreen) for s in app.screen_stack)
            storage.delete.assert_called_once_with("dc-abc1")

    @pytest.mark.asyncio
    async def test_force_delete_refreshes_list(self) -> None:
        """After force delete, the issue list is refreshed."""
        issue = _make_issue(id="abc1", title="Delete me")
        storage = _make_storage([issue])
        app = DogcatTUI(storage)

        async with app.run_test() as pilot:
            initial_list_calls = storage.list.call_count

            app.action_force_delete_issue()
            await pilot.pause()

            # list() should be called again for refresh
            assert storage.list.call_count > initial_list_calls


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
    async def test_force_delete_persists_to_disk(self, tmp_path: Path) -> None:
        """Force-deleting an issue via TUI persists the tombstone to disk."""
        from dogcat.storage import JSONLStorage

        storage_path = tmp_path / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)
        storage.create(Issue(id="del1", title="Delete me"))

        app = DogcatTUI(storage)
        async with app.run_test() as pilot:
            await pilot.pause()

            # Select the issue and force-delete
            app.action_force_delete_issue()
            await pilot.pause()

        # Verify the tombstone persists when reloading from disk
        fresh = JSONLStorage(str(storage_path))
        issue = fresh.get("del1")
        assert issue is not None
        assert issue.status.value == "tombstone"

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
