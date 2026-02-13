"""Textual TUI dashboard for browsing and managing issues."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, OptionList, Static

from dogcat.cli._formatting import build_hierarchy
from dogcat.tui.shared import make_issue_label

if TYPE_CHECKING:
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
        margin: 1 2 0 2;
    }

    #issue-list {
        margin: 0 2 1 2;
    }
    """

    def __init__(self, storage: JSONLStorage, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._storage = storage
        self._issues: list[tuple[Text, str]] = []
        self._last_selected_id: str | None = None

    def compose(self) -> ComposeResult:
        """Build the dashboard layout."""
        yield Header()
        yield Input(placeholder="Search issues...", id="dashboard-search")
        yield OptionList(id="issue-list")
        yield Footer()

    def on_mount(self) -> None:
        """Populate the list on startup."""
        self._load_issues()
        option_list = self.query_one("#issue-list", OptionList)
        if option_list.option_count > 0:
            option_list.highlighted = 0
        option_list.focus()

    def _load_issues(self) -> None:
        """Load issues as a tree into the option list."""
        issues: list[Issue] = [
            i
            for i in self._storage.list()
            if i.status.value not in ("closed", "tombstone")
        ]

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
            label = make_issue_label(issue)
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
        query = event.value.lower()
        option_list = self.query_one("#issue-list", OptionList)
        option_list.clear_options()
        for label, full_id in self._issues:
            if query in full_id.lower() or query in label.plain.lower():
                option_list.add_option(label)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Show issue detail when Enter is pressed on an item."""
        from dogcat.tui.editor import IssueEditorScreen

        selected_text = event.option.prompt
        for label, full_id in self._issues:
            if label == selected_text:
                self._last_selected_id = full_id
                issue = self._storage.get(full_id)
                if issue is not None:
                    self.push_screen(
                        IssueEditorScreen(issue, self._storage, view_mode=True),
                        callback=self._on_editor_done,
                    )
                return

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
        from dogcat.tui.editor import IssueEditorScreen

        full_id = self._get_selected_issue_id()
        if full_id is None:
            self.notify("No issue selected", severity="warning")
            return

        issue = self._storage.get(full_id)
        if issue is None:
            self.notify(f"Issue {full_id} not found", severity="error")
            return

        self._last_selected_id = full_id
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

    def action_refresh(self) -> None:
        """Reload issues from storage."""
        self._load_issues()
        search = self.query_one("#dashboard-search", Input)
        search.value = ""
        self.notify("Refreshed")
