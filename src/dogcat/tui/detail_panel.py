"""Reusable issue detail/edit panel widget for the TUI."""

from __future__ import annotations

import contextlib
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar, cast

from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.message import Message
from textual.widget import Widget
from textual.widgets import (
    Button,
    Checkbox,
    Collapsible,
    Input,
    Label,
    Select,
    Static,
    TextArea,
)

from dogcat.constants import (
    PRIORITY_OPTIONS,
    STATUS_OPTIONS,
    TYPE_OPTIONS,
    parse_labels,
)
from dogcat.tui.shared import SHARED_CSS, make_issue_label

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from dogcat.models import Issue
    from dogcat.storage import JSONLStorage


class IssueDetailPanel(Widget, can_focus=True, can_focus_children=True):
    """Standalone issue detail/edit panel.

    Can be embedded in the dashboard split-pane or wrapped by
    ``IssueEditorScreen`` for modal usage.
    """

    class Saved(Message):
        """Posted when an issue is saved."""

        def __init__(self, issue: Issue) -> None:
            super().__init__()
            self.issue = issue

    class Cancelled(Message):
        """Posted when editing is cancelled."""

    class EditModeChanged(Message):
        """Posted when entering or leaving edit mode."""

        def __init__(self, *, editing: bool) -> None:
            super().__init__()
            self.editing = editing

    BINDINGS: ClassVar = [
        Binding("ctrl+s", "save", "Save", priority=True),
        Binding("e", "enter_edit", "Edit"),
    ]

    DEFAULT_CSS = (
        SHARED_CSS
        + """
    IssueDetailPanel {
        height: 1fr;
        width: 1fr;
    }

    IssueDetailPanel #editor-form {
        padding: 1 2;
    }

    IssueDetailPanel #title-input {
        width: 1fr;
    }

    IssueDetailPanel #title-bar Button {
        margin-left: 1;
    }

    IssueDetailPanel #description-input {
        min-height: 8;
        max-height: 20;
    }

    IssueDetailPanel .detail-section-body {
        margin-left: 2;
        margin-bottom: 1;
    }
    """
    )

    def __init__(
        self,
        issue: Issue,
        storage: JSONLStorage,
        *,
        create_mode: bool = False,
        view_mode: bool = False,
        namespace: str = "dc",
        existing_ids: set[str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._issue = issue
        self._storage = storage
        self._create_mode = create_mode
        self._view_mode = view_mode
        self._namespace = namespace
        self._existing_ids = existing_ids or set()

    @property
    def issue(self) -> Issue:
        """The issue currently loaded in the panel."""
        return self._issue

    @property
    def is_view_mode(self) -> bool:
        """Whether the panel is in read-only view mode."""
        return self._view_mode

    def _get_descendants(self, issue_id: str) -> set[str]:
        """Recursively collect all descendant IDs of an issue."""
        descendants: set[str] = set()
        stack = [issue_id]
        while stack:
            current = stack.pop()
            for child in self._storage.get_children(current):
                if child.full_id not in descendants:
                    descendants.add(child.full_id)
                    stack.append(child.full_id)
        return descendants

    def _get_parent_options(self) -> list[tuple[Any, str]]:
        """Build the list of valid parent options, excluding self and descendants."""
        excluded = {self._issue.full_id}
        if not self._create_mode and self._issue.id:
            excluded |= self._get_descendants(self._issue.full_id)

        options: list[tuple[Any, str]] = []
        for issue in self._storage.list():
            if issue.full_id in excluded or issue.is_tombstone():
                continue
            options.append((make_issue_label(issue), issue.full_id))
        return options

    def compose(self) -> ComposeResult:
        """Compose the detail/edit form (no Header/Footer)."""
        ro = self._view_mode

        with Horizontal(id="title-bar"):
            id_text = "New Issue" if self._create_mode else self._issue.full_id
            yield Static(id_text, id="id-display")
            yield Input(
                value=self._issue.title,
                placeholder="Title",
                id="title-input",
                disabled=ro,
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
                    disabled=ro,
                )
                yield Select(
                    options=[(label, val) for label, val in STATUS_OPTIONS],
                    value=self._issue.status.value,
                    id="status-input",
                    allow_blank=False,
                    disabled=ro,
                )
                yield Select(
                    options=[(label, val) for label, val in PRIORITY_OPTIONS],
                    value=self._issue.priority,
                    id="priority-input",
                    allow_blank=False,
                    disabled=ro,
                )
                yield Checkbox(
                    "Manual",
                    value=bool(
                        self._issue.metadata.get("manual")
                        or self._issue.metadata.get("no_agent"),
                    ),
                    id="manual-input",
                    disabled=ro,
                )

            with Horizontal(classes="info-row"):
                yield Input(
                    value=self._issue.owner or "",
                    placeholder="Owner",
                    id="owner-input",
                    disabled=ro,
                )
                yield Select(
                    options=self._get_parent_options(),
                    value=(self._issue.parent or Select.BLANK),
                    prompt="Parent",
                    allow_blank=True,
                    id="parent-input",
                    disabled=ro,
                )
                yield Input(
                    value=self._issue.external_ref or "",
                    placeholder="External ref",
                    id="external-ref-input",
                    disabled=ro,
                )
                yield Input(
                    value=", ".join(self._issue.labels) if self._issue.labels else "",
                    placeholder="Labels (comma or space separated)",
                    id="labels-input",
                    disabled=ro,
                )

            yield Label("Description", classes="field-label")
            yield TextArea(
                self._issue.description or "",
                id="description-input",
                read_only=ro,
            )

            with Collapsible(
                title="Notes",
                collapsed=not self._issue.notes,
            ):
                yield TextArea(
                    self._issue.notes or "",
                    id="notes-input",
                    classes="collapsible-textarea",
                    read_only=ro,
                )

            with Collapsible(
                title="Acceptance Criteria",
                collapsed=not self._issue.acceptance,
            ):
                yield TextArea(
                    self._issue.acceptance or "",
                    id="acceptance-input",
                    classes="collapsible-textarea",
                    read_only=ro,
                )

            with Collapsible(
                title="Design",
                collapsed=not self._issue.design,
            ):
                yield TextArea(
                    self._issue.design or "",
                    id="design-input",
                    classes="collapsible-textarea",
                    read_only=ro,
                )

            with Collapsible(
                title="Plan",
                collapsed=not self._issue.plan,
            ):
                yield TextArea(
                    self._issue.plan or "",
                    id="plan-input",
                    classes="collapsible-textarea",
                    read_only=ro,
                )

            if ro:
                yield from self._compose_view_sections()

    def _compose_view_sections(self) -> ComposeResult:
        """Yield read-only dependency/children/comment sections."""
        deps = self._storage.get_dependencies(self._issue.full_id)
        if deps:
            with Collapsible(title="Dependencies", collapsed=False, id="deps-section"):
                for dep in deps:
                    yield Static(
                        f"  \u2192 {dep.depends_on_id} ({dep.dep_type.value})",
                        classes="detail-section-body",
                    )

        children = self._storage.get_children(self._issue.full_id)
        if children:
            with Collapsible(title="Children", collapsed=False, id="children-section"):
                for child in children:
                    yield Static(
                        f"  \u21b3 {child.id}: {child.title}",
                        classes="detail-section-body",
                    )

        if self._issue.comments:
            with Collapsible(title="Comments", collapsed=False, id="comments-section"):
                for comment in self._issue.comments:
                    yield Static(
                        f"  [{comment.id}] {comment.author}\n    {comment.text}",
                        classes="detail-section-body",
                    )

    def on_mount(self) -> None:
        """Hide buttons in view mode; focus title for edit/create."""
        if self._view_mode:
            self.query_one("#cancel-btn", Button).display = False
            self.query_one("#save-btn", Button).display = False
        elif self._create_mode:
            self.query_one("#title-input", Input).focus()
        else:
            self.query_one("#title-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "cancel-btn":
            self.post_message(self.Cancelled())
        elif event.button.id == "save-btn":
            self.do_save()

    def check_action(  # type: ignore[override]
        self,
        action: str,
        parameters: tuple[object, ...],  # noqa: ARG002
    ) -> bool | None:
        """Conditionally enable bindings based on the current mode."""
        if action == "enter_edit":
            return self._view_mode
        if action == "save":
            return not self._view_mode
        return True

    def action_save(self) -> None:
        """Save the issue (Ctrl+S)."""
        self.do_save()

    def action_enter_edit(self) -> None:
        """Switch from view mode to edit mode (e key)."""
        self.enter_edit()

    def enter_edit(self) -> None:
        """Enable editing on all form fields."""
        self._view_mode = False

        for inp in self.query(Input):
            inp.disabled = False
        for sel in self.query(Select):  # type: ignore[reportUnknownVariableType]
            sel.disabled = False  # type: ignore[reportUnknownMemberType]
        self.query_one("#manual-input", Checkbox).disabled = False
        for ta in self.query(TextArea):
            ta.read_only = False

        self.query_one("#cancel-btn", Button).display = True
        self.query_one("#save-btn", Button).display = True

        for section_id in ("deps-section", "children-section", "comments-section"):
            with contextlib.suppress(Exception):
                self.query_one(f"#{section_id}").remove()

        self.refresh_bindings()
        self.query_one("#title-input", Input).focus()
        self.post_message(self.EditModeChanged(editing=True))

    def cancel_edit(self) -> None:
        """Revert to view mode by recomposing."""
        self._view_mode = True
        self.post_message(self.Cancelled())

    async def load_issue(self, issue: Issue) -> None:
        """Load a new issue into the panel, recomposing the widget."""
        self._issue = issue
        self._view_mode = True
        self._create_mode = False
        await self.recompose()

    def do_save(self) -> None:
        """Execute the save."""
        title = self.query_one("#title-input", Input).value.strip()
        if not title:
            self.notify("Title cannot be empty", severity="error")
            return

        type_val = cast("Select[str]", self.query_one("#type-input", Select)).value
        status_val = cast("Select[str]", self.query_one("#status-input", Select)).value
        priority_val = cast(
            "Select[int]",
            self.query_one("#priority-input", Select),
        ).value
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

        parent_val = cast("Select[str]", self.query_one("#parent-input", Select)).value
        parent = parent_val if isinstance(parent_val, str) else None

        manual_val = self.query_one("#manual-input", Checkbox).value
        metadata: dict[str, Any] = {}
        if manual_val:
            metadata["manual"] = True

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
            parent=parent,
            external_ref=(
                self.query_one("#external-ref-input", Input).value.strip() or None
            ),
            labels=parse_labels(self.query_one("#labels-input", Input).value),
            notes=self.query_one("#notes-input", TextArea).text.strip() or None,
            acceptance=(
                self.query_one("#acceptance-input", TextArea).text.strip() or None
            ),
            design=self.query_one("#design-input", TextArea).text.strip() or None,
            plan=self.query_one("#plan-input", TextArea).text.strip() or None,
            metadata=metadata,
            created_at=timestamp,
            updated_at=timestamp,
        )

        try:
            self._storage.create(issue)
            self.post_message(self.Saved(issue))
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

        parent_val = cast("Select[str]", self.query_one("#parent-input", Select)).value
        new_parent = parent_val if isinstance(parent_val, str) else None
        if new_parent != self._issue.parent:
            updates["parent"] = new_parent

        new_labels = parse_labels(self.query_one("#labels-input", Input).value)
        if new_labels != self._issue.labels:
            updates["labels"] = new_labels

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

        new_plan = self.query_one("#plan-input", TextArea).text.strip() or None
        if new_plan != self._issue.plan:
            updates["plan"] = new_plan

        manual_val = self.query_one("#manual-input", Checkbox).value
        was_manual = bool(
            self._issue.metadata.get("manual") or self._issue.metadata.get("no_agent"),
        )
        if manual_val != was_manual:
            new_metadata = dict(self._issue.metadata) if self._issue.metadata else {}
            if manual_val:
                new_metadata["manual"] = True
            else:
                new_metadata.pop("manual", None)
            new_metadata.pop("no_agent", None)
            updates["metadata"] = new_metadata

        if not updates:
            self.notify("No changes to save")
            self.post_message(self.Cancelled())
            return

        try:
            updated = self._storage.update(self._issue.full_id, updates)
            self.post_message(self.Saved(updated))
        except Exception as e:
            self.notify(f"Save failed: {e}", severity="error")
