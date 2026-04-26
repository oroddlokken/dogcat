"""Tests for ``dogcat.utils.estimate_tokens``.

The heuristic underwrites the ``dcat prime`` token budget — if it drifts
silently the prime command can balloon past its budget without any test
catching it. Lock the contract here.
"""

from __future__ import annotations

from dogcat.utils import estimate_tokens


class TestEstimateTokens:
    """Lock down the chars/4 heuristic."""

    def test_empty_string(self) -> None:
        """Empty string."""
        assert estimate_tokens("") == 0

    def test_short_string_floors_to_zero(self) -> None:
        """Short string floors to zero."""
        # 3 chars / 4 == 0 by floor division
        assert estimate_tokens("abc") == 0

    def test_exactly_four_chars(self) -> None:
        """Exactly four chars."""
        assert estimate_tokens("abcd") == 1

    def test_floor_division_not_round(self) -> None:
        """Floor division not round."""
        # 7 chars / 4 == 1 (floor), not 2 (round).
        assert estimate_tokens("abcdefg") == 1

    def test_proportional_to_length(self) -> None:
        """Proportional to length."""
        assert estimate_tokens("a" * 400) == 100

    def test_unicode_counts_codepoints(self) -> None:
        """Unicode counts codepoints."""
        # Heuristic uses len() — codepoints, not bytes.
        text = "é" * 4
        assert estimate_tokens(text) == 1
