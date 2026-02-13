"""Tests for the IssueEditorScreen in view (read-only) mode."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from textual.widgets import (
    Button,
    Checkbox,
    Collapsible,
    Header,
    Input,
    Select,
    Static,
    TextArea,
)

from dogcat.models import Issue
from dogcat.tui.editor import IssueEditorScreen


def _make_issue(**kwargs: object) -> Issue:
    """Create a test issue with sensible defaults."""
    defaults: dict[str, Any] = {
        "id": "test",
        "title": "Test issue",
        "namespace": "dc",
    }
    defaults.update(kwargs)
    return Issue(**defaults)  # type: ignore[arg-type]


def _make_storage() -> MagicMock:
    """Create a mock storage backend."""
    storage = MagicMock()
    storage.get.return_value = None
    storage.list.return_value = []
    storage.get_dependencies.return_value = []
    storage.get_links.return_value = []
    storage.get_incoming_links.return_value = []
    storage.get_children.return_value = []
    return storage


async def _push_view(
    issue: Issue,
    storage: MagicMock | None = None,
) -> tuple[Any, IssueEditorScreen, Any]:
    """Create a test app and editor screen in view mode."""
    from textual.app import App, ComposeResult

    if storage is None:
        storage = _make_storage()

    screen = IssueEditorScreen(issue, storage, view_mode=True)

    class TestApp(App[None]):
        def compose(self) -> ComposeResult:
            yield Header()

    app = TestApp()
    return app, screen, storage


class TestViewModeLayout:
    """Test that view mode renders a read-only editor layout."""

    @pytest.mark.asyncio
    async def test_title_bar_renders(self) -> None:
        """Title bar with ID display and disabled title input."""
        issue = _make_issue(id="abc1", title="My issue")
        app, screen, _ = await _push_view(issue)

        async with app.run_test() as pilot:
            app.push_screen(screen)
            await pilot.pause()

            id_display = screen.query_one("#id-display", Static)
            assert "dc-abc1" in str(id_display.render())

            title_input = screen.query_one("#title-input", Input)
            assert title_input.value == "My issue"
            assert title_input.disabled is True

    @pytest.mark.asyncio
    async def test_buttons_hidden_in_view_mode(self) -> None:
        """Cancel and Save buttons are hidden in view mode."""
        issue = _make_issue()
        app, screen, _ = await _push_view(issue)

        async with app.run_test() as pilot:
            app.push_screen(screen)
            await pilot.pause()

            cancel_btn = screen.query_one("#cancel-btn", Button)
            save_btn = screen.query_one("#save-btn", Button)
            assert cancel_btn.display is False
            assert save_btn.display is False

    @pytest.mark.asyncio
    async def test_field_row_selects_disabled(self) -> None:
        """Type, status, and priority selects are rendered and disabled."""
        from dogcat.models import IssueType, Status

        issue = _make_issue(
            issue_type=IssueType.BUG,
            status=Status.IN_PROGRESS,
            priority=1,
        )
        app, screen, _ = await _push_view(issue)

        async with app.run_test() as pilot:
            app.push_screen(screen)
            await pilot.pause()

            type_select = screen.query_one("#type-input", Select)
            assert type_select.value == "bug"
            assert type_select.disabled is True

            status_select = screen.query_one("#status-input", Select)
            assert status_select.value == "in_progress"
            assert status_select.disabled is True

            priority_select = screen.query_one("#priority-input", Select)
            assert priority_select.value == 1
            assert priority_select.disabled is True

    @pytest.mark.asyncio
    async def test_manual_checkbox_disabled(self) -> None:
        """Manual checkbox is rendered and disabled."""
        issue = _make_issue(metadata={"manual": True})
        app, screen, _ = await _push_view(issue)

        async with app.run_test() as pilot:
            app.push_screen(screen)
            await pilot.pause()

            checkbox = screen.query_one("#manual-input", Checkbox)
            assert checkbox.value is True
            assert checkbox.disabled is True

    @pytest.mark.asyncio
    async def test_info_row_inputs_disabled(self) -> None:
        """Owner, external ref, labels inputs are disabled."""
        issue = _make_issue(
            owner="alice@example.com",
            external_ref="JIRA-123",
            labels=["ui", "ux"],
        )
        app, screen, _ = await _push_view(issue)

        async with app.run_test() as pilot:
            app.push_screen(screen)
            await pilot.pause()

            owner = screen.query_one("#owner-input", Input)
            assert owner.value == "alice@example.com"
            assert owner.disabled is True

            ext_ref = screen.query_one("#external-ref-input", Input)
            assert ext_ref.value == "JIRA-123"
            assert ext_ref.disabled is True

            labels = screen.query_one("#labels-input", Input)
            assert labels.value == "ui, ux"
            assert labels.disabled is True

    @pytest.mark.asyncio
    async def test_description_textarea_readonly(self) -> None:
        """Description textarea is read-only."""
        issue = _make_issue(description="Some description")
        app, screen, _ = await _push_view(issue)

        async with app.run_test() as pilot:
            app.push_screen(screen)
            await pilot.pause()

            desc = screen.query_one("#description-input", TextArea)
            assert desc.text == "Some description"
            assert desc.read_only is True


class TestViewModeCollapsibles:
    """Test collapsible sections behavior in view mode."""

    @pytest.mark.asyncio
    async def test_notes_expanded_when_set(self) -> None:
        """Notes collapsible is expanded when notes exist."""
        issue = _make_issue(notes="Some notes")
        app, screen, _ = await _push_view(issue)

        async with app.run_test() as pilot:
            app.push_screen(screen)
            await pilot.pause()

            collapsibles = {c.title: c for c in screen.query(Collapsible)}
            assert "Notes" in collapsibles
            assert collapsibles["Notes"].collapsed is False

            notes_ta = screen.query_one("#notes-input", TextArea)
            assert notes_ta.text == "Some notes"
            assert notes_ta.read_only is True

    @pytest.mark.asyncio
    async def test_notes_collapsed_when_empty(self) -> None:
        """Notes collapsible is collapsed when notes is None."""
        issue = _make_issue(notes=None)
        app, screen, _ = await _push_view(issue)

        async with app.run_test() as pilot:
            app.push_screen(screen)
            await pilot.pause()

            collapsibles = {c.title: c for c in screen.query(Collapsible)}
            assert "Notes" in collapsibles
            assert collapsibles["Notes"].collapsed is True

    @pytest.mark.asyncio
    async def test_all_content_sections_present(self) -> None:
        """All content sections present (Notes, Acceptance, Design)."""
        issue = _make_issue(
            description="desc",
            notes="notes",
            acceptance="criteria",
            design="design doc",
        )
        app, screen, _ = await _push_view(issue)

        async with app.run_test() as pilot:
            app.push_screen(screen)
            await pilot.pause()

            collapsibles = screen.query(Collapsible)
            titles = [c.title for c in collapsibles]
            assert "Notes" in titles
            assert "Acceptance Criteria" in titles
            assert "Design" in titles


class TestViewModeExtraSections:
    """Test dependencies, children, and comments sections in view mode."""

    @pytest.mark.asyncio
    async def test_children_section_shown(self) -> None:
        """Children collapsible is shown when issue has children."""
        issue = _make_issue()
        child = _make_issue(id="ch1", title="Child issue")
        storage = _make_storage()
        storage.get_children.return_value = [child]
        app, screen, _ = await _push_view(issue, storage)

        async with app.run_test() as pilot:
            app.push_screen(screen)
            await pilot.pause()

            collapsibles = screen.query(Collapsible)
            titles = [c.title for c in collapsibles]
            assert "Children" in titles

    @pytest.mark.asyncio
    async def test_children_section_hidden_when_no_children(self) -> None:
        """Children collapsible is not shown when no children exist."""
        issue = _make_issue()
        app, screen, _ = await _push_view(issue)

        async with app.run_test() as pilot:
            app.push_screen(screen)
            await pilot.pause()

            collapsibles = screen.query(Collapsible)
            titles = [c.title for c in collapsibles]
            assert "Children" not in titles

    @pytest.mark.asyncio
    async def test_dependencies_section_shown(self) -> None:
        """Dependencies collapsible is shown when deps exist."""
        from dogcat.models import Dependency, DependencyType

        issue = _make_issue()
        storage = _make_storage()
        storage.get_dependencies.return_value = [
            Dependency(
                issue_id="dc-test",
                depends_on_id="dc-other",
                dep_type=DependencyType.BLOCKS,
            ),
        ]
        app, screen, _ = await _push_view(issue, storage)

        async with app.run_test() as pilot:
            app.push_screen(screen)
            await pilot.pause()

            collapsibles = screen.query(Collapsible)
            titles = [c.title for c in collapsibles]
            assert "Dependencies" in titles


class TestViewToEditTransition:
    """Test switching from view mode to edit mode."""

    @pytest.mark.asyncio
    async def test_enter_edit_enables_fields(self) -> None:
        """Pressing e in view mode enables all form fields."""
        issue = _make_issue(id="abc1", title="Test")
        app, screen, _ = await _push_view(issue)

        async with app.run_test() as pilot:
            app.push_screen(screen)
            await pilot.pause()

            # Verify fields start disabled
            assert screen.query_one("#title-input", Input).disabled is True

            # Switch to edit mode
            screen.action_enter_edit()
            await pilot.pause()

            # Fields should now be enabled
            assert screen.query_one("#title-input", Input).disabled is False
            assert screen.query_one("#owner-input", Input).disabled is False
            assert screen.query_one("#type-input", Select).disabled is False
            assert screen.query_one("#manual-input", Checkbox).disabled is False

            # TextAreas should be writable
            assert screen.query_one("#description-input", TextArea).read_only is False

    @pytest.mark.asyncio
    async def test_enter_edit_shows_buttons(self) -> None:
        """Pressing e shows Save and Cancel buttons."""
        issue = _make_issue(id="abc1", title="Test")
        app, screen, _ = await _push_view(issue)

        async with app.run_test() as pilot:
            app.push_screen(screen)
            await pilot.pause()

            # Buttons hidden in view mode
            assert screen.query_one("#cancel-btn", Button).display is False
            assert screen.query_one("#save-btn", Button).display is False

            # Switch to edit mode
            screen.action_enter_edit()
            await pilot.pause()

            # Buttons now visible
            assert screen.query_one("#cancel-btn", Button).display is True
            assert screen.query_one("#save-btn", Button).display is True

    @pytest.mark.asyncio
    async def test_enter_edit_removes_view_sections(self) -> None:
        """View-only sections (deps, children) are removed on edit."""
        issue = _make_issue()
        child = _make_issue(id="ch1", title="Child")
        storage = _make_storage()
        storage.get_children.return_value = [child]
        app, screen, _ = await _push_view(issue, storage)

        async with app.run_test() as pilot:
            app.push_screen(screen)
            await pilot.pause()

            # Children section exists in view mode
            collapsibles = [c.title for c in screen.query(Collapsible)]
            assert "Children" in collapsibles

            # Switch to edit mode
            screen.action_enter_edit()
            await pilot.pause()

            # Children section removed
            collapsibles = [c.title for c in screen.query(Collapsible)]
            assert "Children" not in collapsibles

    @pytest.mark.asyncio
    async def test_check_action_controls_bindings(self) -> None:
        """check_action hides save in view mode and edit in non-view mode."""
        issue = _make_issue()
        app, screen, _ = await _push_view(issue)

        async with app.run_test() as pilot:
            app.push_screen(screen)
            await pilot.pause()

            # In view mode: edit visible, save hidden
            assert screen.check_action("enter_edit", ()) is True
            assert screen.check_action("save", ()) is False

            # Switch to edit mode
            screen.action_enter_edit()
            await pilot.pause()

            # In edit mode: edit hidden, save visible
            assert screen.check_action("enter_edit", ()) is False
            assert screen.check_action("save", ()) is True
