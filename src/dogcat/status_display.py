"""Shared status-glyph resolution for issue renderers (CLI, TUI, web).

Which glyph and color an issue shows is a subtle rule: a dependency-blocked
issue displays the blocked "■" glyph, UNLESS its status is one of the
advanced states (in_review / deferred / closed), which take display
precedence. ``dcat list``, the Rich table and the TUI all render through here,
which is what keeps the three from disagreeing — re-implementing the rule at a
new surface is how they start to.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dogcat.constants import BLOCKED_DISPLAY_EXEMPT_STATUSES, STATUS_SYMBOLS

if TYPE_CHECKING:
    from dogcat.models import Issue

# Color key (into STATUS_COLORS) for the dependency-blocked override.
_BLOCKED_COLOR_KEY = "blocked"


def is_blocked_display(issue: Issue, blocked_ids: set[str] | None) -> bool:
    """Return True when the issue should render with the blocked glyph.

    An issue renders as blocked when it is in ``blocked_ids`` and its status
    is not one of the display-exempt advanced states.
    """
    return bool(
        blocked_ids
        and issue.full_id in blocked_ids
        and issue.status.value not in BLOCKED_DISPLAY_EXEMPT_STATUSES
    )


def resolve_status_glyph(
    issue: Issue,
    blocked_ids: set[str] | None,
) -> tuple[str, str]:
    """Return the ``(symbol, color_key)`` an issue should display.

    ``color_key`` is a key into ``constants.STATUS_COLORS`` — ``"blocked"``
    for a dependency-blocked issue, otherwise the issue's own status value.
    Renderers apply their own dimming and output-format wrapping on top of
    this base decision.
    """
    if is_blocked_display(issue, blocked_ids):
        return STATUS_SYMBOLS["blocked"], _BLOCKED_COLOR_KEY
    return issue.get_status_emoji(), issue.status.value
