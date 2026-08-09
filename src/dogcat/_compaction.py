"""Append-only JSONL compaction policy: when a rewrite is worth its cost.

Policy only — the snapshot writer is :mod:`dogcat._persistence` and the
atomic file primitives are :mod:`dogcat._jsonl_io`.
"""

from __future__ import annotations

# Compact when appended lines exceed this fraction of the base file size.
# 0.5 caps between-compaction growth at ~1.5x the compacted size: a lower
# ratio rewrites the whole file more often (write amplification), a higher
# ratio lets it grow larger before reclaiming (more disk, slower loads).
# 0.5 is the midpoint balancing those two costs.
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
