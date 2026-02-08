"""Tests for parse_labels utility."""

from __future__ import annotations

import pytest

from dogcat.constants import parse_labels


class TestParseLabels:
    """Tests for parse_labels function."""

    def test_comma_separated(self) -> None:
        """Comma-separated labels are split correctly."""
        assert parse_labels("bug,fix") == ["bug", "fix"]

    def test_space_separated(self) -> None:
        """Space-separated labels are split correctly."""
        assert parse_labels("bug fix") == ["bug", "fix"]

    def test_comma_and_space(self) -> None:
        """Comma-and-space separated labels are split correctly."""
        assert parse_labels("bug, fix") == ["bug", "fix"]

    def test_multiple_spaces(self) -> None:
        """Multiple spaces between labels are handled."""
        assert parse_labels("bug   fix") == ["bug", "fix"]

    def test_mixed_separators(self) -> None:
        """Mixed commas and spaces are handled."""
        assert parse_labels("bug, fix  deploy") == ["bug", "fix", "deploy"]

    def test_empty_string(self) -> None:
        """Empty string returns empty list."""
        assert parse_labels("") == []

    def test_only_whitespace(self) -> None:
        """Whitespace-only string returns empty list."""
        assert parse_labels("   ") == []

    def test_only_commas(self) -> None:
        """Commas-only string returns empty list."""
        assert parse_labels(",,,") == []

    def test_single_label(self) -> None:
        """Single label returns single-element list."""
        assert parse_labels("bug") == ["bug"]

    def test_trailing_comma(self) -> None:
        """Trailing comma is ignored."""
        assert parse_labels("bug,fix,") == ["bug", "fix"]

    def test_leading_comma(self) -> None:
        """Leading comma is ignored."""
        assert parse_labels(",bug,fix") == ["bug", "fix"]

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("a,b,c", ["a", "b", "c"]),
            ("a b c", ["a", "b", "c"]),
            ("a, b, c", ["a", "b", "c"]),
            ("a , b , c", ["a", "b", "c"]),
        ],
    )
    def test_various_formats(self, raw: str, expected: list[str]) -> None:
        """Various separator formats all produce the same result."""
        assert parse_labels(raw) == expected
