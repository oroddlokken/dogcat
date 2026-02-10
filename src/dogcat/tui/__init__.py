"""Textual TUI components for dogcat."""

from dogcat.tui.dashboard import DogcatTUI
from dogcat.tui.detail import IssueDetailScreen
from dogcat.tui.editor import IssueEditorApp, edit_issue, new_issue
from dogcat.tui.picker import IssuePickerApp, pick_issue
from dogcat.tui.shared import make_issue_label

__all__ = [
    "DogcatTUI",
    "IssueDetailScreen",
    "IssueEditorApp",
    "IssuePickerApp",
    "edit_issue",
    "make_issue_label",
    "new_issue",
    "pick_issue",
]
