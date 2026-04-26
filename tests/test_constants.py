"""Boundary tests for ``constants.is_valid_namespace``."""

from __future__ import annotations

import pytest

from dogcat.constants import MAX_NAMESPACE_LEN, is_valid_namespace


class TestIsValidNamespace:
    """Lock down the namespace whitelist edges."""

    def test_empty_string_rejected(self) -> None:
        """Empty string rejected."""
        assert not is_valid_namespace("")

    def test_single_char_accepted(self) -> None:
        """Single char accepted."""
        assert is_valid_namespace("a")

    def test_max_length_accepted(self) -> None:
        """Max length accepted."""
        assert is_valid_namespace("a" * MAX_NAMESPACE_LEN)

    def test_over_max_length_rejected(self) -> None:
        """Over max length rejected."""
        assert not is_valid_namespace("a" * (MAX_NAMESPACE_LEN + 1))

    @pytest.mark.parametrize(
        "value",
        ["abc", "a-b", "a_b", "ABC", "abc123", "a-b_c", "0name"],
    )
    def test_valid_examples(self, value: str) -> None:
        """Valid examples."""
        assert is_valid_namespace(value)

    @pytest.mark.parametrize(
        "value",
        ["a b", "a/b", "a.b", "a:b", "a@b", "aéb", "a\nb", "  abc"],
    )
    def test_invalid_examples(self, value: str) -> None:
        """Invalid examples."""
        assert not is_valid_namespace(value)
