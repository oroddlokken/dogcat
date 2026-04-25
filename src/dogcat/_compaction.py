"""Append-only JSONL compaction policy.

Extracted from ``storage.py`` to keep the compaction trigger logic in one
place where it can be reasoned about (and tested) independently of the
storage class.
"""

from __future__ import annotations

# Compact when appended lines exceed this fraction of the base file size.
COMPACTION_RATIO = 0.5
# Minimum base size before ratio-based compaction kicks in. Files smaller
# than this skip compaction entirely; the cost of rewriting outweighs the
# gain at small sizes.
COMPACTION_MIN_BASE = 20


def should_compact(base_lines: int, appended_lines: int) -> bool:
    """Return True if a JSONL file should be auto-compacted now.

    The trigger is *additive*: appended-line count must exceed
    ``COMPACTION_RATIO`` of the base size, and the base must be at least
    ``COMPACTION_MIN_BASE`` lines (so trivial files don't churn).
    """
    return (
        base_lines >= COMPACTION_MIN_BASE
        and appended_lines > base_lines * COMPACTION_RATIO
    )
