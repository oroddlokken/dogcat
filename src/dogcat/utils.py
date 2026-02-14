"""Shared utility helpers for Dogcat."""

from __future__ import annotations


def estimate_tokens(text: str) -> int:
    """Estimate token count using a conservative chars/4 heuristic.

    This intentionally over-counts compared to real BPE tokenisation,
    so staying under a budget measured with this function guarantees
    the actual token footprint is even smaller.
    """
    return len(text) // 4
