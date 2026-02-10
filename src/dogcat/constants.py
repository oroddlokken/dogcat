"""Constants for Dogcat CLI."""

from __future__ import annotations

import re


def parse_labels(raw: str) -> list[str]:
    """Parse a labels string that may be comma-separated, space-separated, or both.

    Examples:
        "bug,fix"     -> ["bug", "fix"]
        "bug fix"     -> ["bug", "fix"]
        "bug, fix"    -> ["bug", "fix"]
        ""            -> []
    """
    return [lbl for lbl in re.split(r"[,\s]+", raw) if lbl]


# Default values
DEFAULT_TYPE = "task"
DEFAULT_PRIORITY = 2

# Priority shorthand: single digits 0-4
PRIORITY_SHORTHANDS = frozenset("01234")

# Type shorthands: single characters mapping to issue types
TYPE_SHORTHANDS = {
    "b": "bug",
    "c": "chore",
    "d": "draft",
    "e": "epic",
    "f": "feature",
    "q": "question",
    "s": "story",
    "t": "task",
}

# All valid shorthands
ALL_SHORTHANDS = PRIORITY_SHORTHANDS | frozenset(TYPE_SHORTHANDS.keys())

# Color mappings for CLI/TUI display
PRIORITY_COLORS = {
    0: "bright_red",
    1: "yellow",
    2: "white",
    3: "cyan",
    4: "bright_black",
}

TYPE_COLORS = {
    "task": "white",
    "bug": "bright_red",
    "feature": "bright_green",
    "story": "bright_blue",
    "chore": "bright_black",
    "epic": "bright_magenta",
    "subtask": "cyan",
    "question": "bright_yellow",
    "draft": "bright_black",
}

STATUS_COLORS = {
    "open": "bright_green",
    "in_progress": "bright_blue",
    "in_review": "bright_yellow",
    "blocked": "bright_red",
    "deferred": "bright_black",
    "closed": "white",
}

# UI dropdown options (display_label, value)
TYPE_OPTIONS = [
    ("Task", "task"),
    ("Bug", "bug"),
    ("Feature", "feature"),
    ("Story", "story"),
    ("Chore", "chore"),
    ("Epic", "epic"),
    ("Subtask", "subtask"),
    ("Question", "question"),
    ("Draft", "draft"),
]

PRIORITY_OPTIONS = [
    ("P0 - Critical", 0),
    ("P1 - High", 1),
    ("P2 - Medium", 2),
    ("P3 - Low", 3),
    ("P4 - Minimal", 4),
]

# String name to priority int mapping
PRIORITY_NAMES: dict[str, int] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "minimal": 4,
}

STATUS_OPTIONS = [
    ("Open", "open"),
    ("In Progress", "in_progress"),
    ("In Review", "in_review"),
    ("Blocked", "blocked"),
    ("Deferred", "deferred"),
    ("Closed", "closed"),
]

# Progressive ID length scaling thresholds
# Tuple of (max_issue_count, id_length)
# IDs scale: 4 chars for 0-500 issues, 5 chars for 501-1500, 6+ beyond
ID_LENGTH_THRESHOLDS = (
    (500, 4),
    (1500, 5),
    (5000, 6),
)
ID_LENGTH_MAX = 7

# Config file for external .dogcats directory
DOGCATRC_FILENAME = ".dogcatrc"

# Fields tracked in the event log (content fields only)
TRACKED_FIELDS: frozenset[str] = frozenset(
    {
        "title",
        "description",
        "labels",
        "external_ref",
        "issue_type",
        "priority",
        "parent",
        "acceptance",
        "notes",
        "design",
        "status",
        "owner",
    },
)

# Symbols for history/diff output
EVENT_SYMBOLS: dict[str, str] = {
    "created": "+",
    "closed": "\u2713",
    "updated": "~",
    "deleted": "\u2717",
}
