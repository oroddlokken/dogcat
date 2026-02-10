"""Read-only issue detail screen reusing the editor layout."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Checkbox,
    Collapsible,
    Footer,
    Header,
    Input,
    Label,
    Select,
    Static,
    TextArea,
)

from dogcat.constants import PRIORITY_OPTIONS, STATUS_OPTIONS, TYPE_OPTIONS
from dogcat.tui.shared import SHARED_CSS, make_issue_label

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from dogcat.models import Issue
    from dogcat.storage import JSONLStorage


class IssueDetailScreen(Screen[None]):
    """Full-screen read-only detail view reusing the editor layout."""

    BINDINGS: ClassVar = [
        Binding("escape", "go_back", "Back", priority=True),
        Binding("q", "go_back", "Back"),
    ]

    CSS = SHARED_CSS + """
    #editor-form {
        padding: 1 2;
    }

    #title-input {
        width: 1fr;
    }

    #description-input {
        min-height: 8;
        max-height: 20;
    }

    .detail-section-body {
        margin-left: 2;
        margin-bottom: 1;
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
        """Build the detail view using the same layout as the editor."""
        issue = self._issue

        yield Header()

        # Title bar — same as editor but without Cancel/Save buttons
        with Horizontal(id="title-bar"):
            yield Static(issue.full_id, id="id-display")
            yield Input(
                value=issue.title,
                id="title-input",
                disabled=True,
            )

        with VerticalScroll(id="editor-form"):
            # Field row — same Select widgets as editor, all disabled
            with Horizontal(classes="field-row"):
                yield Select(
                    options=[(label, val) for label, val in TYPE_OPTIONS],
                    value=issue.issue_type.value,
                    id="type-input",
                    allow_blank=False,
                    disabled=True,
                )
                yield Select(
                    options=[(label, val) for label, val in STATUS_OPTIONS],
                    value=issue.status.value,
                    id="status-input",
                    allow_blank=False,
                    disabled=True,
                )
                yield Select(
                    options=[(label, val) for label, val in PRIORITY_OPTIONS],
                    value=issue.priority,
                    id="priority-input",
                    allow_blank=False,
                    disabled=True,
                )
                yield Checkbox(
                    "Manual",
                    value=bool(
                        issue.metadata.get("manual") or issue.metadata.get("no_agent"),
                    ),
                    id="manual-input",
                    disabled=True,
                )

            # Info row — same Input/Select widgets as editor, all disabled
            with Horizontal(classes="info-row"):
                yield Input(
                    value=issue.owner or "",
                    placeholder="Owner",
                    id="owner-input",
                    disabled=True,
                )
                yield Select(
                    options=self._get_parent_options(),
                    value=(issue.parent if issue.parent else Select.BLANK),
                    prompt="Parent",
                    allow_blank=True,
                    id="parent-input",
                    disabled=True,
                )
                yield Input(
                    value=issue.external_ref or "",
                    placeholder="External ref",
                    id="external-ref-input",
                    disabled=True,
                )
                yield Input(
                    value=", ".join(issue.labels) if issue.labels else "",
                    placeholder="Labels",
                    id="labels-input",
                    disabled=True,
                )

            # Description — same TextArea as editor, read-only
            yield Label("Description", classes="field-label")
            yield TextArea(
                issue.description or "",
                id="description-input",
                read_only=True,
            )

            # Collapsible text sections — same as editor, read-only
            with Collapsible(
                title="Notes",
                collapsed=not issue.notes,
            ):
                yield TextArea(
                    issue.notes or "",
                    id="notes-input",
                    classes="collapsible-textarea",
                    read_only=True,
                )

            with Collapsible(
                title="Acceptance Criteria",
                collapsed=not issue.acceptance,
            ):
                yield TextArea(
                    issue.acceptance or "",
                    id="acceptance-input",
                    classes="collapsible-textarea",
                    read_only=True,
                )

            with Collapsible(
                title="Design",
                collapsed=not issue.design,
            ):
                yield TextArea(
                    issue.design or "",
                    id="design-input",
                    classes="collapsible-textarea",
                    read_only=True,
                )

            # Extra sections not in the editor: deps, children, comments
            deps = self._storage.get_dependencies(issue.full_id)
            if deps:
                with Collapsible(title="Dependencies", collapsed=False):
                    for dep in deps:
                        yield Static(
                            f"  \u2192 {dep.depends_on_id} ({dep.dep_type.value})",
                            classes="detail-section-body",
                        )

            children = self._storage.get_children(issue.full_id)
            if children:
                with Collapsible(title="Children", collapsed=False):
                    for child in children:
                        yield Static(
                            f"  \u21b3 {child.id}: {child.title}",
                            classes="detail-section-body",
                        )

            if issue.comments:
                with Collapsible(title="Comments", collapsed=False):
                    for comment in issue.comments:
                        yield Static(
                            f"  [{comment.id}] {comment.author}\n    {comment.text}",
                            classes="detail-section-body",
                        )

        yield Footer()

    def _get_parent_options(self) -> list[tuple[Any, str]]:
        """Build parent options list for the disabled parent selector."""
        options: list[tuple[Any, str]] = []
        for issue in self._storage.list():
            if issue.is_tombstone():
                continue
            options.append((make_issue_label(issue), issue.full_id))
        return options

    def on_mount(self) -> None:
        """Set the screen title."""
        self.app.title = f"{self._issue.full_id}: {self._issue.title}"  # type: ignore[reportUnknownMemberType]

    def action_go_back(self) -> None:
        """Return to the issue list."""
        self.dismiss()
