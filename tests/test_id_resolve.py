"""Tests for shared partial-id resolution."""

from __future__ import annotations

import pytest

from dogcat._id_resolve import resolve_partial_id


class TestExactMatch:
    """Exact-match path of resolve_partial_id."""

    def test_exact_match_wins(self) -> None:
        """Full id present in the set returns it directly."""
        ids = {"dc-abc", "dc-abcd"}
        assert resolve_partial_id("dc-abc", ids) == "dc-abc"

    def test_no_match_returns_none(self) -> None:
        """Unknown partial returns None."""
        assert resolve_partial_id("zzz", {"dc-abc", "dc-def"}) is None


class TestSuffixMatch:
    """Suffix / hash-segment match."""

    def test_short_hash_suffix(self) -> None:
        """Short hash matches via endswith."""
        assert resolve_partial_id("abc", {"dc-abc", "dc-def"}) == "dc-abc"

    def test_full_hash_after_last_dash(self) -> None:
        """Hash equal to the last dash-segment matches."""
        ids = {"dc-3hup", "dc-other"}
        assert resolve_partial_id("3hup", ids) == "dc-3hup"


class TestAmbiguity:
    """Multiple matches must raise."""

    def test_ambiguous_partial_raises(self) -> None:
        """Two ids share the suffix → ValueError."""
        ids = {"dc-abc", "ns-abc"}
        with pytest.raises(ValueError, match="Ambiguous"):
            resolve_partial_id("abc", ids)

    def test_ambiguity_kind_appears_in_message(self) -> None:
        """Custom ``kind`` is plural-formatted in the error message."""
        ids = {"dc-abc", "ns-abc"}
        with pytest.raises(ValueError, match="2 issues"):
            resolve_partial_id("abc", ids, kind="issues")


class TestHyphenatedNamespace:
    """Multi-segment namespaces (e.g. ``dogcat-inbox-X``) must use rsplit."""

    def test_multi_segment_full_id_resolves_by_hash(self) -> None:
        """The hash after the *last* dash matches even for ns-with-dashes."""
        ids = {"dogcat-inbox-4kzj", "dogcat-inbox-9zzz"}
        assert resolve_partial_id("4kzj", ids) == "dogcat-inbox-4kzj"

    def test_multi_segment_full_id_exact_match(self) -> None:
        """Exact match still wins for multi-segment ids."""
        ids = {"dogcat-inbox-4kzj"}
        assert resolve_partial_id("dogcat-inbox-4kzj", ids) == "dogcat-inbox-4kzj"

    def test_split_vs_rsplit_safety(self) -> None:
        """Hash lookup uses the last dash-segment (rsplit), not the first.

        ``my-ns-with-dashes-abc1`` splits to ``ns-with-dashes-abc1`` under
        the old logic; under the new logic it splits to ``abc1``.
        """
        ids = {"my-ns-with-dashes-abc1", "other-ns-abc2"}
        assert resolve_partial_id("abc1", ids) == "my-ns-with-dashes-abc1"
