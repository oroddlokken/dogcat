"""Tests for the Textual-based issue editor."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from rich.text import Text
from textual.widgets import Collapsible, Input, OptionList, Select, Static, TextArea

from dogcat.models import Issue
from dogcat.tui.editor import IssueEditorApp
from dogcat.tui.picker import IssuePickerApp
from dogcat.tui.shared import make_issue_label


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
    return storage


class TestCollapsibleFields:
    """Test collapsible notes, acceptance, and design fields."""

    @pytest.mark.asyncio
    async def test_collapsible_sections_exist(self) -> None:
        """All three collapsible sections are rendered."""
        issue = _make_issue()
        app = IssueEditorApp(issue, _make_storage())

        async with app.run_test() as _pilot:
            collapsibles = app.query(Collapsible)
            titles = [c.title for c in collapsibles]
            assert "Notes" in titles
            assert "Acceptance Criteria" in titles
            assert "Design" in titles

    @pytest.mark.asyncio
    async def test_empty_fields_collapsed(self) -> None:
        """Collapsible sections are collapsed when the field is empty."""
        issue = _make_issue(notes=None, acceptance=None, design=None)
        app = IssueEditorApp(issue, _make_storage())

        async with app.run_test() as _pilot:
            for collapsible in app.query(Collapsible):
                assert collapsible.collapsed is True

    @pytest.mark.asyncio
    async def test_populated_fields_expanded(self) -> None:
        """Collapsible sections are expanded when the field has content."""
        issue = _make_issue(
            notes="some notes",
            acceptance="some criteria",
            design="some design",
        )
        app = IssueEditorApp(issue, _make_storage())

        async with app.run_test() as _pilot:
            for collapsible in app.query(Collapsible):
                assert collapsible.collapsed is False

    @pytest.mark.asyncio
    async def test_textareas_contain_field_values(self) -> None:
        """TextAreas within collapsibles contain the issue field values."""
        issue = _make_issue(
            notes="my notes",
            acceptance="my criteria",
            design="my design",
        )
        app = IssueEditorApp(issue, _make_storage())

        async with app.run_test() as _pilot:
            assert app.query_one("#notes-input", TextArea).text == "my notes"
            assert app.query_one("#acceptance-input", TextArea).text == "my criteria"
            assert app.query_one("#design-input", TextArea).text == "my design"

    @pytest.mark.asyncio
    async def test_save_includes_new_fields(self) -> None:
        """Saving captures changes to notes, acceptance, and design."""
        issue = _make_issue(notes=None, acceptance=None, design=None)
        storage = _make_storage()
        updated_issue = _make_issue(
            notes="new notes",
            acceptance="new criteria",
            design="new design",
        )
        storage.update.return_value = updated_issue
        app = IssueEditorApp(issue, storage)

        async with app.run_test() as pilot:
            # Set values in the collapsible textareas
            notes_ta = app.query_one("#notes-input", TextArea)
            notes_ta.load_text("new notes")

            acceptance_ta = app.query_one("#acceptance-input", TextArea)
            acceptance_ta.load_text("new criteria")

            design_ta = app.query_one("#design-input", TextArea)
            design_ta.load_text("new design")

            # Trigger save
            await pilot.press("ctrl+s")

        storage.update.assert_called_once()
        updates = storage.update.call_args[0][1]
        assert updates["notes"] == "new notes"
        assert updates["acceptance"] == "new criteria"
        assert updates["design"] == "new design"

    @pytest.mark.asyncio
    async def test_save_skips_unchanged_fields(self) -> None:
        """Unchanged collapsible fields are not included in updates."""
        issue = _make_issue(notes="existing", acceptance=None, design=None)
        storage = _make_storage()
        storage.update.return_value = _make_issue(title="Changed title")
        app = IssueEditorApp(issue, storage)

        async with app.run_test() as pilot:
            # Only change the title
            from textual.widgets import Input

            title_input = app.query_one("#title-input", Input)
            title_input.value = "Changed title"

            await pilot.press("ctrl+s")

        storage.update.assert_called_once()
        updates = storage.update.call_args[0][1]
        assert "notes" not in updates
        assert "acceptance" not in updates
        assert "design" not in updates

    @pytest.mark.asyncio
    async def test_mixed_collapsed_state(self) -> None:
        """Only sections with content are expanded."""
        issue = _make_issue(notes="has notes", acceptance=None, design="has design")
        app = IssueEditorApp(issue, _make_storage())

        async with app.run_test() as _pilot:
            collapsibles = {c.title: c for c in app.query(Collapsible)}
            assert collapsibles["Notes"].collapsed is False
            assert collapsibles["Acceptance Criteria"].collapsed is True
            assert collapsibles["Design"].collapsed is False


class TestExternalRefField:
    """Test external reference field in the edit form."""

    @pytest.mark.asyncio
    async def test_external_ref_field_exists(self) -> None:
        """External ref input is rendered in the info row."""
        issue = _make_issue()
        app = IssueEditorApp(issue, _make_storage())

        async with app.run_test() as _pilot:
            ref_input = app.query_one("#external-ref-input", Input)
            assert ref_input.value == ""

    @pytest.mark.asyncio
    async def test_external_ref_displays_value(self) -> None:
        """External ref input shows existing value."""
        issue = _make_issue(external_ref="JIRA-123")
        app = IssueEditorApp(issue, _make_storage())

        async with app.run_test() as _pilot:
            ref_input = app.query_one("#external-ref-input", Input)
            assert ref_input.value == "JIRA-123"

    @pytest.mark.asyncio
    async def test_save_includes_external_ref(self) -> None:
        """Saving captures changes to external_ref."""
        issue = _make_issue(external_ref=None)
        storage = _make_storage()
        storage.update.return_value = _make_issue(external_ref="https://example.com")
        app = IssueEditorApp(issue, storage)

        async with app.run_test() as pilot:
            ref_input = app.query_one("#external-ref-input", Input)
            ref_input.value = "https://example.com"
            await pilot.press("ctrl+s")

        storage.update.assert_called_once()
        updates = storage.update.call_args[0][1]
        assert updates["external_ref"] == "https://example.com"

    @pytest.mark.asyncio
    async def test_save_skips_unchanged_external_ref(self) -> None:
        """Unchanged external_ref is not included in updates."""
        issue = _make_issue(external_ref="JIRA-123")
        storage = _make_storage()
        storage.update.return_value = _make_issue(title="New title")
        app = IssueEditorApp(issue, storage)

        async with app.run_test() as pilot:
            title_input = app.query_one("#title-input", Input)
            title_input.value = "New title"
            await pilot.press("ctrl+s")

        storage.update.assert_called_once()
        updates = storage.update.call_args[0][1]
        assert "external_ref" not in updates


class TestCreateMode:
    """Test IssueEditorApp in create mode."""

    @pytest.mark.asyncio
    async def test_shows_new_issue_label(self) -> None:
        """Create mode shows 'New Issue' instead of issue ID."""
        issue = _make_issue(id="", title="")
        app = IssueEditorApp(issue, _make_storage(), create_mode=True, namespace="dc")

        async with app.run_test() as _pilot:
            id_display = app.query_one("#id-display", Static)
            assert str(id_display.render()) == "New Issue"

    @pytest.mark.asyncio
    async def test_create_mode_calls_storage_create(self) -> None:
        """Save in create mode calls storage.create() instead of update()."""
        issue = _make_issue(id="", title="")
        storage = _make_storage()
        storage.get_issue_ids.return_value = set()
        app = IssueEditorApp(issue, storage, create_mode=True, namespace="dc")

        async with app.run_test() as pilot:
            app.query_one("#title-input", Input).value = "My new issue"
            await pilot.press("ctrl+s")

        storage.create.assert_called_once()
        created = storage.create.call_args[0][0]
        assert created.title == "My new issue"
        assert created.id != ""

    @pytest.mark.asyncio
    async def test_create_mode_requires_title(self) -> None:
        """Create mode rejects empty title."""
        issue = _make_issue(id="", title="")
        storage = _make_storage()
        app = IssueEditorApp(issue, storage, create_mode=True, namespace="dc")

        async with app.run_test() as pilot:
            # Leave title empty, try to save
            await pilot.press("ctrl+s")

        storage.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancel_returns_none(self) -> None:
        """Cancelling in create mode does not create an issue."""
        issue = _make_issue(id="", title="")
        storage = _make_storage()
        app = IssueEditorApp(issue, storage, create_mode=True, namespace="dc")

        async with app.run_test() as pilot:
            await pilot.press("escape")

        storage.create.assert_not_called()
        assert app.saved is False

    @pytest.mark.asyncio
    async def test_create_captures_all_fields(self) -> None:
        """All form fields are included when creating an issue."""
        issue = _make_issue(id="", title="")
        storage = _make_storage()
        storage.get_issue_ids.return_value = set()
        app = IssueEditorApp(issue, storage, create_mode=True, namespace="dc")

        async with app.run_test() as pilot:
            app.query_one("#title-input", Input).value = "Full issue"
            app.query_one("#owner-input", Input).value = "alice@example.com"
            app.query_one("#external-ref-input", Input).value = "JIRA-999"
            app.query_one("#description-input", TextArea).load_text("A description")
            app.query_one("#notes-input", TextArea).load_text("Some notes")
            app.query_one("#acceptance-input", TextArea).load_text("Criteria here")
            app.query_one("#design-input", TextArea).load_text("Design doc")
            await pilot.press("ctrl+s")

        created = storage.create.call_args[0][0]
        assert created.title == "Full issue"
        assert created.owner == "alice@example.com"
        assert created.external_ref == "JIRA-999"
        assert created.description == "A description"
        assert created.notes == "Some notes"
        assert created.acceptance == "Criteria here"
        assert created.design == "Design doc"

    @pytest.mark.asyncio
    async def test_create_uses_correct_defaults(self) -> None:
        """New issue gets correct default status, priority, and type."""
        issue = _make_issue(id="", title="")
        storage = _make_storage()
        storage.get_issue_ids.return_value = set()
        app = IssueEditorApp(issue, storage, create_mode=True, namespace="dc")

        async with app.run_test() as pilot:
            app.query_one("#title-input", Input).value = "Default test"
            await pilot.press("ctrl+s")

        created = storage.create.call_args[0][0]
        assert created.status.value == "open"
        assert created.priority == 2
        assert created.issue_type.value == "task"

    @pytest.mark.asyncio
    async def test_create_uses_namespace(self) -> None:
        """Created issue uses the provided namespace."""
        issue = _make_issue(id="", title="", namespace="myns")
        storage = _make_storage()
        storage.get_issue_ids.return_value = set()
        app = IssueEditorApp(issue, storage, create_mode=True, namespace="myns")

        async with app.run_test() as pilot:
            app.query_one("#title-input", Input).value = "Namespace test"
            await pilot.press("ctrl+s")

        created = storage.create.call_args[0][0]
        assert created.namespace == "myns"

    @pytest.mark.asyncio
    async def test_create_does_not_call_update(self) -> None:
        """Create mode never calls storage.update()."""
        issue = _make_issue(id="", title="")
        storage = _make_storage()
        storage.get_issue_ids.return_value = set()
        app = IssueEditorApp(issue, storage, create_mode=True, namespace="dc")

        async with app.run_test() as pilot:
            app.query_one("#title-input", Input).value = "No update"
            await pilot.press("ctrl+s")

        storage.update.assert_not_called()
        storage.create.assert_called_once()


class TestCreateModeShorthands:
    """Test IssueEditorApp in create mode with pre-filled shorthands."""

    @pytest.mark.asyncio
    async def test_prefilled_title(self) -> None:
        """Pre-filled title appears in the title input."""
        issue = _make_issue(id="", title="My bug report")
        app = IssueEditorApp(issue, _make_storage(), create_mode=True, namespace="dc")

        async with app.run_test() as _pilot:
            title_input = app.query_one("#title-input", Input)
            assert title_input.value == "My bug report"

    @pytest.mark.asyncio
    async def test_prefilled_priority(self) -> None:
        """Pre-filled priority is selected in the dropdown."""
        issue = _make_issue(id="", title="", priority=0)
        app = IssueEditorApp(issue, _make_storage(), create_mode=True, namespace="dc")

        async with app.run_test() as _pilot:
            priority_select = cast(
                "Select[int]",
                app.query_one("#priority-input", Select),
            )
            assert priority_select.value == 0

    @pytest.mark.asyncio
    async def test_prefilled_type(self) -> None:
        """Pre-filled issue type is selected in the dropdown."""
        from dogcat.models import IssueType

        issue = _make_issue(id="", title="", issue_type=IssueType.BUG)
        app = IssueEditorApp(issue, _make_storage(), create_mode=True, namespace="dc")

        async with app.run_test() as _pilot:
            type_select = cast("Select[str]", app.query_one("#type-input", Select))
            assert type_select.value == "bug"

    @pytest.mark.asyncio
    async def test_prefilled_all_shorthands_saved(self) -> None:
        """Pre-filled title, priority, and type are persisted on save."""
        from dogcat.models import IssueType

        issue = _make_issue(
            id="",
            title="Critical crash",
            priority=1,
            issue_type=IssueType.BUG,
        )
        storage = _make_storage()
        storage.get_issue_ids.return_value = set()
        app = IssueEditorApp(issue, storage, create_mode=True, namespace="dc")

        async with app.run_test() as pilot:
            await pilot.press("ctrl+s")

        storage.create.assert_called_once()
        created = storage.create.call_args[0][0]
        assert created.title == "Critical crash"
        assert created.priority == 1
        assert created.issue_type == IssueType.BUG


class TestParentPicker:
    """Test interactive parent issue picker."""

    def _make_storage_with_issues(self) -> MagicMock:
        """Create mock storage with a set of issues for parent selection."""
        storage = _make_storage()
        parent_issue = _make_issue(id="par1", title="Parent issue")
        other_issue = _make_issue(id="oth1", title="Other issue")
        child_issue = _make_issue(id="ch1", title="Child issue", parent="dc-test")
        storage.list.return_value = [
            _make_issue(id="test", title="Current issue"),
            parent_issue,
            other_issue,
            child_issue,
        ]
        storage.get_children.return_value = [child_issue]
        return storage

    @pytest.mark.asyncio
    async def test_parent_select_renders(self) -> None:
        """Parent Select widget is rendered in the form."""
        issue = _make_issue()
        storage = _make_storage()
        storage.list.return_value = []
        storage.get_children.return_value = []
        app = IssueEditorApp(issue, storage)

        async with app.run_test() as _pilot:
            parent_select = cast("Select[str]", app.query_one("#parent-input", Select))
            assert parent_select is not None

    @pytest.mark.asyncio
    async def test_parent_shows_current_value(self) -> None:
        """Parent Select shows the current parent issue."""
        issue = _make_issue(parent="dc-par1")
        storage = _make_storage()
        parent_issue = _make_issue(id="par1", title="Parent issue")
        storage.list.return_value = [parent_issue]
        storage.get_children.return_value = []
        app = IssueEditorApp(issue, storage)

        async with app.run_test() as _pilot:
            parent_select = cast("Select[str]", app.query_one("#parent-input", Select))
            assert parent_select.value == "dc-par1"

    @pytest.mark.asyncio
    async def test_parent_blank_when_no_parent(self) -> None:
        """Parent Select is blank when issue has no parent."""
        issue = _make_issue(parent=None)
        storage = _make_storage()
        storage.list.return_value = []
        storage.get_children.return_value = []
        app = IssueEditorApp(issue, storage)

        async with app.run_test() as _pilot:
            parent_select = cast("Select[str]", app.query_one("#parent-input", Select))
            assert parent_select.value == Select.BLANK

    @pytest.mark.asyncio
    async def test_excludes_self_from_options(self) -> None:
        """Current issue is excluded from parent options."""
        issue = _make_issue(id="test", title="Current")
        storage = self._make_storage_with_issues()
        app = IssueEditorApp(issue, storage)

        async with app.run_test() as _pilot:
            parent_select = cast("Select[str]", app.query_one("#parent-input", Select))
            option_values = [opt[1] for opt in parent_select._options]
            assert "dc-test" not in option_values
            assert "dc-par1" in option_values
            assert "dc-oth1" in option_values

    @pytest.mark.asyncio
    async def test_excludes_descendants_from_options(self) -> None:
        """Descendants of current issue are excluded from parent options."""
        issue = _make_issue(id="test", title="Current")
        storage = self._make_storage_with_issues()
        app = IssueEditorApp(issue, storage)

        async with app.run_test() as _pilot:
            parent_select = cast("Select[str]", app.query_one("#parent-input", Select))
            option_values = [opt[1] for opt in parent_select._options]
            assert "dc-ch1" not in option_values

    @pytest.mark.asyncio
    async def test_save_captures_parent_change(self) -> None:
        """Changing the parent is captured on save."""
        issue = _make_issue(parent=None)
        storage = _make_storage()
        storage.list.return_value = [_make_issue(id="par1", title="New parent")]
        storage.get_children.return_value = []
        storage.update.return_value = _make_issue(parent="dc-par1")
        app = IssueEditorApp(issue, storage)

        async with app.run_test() as pilot:
            app.query_one("#parent-input", Select).value = "dc-par1"
            await pilot.press("ctrl+s")

        storage.update.assert_called_once()
        updates = storage.update.call_args[0][1]
        assert updates["parent"] == "dc-par1"

    @pytest.mark.asyncio
    async def test_save_clears_parent(self) -> None:
        """Clearing the parent sets it to None on save."""
        issue = _make_issue(parent="dc-par1")
        storage = _make_storage()
        storage.list.return_value = [_make_issue(id="par1", title="Parent")]
        storage.get_children.return_value = []
        storage.update.return_value = _make_issue(parent=None)
        app = IssueEditorApp(issue, storage)

        async with app.run_test() as pilot:
            app.query_one("#parent-input", Select).value = Select.BLANK
            await pilot.press("ctrl+s")

        storage.update.assert_called_once()
        updates = storage.update.call_args[0][1]
        assert updates["parent"] is None

    @pytest.mark.asyncio
    async def test_unchanged_parent_not_in_updates(self) -> None:
        """Unchanged parent is not included in updates."""
        issue = _make_issue(parent="dc-par1")
        storage = _make_storage()
        storage.list.return_value = [_make_issue(id="par1", title="Parent")]
        storage.get_children.return_value = []
        storage.update.return_value = _make_issue(title="New title")
        app = IssueEditorApp(issue, storage)

        async with app.run_test() as pilot:
            app.query_one("#title-input", Input).value = "New title"
            await pilot.press("ctrl+s")

        storage.update.assert_called_once()
        updates = storage.update.call_args[0][1]
        assert "parent" not in updates


class TestMakeIssueLabel:
    """Test make_issue_label includes labels and manual flag."""

    def test_labels_shown(self) -> None:
        """Labels appear in the picker label text."""
        issue = _make_issue(labels=["ui", "ux"])
        text = make_issue_label(issue)
        assert "[ui, ux]" in text.plain

    def test_no_labels_when_empty(self) -> None:
        """No label bracket when issue has no labels."""
        issue = _make_issue(labels=[])
        text = make_issue_label(issue)
        assert "[ui" not in text.plain

    def test_manual_flag_shown(self) -> None:
        """Manual flag appears when metadata.manual is set."""
        issue = _make_issue(metadata={"manual": True})
        text = make_issue_label(issue)
        assert "[manual]" in text.plain

    def test_no_manual_flag_by_default(self) -> None:
        """No manual flag when metadata has no manual key."""
        issue = _make_issue()
        text = make_issue_label(issue)
        assert "[manual]" not in text.plain


def _make_picker_issues() -> list[tuple[Text, str]]:
    """Create test issue labels for the picker."""
    issues: list[tuple[Text, str]] = []
    for id_, type_, title in [
        ("dc-abc1", "bug", "Fix login crash"),
        ("dc-def2", "feature", "Add dark mode"),
        ("dc-ghi3", "task", "Update docs"),
    ]:
        label = Text()
        label.append(f"[{type_}] ", style="white")
        label.append(f"{id_} {title}")
        issues.append((label, id_))
    return issues


class TestIssuePicker:
    """Test the Textual issue picker."""

    @pytest.mark.asyncio
    async def test_picker_renders_issues(self) -> None:
        """Picker shows all issues in the option list."""
        issues = _make_picker_issues()
        app = IssuePickerApp(issues)

        async with app.run_test() as _pilot:
            option_list = app.query_one("#picker-list", OptionList)
            assert option_list.option_count == 3

    @pytest.mark.asyncio
    async def test_picker_cancel_returns_none(self) -> None:
        """Pressing escape returns None."""
        issues = _make_picker_issues()
        app = IssuePickerApp(issues)

        async with app.run_test() as pilot:
            await pilot.press("escape")

        assert app.selected_id is None

    @pytest.mark.asyncio
    async def test_picker_filter_narrows_options(self) -> None:
        """Typing in the search input filters the option list."""
        issues = _make_picker_issues()
        app = IssuePickerApp(issues)

        async with app.run_test() as pilot:
            search = app.query_one("#picker-search", Input)
            search.value = "login"
            await pilot.pause()

            option_list = app.query_one("#picker-list", OptionList)
            assert option_list.option_count == 1

    @pytest.mark.asyncio
    async def test_picker_filter_by_id(self) -> None:
        """Filtering by issue ID works."""
        issues = _make_picker_issues()
        app = IssuePickerApp(issues)

        async with app.run_test() as pilot:
            search = app.query_one("#picker-search", Input)
            search.value = "def2"
            await pilot.pause()

            option_list = app.query_one("#picker-list", OptionList)
            assert option_list.option_count == 1

    @pytest.mark.asyncio
    async def test_picker_empty_filter_shows_all(self) -> None:
        """Clearing the filter shows all issues again."""
        issues = _make_picker_issues()
        app = IssuePickerApp(issues)

        async with app.run_test() as pilot:
            search = app.query_one("#picker-search", Input)
            search.value = "login"
            await pilot.pause()
            search.value = ""
            await pilot.pause()

            option_list = app.query_one("#picker-list", OptionList)
            assert option_list.option_count == 3


class TestButtonHandlers:
    """Test button press handlers."""

    @pytest.mark.asyncio
    async def test_cancel_button_exits(self) -> None:
        """Clicking cancel button exits without saving."""
        issue = _make_issue()
        storage = _make_storage()
        app = IssueEditorApp(issue, storage)

        async with app.run_test() as pilot:
            await pilot.click("#cancel-btn")

        assert app.saved is False
        storage.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_save_button_saves(self) -> None:
        """Clicking save button triggers save."""
        issue = _make_issue()
        storage = _make_storage()
        storage.update.return_value = _make_issue(title="Changed")
        app = IssueEditorApp(issue, storage)

        async with app.run_test() as pilot:
            app.query_one("#title-input", Input).value = "Changed"
            await pilot.click("#save-btn")

        storage.update.assert_called_once()


class TestManualCheckboxToggle:
    """Test manual checkbox behavior in edit form."""

    @pytest.mark.asyncio
    async def test_manual_toggle_on(self) -> None:
        """Toggling manual checkbox on includes metadata update."""
        issue = _make_issue(metadata={})
        storage = _make_storage()
        storage.update.return_value = _make_issue(metadata={"manual": True})
        app = IssueEditorApp(issue, storage)

        async with app.run_test() as pilot:
            from textual.widgets import Checkbox

            checkbox = app.query_one("#manual-input", Checkbox)
            checkbox.value = True
            await pilot.press("ctrl+s")

        storage.update.assert_called_once()
        updates = storage.update.call_args[0][1]
        assert "metadata" in updates
        assert updates["metadata"]["manual"] is True

    @pytest.mark.asyncio
    async def test_manual_toggle_off(self) -> None:
        """Toggling manual checkbox off removes manual from metadata."""
        issue = _make_issue(metadata={"manual": True})
        storage = _make_storage()
        storage.update.return_value = _make_issue(metadata={})
        app = IssueEditorApp(issue, storage)

        async with app.run_test() as pilot:
            from textual.widgets import Checkbox

            checkbox = app.query_one("#manual-input", Checkbox)
            checkbox.value = False
            await pilot.press("ctrl+s")

        storage.update.assert_called_once()
        updates = storage.update.call_args[0][1]
        assert "metadata" in updates
        assert "manual" not in updates["metadata"]


class TestNoChangesToSave:
    """Test saving when no changes were made."""

    @pytest.mark.asyncio
    async def test_no_changes_exits_without_update(self) -> None:
        """Saving with no changes exits without calling update."""
        issue = _make_issue()
        storage = _make_storage()
        storage.list.return_value = []
        storage.get_children.return_value = []
        app = IssueEditorApp(issue, storage)

        async with app.run_test() as pilot:
            # Don't change anything, just save
            await pilot.press("ctrl+s")

        storage.update.assert_not_called()
        assert app.saved is False


class TestCreateModeStorageException:
    """Test that create mode handles storage exceptions."""

    @pytest.mark.asyncio
    async def test_create_exception_shows_notification(self) -> None:
        """Storage.create exception is handled gracefully."""
        issue = _make_issue(id="", title="")
        storage = _make_storage()
        storage.get_issue_ids.return_value = set()
        storage.create.side_effect = RuntimeError("DB error")
        app = IssueEditorApp(issue, storage, create_mode=True, namespace="dc")

        async with app.run_test() as pilot:
            app.query_one("#title-input", Input).value = "Will fail"
            await pilot.press("ctrl+s")

        # create was called but raised
        storage.create.assert_called_once()
        # Should not mark as saved
        assert app.saved is False


class TestUpdateModeStorageException:
    """Test that update mode handles storage exceptions."""

    @pytest.mark.asyncio
    async def test_update_exception_shows_notification(self) -> None:
        """Storage.update exception is handled gracefully."""
        issue = _make_issue()
        storage = _make_storage()
        storage.list.return_value = []
        storage.get_children.return_value = []
        storage.update.side_effect = RuntimeError("DB error")
        app = IssueEditorApp(issue, storage)

        async with app.run_test() as pilot:
            app.query_one("#title-input", Input).value = "Changed title"
            await pilot.press("ctrl+s")

        storage.update.assert_called_once()
        assert app.saved is False
