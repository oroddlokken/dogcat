"""Reusable issue detail/edit panel widget for the TUI."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, cast

from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import (
    Button,
    Checkbox,
    Collapsible,
    Input,
    Label,
    OptionList,
    Select,
    Static,
    TextArea,
)

from dogcat.constants import (
    MAX_DESC_LEN,
    MAX_TITLE_LEN,
    PRIORITY_OPTIONS,
    STATUS_OPTIONS,
    TYPE_OPTIONS,
    parse_labels,
)
from dogcat.models import DependencyType, is_manual_issue
from dogcat.tui.shared import SHARED_CSS, make_issue_label

if TYPE_CHECKING:
    from rich.text import Text
    from textual.app import ComposeResult

    from dogcat.models import Issue
    from dogcat.storage import JSONLStorage


_PARENT_PLACEHOLDER = "No parent"


@dataclass
class _DepPlan:
    """A validated set of dependency mutations ready to commit."""

    add_deps: list[str] = field(default_factory=list[str])
    rem_deps: list[str] = field(default_factory=list[str])
    add_blks: list[str] = field(default_factory=list[str])
    rem_blks: list[str] = field(default_factory=list[str])

    def is_empty(self) -> bool:
        return not (self.add_deps or self.rem_deps or self.add_blks or self.rem_blks)


class ParentPickerScreen(ModalScreen[str | None]):
    """Modal screen for selecting a parent issue with search."""

    BINDINGS: ClassVar = [
        Binding("escape", "dismiss_picker", "Cancel"),
    ]

    DEFAULT_CSS = """
    ParentPickerScreen {
        align: center middle;
    }

    #parent-picker-container {
        width: 90%;
        max-width: 120;
        height: 24;
        max-height: 80%;
        background: $surface;
        border: tall $accent;
        padding: 1 2;
    }

    #parent-picker-search {
        margin-bottom: 1;
    }

    #parent-picker-list {
        height: 1fr;
    }

    #parent-picker-clear {
        margin-top: 1;
        width: auto;
    }
    """

    def __init__(
        self,
        issues: list[tuple[str, str, Text]],
        current_parent: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        # list of (plain_text_for_search, full_id, rich_label)
        self._issues = issues
        self._current_parent = current_parent
        # Visible items in current filter, maps option index to issue index
        self._visible: list[int] = []

    def compose(self) -> ComposeResult:
        """Compose the picker UI with search input and option list."""
        from textual.containers import Vertical

        with Vertical(id="parent-picker-container"):
            yield Input(
                placeholder="Type to filter by ID or title...",
                id="parent-picker-search",
            )
            yield OptionList(id="parent-picker-list")
            yield Button("Clear parent", id="parent-picker-clear", variant="default")

    def on_mount(self) -> None:
        """Focus search input and populate options on mount."""
        self._refresh_options("")
        search = self.query_one("#parent-picker-search", Input)
        search.focus()

    def _refresh_options(self, query: str) -> None:
        """Filter and refresh the option list based on search query."""
        option_list = self.query_one("#parent-picker-list", OptionList)
        option_list.clear_options()
        self._visible = []
        query_lower = query.lower()
        for idx, (plain_label, full_id, rich_label) in enumerate(self._issues):
            if (
                query_lower
                and query_lower not in full_id.lower()
                and query_lower not in plain_label.lower()
            ):
                continue

            display = rich_label.copy()
            if full_id == self._current_parent:
                display.append(" (current)", style="dim")
            option_list.add_option(display)
            self._visible.append(idx)
        if option_list.option_count > 0:
            option_list.highlighted = 0

    def on_input_changed(self, event: Input.Changed) -> None:
        """Filter options as the user types."""
        self._refresh_options(event.value)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle issue selection from the option list."""
        if event.option_index < len(self._visible):
            issue_idx = self._visible[event.option_index]
            self.dismiss(self._issues[issue_idx][1])

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle clear parent button press."""
        if event.button.id == "parent-picker-clear":
            self.dismiss("")  # empty string signals "clear parent"

    def action_dismiss_picker(self) -> None:
        """Cancel the picker without changing the parent."""
        self.dismiss(None)  # None = cancelled, no change


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
        Binding("p", "pick_parent", "Parent"),
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

    IssueDetailPanel .parent-field {
        width: 1fr;
        min-width: 16;
        height: 3;
        text-align: left;
    }

    IssueDetailPanel .parent-placeholder {
        color: $text-muted;
    }

    IssueDetailPanel Button.parent-broken {
        color: $error;
        text-style: bold;
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

    def _get_depends_on_ids(self) -> list[str]:
        """Get the IDs this issue currently depends on (blocks type)."""
        if self._create_mode or not self._issue.id:
            return []
        deps = self._storage.get_dependencies(self._issue.full_id)
        return [d.depends_on_id for d in deps if d.dep_type == DependencyType.BLOCKS]

    def _get_blocks_ids(self) -> list[str]:
        """Get the IDs this issue currently blocks."""
        if self._create_mode or not self._issue.id:
            return []
        dependents = self._storage.get_dependents(self._issue.full_id)
        return [d.issue_id for d in dependents if d.dep_type == DependencyType.BLOCKS]

    def _get_parent_options(self) -> list[tuple[str, str, Text]]:
        """Build the list of valid parent options.

        Excludes self, descendants, tombstones, and closed issues
        (unless the closed issue has open children).

        Returns list of (plain_label, full_id, rich_label) tuples where
        labels use the same format as ``dcat list``.
        """
        excluded = {self._issue.full_id}
        if not self._create_mode and self._issue.id:
            excluded |= self._get_descendants(self._issue.full_id)

        # Collect IDs of closed issues that have at least one open child
        closed_with_open_children: set[str] = set()
        for issue in self._storage.list():
            if issue.is_closed() and not issue.is_tombstone():
                children = self._storage.get_children(issue.full_id)
                if any(not c.is_closed() and not c.is_tombstone() for c in children):
                    closed_with_open_children.add(issue.full_id)

        options: list[tuple[str, str, Text]] = []
        for issue in self._storage.list():
            if issue.full_id in excluded or issue.is_tombstone():
                continue
            if issue.is_closed() and issue.full_id not in closed_with_open_children:
                continue
            rich_label = make_issue_label(issue)
            options.append((rich_label.plain, issue.full_id, rich_label))
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
                    value=is_manual_issue(self._issue.metadata),
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

            with Horizontal(classes="deps-row"):
                yield Button(
                    self._issue.parent or _PARENT_PLACEHOLDER,
                    id="parent-input",
                    variant="default",
                    classes="parent-field"
                    + (" parent-placeholder" if not self._issue.parent else ""),
                )
                depends_on_ids = self._get_depends_on_ids()
                yield Input(
                    value=(
                        "blocked by: " + ", ".join(depends_on_ids)
                        if depends_on_ids
                        else ""
                    ),
                    placeholder="Blocked by (no blockers)",
                    id="depends-on-input",
                    disabled=True,
                )
                blocks_ids = self._get_blocks_ids()
                yield Input(
                    value=("blocking: " + ", ".join(blocks_ids) if blocks_ids else ""),
                    placeholder="Blocks (none)",
                    id="blocks-input",
                    disabled=True,
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

            if ro:
                yield from self._compose_view_sections()
            elif self._issue.comments:
                yield from self._compose_comments_section()

    def _compose_view_sections(self) -> ComposeResult:
        """Yield read-only dependency/children/comment sections."""
        deps = self._storage.get_dependencies(self._issue.full_id)
        dependents = self._storage.get_dependents(self._issue.full_id)
        if deps or dependents:
            with Collapsible(title="Dependencies", collapsed=False, id="deps-section"):
                for dep in deps:
                    yield Static(
                        f"  blocked by: {dep.depends_on_id}",
                        classes="detail-section-body",
                    )
                for dep in dependents:
                    yield Static(
                        f"  blocks: {dep.issue_id}",
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
            yield from self._compose_comments_section()

    def _compose_comments_section(self) -> ComposeResult:
        """Yield read-only comments section."""
        with Collapsible(title="Comments", collapsed=False, id="comments-section"):
            for comment in self._issue.comments:
                ts = comment.created_at.strftime("%Y-%m-%d %H:%M:%S")
                body = f"  [{comment.id}] {comment.author} ({ts})"
                body += f"\n    {comment.text}\n"
                yield Static(body, classes="detail-section-body")

    def on_mount(self) -> None:
        """Hide buttons in view mode; focus title for edit/create."""
        if self._view_mode:
            self.query_one("#cancel-btn", Button).display = False
            self.query_one("#save-btn", Button).display = False
        elif self._create_mode:
            self.query_one("#title-input", Input).focus()
        else:
            self.query_one("#title-input", Input).focus()
        self._flag_broken_parent()

    def _flag_broken_parent(self) -> None:
        """Mark the parent button broken if the parent is tombstoned/missing.

        Catches the concurrent-edit case where another process tombstones
        an issue's parent between loads; without this, save would write
        back the stale ID and the user would never see the breakage.
        """
        if not self._issue.parent or self._create_mode:
            return
        parent = self._storage.get(self._issue.parent)
        if parent is not None and not parent.is_tombstone():
            return
        # Visual-only signal: red color + "(deleted)" text suffix. We used
        # to also notify here, but the panel re-mounts on every selection
        # change in split mode, so navigating past a broken-parent child
        # would burst N toasts. The visual is sufficient.
        with contextlib.suppress(Exception):
            btn = self.query_one("#parent-input", Button)
            btn.add_class("parent-broken")
            btn.label = f"{self._issue.parent} (deleted)"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "cancel-btn":
            self.post_message(self.Cancelled())
        elif event.button.id == "save-btn":
            self.do_save()
        elif event.button.id == "parent-input":
            self._handle_parent_button(event)

    def _handle_parent_button(self, event: Button.Pressed) -> None:
        """Open parent picker when the parent button is clicked."""
        if event.button.id != "parent-input":
            return
        if self._view_mode:
            self.notify("Press [b]e[/b] to enter edit mode", markup=True)
        else:
            self._open_parent_picker()

    def _get_selected_parent(self) -> str | None:
        """Read the currently selected parent from the field."""
        btn = self.query_one("#parent-input", Button)
        text = str(btn.label)
        if text == _PARENT_PLACEHOLDER:
            return None
        # Strip the "(deleted)" decoration applied by _flag_broken_parent so
        # we save the original id back, not "abc (deleted)".
        return text.removesuffix(" (deleted)")

    def _open_parent_picker(self) -> None:
        """Open the parent picker modal."""
        options = self._get_parent_options()
        current = self._get_selected_parent()
        self.app.push_screen(  # type: ignore[reportUnknownMemberType]
            ParentPickerScreen(options, current_parent=current),
            callback=self._on_parent_picked,
        )

    def _on_parent_picked(self, result: str | None) -> None:
        """Handle parent picker result."""
        if result is None:
            return  # cancelled
        btn = self.query_one("#parent-input", Button)
        if result:
            btn.label = result
            btn.remove_class("parent-placeholder")
        else:
            btn.label = _PARENT_PLACEHOLDER
            btn.add_class("parent-placeholder")

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
        if action == "pick_parent":
            return not self._view_mode
        return True

    def action_save(self) -> None:
        """Save the issue (Ctrl+S)."""
        self.do_save()

    def action_enter_edit(self) -> None:
        """Switch from view mode to edit mode (e key)."""
        self.enter_edit()

    def action_pick_parent(self) -> None:
        """Open the parent picker (p key)."""
        self._open_parent_picker()

    def enter_edit(self) -> None:
        """Enable editing on all form fields."""
        self._view_mode = False

        # Swap deps inputs from "blocked by: a, b" prefix-style display values
        # to bare comma-separated IDs the user can edit directly. Cancel
        # remounts the panel and restores the prefix display via compose().
        deps_input = self.query_one("#depends-on-input", Input)
        deps_input.value = ", ".join(self._get_depends_on_ids())
        deps_input.placeholder = "Blocked by (comma-separated IDs)"
        blocks_input = self.query_one("#blocks-input", Input)
        blocks_input.value = ", ".join(self._get_blocks_ids())
        blocks_input.placeholder = "Blocks (comma-separated IDs)"

        for inp in self.query(Input):
            inp.disabled = False
        for sel in self.query(Select):  # type: ignore[reportUnknownVariableType]
            sel.disabled = False  # type: ignore[reportUnknownMemberType]
        self.query_one("#manual-input", Checkbox).disabled = False
        for ta in self.query(TextArea):
            ta.read_only = False

        self.query_one("#cancel-btn", Button).display = True
        self.query_one("#save-btn", Button).display = True

        for section_id in ("deps-section", "children-section"):
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

    @staticmethod
    def _parse_dep_ids(value: str) -> list[str]:
        """Parse comma/space separated issue IDs from an input value."""
        raw = value.replace(",", " ").split()
        return [v.strip() for v in raw if v.strip()]

    def _compute_dep_plan(
        self,
        issue_id: str,
    ) -> tuple[list[str], _DepPlan]:
        """Diff form deps against storage and pre-validate the change set.

        Returns ``(errors, plan)``. If ``errors`` is non-empty, the caller
        should surface them and abort the save before touching storage.
        Otherwise ``plan`` is safe to pass to :meth:`_apply_dep_plan`.

        Resolves partial IDs up front so cycle checks and the commit phase
        agree on full IDs. Pre-validating the entire diff here lets the
        caller refuse to half-apply a form (e.g. commit a title change but
        bail on a bad dep id).
        """
        from dogcat.deps import would_create_cycle

        new_depends_on = self._parse_dep_ids(
            self.query_one("#depends-on-input", Input).value,
        )
        new_blocks = self._parse_dep_ids(
            self.query_one("#blocks-input", Input).value,
        )
        old_depends_on = set(self._get_depends_on_ids())
        old_blocks = set(self._get_blocks_ids())

        errors: list[str] = []
        resolved_add_deps: list[str] = []
        resolved_add_blks: list[str] = []

        for dep_id in (d for d in new_depends_on if d not in old_depends_on):
            resolved = self._storage.resolve_id(dep_id)
            if resolved is None:
                errors.append(f"Unknown issue: {dep_id}")
                continue
            if issue_id and would_create_cycle(self._storage, issue_id, resolved):
                errors.append(f"Cycle: {issue_id} -> {resolved}")
                continue
            resolved_add_deps.append(resolved)

        for dep_id in (d for d in new_blocks if d not in old_blocks):
            resolved = self._storage.resolve_id(dep_id)
            if resolved is None:
                errors.append(f"Unknown issue: {dep_id}")
                continue
            if issue_id and would_create_cycle(self._storage, resolved, issue_id):
                errors.append(f"Cycle: {resolved} -> {issue_id}")
                continue
            resolved_add_blks.append(resolved)

        plan = _DepPlan(
            add_deps=resolved_add_deps,
            rem_deps=[d for d in old_depends_on if d not in new_depends_on],
            add_blks=resolved_add_blks,
            rem_blks=[d for d in old_blocks if d not in new_blocks],
        )
        return errors, plan

    def _apply_dep_plan(self, issue_id: str, plan: _DepPlan) -> None:
        """Commit a validated dep plan. Raises on commit failure."""
        for dep_id in plan.add_deps:
            self._storage.add_dependency(
                issue_id,
                dep_id,
                DependencyType.BLOCKS.value,
            )
        for dep_id in plan.rem_deps:
            self._storage.remove_dependency(issue_id, dep_id)
        for dep_id in plan.add_blks:
            self._storage.add_dependency(
                dep_id,
                issue_id,
                DependencyType.BLOCKS.value,
            )
        for dep_id in plan.rem_blks:
            self._storage.remove_dependency(dep_id, issue_id)

    def do_save(self) -> None:
        """Execute the save."""
        title = self.query_one("#title-input", Input).value.strip()
        if not title:
            self.notify("Title cannot be empty", severity="error")
            return
        if len(title) > MAX_TITLE_LEN:
            self.notify(
                f"Title is {len(title)} chars; max is {MAX_TITLE_LEN}",
                severity="error",
            )
            return

        type_val = cast("Select[str]", self.query_one("#type-input", Select)).value
        status_val = cast("Select[str]", self.query_one("#status-input", Select)).value
        priority_val = cast(
            "Select[int]",
            self.query_one("#priority-input", Select),
        ).value
        description = self.query_one("#description-input", TextArea).text.strip()
        if len(description) > MAX_DESC_LEN:
            self.notify(
                f"Description is {len(description)} chars; max is {MAX_DESC_LEN}",
                severity="error",
            )
            return

        if self._create_mode:
            self._do_create(title, type_val, status_val, priority_val, description)
        else:
            # Pre-validate the dep diff so a bad dep id never half-applies a
            # form save (e.g. title commits, then deps fail). For create mode
            # the issue doesn't exist yet, so we validate post-create instead.
            errors, plan = self._compute_dep_plan(self._issue.full_id)
            if errors:
                self.notify(
                    "Dependency error:\n" + "\n".join(errors),
                    severity="error",
                )
                return
            self._do_update(
                title, type_val, status_val, priority_val, description, plan
            )

    def _do_create(
        self,
        title: str,
        type_val: Any,
        status_val: Any,
        priority_val: Any,
        description: str,
    ) -> None:
        """Create a new issue from the form values."""
        from dogcat.models import IssueType, Status

        parent = self._get_selected_parent()

        manual_val = self.query_one("#manual-input", Checkbox).value
        metadata: dict[str, Any] = {}
        if manual_val:
            metadata["manual"] = True

        try:
            issue = self._storage.create_issue(
                title=title,
                namespace=self._namespace,
                description=description or None,
                status=(
                    Status(status_val) if isinstance(status_val, str) else Status.OPEN
                ),
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
                metadata=metadata,
            )
        except (ValueError, RuntimeError, OSError) as e:
            self.notify(f"Create failed: {e}", severity="error")
            return

        # Now that the new issue exists in storage we can validate dep IDs
        # (cycle checks are vacuous — a fresh issue has no graph edges yet).
        errors, plan = self._compute_dep_plan(issue.full_id)
        if errors:
            self.notify(
                "Issue created, but dependency error:\n" + "\n".join(errors),
                severity="error",
            )
            self.post_message(self.Saved(issue))
            return
        try:
            self._apply_dep_plan(issue.full_id, plan)
        except (ValueError, RuntimeError, OSError) as e:
            self.notify(f"Dependency commit failed: {e}", severity="error")
        self.post_message(self.Saved(issue))

    def _do_update(
        self,
        title: str,
        type_val: Any,
        status_val: Any,
        priority_val: Any,
        description: str,
        dep_plan: _DepPlan,
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

        new_parent = self._get_selected_parent()
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

        manual_val = self.query_one("#manual-input", Checkbox).value
        was_manual = is_manual_issue(self._issue.metadata)
        if manual_val != was_manual:
            from dogcat.models import set_manual_flag

            updates["metadata"] = set_manual_flag(
                self._issue.metadata or {}, manual=manual_val
            )

        if not updates and dep_plan.is_empty():
            self.notify("No changes to save")
            self.post_message(self.Cancelled())
            return

        try:
            if updates:
                updated = self._storage.update(self._issue.full_id, updates)
            else:
                updated = self._issue
            self._apply_dep_plan(self._issue.full_id, dep_plan)
            self.post_message(self.Saved(updated))
        except (ValueError, RuntimeError, OSError) as e:
            self.notify(f"Save failed: {e}", severity="error")
