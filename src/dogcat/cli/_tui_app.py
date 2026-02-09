"""Textual TUI dashboard for browsing and managing issues."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, cast

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

from dogcat.constants import PRIORITY_COLORS, TYPE_COLORS

if TYPE_CHECKING:
    from dogcat.models import Issue
    from dogcat.storage import JSONLStorage


def _build_show_text(issue: Issue, storage: JSONLStorage) -> str:
    """Build the same detail text that ``dcat show`` displays."""
    dt_fmt = "%Y-%m-%d %H:%M:%S"
    lines: list[str] = [
        f"ID: {issue.full_id}",
        f"Title: {issue.title}",
        "",
        f"Status: {issue.status.value}",
        f"Priority: {issue.priority}",
        f"Type: {issue.issue_type.value}",
        "",
    ]

    if issue.parent:
        parent_line = f"Parent: {issue.parent}"
        parent_issue = storage.get(issue.parent)
        if parent_issue:
            parent_line += f" ({parent_issue.title})"
        lines.append(parent_line)
    if issue.owner:
        lines.append(f"Owner: {issue.owner}")
    if issue.labels:
        lines.append(f"Labels: {', '.join(issue.labels)}")
    if issue.duplicate_of:
        lines.append(f"Duplicate of: {issue.duplicate_of}")

    lines.append(f"Created: {issue.created_at.strftime(dt_fmt)}")
    if issue.closed_at:
        closed_line = f"Closed: {issue.closed_at.strftime(dt_fmt)}"
        if issue.close_reason:
            closed_line += f" ({issue.close_reason})"
        lines.append(closed_line)

    if issue.description:
        lines.append(f"\nDescription:\n{issue.description}")
    if issue.notes:
        lines.append(f"\nNotes:\n{issue.notes}")
    if issue.acceptance:
        lines.append(f"\nAcceptance criteria:\n{issue.acceptance}")
    if issue.design:
        lines.append(f"\nDesign:\n{issue.design}")
    if issue.comments:
        lines.append("\nComments:")
        for comment in issue.comments:
            lines.append(f"  [{comment.id}] {comment.author}")
            lines.append(f"  {comment.text}")

    # Dependencies
    deps = storage.get_dependencies(issue.full_id)
    if deps:
        lines.append("\nDependencies:")
        lines.extend(f"  → {dep.depends_on_id} ({dep.dep_type.value})" for dep in deps)

    # Links
    outgoing = storage.get_links(issue.full_id)
    incoming = storage.get_incoming_links(issue.full_id)
    if outgoing or incoming:
        lines.append("\nLinks:")
        lines.extend(f"  → {link.to_id} ({link.link_type})" for link in outgoing)
        lines.extend(f"  ← {link.from_id} ({link.link_type})" for link in incoming)

    # Children
    children = storage.get_children(issue.full_id)
    if children:
        lines.append("\nChildren:")
        lines.extend(f"  ↳ {child.id}: {child.title}" for child in children)

    # Metadata
    if issue.metadata:
        lines.append("\nMetadata:")
        for key, value in issue.metadata.items():
            lines.append(f"  {key}: {value}")

    return "\n".join(lines)


class IssueDetailScreen(Screen[None]):
    """Full-screen detail view of a single issue."""

    BINDINGS: ClassVar = [
        Binding("escape", "go_back", "Back", priority=True),
        Binding("q", "go_back", "Back"),
    ]

    CSS = """
    #detail-scroll {
        padding: 1 2;
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

    def compose(self) -> ComposeResult:
        """Build the detail view."""
        yield Header()
        with VerticalScroll(id="detail-scroll"):
            yield Static(
                _build_show_text(self._issue, self._storage),
                id="detail-body",
            )
        yield Footer()

    def on_mount(self) -> None:
        """Set the screen title."""
        self.app.title = f"{self._issue.full_id}: {self._issue.title}"

    def action_go_back(self) -> None:
        """Return to the issue list."""
        self.app.pop_screen()


class DogcatTUI(App[None]):
    """Interactive issue dashboard."""

    TITLE = "dogcat"

    BINDINGS: ClassVar = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
    ]

    CSS = """
    DataTable {
        height: 1fr;
    }
    """

    def __init__(self, storage: JSONLStorage, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._storage = storage

    def compose(self) -> ComposeResult:
        """Build the dashboard layout."""
        yield Header()
        yield DataTable[Any](id="issue-table")
        yield Footer()

    def on_mount(self) -> None:
        """Populate the table on startup."""
        table = cast("DataTable[Any]", self.query_one("#issue-table", DataTable))
        table.cursor_type = "row"
        table.add_columns("P", "Status", "Type", "ID", "Title", "Owner")
        self._load_issues()

    def _load_issues(self) -> None:
        """Load issues into the data table."""
        table = cast("DataTable[Any]", self.query_one("#issue-table", DataTable))
        table.clear()

        issues = [
            i
            for i in self._storage.list()
            if i.status.value not in ("closed", "tombstone")
        ]
        issues.sort(key=lambda i: (i.priority, i.id))

        for issue in issues:
            p_color = PRIORITY_COLORS.get(issue.priority, "white")
            t_color = TYPE_COLORS.get(issue.issue_type.value, "white")

            table.add_row(
                Text(str(issue.priority), style=f"bold {p_color}"),
                Text(issue.get_status_emoji()),
                Text(issue.issue_type.value, style=t_color),
                Text(issue.full_id, style="bold"),
                issue.title,
                issue.owner or "",
                key=issue.full_id,
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Show issue detail when Enter is pressed on a row."""
        issue_id = str(event.row_key.value)
        if not issue_id:
            return
        issue = self._storage.get(issue_id)
        if issue is None:
            return
        self.push_screen(IssueDetailScreen(issue, self._storage))

    def action_refresh(self) -> None:
        """Reload issues from storage."""
        self._load_issues()
        self.notify("Refreshed")
