"""Tests for shared partial-id resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from dogcat._id_resolve import TRAILING_PUNCTUATION, resolve_partial_id
from dogcat._lazy_issues import LazyIssueMap
from dogcat.models import Issue, Status, issue_to_dict
from dogcat.storage import JSONLStorage

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


def _lazy_map(*full_ids: str) -> LazyIssueMap:
    """Build a LazyIssueMap holding unmaterialized records for ``full_ids``."""
    m = LazyIssueMap()
    for full_id in full_ids:
        namespace, _, issue_id = full_id.rpartition("-")
        m.set_raw(
            full_id,
            issue_to_dict(Issue(id=issue_id, namespace=namespace, title=full_id)),
        )
    return m


class TestExactMatch:
    """Exact-match path of resolve_partial_id."""

    def test_exact_match_wins(self) -> None:
        """Full id present in the set returns it directly."""
        ids = {"dc-abc", "dc-abcd"}
        assert resolve_partial_id("dc-abc", ids) == "dc-abc"

    def test_no_match_returns_none(self) -> None:
        """Unknown partial returns None."""
        assert resolve_partial_id("zzz", {"dc-abc", "dc-def"}) is None


class TestEmptyInput:
    """Empty / whitespace-only partial IDs must not match anything."""

    def test_empty_string_returns_none(self) -> None:
        """Empty partial ID returns None even when ids contain a single match."""
        assert resolve_partial_id("", {"dc-abc"}) is None

    def test_empty_string_returns_none_with_multiple_ids(self) -> None:
        """Empty partial ID never matches across many ids."""
        assert resolve_partial_id("", {"dc-abc", "dc-def", "ns-abc"}) is None

    def test_whitespace_returns_none(self) -> None:
        """Whitespace-only partial ID is rejected."""
        assert resolve_partial_id("   ", {"dc-abc"}) is None

    def test_empty_string_works_for_proposals(self) -> None:
        """Same guard applies to multi-segment proposal ids."""
        assert resolve_partial_id("", {"dogcat-inbox-4kzj"}) is None


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


class TestTrailingPunctuation:
    """Ids copied out of a pane or a sentence carry trailing punctuation."""

    @pytest.mark.parametrize("char", TRAILING_PUNCTUATION)
    def test_full_id_with_trailing_punctuation(self, char: str) -> None:
        """Exact match still wins once the punctuation is stripped."""
        ids = {"dogcat-1iw8", "dogcat-other"}
        assert resolve_partial_id(f"dogcat-1iw8{char}", ids) == "dogcat-1iw8"

    @pytest.mark.parametrize("char", TRAILING_PUNCTUATION)
    def test_partial_suffix_with_trailing_punctuation(self, char: str) -> None:
        """Short hash with trailing punctuation resolves by suffix."""
        ids = {"dogcat-1iw8", "dogcat-other"}
        assert resolve_partial_id(f"1iw8{char}", ids) == "dogcat-1iw8"

    @pytest.mark.parametrize("char", TRAILING_PUNCTUATION)
    def test_punctuation_only_returns_none(self, char: str) -> None:
        """A bare punctuation character is empty after stripping."""
        assert resolve_partial_id(char, {"dc-abc"}) is None

    def test_mixed_trailing_run_is_stripped(self) -> None:
        """A run of different trailing characters is stripped in full."""
        ids = {"dogcat-inbox-4kzj"}
        assert resolve_partial_id("4kzj:).", ids) == "dogcat-inbox-4kzj"

    @pytest.mark.parametrize("char", TRAILING_PUNCTUATION)
    def test_only_trailing_punctuation_stripped(self, char: str) -> None:
        """A leading punctuation character is not stripped, so it must not match."""
        assert resolve_partial_id(f"{char}abc", {"dc-abc"}) is None

    def test_hyphen_is_not_stripped(self) -> None:
        """Hyphen separates namespace from hash, so it stays put."""
        assert resolve_partial_id("dc-", {"dc-abc"}) is None


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


class _ExplodingIterMap(dict[str, str]):
    """Mapping whose iteration fails, to prove the exact-match path skips it."""

    def __iter__(self) -> Iterator[str]:
        msg = "iterated the mapping on an exact-id hit"
        raise AssertionError(msg)


class TestExactMatchSkipsScan:
    """An exact full-id hit must not touch every key (dogcat-4p8t)."""

    def test_exact_match_never_iterates_the_mapping(self) -> None:
        """Exact hit answers from __contains__ alone, so __iter__ never runs."""
        ids = _ExplodingIterMap({"dc-abc": "", "dc-def": ""})
        assert resolve_partial_id("dc-abc", ids) == "dc-abc"

    def test_exact_match_survives_trailing_punctuation(self) -> None:
        """Stripping punctuation still lands on the no-scan path."""
        ids = _ExplodingIterMap({"dc-abc": ""})
        assert resolve_partial_id("dc-abc:", ids) == "dc-abc"

    def test_suffix_fallback_still_scans(self) -> None:
        """A non-exact partial does iterate — the guard above is meaningful."""
        ids = _ExplodingIterMap({"dc-abc": ""})
        with pytest.raises(AssertionError, match="iterated the mapping"):
            resolve_partial_id("abc", ids)


class TestNonReiterableInput:
    """One-shot iterables must not be consumed by the membership test."""

    def test_generator_exact_match(self) -> None:
        """A generator is copied first, so the exact id still resolves."""
        ids = (i for i in ("dc-abc", "dc-def"))
        assert resolve_partial_id("dc-abc", ids) == "dc-abc"

    def test_generator_suffix_match(self) -> None:
        """The suffix scan sees every element of a generator."""
        ids = (i for i in ("dc-abc", "dc-def"))
        assert resolve_partial_id("def", ids) == "dc-def"

    def test_list_suffix_match(self) -> None:
        """A list has O(n) membership but is re-iterable; both paths work."""
        assert resolve_partial_id("def", ["dc-abc", "dc-def"]) == "dc-def"


class TestLazyIssueMapInput:
    """Storage passes a LazyIssueMap; its key space must match ``set(ids)``."""

    def test_contains_matches_iteration(self) -> None:
        """__contains__ and __iter__ cover the same keys, tombstones included."""
        m = _lazy_map("dc-abc", "dogcat-inbox-4kzj", "my-ns-with-dashes-abc1")
        assert set(m) == {"dc-abc", "dogcat-inbox-4kzj", "my-ns-with-dashes-abc1"}
        assert all(key in m for key in set(m))

    def test_exact_full_id(self) -> None:
        """Full id resolves through the mapping."""
        m = _lazy_map("dc-abc", "dc-def")
        assert resolve_partial_id("dc-abc", m, kind="issues") == "dc-abc"

    def test_exact_full_id_does_not_materialize(self) -> None:
        """The fast path answers without constructing a single Issue."""
        m = _lazy_map("dc-abc", "dc-def")
        assert resolve_partial_id("dc-abc", m, kind="issues") == "dc-abc"
        assert not any(isinstance(v, Issue) for v in m._entries.values())

    def test_unique_suffix(self) -> None:
        """Short hash resolves by the fallback scan."""
        m = _lazy_map("dc-3hup", "dc-other")
        assert resolve_partial_id("3hup", m, kind="issues") == "dc-3hup"

    def test_namespace_qualified_key(self) -> None:
        """Multi-segment namespaces resolve by their last dash-segment."""
        m = _lazy_map("my-ns-with-dashes-abc1", "other-ns-abc2")
        assert resolve_partial_id("abc1", m) == "my-ns-with-dashes-abc1"

    def test_ambiguous_partial_raises(self) -> None:
        """Ambiguity reports the same way as it does for a plain set."""
        m = _lazy_map("dc-abc", "ns-abc")
        with pytest.raises(ValueError, match="Ambiguous partial ID 'abc'"):
            resolve_partial_id("abc", m, kind="issues")

    def test_no_match_returns_none(self) -> None:
        """Unknown partial returns None."""
        assert resolve_partial_id("zzz", _lazy_map("dc-abc")) is None


class TestTombstonedIds:
    """A deleted issue stays in the key space and stays resolvable."""

    def test_tombstone_only_id_resolves(self) -> None:
        """Tombstones are ordinary keys to the resolver."""
        m = LazyIssueMap()
        issue = Issue(id="abc", namespace="dc", title="gone", status=Status.TOMBSTONE)
        m.set_raw(issue.full_id, issue_to_dict(issue))
        assert resolve_partial_id("dc-abc", m, kind="issues") == "dc-abc"
        assert resolve_partial_id("abc", m, kind="issues") == "dc-abc"

    def test_storage_resolves_deleted_issue(self, temp_dogcats_dir: Path) -> None:
        """End to end: delete then resolve, by full id and by hash."""
        storage = JSONLStorage(str(temp_dogcats_dir / "issues.jsonl"), create_dir=True)
        created = storage.create(Issue(id="abc", namespace="dc", title="doomed"))
        storage.delete(created.full_id)

        assert storage.get(created.full_id) is not None
        assert storage.get(created.full_id).status == Status.TOMBSTONE  # type: ignore[union-attr]
        assert storage.resolve_id(created.full_id) == created.full_id
        assert storage.resolve_id("abc") == created.full_id

    def test_tombstone_participates_in_ambiguity(self) -> None:
        """A tombstone counts toward the ambiguity total, as before."""
        m = LazyIssueMap()
        for namespace, status in (("dc", Status.OPEN), ("ns", Status.TOMBSTONE)):
            issue = Issue(id="abc", namespace=namespace, title="t", status=status)
            m.set_raw(issue.full_id, issue_to_dict(issue))
        with pytest.raises(ValueError, match="matches 2 issues"):
            resolve_partial_id("abc", m, kind="issues")
