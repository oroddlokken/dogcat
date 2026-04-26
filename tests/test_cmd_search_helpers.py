"""Boundary tests for the ``_extract_snippet`` helper in ``_cmd_search``."""

from __future__ import annotations

import re

from dogcat.cli._cmd_search import _extract_snippet


class TestExtractSnippet:
    """Lock down the snippet-extraction edges."""

    def test_empty_text_no_match(self) -> None:
        """Empty text no match."""
        pat = re.compile("foo")
        assert _extract_snippet("", pat) == ""

    def test_no_match_returns_empty(self) -> None:
        """No match returns empty."""
        pat = re.compile("zzz")
        assert _extract_snippet("hello world", pat) == ""

    def test_zero_context_returns_only_match(self) -> None:
        """Zero context returns only match."""
        pat = re.compile("world")
        result = _extract_snippet("hello world today", pat, context=0)
        assert result == "...world..."

    def test_match_at_start_no_leading_ellipsis(self) -> None:
        """Match at start no leading ellipsis."""
        pat = re.compile("hello")
        result = _extract_snippet("hello world", pat, context=40)
        assert result.startswith("hello")
        assert not result.startswith("...")

    def test_match_at_end_no_trailing_ellipsis(self) -> None:
        """Match at end no trailing ellipsis."""
        pat = re.compile("end")
        result = _extract_snippet("the end", pat, context=40)
        assert result.endswith("end")
        assert not result.endswith("...")

    def test_match_longer_than_text(self) -> None:
        """Match longer than text."""
        pat = re.compile("hello world")
        result = _extract_snippet("hello world", pat, context=40)
        assert result == "hello world"

    def test_newlines_collapsed_to_spaces(self) -> None:
        """Newlines collapsed to spaces."""
        pat = re.compile("foo")
        result = _extract_snippet("a\nfoo\nb", pat, context=40)
        assert "\n" not in result
        assert "foo" in result
