"""Tests for the IssueEditorScreen in view (read-only) mode."""

from __future__ import annotations

from typing import Any, cast
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
    storage.get_dependents.return_value = []
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

            type_select = cast("Select[str]", screen.query_one("#type-input", Select))
            assert type_select.value == "bug"
            assert type_select.disabled is True

            status_select = cast(
                "Select[str]",
                screen.query_one("#status-input", Select),
            )
            assert status_select.value == "in_progress"
            assert status_select.disabled is True

            priority_select = cast(
                "Select[int]",
                screen.query_one("#priority-input", Select),
            )
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

    @pytest.mark.asyncio
    async def test_escape_blocked_in_edit_mode(self) -> None:
        """Escape does not dismiss the screen after switching to edit mode."""
        issue = _make_issue()
        app, screen, _ = await _push_view(issue)

        async with app.run_test() as pilot:
            app.push_screen(screen)
            await pilot.pause()

            # Switch to edit mode
            screen.action_enter_edit()
            await pilot.pause()

            # Escape should be a no-op — screen stays open
            screen.action_go_back()
            await pilot.pause()

            # Screen should still be active (not dismissed)
            assert screen in app.screen_stack

    @pytest.mark.asyncio
    async def test_escape_works_in_view_mode(self) -> None:
        """Escape dismisses the screen in view mode."""
        issue = _make_issue()
        app, screen, _ = await _push_view(issue)

        async with app.run_test() as pilot:
            app.push_screen(screen)
            await pilot.pause()

            # Escape should dismiss in view mode
            screen.action_go_back()
            await pilot.pause()

            assert screen not in app.screen_stack


class TestDependencyInputs:
    """Test dependency input fields in the editor."""

    @pytest.mark.asyncio
    async def test_deps_inputs_disabled_in_view_mode(self) -> None:
        """Depends-on and blocks inputs are rendered and disabled in view mode."""
        issue = _make_issue()
        app, screen, _ = await _push_view(issue)

        async with app.run_test() as pilot:
            app.push_screen(screen)
            await pilot.pause()

            depends_on = screen.query_one("#depends-on-input", Input)
            assert depends_on.disabled is True

            blocks = screen.query_one("#blocks-input", Input)
            assert blocks.disabled is True

    @pytest.mark.asyncio
    async def test_deps_inputs_prepopulated(self) -> None:
        """Depends-on and blocks inputs are pre-populated from storage."""
        from dogcat.models import Dependency, DependencyType

        issue = _make_issue()
        storage = _make_storage()
        storage.get_dependencies.return_value = [
            Dependency(
                issue_id="dc-test",
                depends_on_id="dc-blocker",
                dep_type=DependencyType.BLOCKS,
            ),
        ]
        storage.get_dependents.return_value = [
            Dependency(
                issue_id="dc-blocked",
                depends_on_id="dc-test",
                dep_type=DependencyType.BLOCKS,
            ),
        ]
        app, screen, _ = await _push_view(issue, storage)

        async with app.run_test() as pilot:
            app.push_screen(screen)
            await pilot.pause()

            depends_on = screen.query_one("#depends-on-input", Input)
            assert depends_on.value == "blocked by: dc-blocker"

            blocks = screen.query_one("#blocks-input", Input)
            assert blocks.value == "blocking: dc-blocked"

    @pytest.mark.asyncio
    async def test_deps_inputs_become_editable_after_edit(self) -> None:
        """Depends-on / blocks inputs become editable on enter_edit (dogcat-3nrb).

        The displayed value also switches from "blocked by: a, b" prefix-style
        to bare "a, b" so the user can type IDs directly.
        """
        from dogcat.models import Dependency, DependencyType

        issue = _make_issue()
        storage = _make_storage()
        storage.get_dependencies.return_value = [
            Dependency(
                issue_id="dc-test",
                depends_on_id="dc-blocker",
                dep_type=DependencyType.BLOCKS,
            ),
        ]
        storage.get_dependents.return_value = [
            Dependency(
                issue_id="dc-blocked",
                depends_on_id="dc-test",
                dep_type=DependencyType.BLOCKS,
            ),
        ]
        app, screen, _ = await _push_view(issue, storage)

        async with app.run_test() as pilot:
            app.push_screen(screen)
            await pilot.pause()

            assert screen.query_one("#depends-on-input", Input).disabled is True
            assert screen.query_one("#blocks-input", Input).disabled is True

            screen.action_enter_edit()
            await pilot.pause()

            depends_on = screen.query_one("#depends-on-input", Input)
            blocks = screen.query_one("#blocks-input", Input)
            assert depends_on.disabled is False
            assert blocks.disabled is False
            # Value swaps from prefix-style display to bare CSV for editing
            assert depends_on.value == "dc-blocker"
            assert blocks.value == "dc-blocked"


class TestDependencyViewSections:
    """Test enhanced dependency display in view mode."""

    @pytest.mark.asyncio
    async def test_view_shows_depends_on_and_blocks(self) -> None:
        """View mode shows both depends-on and blocks in the Dependencies section."""
        from dogcat.models import Dependency, DependencyType

        issue = _make_issue()
        storage = _make_storage()
        storage.get_dependencies.return_value = [
            Dependency(
                issue_id="dc-test",
                depends_on_id="dc-dep1",
                dep_type=DependencyType.BLOCKS,
            ),
        ]
        storage.get_dependents.return_value = [
            Dependency(
                issue_id="dc-blocked1",
                depends_on_id="dc-test",
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

            # Check the static text content inside the deps section
            deps_section = screen.query_one("#deps-section", Collapsible)
            statics = deps_section.query(Static)
            texts = [str(s.render()) for s in statics]
            assert any("blocked by:" in t and "dc-dep1" in t for t in texts)
            assert any("blocks:" in t and "dc-blocked1" in t for t in texts)

    @pytest.mark.asyncio
    async def test_view_shows_deps_for_dependents_only(self) -> None:
        """Dependencies section shows even when only dependents (blocks) exist."""
        from dogcat.models import Dependency, DependencyType

        issue = _make_issue()
        storage = _make_storage()
        storage.get_dependents.return_value = [
            Dependency(
                issue_id="dc-other",
                depends_on_id="dc-test",
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


class TestFormSafetyGuards:
    """Pre-validate length, narrow exceptions, escape markup (dogcat-3sor)."""

    @pytest.mark.asyncio
    async def test_oversized_title_short_circuits_with_clear_error(self) -> None:
        """Title > MAX_TITLE_LEN must notify and not reach storage."""
        from textual.app import App, ComposeResult

        from dogcat.constants import MAX_TITLE_LEN
        from dogcat.tui.detail_panel import IssueDetailPanel

        issue = _make_issue()
        storage = _make_storage()
        screen = IssueEditorScreen(issue, storage)

        class TestApp(App[None]):
            def compose(self) -> ComposeResult:
                yield Header()

        app = TestApp()
        async with app.run_test() as pilot:
            app.push_screen(screen)
            await pilot.pause()

            panel = screen.query_one("#editor-panel", IssueDetailPanel)
            panel.query_one("#title-input", Input).value = "x" * (MAX_TITLE_LEN + 1)
            panel.do_save()
            await pilot.pause()

            storage.update.assert_not_called()
            storage.create_issue.assert_not_called()

    @pytest.mark.asyncio
    async def test_oversized_description_short_circuits(self) -> None:
        """Description > MAX_DESC_LEN must notify and not reach storage."""
        from textual.app import App, ComposeResult

        from dogcat.constants import MAX_DESC_LEN
        from dogcat.tui.detail_panel import IssueDetailPanel

        issue = _make_issue()
        storage = _make_storage()
        screen = IssueEditorScreen(issue, storage)

        class TestApp(App[None]):
            def compose(self) -> ComposeResult:
                yield Header()

        app = TestApp()
        async with app.run_test() as pilot:
            app.push_screen(screen)
            await pilot.pause()

            panel = screen.query_one("#editor-panel", IssueDetailPanel)
            panel.query_one("#description-input", TextArea).text = "y" * (
                MAX_DESC_LEN + 1
            )
            panel.do_save()
            await pilot.pause()

            storage.update.assert_not_called()


class TestConfirmDeleteMarkupEscape:
    """ConfirmDeleteScreen must not render Rich markup in user-controlled title."""

    @pytest.mark.asyncio
    async def test_markup_in_title_renders_as_literal(self) -> None:
        """A title containing [red]...[/red] must not style the dialog."""
        from textual.app import App, ComposeResult

        from dogcat.tui.dashboard import ConfirmDeleteScreen

        screen = ConfirmDeleteScreen("dc-abc1", "[red]boom[/red]")

        class TestApp(App[None]):
            def compose(self) -> ComposeResult:
                yield Header()

        app = TestApp()
        async with app.run_test() as pilot:
            app.push_screen(screen)
            await pilot.pause()

            statics = list(screen.query(Static))
            rendered = [str(s.render()) for s in statics]
            # The literal brackets must survive in the rendered output
            assert any("[red]" in r and "[/red]" in r for r in rendered), rendered


class TestDependencyEditingRoundTrip:
    """Inline dep editing + atomic reconcile (dogcat-3nrb / dogcat-11n6).

    These run against real ``JSONLStorage`` because the validation path
    walks the dep graph through ``would_create_cycle``.
    """

    @pytest.mark.asyncio
    async def test_save_adds_new_depends_on(self, tmp_path: Any) -> None:
        """Typing a valid issue id into depends-on and saving creates the dep."""
        from textual.app import App, ComposeResult

        from dogcat.storage import JSONLStorage
        from dogcat.tui.detail_panel import IssueDetailPanel

        storage_path = tmp_path / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)
        storage.create(_make_issue(id="src", title="Source"))
        storage.create(_make_issue(id="tgt", title="Target"))

        src = storage.get("dc-src")
        assert src is not None
        screen = IssueEditorScreen(src, storage)

        class TestApp(App[None]):
            def compose(self) -> ComposeResult:
                yield Header()

        app = TestApp()
        async with app.run_test() as pilot:
            app.push_screen(screen)
            await pilot.pause()

            panel = screen.query_one("#editor-panel", IssueDetailPanel)
            panel.query_one("#depends-on-input", Input).value = "dc-tgt"
            panel.do_save()
            await pilot.pause()

            deps = storage.get_dependencies("dc-src")
            assert any(d.depends_on_id == "dc-tgt" for d in deps)

    @pytest.mark.asyncio
    async def test_unknown_dep_id_aborts_entire_save(self, tmp_path: Any) -> None:
        """An unknown dep id must NOT half-apply a title change."""
        from textual.app import App, ComposeResult

        from dogcat.storage import JSONLStorage
        from dogcat.tui.detail_panel import IssueDetailPanel

        storage_path = tmp_path / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)
        storage.create(_make_issue(id="src", title="Original title"))

        src = storage.get("dc-src")
        assert src is not None
        screen = IssueEditorScreen(src, storage)

        class TestApp(App[None]):
            def compose(self) -> ComposeResult:
                yield Header()

        app = TestApp()
        async with app.run_test() as pilot:
            app.push_screen(screen)
            await pilot.pause()

            panel = screen.query_one("#editor-panel", IssueDetailPanel)
            panel.query_one("#title-input", Input).value = "Renamed"
            panel.query_one("#depends-on-input", Input).value = "dc-ghost"
            panel.do_save()
            await pilot.pause()

            # Title must NOT have been written; deps must be empty.
            after = storage.get("dc-src")
            assert after is not None
            assert after.title == "Original title"
            assert storage.get_dependencies("dc-src") == []

    @pytest.mark.asyncio
    async def test_cycle_aborts_entire_save(self, tmp_path: Any) -> None:
        """Adding a depends-on that would create a cycle is rejected."""
        from textual.app import App, ComposeResult

        from dogcat.storage import JSONLStorage
        from dogcat.tui.detail_panel import IssueDetailPanel

        storage_path = tmp_path / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)
        storage.create(_make_issue(id="a"))
        storage.create(_make_issue(id="b"))
        # b depends on a (i.e. a blocks b). Now adding "a depends on b"
        # would close the loop.
        storage.add_dependency("dc-b", "dc-a", "blocks")

        a = storage.get("dc-a")
        assert a is not None
        screen = IssueEditorScreen(a, storage)

        class TestApp(App[None]):
            def compose(self) -> ComposeResult:
                yield Header()

        app = TestApp()
        async with app.run_test() as pilot:
            app.push_screen(screen)
            await pilot.pause()

            panel = screen.query_one("#editor-panel", IssueDetailPanel)
            panel.query_one("#depends-on-input", Input).value = "dc-b"
            panel.do_save()
            await pilot.pause()

            # No new edge should have been added in either direction
            a_deps = storage.get_dependencies("dc-a")
            assert all(d.depends_on_id != "dc-b" for d in a_deps)


class TestBrokenParentDetection:
    """Detail panel flags a tombstoned parent on mount (dogcat-4g9i)."""

    @pytest.mark.asyncio
    async def test_tombstoned_parent_marks_button_broken(
        self,
        tmp_path: Any,
    ) -> None:
        """Tombstoned parent picks up the ``parent-broken`` class.

        Simulates an issue whose parent was deleted by another process.
        """
        from textual.app import App, ComposeResult

        from dogcat.storage import JSONLStorage
        from dogcat.tui.detail_panel import IssueDetailPanel

        storage_path = tmp_path / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)
        parent = storage.create(_make_issue(id="par", title="Parent"))
        storage.create(_make_issue(id="kid", title="Child", parent=parent.full_id))
        storage.delete(parent.full_id)

        kid = storage.get("dc-kid")
        assert kid is not None
        screen = IssueEditorScreen(kid, storage, view_mode=True)

        class TestApp(App[None]):
            def compose(self) -> ComposeResult:
                yield Header()

        app = TestApp()
        async with app.run_test() as pilot:
            app.push_screen(screen)
            await pilot.pause()

            panel = screen.query_one("#editor-panel", IssueDetailPanel)
            btn = panel.query_one("#parent-input", Button)
            assert "parent-broken" in btn.classes

    @pytest.mark.asyncio
    async def test_intact_parent_does_not_mark_broken(
        self,
        tmp_path: Any,
    ) -> None:
        """Sanity: an intact parent must NOT get the broken class."""
        from textual.app import App, ComposeResult

        from dogcat.storage import JSONLStorage
        from dogcat.tui.detail_panel import IssueDetailPanel

        storage_path = tmp_path / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)
        parent = storage.create(_make_issue(id="par", title="Parent"))
        storage.create(_make_issue(id="kid", title="Child", parent=parent.full_id))

        kid = storage.get("dc-kid")
        assert kid is not None
        screen = IssueEditorScreen(kid, storage, view_mode=True)

        class TestApp(App[None]):
            def compose(self) -> ComposeResult:
                yield Header()

        app = TestApp()
        async with app.run_test() as pilot:
            app.push_screen(screen)
            await pilot.pause()

            panel = screen.query_one("#editor-panel", IssueDetailPanel)
            btn = panel.query_one("#parent-input", Button)
            assert "parent-broken" not in btn.classes
