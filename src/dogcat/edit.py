"""Textual-based issue editor for interactive editing."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import (
    Button,
    Footer,
    Input,
    Label,
    Select,
    Static,
    TextArea,
)

from dogcat.constants import PRIORITY_OPTIONS, STATUS_OPTIONS, TYPE_OPTIONS

if TYPE_CHECKING:
    from dogcat.models import Issue
    from dogcat.storage import JSONLStorage


class IssueEditorApp(App[bool]):
    """Textual app for editing an issue."""

    TITLE = "Edit Issue"

    BINDINGS: ClassVar = [
        Binding("ctrl+s", "save", "Save", priority=True),
        Binding("escape", "quit", "Cancel"),
    ]

    CSS = """
    #editor-form {
        padding: 1 2;
    }

    #title-bar {
        height: auto;
        max-height: 3;
        padding: 0 2;
        margin: 1 0;
    }

    #id-display {
        width: auto;
        min-width: 12;
        padding: 0 2;
        content-align: left middle;
        height: 3;
        color: $text-muted;
    }

    #title-input {
        width: 1fr;
    }

    #title-bar Button {
        margin-left: 1;
    }

    .field-label {
        margin-top: 1;
        color: $text-muted;
    }

    .field-row {
        height: auto;
        max-height: 5;
        margin-bottom: 1;
    }

    .field-row > Select {
        width: 1fr;
    }

    .info-row {
        height: auto;
        max-height: 3;
    }

    .info-row > Input {
        width: 1fr;
    }

    #parent-display {
        width: 1fr;
        padding: 0 2;
        content-align: left middle;
        height: 3;
        background: $surface;
        color: $text-muted;
    }

    #description-input {
        min-height: 8;
        max-height: 20;
    }
    """

    def __init__(
        self,
        issue: Issue,
        storage: JSONLStorage,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._issue = issue
        self._storage = storage
        self.saved = False
        self.updated_issue: Issue | None = None

    def _get_parent_display(self) -> str:
        """Get display text for the parent issue."""
        if not self._issue.parent:
            return "Parent: None"
        parent = self._storage.get(self._issue.parent)
        if parent:
            return f"Parent: {parent.full_id} {parent.title}"
        return f"Parent: {self._issue.parent}"

    def compose(self) -> ComposeResult:
        """Compose the editor form."""
        with Horizontal(id="title-bar"):
            yield Static(self._issue.full_id, id="id-display")
            yield Input(
                value=self._issue.title,
                placeholder="Title",
                id="title-input",
            )
            yield Button("Cancel", id="cancel-btn", variant="default")
            yield Button("Save", id="save-btn", variant="primary")

        with VerticalScroll(id="editor-form"):
            with Horizontal(classes="field-row"):
                yield Select(
                    options=[(label, val) for label, val in TYPE_OPTIONS],
                    value=self._issue.issue_type.value,
                    id="type-input",
                    allow_blank=False,
                )
                yield Select(
                    options=[(label, val) for label, val in STATUS_OPTIONS],
                    value=self._issue.status.value,
                    id="status-input",
                    allow_blank=False,
                )
                yield Select(
                    options=[(label, val) for label, val in PRIORITY_OPTIONS],
                    value=self._issue.priority,
                    id="priority-input",
                    allow_blank=False,
                )

            with Horizontal(classes="info-row"):
                yield Input(
                    value=self._issue.owner or "",
                    placeholder="Owner",
                    id="owner-input",
                )
                yield Static(self._get_parent_display(), id="parent-display")

            yield Label("Description", classes="field-label")
            yield TextArea(
                self._issue.description or "",
                id="description-input",
            )

        yield Footer()

    def on_mount(self) -> None:
        """Focus the title input on mount."""
        self.query_one("#title-input", Input).focus()
        self.title = f"Edit: {self._issue.full_id} - {self._issue.title}"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "cancel-btn":
            self.exit(False)
        elif event.button.id == "save-btn":
            self._do_save()

    def action_save(self) -> None:
        """Save the issue."""
        self._do_save()

    def _do_save(self) -> None:
        """Execute the save."""
        title = self.query_one("#title-input", Input).value.strip()
        if not title:
            self.notify("Title cannot be empty", severity="error")
            return

        type_val = self.query_one("#type-input", Select).value
        status_val = self.query_one("#status-input", Select).value
        priority_val = self.query_one("#priority-input", Select).value
        description = self.query_one("#description-input", TextArea).text.strip()

        updates: dict[str, Any] = {}

        if title != self._issue.title:
            updates["title"] = title
        if isinstance(type_val, str) and type_val != self._issue.issue_type.value:
            updates["issue_type"] = type_val
        if isinstance(status_val, str) and status_val != self._issue.status.value:
            updates["status"] = status_val
        if isinstance(priority_val, int) and priority_val != self._issue.priority:
            updates["priority"] = priority_val

        new_owner = self.query_one("#owner-input", Input).value.strip() or None
        if new_owner != self._issue.owner:
            updates["owner"] = new_owner

        new_desc = description or None
        if new_desc != self._issue.description:
            updates["description"] = new_desc

        if not updates:
            self.notify("No changes to save")
            self.exit(False)
            return

        try:
            self.updated_issue = self._storage.update(self._issue.id, updates)
            self.saved = True
            self.exit(True)
        except Exception as e:
            self.notify(f"Save failed: {e}", severity="error")


def edit_issue(issue_id: str, storage: JSONLStorage) -> Issue | None:
    """Open the Textual editor for an issue.

    Args:
        issue_id: The issue ID to edit.
        storage: The storage backend.

    Returns:
        The updated issue, or None if cancelled/not found.
    """
    issue = storage.get(issue_id)
    if issue is None:
        return None

    editor = IssueEditorApp(issue, storage)
    editor.run()

    if editor.saved and editor.updated_issue is not None:
        return editor.updated_issue
    return None
