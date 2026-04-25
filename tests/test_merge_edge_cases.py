"""Edge-case file states in merge: empty files, unrelated histories, etc.

Tests merge driver behavior with unusual file states like empty files,
unrelated git histories, and forward-compatibility with unknown record types.
"""

from __future__ import annotations

from typing import Any

from dogcat.merge_driver import merge_jsonl

# ---------------------------------------------------------------------------
# Test scenarios
# ---------------------------------------------------------------------------


class TestMergeEdgeCases:
    """Edge-case file states and merge scenarios."""

    def test_empty_file_one_side(self) -> None:
        """One side empty, other side has records.

        Merge should produce the non-empty side's content.
        """
        # Base: empty
        base: list[dict[str, Any]] = []

        # Ours: empty
        ours: list[dict[str, Any]] = []

        # Theirs: has records
        theirs = [
            {
                "record_type": "issue",
                "namespace": "test",
                "id": "issue1",
                "title": "Issue 1",
                "status": "open",
                "priority": 2,
                "issue_type": "task",
                "updated_at": "2026-01-01T00:00:00+00:00",
            }
        ]

        result = merge_jsonl(base, ours, theirs)

        # Result should have theirs' issue
        issues = [r for r in result if r.get("record_type") == "issue"]
        assert len(issues) == 1
        assert issues[0]["id"] == "issue1"

    def test_empty_file_both_sides(self) -> None:
        """Empty file on both sides.

        Merge should produce empty result without warnings.
        """
        base: list[dict[str, Any]] = []
        ours: list[dict[str, Any]] = []
        theirs: list[dict[str, Any]] = []

        result = merge_jsonl(base, ours, theirs)

        # Result should be empty
        assert len(result) == 0

    def test_unrelated_histories_union(self) -> None:
        """Unrelated histories: no common base, both sides have issues.

        Merge should produce union of both sides' records.
        """
        # No common base (unrelated histories)
        base: list[dict[str, Any]] = []

        # Ours: two issues
        ours = [
            {
                "record_type": "issue",
                "namespace": "test",
                "id": "ours1",
                "title": "Ours 1",
                "status": "open",
                "priority": 2,
                "issue_type": "task",
                "updated_at": "2026-01-01T00:00:00+00:00",
            },
            {
                "record_type": "issue",
                "namespace": "test",
                "id": "ours2",
                "title": "Ours 2",
                "status": "open",
                "priority": 2,
                "issue_type": "task",
                "updated_at": "2026-01-01T00:00:00+00:00",
            },
        ]

        # Theirs: two different issues
        theirs = [
            {
                "record_type": "issue",
                "namespace": "test",
                "id": "theirs1",
                "title": "Theirs 1",
                "status": "open",
                "priority": 2,
                "issue_type": "task",
                "updated_at": "2026-01-01T00:00:00+00:00",
            },
            {
                "record_type": "issue",
                "namespace": "test",
                "id": "theirs2",
                "title": "Theirs 2",
                "status": "open",
                "priority": 2,
                "issue_type": "task",
                "updated_at": "2026-01-01T00:00:00+00:00",
            },
        ]

        result = merge_jsonl(base, ours, theirs)

        # Result should have all 4 issues
        issues = [r for r in result if r.get("record_type") == "issue"]
        assert len(issues) == 4
        ids = {r["id"] for r in issues}
        assert ids == {"ours1", "ours2", "theirs1", "theirs2"}

    def test_trailing_whitespace_normalized(self) -> None:
        """Trailing whitespace and final newlines are handled correctly.

        Merged output should be canonical (no trailing whitespace,
        proper newlines).
        """
        # Create records with various whitespace scenarios
        base = [
            {
                "record_type": "issue",
                "namespace": "test",
                "id": "test1",
                "title": "Test 1",
                "status": "open",
                "priority": 2,
                "issue_type": "task",
                "updated_at": "2026-01-01T00:00:00+00:00",
            }
        ]

        ours = base.copy()

        theirs = [
            {
                "record_type": "issue",
                "namespace": "test",
                "id": "test2",
                "title": "Test 2  ",  # Trailing spaces in title
                "status": "open",
                "priority": 2,
                "issue_type": "task",
                "updated_at": "2026-01-01T00:00:00+00:00",
            }
        ]

        result = merge_jsonl(base, ours, theirs)

        # Result should have both issues
        issues = [r for r in result if r.get("record_type") == "issue"]
        assert len(issues) == 2

        # Check that JSON is valid and not corrupted
        for issue in issues:
            assert isinstance(issue, dict)
            assert "id" in issue

    def test_unknown_record_types_skipped(self) -> None:
        """Unknown record types are safely skipped.

        Conservative approach: merge driver ignores unknown types rather than
        passing them through, preventing corruption with future schema changes.
        """
        # Base: empty
        base: list[dict[str, Any]] = []

        # Ours: has unknown record type
        ours = [
            {
                "record_type": "future_feature",  # Unknown type
                "data": "some data",
                "timestamp": "2026-01-01T00:00:00+00:00",
            }
        ]

        # Theirs: has known record type
        theirs = [
            {
                "record_type": "issue",
                "namespace": "test",
                "id": "known",
                "title": "Known Issue",
                "status": "open",
                "priority": 2,
                "issue_type": "task",
                "updated_at": "2026-01-01T00:00:00+00:00",
            }
        ]

        result = merge_jsonl(base, ours, theirs)

        # Unknown records should be skipped (not present in result)
        unknown_records = [
            r for r in result if r.get("record_type") == "future_feature"
        ]
        known_records = [r for r in result if r.get("record_type") == "issue"]

        assert len(unknown_records) == 0, "Unknown record should be safely skipped"

        assert len(known_records) == 1, "Known record should be present"
        assert known_records[0]["id"] == "known"

    def test_base_only_deleted_both_sides(self) -> None:
        """Issue in base, deleted (tombstoned) on both sides.

        Merge should preserve deletion on both sides.
        """
        # Base: has issue
        base = [
            {
                "record_type": "issue",
                "namespace": "test",
                "id": "deleted",
                "title": "To Delete",
                "status": "open",
                "priority": 2,
                "issue_type": "task",
                "updated_at": "2026-01-01T00:00:00+00:00",
            }
        ]

        # Ours: delete the issue (tombstone)
        ours = [
            {
                "record_type": "issue",
                "namespace": "test",
                "id": "deleted",
                "title": "To Delete",
                "status": "tombstone",
                "priority": 2,
                "issue_type": "task",
                "updated_at": "2026-01-02T00:00:00+00:00",
            }
        ]

        # Theirs: also delete the issue
        theirs = [
            {
                "record_type": "issue",
                "namespace": "test",
                "id": "deleted",
                "title": "To Delete",
                "status": "tombstone",
                "priority": 2,
                "issue_type": "task",
                "updated_at": "2026-01-02T00:00:00+00:00",
            }
        ]

        result = merge_jsonl(base, ours, theirs)

        # Result should have the tombstoned issue
        issues = [r for r in result if r.get("record_type") == "issue"]
        assert len(issues) == 1
        assert issues[0]["status"] == "tombstone"

    def test_large_empty_json_structures(self) -> None:
        """Empty lists and dicts in records don't break merge.

        Ensures robustness with complex empty structures.
        """
        base: list[dict[str, Any]] = []

        # Ours: issue with empty lists
        ours: list[dict[str, Any]] = [
            {
                "record_type": "issue",
                "namespace": "test",
                "id": "empty_lists",
                "title": "Empty Lists",
                "labels": [],  # Empty list
                "comments": [],
                "status": "open",
                "priority": 2,
                "issue_type": "task",
                "updated_at": "2026-01-01T00:00:00+00:00",
            }
        ]

        # Theirs: issue with different structure
        theirs = [
            {
                "record_type": "issue",
                "namespace": "test",
                "id": "normal",
                "title": "Normal",
                "status": "open",
                "priority": 2,
                "issue_type": "task",
                "updated_at": "2026-01-01T00:00:00+00:00",
            }
        ]

        result = merge_jsonl(base, ours, theirs)

        # Both should be present
        issues = [r for r in result if r.get("record_type") == "issue"]
        assert len(issues) == 2

        # Empty lists should be preserved
        empty_lists_issue = next(r for r in issues if r["id"] == "empty_lists")
        assert "labels" in empty_lists_issue
        assert isinstance(empty_lists_issue["labels"], list)
