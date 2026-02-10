"""Textual TUI dashboard for browsing and managing issues."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, Input, OptionList

from dogcat.cli._formatting import build_hierarchy
from dogcat.tui.shared import make_issue_label

if TYPE_CHECKING:
    from dogcat.models import Issue
    from dogcat.storage import JSONLStorage


class DogcatTUI(App[None]):
    """Interactive issue dashboard."""

    TITLE = "dogcat"

    BINDINGS: ClassVar = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
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

    def _on_detail_dismissed(self, _result: None) -> None:
        """Restore the dashboard after a detail screen is dismissed."""
        self.title = "dogcat"
        self._repopulate_option_list()
        option_list = self.query_one("#issue-list", OptionList)
        self._highlight_issue(option_list, self._last_selected_id)
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

    def _repopulate_option_list(self) -> None:
        """Re-populate the OptionList from the current _issues and search query."""
        query = self.query_one("#dashboard-search", Input).value.lower()
        option_list = self.query_one("#issue-list", OptionList)
        option_list.clear_options()
        for label, full_id in self._issues:
            if not query or query in full_id.lower() or query in label.plain.lower():
                option_list.add_option(label)

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
        from dogcat.tui.detail import IssueDetailScreen

        selected_text = event.option.prompt
        for label, full_id in self._issues:
            if label == selected_text:
                self._last_selected_id = full_id
                issue = self._storage.get(full_id)
                if issue is not None:
                    self.push_screen(
                        IssueDetailScreen(issue, self._storage),
                        callback=self._on_detail_dismissed,
                    )
                return

    def action_refresh(self) -> None:
        """Reload issues from storage."""
        self._load_issues()
        search = self.query_one("#dashboard-search", Input)
        search.value = ""
        self.notify("Refreshed")
