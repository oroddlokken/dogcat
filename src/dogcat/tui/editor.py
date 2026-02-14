"""Textual-based issue editor for interactive editing."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header

from dogcat.tui.detail_panel import IssueDetailPanel
from dogcat.tui.shared import SHARED_CSS

if TYPE_CHECKING:
    from textual.dom import DOMNode

    from dogcat.models import Issue
    from dogcat.storage import JSONLStorage


class IssueEditorScreen(Screen["Issue | None"]):
    """Screen for editing or creating an issue.

    Thin wrapper around ``IssueDetailPanel`` that adds Header/Footer and
    screen-level navigation.  Dismisses with the saved ``Issue`` on
    success, or ``None`` on cancel.
    """

    BINDINGS: ClassVar = [
        Binding("ctrl+s", "save", "Save", priority=True),
        Binding("escape", "go_back", "Back", priority=True, show=False),
        Binding("q", "go_back", "Quit", show=False),
        Binding("e", "enter_edit", "Edit"),
    ]

    CSS = (
        SHARED_CSS
        + """
    #editor-form {
        padding: 1 2;
    }

    #title-input {
        width: 1fr;
    }

    #title-bar Button {
        margin-left: 1;
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
    def _panel(self) -> IssueDetailPanel | None:
        """Return the embedded detail panel, or None before compose."""
        try:
            return self.query_one("#editor-panel", IssueDetailPanel)
        except Exception:
            return None

    def compose(self) -> ComposeResult:
        """Compose the editor screen: Header, detail panel, Footer."""
        yield Header()
        yield IssueDetailPanel(
            self._issue,
            self._storage,
            create_mode=self._create_mode,
            view_mode=self._view_mode,
            namespace=self._namespace,
            existing_ids=self._existing_ids,
            id="editor-panel",
        )
        yield Footer()

    def on_mount(self) -> None:
        """Set app title based on mode."""
        if self._view_mode:
            self.app.title = f"{self._issue.full_id}: {self._issue.title}"  # type: ignore[reportUnknownMemberType]
        elif self._create_mode:
            self.app.title = "New Issue"  # type: ignore[reportUnknownMemberType]
        else:
            self.app.title = f"Edit: {self._issue.full_id} - {self._issue.title}"  # type: ignore[reportUnknownMemberType]

    def on_issue_detail_panel_saved(self, event: IssueDetailPanel.Saved) -> None:
        """Dismiss the screen with the saved issue."""
        self.dismiss(event.issue)

    def on_issue_detail_panel_cancelled(
        self,
        event: IssueDetailPanel.Cancelled,  # noqa: ARG002
    ) -> None:
        """Dismiss the screen on cancel."""
        self.dismiss(None)

    def action_save(self) -> None:
        """Delegate save to the panel."""
        panel = self._panel
        if panel is not None:
            panel.do_save()

    def action_go_back(self) -> None:
        """Cancel and return.  Only allowed in view mode to prevent data loss."""
        panel = self._panel
        if panel is not None and not panel.is_view_mode:
            return
        self.dismiss(None)

    def check_action(  # type: ignore[override]
        self,
        action: str,
        parameters: tuple[object, ...],  # noqa: ARG002
    ) -> bool | None:
        """Conditionally enable bindings based on the panel mode."""
        panel = self._panel
        if panel is None:
            # Fallback before panel is composed
            if action == "enter_edit":
                return self._view_mode
            if action == "save":
                return not self._view_mode
            return True
        if action == "enter_edit":
            return panel.is_view_mode
        if action == "save":
            return not panel.is_view_mode
        return True

    def action_enter_edit(self) -> None:
        """Switch from view mode to edit mode."""
        panel = self._panel
        if panel is not None:
            panel.enter_edit()
            self.app.title = f"Edit: {self._issue.full_id} - {self._issue.title}"  # type: ignore[reportUnknownMemberType]


class IssueEditorApp(App["Issue | None"]):
    """Standalone Textual app wrapper for the editor screen.

    Used by the ``dcat edit`` and ``dcat new`` CLI commands.  The dashboard
    pushes ``IssueEditorScreen`` directly instead of going through this app.
    """

    TITLE = "Edit Issue"
    ENABLE_COMMAND_PALETTE = False

    CSS = IssueEditorScreen.CSS

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
        self._existing_ids = existing_ids
        self.saved = False
        self.updated_issue: Issue | None = None
        self.result_issue: Issue | None = None

    def _get_dom_base(self) -> DOMNode:  # type: ignore[override]
        """Route queries to the active screen so tests can use app.query()."""
        return self.screen

    async def on_mount(self) -> None:
        """Push the editor screen on startup."""
        await self.push_screen(
            IssueEditorScreen(
                self._issue,
                self._storage,
                create_mode=self._create_mode,
                namespace=self._namespace,
                existing_ids=self._existing_ids,
            ),
            callback=self._on_editor_done,
        )

    def _on_editor_done(self, result: Issue | None) -> None:
        """Handle editor screen dismissal."""
        self.result_issue = result
        if result is not None:
            self.saved = True
            self.updated_issue = result
        self.exit(result)


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
    return editor.result_issue


def new_issue(
    storage: JSONLStorage,
    namespace: str,
    owner: str | None = None,
    *,
    title: str = "",
    priority: int | None = None,
    issue_type: str | None = None,
    status: str | None = None,
) -> Issue | None:
    """Open the Textual editor to create a new issue.

    Args:
        storage: The storage backend.
        namespace: The issue namespace/prefix.
        owner: Default owner for the new issue.
        title: Pre-filled title for the new issue.
        priority: Pre-filled priority (0-4) for the new issue.
        issue_type: Pre-filled issue type (e.g. "bug", "feature").
        status: Pre-filled status (e.g. "draft").

    Returns:
        The created issue, or None if cancelled.
    """
    from dogcat.models import Issue, IssueType, Status

    kwargs: dict[str, Any] = {
        "id": "",
        "title": title,
        "namespace": namespace,
        "owner": owner,
    }
    if priority is not None:
        kwargs["priority"] = priority
    if issue_type is not None:
        kwargs["issue_type"] = IssueType(issue_type)
    if status is not None:
        kwargs["status"] = Status(status)

    skeleton = Issue(**kwargs)

    editor = IssueEditorApp(
        skeleton,
        storage,
        create_mode=True,
        namespace=namespace,
        existing_ids=storage.get_issue_ids(),
    )
    editor.run()
    return editor.result_issue
