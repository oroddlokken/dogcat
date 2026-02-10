"""Textual-based issue picker for interactive selection."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Input, OptionList

from dogcat.tui.shared import make_issue_label

if TYPE_CHECKING:
    from rich.text import Text

    from dogcat.storage import JSONLStorage


class IssuePickerApp(App[str | None]):
    """Textual app for selecting an issue from a searchable list."""

    TITLE = "Select Issue"

    BINDINGS: ClassVar = [
        Binding("escape", "quit", "Cancel"),
    ]

    CSS = """
    #picker-search {
        margin: 1 2 0 2;
    }

    #picker-list {
        margin: 0 2 1 2;
    }
    """

    def __init__(
        self,
        issues: list[tuple[Text, str]],
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._issues = issues
        self.selected_id: str | None = None

    def compose(self) -> ComposeResult:
        """Compose the picker UI."""
        yield Input(placeholder="Search issues...", id="picker-search")
        yield OptionList(*[label for label, _ in self._issues], id="picker-list")
        yield Footer()

    def on_mount(self) -> None:
        """Focus the issue list on mount."""
        option_list = self.query_one("#picker-list", OptionList)
        if option_list.option_count > 0:
            option_list.highlighted = 0
        option_list.focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Filter the option list based on search input."""
        query = event.value.lower()
        option_list = self.query_one("#picker-list", OptionList)
        option_list.clear_options()
        for label, full_id in self._issues:
            if query in full_id.lower() or query in label.plain.lower():
                option_list.add_option(label)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle issue selection."""
        # Find the matching issue by label text
        selected_text = event.option.prompt
        for label, full_id in self._issues:
            if label == selected_text:
                self.selected_id = full_id
                self.exit(full_id)
                return


def pick_issue(storage: JSONLStorage) -> str | None:
    """Open a Textual picker to select an issue.

    Args:
        storage: The storage backend.

    Returns:
        The selected issue ID, or None if cancelled.
    """
    issues: list[tuple[Text, str]] = []
    for issue in storage.list():
        if issue.is_tombstone() or issue.is_closed():
            continue
        label = make_issue_label(issue)
        issues.append((label, issue.full_id))

    if not issues:
        return None

    picker = IssuePickerApp(issues)
    picker.run()
    return picker.selected_id
