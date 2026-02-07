"""Tests for the Textual-based issue editor."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from textual.widgets import Collapsible, Input, TextArea

from dogcat.edit import IssueEditorApp
from dogcat.models import Issue


def _make_issue(**kwargs: object) -> Issue:
    """Create a test issue with sensible defaults."""
    defaults = {
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

        async with app.run_test() as pilot:  # noqa: F841
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

        async with app.run_test() as pilot:  # noqa: F841
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

        async with app.run_test() as pilot:  # noqa: F841
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

        async with app.run_test() as pilot:  # noqa: F841
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

        async with app.run_test() as pilot:  # noqa: F841
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

        async with app.run_test() as pilot:  # noqa: F841
            ref_input = app.query_one("#external-ref-input", Input)
            assert ref_input.value == ""

    @pytest.mark.asyncio
    async def test_external_ref_displays_value(self) -> None:
        """External ref input shows existing value."""
        issue = _make_issue(external_ref="JIRA-123")
        app = IssueEditorApp(issue, _make_storage())

        async with app.run_test() as pilot:  # noqa: F841
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
