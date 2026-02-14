"""Textual TUI components for dogcat."""

from dogcat.tui.dashboard import DogcatTUI
from dogcat.tui.detail_panel import IssueDetailPanel
from dogcat.tui.editor import IssueEditorApp, IssueEditorScreen, edit_issue, new_issue
from dogcat.tui.picker import IssuePickerApp, pick_issue
from dogcat.tui.shared import make_issue_label

__all__ = [
    "DogcatTUI",
    "IssueDetailPanel",
    "IssueEditorApp",
    "IssueEditorScreen",
    "IssuePickerApp",
    "edit_issue",
    "make_issue_label",
    "new_issue",
    "pick_issue",
]
