"""Textual-based issue editor for interactive editing."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import (
    Button,
    Collapsible,
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

    .collapsible-textarea {
        height: auto;
        min-height: 5;
        max-height: 8;
    }
    """

    def __init__(
        self,
        issue: Issue,
        storage: JSONLStorage,
        *,
        create_mode: bool = False,
        namespace: str = "dc",
        existing_ids: set[str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._issue = issue
        self._storage = storage
        self._create_mode = create_mode
        self._namespace = namespace
        self._existing_ids = existing_ids or set()
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
            id_text = "New Issue" if self._create_mode else self._issue.full_id
            yield Static(id_text, id="id-display")
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
                yield Input(
                    value=self._issue.external_ref or "",
                    placeholder="External ref",
                    id="external-ref-input",
                )

            yield Label("Description", classes="field-label")
            yield TextArea(
                self._issue.description or "",
                id="description-input",
            )

            with Collapsible(
                title="Notes",
                collapsed=not self._issue.notes,
            ):
                yield TextArea(
                    self._issue.notes or "",
                    id="notes-input",
                    classes="collapsible-textarea",
                )

            with Collapsible(
                title="Acceptance Criteria",
                collapsed=not self._issue.acceptance,
            ):
                yield TextArea(
                    self._issue.acceptance or "",
                    id="acceptance-input",
                    classes="collapsible-textarea",
                )

            with Collapsible(
                title="Design",
                collapsed=not self._issue.design,
            ):
                yield TextArea(
                    self._issue.design or "",
                    id="design-input",
                    classes="collapsible-textarea",
                )

        yield Footer()

    def on_mount(self) -> None:
        """Focus the title input on mount."""
        self.query_one("#title-input", Input).focus()
        if self._create_mode:
            self.title = "New Issue"
        else:
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

        if self._create_mode:
            self._do_create(title, type_val, status_val, priority_val, description)
        else:
            self._do_update(title, type_val, status_val, priority_val, description)

    def _do_create(
        self,
        title: str,
        type_val: Any,
        status_val: Any,
        priority_val: Any,
        description: str,
    ) -> None:
        """Create a new issue from the form values."""
        from dogcat.idgen import IDGenerator
        from dogcat.models import Issue, IssueType, Status

        timestamp = datetime.now().astimezone()
        idgen = IDGenerator(existing_ids=self._existing_ids, prefix=self._namespace)
        issue_id = idgen.generate_issue_id(
            title,
            timestamp=timestamp,
            namespace=self._namespace,
        )

        issue = Issue(
            id=issue_id,
            title=title,
            namespace=self._namespace,
            description=description or None,
            status=Status(status_val) if isinstance(status_val, str) else Status.OPEN,
            priority=priority_val if isinstance(priority_val, int) else 2,
            issue_type=(
                IssueType(type_val) if isinstance(type_val, str) else IssueType.TASK
            ),
            owner=self.query_one("#owner-input", Input).value.strip() or None,
            external_ref=(
                self.query_one("#external-ref-input", Input).value.strip() or None
            ),
            notes=self.query_one("#notes-input", TextArea).text.strip() or None,
            acceptance=(
                self.query_one("#acceptance-input", TextArea).text.strip() or None
            ),
            design=self.query_one("#design-input", TextArea).text.strip() or None,
            created_at=timestamp,
            updated_at=timestamp,
        )

        try:
            self._storage.create(issue)
            self.updated_issue = issue
            self.saved = True
            self.exit(True)
        except Exception as e:
            self.notify(f"Create failed: {e}", severity="error")

    def _do_update(
        self,
        title: str,
        type_val: Any,
        status_val: Any,
        priority_val: Any,
        description: str,
    ) -> None:
        """Update an existing issue with changed fields."""
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

        new_ref = self.query_one("#external-ref-input", Input).value.strip() or None
        if new_ref != self._issue.external_ref:
            updates["external_ref"] = new_ref

        new_desc = description or None
        if new_desc != self._issue.description:
            updates["description"] = new_desc

        new_notes = self.query_one("#notes-input", TextArea).text.strip() or None
        if new_notes != self._issue.notes:
            updates["notes"] = new_notes

        new_acceptance = (
            self.query_one("#acceptance-input", TextArea).text.strip() or None
        )
        if new_acceptance != self._issue.acceptance:
            updates["acceptance"] = new_acceptance

        new_design = self.query_one("#design-input", TextArea).text.strip() or None
        if new_design != self._issue.design:
            updates["design"] = new_design

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


def new_issue(
    storage: JSONLStorage,
    namespace: str,
    owner: str | None = None,
) -> Issue | None:
    """Open the Textual editor to create a new issue.

    Args:
        storage: The storage backend.
        namespace: The issue namespace/prefix.
        owner: Default owner for the new issue.

    Returns:
        The created issue, or None if cancelled.
    """
    from dogcat.models import Issue

    skeleton = Issue(
        id="",
        title="",
        namespace=namespace,
        owner=owner,
    )

    editor = IssueEditorApp(
        skeleton,
        storage,
        create_mode=True,
        namespace=namespace,
        existing_ids=storage.get_issue_ids(),
    )
    editor.run()

    if editor.saved and editor.updated_issue is not None:
        return editor.updated_issue
    return None
