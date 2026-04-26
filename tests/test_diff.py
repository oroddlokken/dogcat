"""Direct tests for ``dogcat._diff`` normalization and change-tracking.

The functions in :mod:`dogcat._diff` are the canonical rule used by
storage, inbox, validate, and the diff CLI. Regressions to the diff
semantics could pass every end-to-end test while quietly corrupting the
event log. (dogcat-4skc)
"""

from __future__ import annotations

from enum import Enum

import pytest

from dogcat._diff import field_value, tracked_changes
from dogcat.models import IssueType, Status


class _ColorEnum(Enum):
    RED = "red"
    BLUE = "blue"


class _IntEnum(Enum):
    ONE = 1
    TWO = 2


class TestFieldValue:
    """Cover ``field_value`` enum unwrap and pass-through semantics."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (Status.OPEN, "open"),
            (Status.CLOSED, "closed"),
            (IssueType.BUG, "bug"),
            (_ColorEnum.RED, "red"),
            (_IntEnum.ONE, 1),
        ],
    )
    def test_unwraps_enums(self, raw: object, expected: object) -> None:
        """Enums and ``.value``-bearing wrappers unwrap to their scalar."""
        assert field_value(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        ["plain", 42, 3.14, None, True, False, [1, 2], (1, 2)],
    )
    def test_passes_through_plain_scalars(self, raw: object) -> None:
        """Plain scalars (no ``.value`` attribute) round-trip unchanged."""
        assert field_value(raw) == raw

    def test_dict_passed_through_unchanged(self) -> None:
        """Dicts have no ``.value`` and pass through identity-equal."""
        d = {"a": 1, "b": 2}
        assert field_value(d) is d

    def test_enum_string_equality_after_unwrap(self) -> None:
        """Enum and its string form compare equal after normalization.

        The whole point of ``field_value`` is that ``Status.OPEN`` and
        the raw ``"open"`` string compare equal in diffs.
        """
        assert field_value(Status.OPEN) == "open"
        assert field_value("open") == "open"
        assert field_value(Status.OPEN) == field_value("open")

    def test_object_with_value_attribute_is_unwrapped(self) -> None:
        """Any object exposing ``.value`` is treated as enum-like.

        Documents the duck-typing rule — a regression that adds an
        explicit ``isinstance(Enum)`` check would change semantics for
        custom value-wrapping types.
        """

        class Wrapper:
            value = "wrapped"

        assert field_value(Wrapper()) == "wrapped"


class TestTrackedChanges:
    """Cover ``tracked_changes`` field-by-field diff over an iterable."""

    def test_empty_inputs_return_empty(self) -> None:
        """Empty old/new and empty tracked iterables both return ``{}``."""
        assert tracked_changes({}, {}, []) == {}
        assert tracked_changes({}, {}, ["title"]) == {}

    def test_returns_only_tracked_fields(self) -> None:
        """Untracked fields are not surfaced even when they differ."""
        old = {"title": "old", "priority": 2, "ignored": "a"}
        new = {"title": "new", "priority": 2, "ignored": "b"}
        changes = tracked_changes(old, new, ["title", "priority"])
        assert "title" in changes
        assert "priority" not in changes
        assert "ignored" not in changes

    def test_change_record_shape(self) -> None:
        """Each entry is ``{field: {"old": ..., "new": ...}}``."""
        changes = tracked_changes({"title": "old"}, {"title": "new"}, ["title"])
        assert changes == {"title": {"old": "old", "new": "new"}}

    def test_missing_key_equals_none(self) -> None:
        """A field absent on one side compares equal to None on the other.

        ``.get()`` returns None for missing keys; callers rely on this so
        an UNSET → None update is a no-op.
        """
        assert tracked_changes({"title": None}, {}, ["title"]) == {}
        assert tracked_changes({}, {"title": None}, ["title"]) == {}

    def test_field_absent_from_both_is_noop(self) -> None:
        """Tracked fields that exist on neither side are not in the diff."""
        assert tracked_changes({}, {}, ["title", "priority"]) == {}

    def test_enum_to_string_does_not_show_as_change(self) -> None:
        """Enum → string of same value is not reported as a change.

        Without this, every save through the storage path would emit
        spurious status events.
        """
        assert (
            tracked_changes({"status": Status.OPEN}, {"status": "open"}, ["status"])
            == {}
        )

    def test_string_to_enum_does_not_show_as_change(self) -> None:
        """String → enum of same value is not a change either."""
        assert (
            tracked_changes({"status": "open"}, {"status": Status.OPEN}, ["status"])
            == {}
        )

    def test_enum_to_different_enum_is_a_change(self) -> None:
        """Distinct enum values diff to their unwrapped scalars."""
        changes = tracked_changes(
            {"status": Status.OPEN},
            {"status": Status.CLOSED},
            ["status"],
        )
        assert changes == {"status": {"old": "open", "new": "closed"}}

    def test_nested_dict_compared_by_equality(self) -> None:
        """Nested dicts compare via ``!=``.

        Identical content is no change; any difference is a change.
        This is the contract metadata diffs depend on.
        """
        same = {"k": 1, "list": [1, 2]}
        assert (
            tracked_changes({"metadata": same}, {"metadata": dict(same)}, ["metadata"])
            == {}
        )
        diff_changes = tracked_changes(
            {"metadata": {"k": 1}}, {"metadata": {"k": 2}}, ["metadata"]
        )
        assert "metadata" in diff_changes

    @pytest.mark.parametrize(
        ("tracked", "label"),
        [
            (["a", "b"], "list"),
            (("a", "b"), "tuple"),
            ({"a", "b"}, "set"),
            (frozenset({"a", "b"}), "frozenset"),
            (iter(["a", "b"]), "iterator"),
        ],
        ids=["list", "tuple", "set", "frozenset", "iterator"],
    )
    def test_tracked_accepts_any_iterable(self, tracked: object, label: str) -> None:
        """``tracked`` accepts any iterable, not only sets.

        The implementation coerces to frozenset, so a plain
        list/tuple/iterator must work and be consumed exactly once.
        """
        del label
        old = {"a": 1, "b": 2}
        new = {"a": 9, "b": 2}
        changes = tracked_changes(old, new, tracked)  # type: ignore[arg-type]
        assert changes == {"a": {"old": 1, "new": 9}}

    def test_no_changes_returns_empty(self) -> None:
        """Identical old and new produce an empty diff."""
        old = {"title": "same", "priority": 1}
        new = {"title": "same", "priority": 1}
        assert tracked_changes(old, new, ["title", "priority"]) == {}

    def test_tracked_field_only_in_new(self) -> None:
        """A new field that wasn't in old must show up as None → value."""
        changes = tracked_changes({}, {"title": "added"}, ["title"])
        assert changes == {"title": {"old": None, "new": "added"}}

    def test_tracked_field_only_in_old(self) -> None:
        """A removed field shows as value → None."""
        changes = tracked_changes({"title": "removed"}, {}, ["title"])
        assert changes == {"title": {"old": "removed", "new": None}}
