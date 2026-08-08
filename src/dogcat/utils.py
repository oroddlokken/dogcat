"""Shared utility helpers for Dogcat."""

from __future__ import annotations


def estimate_tokens(text: str) -> int:
    """Estimate token count with a chars/4 heuristic.

    Uncalibrated: nothing here has been compared against a real BPE
    tokenizer, and the divisor counts codepoints, so a run of box-drawing
    glyphs or accented text can tokenize to more than this returns rather
    than less. Treat the result as a tripwire for runaway output, not as a
    bound you can spend against.
    """
    return len(text) // 4
