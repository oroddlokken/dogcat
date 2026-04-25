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

# Maximum number of preview subtasks shown under deferred parents in list view
MAX_PREVIEW_SUBTASKS = 3

# Split-pane TUI thresholds
SPLIT_PANE_MIN_COLS = 200
SPLIT_PANE_MIN_ROWS = 40

# Maximum estimated token count for `dcat prime` output.
# Measured with a conservative char-based estimator (chars / 4) that over-counts
# vs real Claude BPE tokenisation, so staying under this limit guarantees the
# actual token footprint is even smaller.
MAX_PRIME_TOKENS = 1500
MAX_PRIME_TOKENS_OPINIONATED = 2000

# Priority shorthand: single digits 0-4
PRIORITY_SHORTHANDS = frozenset("01234")

# Type shorthands: single characters mapping to issue types
TYPE_SHORTHANDS = {
    "b": "bug",
    "c": "chore",
    "e": "epic",
    "f": "feature",
    "q": "question",
    "s": "story",
    "t": "task",
}

# Status shorthands: single characters mapping to statuses
STATUS_SHORTHANDS = {
    "d": "draft",
}

# All valid shorthands
ALL_SHORTHANDS = (
    PRIORITY_SHORTHANDS
    | frozenset(TYPE_SHORTHANDS.keys())
    | frozenset(STATUS_SHORTHANDS.keys())
)

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
    "question": "bright_yellow",
}

STATUS_COLORS = {
    "draft": "bright_black",
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
    ("Question", "question"),
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
    ("Draft", "draft"),
    ("Open", "open"),
    ("In Progress", "in_progress"),
    ("In Review", "in_review"),
    ("Blocked", "blocked"),
    ("Deferred", "deferred"),
    ("Closed", "closed"),
]

# Inbox proposal statuses (display_label, value)
INBOX_STATUS_OPTIONS = [
    ("Open", "open"),
    ("Closed", "closed"),
    ("Tombstone", "tombstone"),
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

# Git merge driver configuration
MERGE_DRIVER_CMD = "dcat git merge-driver %O %A %B"
MERGE_DRIVER_NAME = "dogcat JSONL merge driver"
MERGE_DRIVER_GIT_KEY = "merge.dcat-jsonl.driver"
MERGE_DRIVER_GIT_NAME_KEY = "merge.dcat-jsonl.name"
GITATTRIBUTES_ENTRY = ".dogcats/*.jsonl merge=dcat-jsonl"

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
        "snoozed_until",
    },
)

# Fields tracked for proposal diffs
TRACKED_PROPOSAL_FIELDS: frozenset[str] = frozenset(
    {
        "title",
        "description",
        "status",
        "proposed_by",
        "source_repo",
        "closed_reason",
        "resolved_issue",
    },
)

# Symbols for history/diff output
EVENT_SYMBOLS: dict[str, str] = {
    "created": "+",
    "closed": "\u2713",
    "updated": "~",
    "deleted": "\u2717",
}

# Statuses that mean "this issue won't move" — used by listing commands
# that filter out closed/tombstoned issues from "active" views.
TERMINAL_STATUSES: frozenset[str] = frozenset({"closed", "tombstone"})


# Status symbols for at-a-glance display
STATUS_SYMBOLS: dict[str, str] = {
    "draft": "\u270e",  # ✎
    "open": "\u25cf",  # ●
    "in_progress": "\u25d0",  # ◐
    "in_review": "?",
    "blocked": "\u25a0",  # ■
    "deferred": "\u25c7",  # ◇
    "closed": "\u2713",  # ✓
    "tombstone": "\u2620",  # ☠
}

# Web server defaults. Overridable via DCAT_WEB_HOST / DCAT_WEB_PORT env vars
# (CLI flags still win).
WEB_DEFAULT_HOST = "127.0.0.1"
WEB_DEFAULT_PORT = 48042
WEB_HOST_ENV_VAR = "DCAT_WEB_HOST"
WEB_PORT_ENV_VAR = "DCAT_WEB_PORT"


# ---------------------------------------------------------------------------
# JSONL filenames + .dogcats directory layout
# ---------------------------------------------------------------------------
# Single source of truth for the on-disk layout. JSONLStorage / InboxStorage /
# event_log default arguments compose paths from these constants instead of
# repeating the literals; the merge driver, doctor, init, etc. read from here
# too so a future rename only has to touch this file.
DOGCATS_DIR_NAME = ".dogcats"
ISSUES_FILENAME = "issues.jsonl"
INBOX_FILENAME = "inbox.jsonl"
LOCK_FILENAME = ".issues.lock"


# ---------------------------------------------------------------------------
# Default branch names for compaction safety
# ---------------------------------------------------------------------------
# Storage avoids compacting on feature branches because that would create
# noisy diffs. The hardcoded fallback covers the conventional defaults; the
# `_is_default_branch` reader also unions in the user's
# ``init.defaultBranch`` git config, so projects on `develop`/`trunk`/etc.
# don't silently lose auto-compaction.
DEFAULT_BRANCH_NAMES: frozenset[str] = frozenset({"main", "master"})


# ---------------------------------------------------------------------------
# Web propose validation limits + namespace rule
# ---------------------------------------------------------------------------
# These are the only namespace shape rules in the codebase. Promoted out of
# the route module so the CLI / IDGenerator / config can reuse the same
# regex when we extend strict-namespace enforcement to other surfaces.
MAX_TITLE_LEN = 500
MAX_DESC_LEN = 50_000
MAX_NAMESPACE_LEN = 64
NAMESPACE_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def is_valid_namespace(value: str) -> bool:
    """Return True if ``value`` is a well-formed namespace identifier.

    Whitelist: ASCII letters, digits, underscore, hyphen, 1-64 chars. The
    web propose form NFKC-normalizes input before calling this; CLI / API
    callers should do the same when accepting user input.
    """
    return (
        bool(value)
        and len(value) <= MAX_NAMESPACE_LEN
        and bool(NAMESPACE_PATTERN.fullmatch(value))
    )


# ---------------------------------------------------------------------------
# Web propose security headers + CSRF cookie
# ---------------------------------------------------------------------------
# Security policies belong in one auditable location, not buried inside
# inner-class dispatch handlers. CSRF_COOKIE_NAME stays where it is (the
# route module) since it's only referenced there.
CSRF_COOKIE_MAX_AGE_SECONDS = 60 * 60  # 1h — limits the leaked-token window
WEB_CSP_HEADER = "default-src 'none'; style-src 'self'; script-src 'self'"


# ---------------------------------------------------------------------------
# Claude Code PreCompact hook
# ---------------------------------------------------------------------------
# The hook command and its surrounding settings.json shape live here so the
# doctor's install + upgrade paths and any future ``dcat hook ...`` command
# all read from one place. The previous string-replace in
# ``_upgrade_precompact_hook`` was fragile if "dcat prime" ever appeared as
# a substring elsewhere in a user's settings.
PRECOMPACT_HOOK_COMMAND = "dcat prime --replay"
PRECOMPACT_HOOK_RECORD: dict[str, object] = {
    "matcher": "",
    "hooks": [{"type": "command", "command": PRECOMPACT_HOOK_COMMAND}],
}
