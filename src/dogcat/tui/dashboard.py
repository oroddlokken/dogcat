"""Textual TUI dashboard for browsing and managing issues."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, OptionList, Static

from dogcat.cli._formatting import build_hierarchy
from dogcat.constants import SPLIT_PANE_MIN_COLS, SPLIT_PANE_MIN_ROWS
from dogcat.tui.shared import make_issue_label

if TYPE_CHECKING:
    from textual.events import Resize

    from dogcat.models import Issue
    from dogcat.storage import JSONLStorage


class ConfirmDeleteScreen(Screen[bool]):
    """Tiny confirmation dialog for issue deletion."""

    BINDINGS: ClassVar = [
        Binding("escape", "cancel", "Cancel", priority=True),
    ]

    CSS = """
    ConfirmDeleteScreen {
        align: center middle;
    }

    #confirm-dialog {
        width: 50;
        height: auto;
        max-height: 10;
        border: thick $accent;
        padding: 1 2;
    }

    #confirm-buttons {
        margin-top: 1;
        height: auto;
        align: center middle;
    }

    #confirm-buttons Button {
        margin: 0 1;
    }
    """

    def __init__(self, issue_id: str, title: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._issue_id = issue_id
        self._title = title

    def compose(self) -> ComposeResult:
        """Build the confirmation dialog."""
        with Vertical(id="confirm-dialog"):
            yield Static(f"Delete [b]{self._issue_id}[/b]?")
            yield Static(f"  {self._title}")
            with Horizontal(id="confirm-buttons"):
                yield Button("Yes", id="yes-btn", variant="error")
                yield Button("No", id="no-btn", variant="default")

    def on_mount(self) -> None:
        """Focus the Yes button by default."""
        self.query_one("#yes-btn", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks."""
        self.dismiss(event.button.id == "yes-btn")

    def action_cancel(self) -> None:
        """Cancel deletion."""
        self.dismiss(False)


class DogcatTUI(App[None]):
    """Interactive issue dashboard."""

    TITLE = "dogcat"
    ENABLE_COMMAND_PALETTE = False

    BINDINGS: ClassVar = [
        Binding("q", "quit", "Quit"),
        Binding("escape", "quit", "Quit", show=False),
        Binding("r", "refresh", "Refresh"),
        Binding("n", "new_issue", "New"),
        Binding("e", "edit_issue", "Edit"),
        Binding("d", "delete_issue", "Delete"),
        Binding("D", "force_delete_issue", "Delete!", show=False),
    ]

    CSS = """
    #dashboard-search {
        margin: 1 2 1 2;
    }

    #issue-list {
        margin: 0 2 1 2;
    }

    /* Split-pane layout */
    #left-pane {
        width: 1fr;
    }

    #right-pane {
        display: none;
        width: 1fr;
        border-left: tall $accent;
    }

    .split-active #left-pane {
        width: 40%;
        min-width: 40;
        max-width: 80;
    }

    .split-active #right-pane {
        display: block;
        width: 1fr;
    }

    .split-active #dashboard-search {
        margin: 1 1 1 1;
    }

    .split-active #issue-list {
        margin: 0 1 1 1;
    }
    """

    _split_mode: reactive[bool] = reactive(False)

    def __init__(self, storage: JSONLStorage, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._storage = storage
        self._issues: list[tuple[Text, str]] = []
        self._blocked_ids: set[str] = set()
        self._last_selected_id: str | None = None

    def compose(self) -> ComposeResult:
        """Build the dashboard layout."""
        yield Header()
        with Horizontal(id="main-pane"):
            with Vertical(id="left-pane"):
                yield Input(placeholder="Search issues...", id="dashboard-search")
                yield OptionList(id="issue-list")
            with Vertical(id="right-pane"):
                yield Static("Select an issue to view details", id="detail-placeholder")
        yield Footer()

    def on_mount(self) -> None:
        """Populate the list on startup."""
        self._load_issues()
        option_list = self.query_one("#issue-list", OptionList)
        if option_list.option_count > 0:
            option_list.highlighted = 0
        option_list.focus()

    def on_resize(self, event: Resize) -> None:
        """Toggle split-pane mode based on terminal size."""
        self._split_mode = (
            event.size.width >= SPLIT_PANE_MIN_COLS
            and event.size.height >= SPLIT_PANE_MIN_ROWS
        )

    async def watch__split_mode(self, split_active: bool) -> None:
        """React to split-mode changes."""
        main_pane = self.query_one("#main-pane", Horizontal)
        if split_active:
            main_pane.add_class("split-active")
            # Show detail for the currently highlighted issue
            full_id = self._get_selected_issue_id()
            if full_id is not None:
                await self._show_issue_in_panel(full_id)
        else:
            main_pane.remove_class("split-active")
            await self._clear_detail_panel()

    async def _show_issue_in_panel(self, full_id: str) -> None:
        """Load an issue into the right-pane detail panel."""
        from dogcat.tui.detail_panel import IssueDetailPanel

        issue = self._storage.get(full_id)
        if issue is None:
            return

        right_pane = self.query_one("#right-pane", Vertical)

        # Remove placeholder if present
        await right_pane.query("#detail-placeholder").remove()

        # Always remove and remount — recompose() is async and must be
        # awaited, so it's simpler to just replace the whole panel.
        await right_pane.query(IssueDetailPanel).remove()
        await right_pane.mount(
            IssueDetailPanel(
                issue,
                self._storage,
                view_mode=True,
                id="detail-panel",
            ),
        )

    async def _clear_detail_panel(self) -> None:
        """Remove the detail panel from the right pane."""
        from dogcat.tui.detail_panel import IssueDetailPanel

        right_pane = self.query_one("#right-pane", Vertical)
        await right_pane.query(IssueDetailPanel).remove()

        # Restore placeholder if missing
        if not right_pane.query("#detail-placeholder"):
            await right_pane.mount(
                Static("Select an issue to view details", id="detail-placeholder"),
            )

    def _load_issues(self) -> None:
        """Load issues as a tree into the option list."""
        from dogcat.config import get_namespace_filter
        from dogcat.deps import get_blocked_issues

        issues: list[Issue] = [
            i
            for i in self._storage.list()
            if i.status.value not in ("closed", "tombstone")
        ]

        ns_filter = get_namespace_filter(str(self._storage.dogcats_dir))
        if ns_filter is not None:
            issues = [i for i in issues if ns_filter(i.namespace)]

        blocked = get_blocked_issues(self._storage)
        self._blocked_ids: set[str] = {bi.issue_id for bi in blocked}

        hierarchy = build_hierarchy(issues)
        self._issues = []
        self._build_tree(hierarchy, parent_id=None, depth=0)

        option_list = self.query_one("#issue-list", OptionList)
        option_list.clear_options()
        for label, _full_id in self._issues:
            option_list.add_option(label)

    def _build_tree(
        self,
        hierarchy: dict[str | None, list[Issue]],
        parent_id: str | None,
        depth: int,
    ) -> None:
        """Recursively build the flat issue list with tree indentation."""
        children = hierarchy.get(parent_id, [])
        children = sorted(children, key=lambda i: (i.priority, i.id))

        for issue in children:
            label = make_issue_label(issue, self._blocked_ids)
            if depth > 0:
                indent = Text("  " * depth, style="dim")
                label = Text.assemble(indent, label)
            self._issues.append((label, issue.full_id))
            self._build_tree(hierarchy, issue.full_id, depth + 1)

    def _get_selected_issue_id(self) -> str | None:
        """Return the full_id of the currently highlighted issue, or None."""
        option_list = self.query_one("#issue-list", OptionList)
        if option_list.highlighted is None or option_list.option_count == 0:
            return None
        try:
            selected_text = option_list.get_option_at_index(
                option_list.highlighted,
            ).prompt
        except Exception:
            return None
        for label, full_id in self._issues:
            if label == selected_text:
                return full_id
        return None

    def _on_editor_done(self, result: Issue | None) -> None:
        """Restore the dashboard after the editor screen is dismissed."""
        self.title = "dogcat"
        self._load_issues()
        option_list = self.query_one("#issue-list", OptionList)
        if result is not None:
            self._highlight_issue(option_list, result.full_id)
        elif self._last_selected_id is not None:
            self._highlight_issue(option_list, self._last_selected_id)
        search = self.query_one("#dashboard-search", Input)
        search.value = ""
        option_list.focus()

    def _highlight_issue(self, option_list: OptionList, full_id: str | None) -> None:
        """Highlight the option matching *full_id*, if present."""
        if full_id is None or option_list.option_count == 0:
            return
        query = self.query_one("#dashboard-search", Input).value.lower()
        idx = 0
        for label, fid in self._issues:
            if query and query not in fid.lower() and query not in label.plain.lower():
                continue
            if fid == full_id:
                option_list.highlighted = idx
                return
            idx += 1

    def on_input_changed(self, event: Input.Changed) -> None:
        """Filter the option list based on search input."""
        if event.input.id != "dashboard-search":
            return
        query = event.value.lower()
        option_list = self.query_one("#issue-list", OptionList)
        option_list.clear_options()
        for label, full_id in self._issues:
            if query in full_id.lower() or query in label.plain.lower():
                option_list.add_option(label)

    async def on_option_list_option_highlighted(
        self,
        event: OptionList.OptionHighlighted,
    ) -> None:
        """In split mode, show the highlighted issue in the detail panel."""
        if not self._split_mode:
            return
        selected_text = event.option.prompt
        for label, full_id in self._issues:
            if label == selected_text:
                await self._show_issue_in_panel(full_id)
                return

    async def on_option_list_option_selected(
        self,
        event: OptionList.OptionSelected,
    ) -> None:
        """Show issue detail when Enter is pressed on an item."""
        selected_text = event.option.prompt
        for label, full_id in self._issues:
            if label == selected_text:
                self._last_selected_id = full_id
                issue = self._storage.get(full_id)
                if issue is None:
                    return

                if self._split_mode:
                    # In split mode, focus the detail panel
                    from dogcat.tui.detail_panel import IssueDetailPanel

                    try:
                        panel = self.query_one("#detail-panel", IssueDetailPanel)
                        panel.focus()
                    except Exception:
                        pass
                else:
                    # Narrow mode: push modal editor
                    from dogcat.tui.editor import IssueEditorScreen

                    await self.push_screen(
                        IssueEditorScreen(issue, self._storage, view_mode=True),
                        callback=self._on_editor_done,
                    )
                return

    async def on_issue_detail_panel_saved(self, event: Any) -> None:
        """Handle save from the inline detail panel."""
        self.title = "dogcat"
        saved_issue = event.issue
        self._load_issues()
        option_list = self.query_one("#issue-list", OptionList)
        self._highlight_issue(option_list, saved_issue.full_id)
        # Reload panel in view mode
        await self._show_issue_in_panel(saved_issue.full_id)

    async def on_issue_detail_panel_cancelled(
        self,
        event: Any,  # noqa: ARG002
    ) -> None:
        """Handle cancel from the inline detail panel."""
        self.title = "dogcat"
        # Reload panel in view mode for the currently selected issue
        full_id = self._get_selected_issue_id()
        if full_id is not None:
            await self._show_issue_in_panel(full_id)
        self.query_one("#issue-list", OptionList).focus()

    def on_issue_detail_panel_edit_mode_changed(self, event: Any) -> None:
        """Update app title when inline edit mode changes."""
        if event.editing:
            full_id = self._get_selected_issue_id()
            if full_id is not None:
                issue = self._storage.get(full_id)
                if issue is not None:
                    self.title = f"Edit: {issue.full_id} - {issue.title}"
        else:
            self.title = "dogcat"

    def _is_panel_editing(self) -> bool:
        """Check if the inline detail panel is in edit mode."""
        from dogcat.tui.detail_panel import IssueDetailPanel

        try:
            panel = self.query_one("#detail-panel", IssueDetailPanel)
        except Exception:
            return False
        else:
            return not panel.is_view_mode

    def check_action(  # type: ignore[override]
        self,
        action: str,
        parameters: tuple[object, ...],  # noqa: ARG002
    ) -> bool | None:
        """Disable dashboard-only actions when a screen is pushed."""
        if action in ("new_issue", "edit_issue", "delete_issue", "force_delete_issue"):
            return self.screen is self.screen_stack[0]
        return not (action == "quit" and self._is_panel_editing())

    def action_new_issue(self) -> None:
        """Open the editor to create a new issue."""
        from dogcat.cli._helpers import get_default_operator
        from dogcat.config import get_issue_prefix
        from dogcat.models import Issue
        from dogcat.tui.editor import IssueEditorScreen

        namespace = get_issue_prefix(str(self._storage.dogcats_dir))
        owner = get_default_operator()

        skeleton = Issue(
            id="",
            title="",
            namespace=namespace,
            owner=owner,
        )
        self.push_screen(
            IssueEditorScreen(
                skeleton,
                self._storage,
                create_mode=True,
                namespace=namespace,
                existing_ids=self._storage.get_issue_ids(),
            ),
            callback=self._on_editor_done,
        )

    def action_edit_issue(self) -> None:
        """Open the editor for the currently selected issue."""
        full_id = self._get_selected_issue_id()
        if full_id is None:
            self.notify("No issue selected", severity="warning")
            return

        issue = self._storage.get(full_id)
        if issue is None:
            self.notify(f"Issue {full_id} not found", severity="error")
            return

        self._last_selected_id = full_id

        if self._split_mode:
            # Inline editing in the detail panel
            from dogcat.tui.detail_panel import IssueDetailPanel

            try:
                panel = self.query_one("#detail-panel", IssueDetailPanel)
                panel.enter_edit()
                self.title = f"Edit: {issue.full_id} - {issue.title}"
            except Exception:
                pass
        else:
            # Narrow mode: push modal editor
            from dogcat.tui.editor import IssueEditorScreen

            self.push_screen(
                IssueEditorScreen(issue, self._storage),
                callback=self._on_editor_done,
            )

    def action_delete_issue(self) -> None:
        """Delete the selected issue after confirmation."""
        full_id = self._get_selected_issue_id()
        if full_id is None:
            self.notify("No issue selected", severity="warning")
            return

        issue = self._storage.get(full_id)
        if issue is None:
            self.notify(f"Issue {full_id} not found", severity="error")
            return

        self.push_screen(
            ConfirmDeleteScreen(full_id, issue.title),
            callback=lambda confirmed: self._do_delete(full_id) if confirmed else None,
        )

    def action_force_delete_issue(self) -> None:
        """Delete the selected issue immediately without confirmation."""
        full_id = self._get_selected_issue_id()
        if full_id is None:
            self.notify("No issue selected", severity="warning")
            return
        self._do_delete(full_id)

    def _do_delete(self, full_id: str) -> None:
        """Execute the deletion and refresh the list."""
        try:
            self._storage.delete(full_id)
            self.notify(f"Deleted {full_id}")
        except Exception as e:
            self.notify(f"Delete failed: {e}", severity="error")
            return
        self._load_issues()
        option_list = self.query_one("#issue-list", OptionList)
        if option_list.option_count > 0:
            option_list.highlighted = min(
                option_list.highlighted or 0,
                option_list.option_count - 1,
            )
        option_list.focus()

    async def action_refresh(self) -> None:
        """Reload issues from disk and refresh the list and detail panel."""
        self._storage.reload()
        self._load_issues()
        search = self.query_one("#dashboard-search", Input)
        search.value = ""

        if self._split_mode:
            full_id = self._get_selected_issue_id()
            if full_id is not None:
                await self._show_issue_in_panel(full_id)
            else:
                await self._clear_detail_panel()

        self.notify("Refreshed")
