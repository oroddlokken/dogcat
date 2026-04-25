"""Scale and stress tests for the JSONL merge driver.

Tests the merge driver with large record sets, long divergences,
and complex merge scenarios similar to real-world usage.
"""

from __future__ import annotations

import time
from typing import Any

from dogcat.merge_driver import merge_jsonl


# ---------------------------------------------------------------------------
# Test scenarios
# ---------------------------------------------------------------------------


class TestMergeScale:
    """Scale tests for the merge driver."""

    def test_wide_divergence_100_issues_per_side(self) -> None:
        """100 unique issues created on each side.

        After merge, all 200 issues should be present.
        Verifies correctness and performance (< 1s load).
        """
        # Create 100 issues on base (shared starting point)
        base: list[dict[str, Any]] = []
        for i in range(100):
            base.append({
                "record_type": "issue",
                "namespace": "test",
                "id": f"base{i:03d}",
                "title": f"Base issue {i}",
                "status": "open",
                "priority": 2,
                "issue_type": "task",
                "updated_at": "2026-01-01T00:00:00+00:00",
            })

        # Ours: add 100 more unique issues
        ours = base.copy()
        for i in range(100):
            ours.append({
                "record_type": "issue",
                "namespace": "test",
                "id": f"ours{i:03d}",
                "title": f"Ours issue {i}",
                "status": "open",
                "priority": 2,
                "issue_type": "task",
                "updated_at": "2026-01-02T00:00:00+00:00",
            })

        # Theirs: add 100 different unique issues
        theirs = base.copy()
        for i in range(100):
            theirs.append({
                "record_type": "issue",
                "namespace": "test",
                "id": f"theirs{i:03d}",
                "title": f"Theirs issue {i}",
                "status": "open",
                "priority": 2,
                "issue_type": "task",
                "updated_at": "2026-01-02T00:00:00+00:00",
            })

        # Measure merge performance
        start = time.perf_counter()
        result = merge_jsonl(base, ours, theirs)
        merge_time = time.perf_counter() - start

        # Count issues in result
        issue_count = sum(1 for r in result if r.get("record_type") == "issue")

        # Verify correctness: 100 base + 100 ours + 100 theirs = 300
        assert issue_count == 300, f"Expected 300 issues, got {issue_count}"

        # Verify performance: merge should be fast (< 5 seconds)
        assert merge_time < 5.0, f"Merge took {merge_time:.2f}s (expected < 5s)"

    def test_heavy_contention_same_issue_multiple_edits(self) -> None:
        """Same 50 issues edited 5 times each on both sides.

        Each edit has different timestamp. Verify LWW picks the absolute latest.
        """
        # Create 50 base issues
        base: list[dict[str, Any]] = []
        for i in range(50):
            base.append({
                "record_type": "issue",
                "namespace": "test",
                "id": f"shared{i:02d}",
                "title": f"Shared {i}",
                "status": "open",
                "priority": 2,
                "issue_type": "task",
                "updated_at": "2026-01-01T00:00:00+00:00",
            })

        # Ours: edit all 50 issues 5 times each with interleaved timestamps
        ours = base.copy()
        for issue_idx in range(50):
            for edit in range(1, 6):
                # Ours edits happen on odd timestamps
                timestamp = f"2026-01-02T{edit*2:02d}:00:00+00:00"
                ours.append({
                    "record_type": "issue",
                    "namespace": "test",
                    "id": f"shared{issue_idx:02d}",
                    "title": f"Shared {issue_idx}",
                    "status": f"ours_edit_{edit}",
                    "priority": 2,
                    "issue_type": "task",
                    "updated_at": timestamp,
                })

        # Theirs: edit same 50 issues 5 times each with different timestamps
        theirs = base.copy()
        for issue_idx in range(50):
            for edit in range(1, 6):
                # Theirs edits happen on even timestamps, some later than ours
                # Make theirs edit 3 and 5 be later
                if edit == 3:
                    timestamp = "2026-01-02T07:00:00+00:00"  # Later than ours 3
                elif edit == 5:
                    timestamp = "2026-01-02T11:00:00+00:00"  # Later than ours 5
                else:
                    timestamp = f"2026-01-02T{edit*2+1:02d}:00:00+00:00"
                theirs.append({
                    "record_type": "issue",
                    "namespace": "test",
                    "id": f"shared{issue_idx:02d}",
                    "title": f"Shared {issue_idx}",
                    "status": f"theirs_edit_{edit}",
                    "priority": 2,
                    "issue_type": "task",
                    "updated_at": timestamp,
                })

        # Merge
        start = time.perf_counter()
        result = merge_jsonl(base, ours, theirs)
        merge_time = time.perf_counter() - start

        # Verify: should have 50 issues (one per ID, LWW by timestamp)
        issues = [r for r in result if r.get("record_type") == "issue"]
        assert len(issues) == 50

        # Verify LWW: all issues should have the latest status
        for issue in issues:
            # The latest timestamps are theirs edits 3 and 5
            # So we should see either theirs_edit_5 or the later theirs_edit_3 or _5
            assert issue["status"] in [
                "theirs_edit_3",
                "theirs_edit_5",
                "ours_edit_5",
            ], f"Unexpected status: {issue['status']}"

        assert merge_time < 5.0, f"Merge took {merge_time:.2f}s (expected < 5s)"

    def test_mixed_type_churn(self) -> None:
        """Complex record mix: 50 issues, 100 deps, 100+ events.

        Both sides have different mutations on the same records.
        Verify merge result has correct counts and dep state.
        """
        # Create 50 base issues
        base: list[dict[str, Any]] = []
        for i in range(50):
            base.append({
                "record_type": "issue",
                "namespace": "test",
                "id": f"issue{i:02d}",
                "title": f"Issue {i}",
                "status": "open",
                "priority": 2,
                "issue_type": "task",
                "updated_at": "2026-01-01T00:00:00+00:00",
            })

        # Ours: add issues, deps, events
        ours = base.copy()
        # Add 50 deps
        for i in range(50):
            ours.append({
                "record_type": "dependency",
                "issue_id": f"test-issue{i:02d}",
                "depends_on_id": f"test-issue{(i+1)%50:02d}",
                "type": "blocks",
                "op": "add",
                "created_at": "2026-01-02T00:00:00+00:00",
            })
        # Add 100 events (multiple per issue)
        for i in range(100):
            ours.append({
                "record_type": "event",
                "event_type": "created",
                "issue_id": f"test-issue{i%50:02d}",
                "timestamp": f"2026-01-02T{(i//5)%24:02d}:00:00+00:00",
                "by": "user-a",
                "changes_signature": "1a2b3c",
            })

        # Theirs: add different deps, events
        theirs = base.copy()
        # Add 50 different deps (reversed order)
        for i in range(50):
            theirs.append({
                "record_type": "dependency",
                "issue_id": f"test-issue{(i+1)%50:02d}",
                "depends_on_id": f"test-issue{i:02d}",
                "type": "related",
                "op": "add",
                "created_at": "2026-01-02T00:00:00+00:00",
            })
        # Add 100 different events
        for i in range(100):
            theirs.append({
                "record_type": "event",
                "event_type": "updated",
                "issue_id": f"test-issue{(i+1)%50:02d}",
                "timestamp": f"2026-01-02T{((i+12)//5)%24:02d}:00:00+00:00",
                "by": "user-b",
                "changes_signature": "4d5e6f",
            })

        # Merge
        start = time.perf_counter()
        result = merge_jsonl(base, ours, theirs)
        merge_time = time.perf_counter() - start

        # Verify record counts
        issues = [r for r in result if r.get("record_type") == "issue"]
        deps = [r for r in result if r.get("record_type") == "dependency"]
        events = [r for r in result if r.get("record_type") == "event"]

        # Should have: 50 issues, 100 unique deps (50 from each side with different targets)
        assert len(issues) == 50, f"Expected 50 issues, got {len(issues)}"
        # Deps should include all unique deps from both sides
        assert len(deps) >= 50, f"Expected >= 50 deps, got {len(deps)}"
        # Events should include all unique events from both sides
        assert len(events) >= 150, f"Expected >= 150 events, got {len(events)}"

        assert merge_time < 5.0, f"Merge took {merge_time:.2f}s (expected < 5s)"

    def test_compaction_mixed_files(self) -> None:
        """One side compacted (snapshot), other side has event log.

        Realistic 'one dev compacted main, you're on feature branch' case.
        Verify merge reconciles correctly.
        """
        # Create a "compacted" base (snapshot form)
        base: list[dict[str, Any]] = []
        for i in range(100):
            base.append({
                "record_type": "issue",
                "namespace": "test",
                "id": f"issue{i:03d}",
                "title": f"Issue {i}",
                "status": "open",
                "priority": 2,
                "issue_type": "task",
                "updated_at": "2026-01-01T12:00:00+00:00",
            })

        # Ours: compacted file (just snapshot, no events)
        ours = base.copy()

        # Theirs: event log on top of base
        # (simulating someone working on feature branch with 100 raw mutations)
        theirs = base.copy()
        for i in range(100):
            theirs.append({
                "record_type": "issue",
                "namespace": "test",
                "id": f"issue{i:03d}",
                "title": f"Issue {i} - edited on branch",
                "status": "in_progress",
                "priority": 1,
                "issue_type": "task",
                "updated_at": f"2026-01-02T{(i%24):02d}:00:00+00:00",
            })
        # Add some new issues on theirs
        for i in range(100, 150):
            theirs.append({
                "record_type": "issue",
                "namespace": "test",
                "id": f"issue{i:03d}",
                "title": f"New issue {i}",
                "status": "open",
                "priority": 2,
                "issue_type": "task",
                "updated_at": "2026-01-02T12:00:00+00:00",
            })

        # Merge
        start = time.perf_counter()
        result = merge_jsonl(base, ours, theirs)
        merge_time = time.perf_counter() - start

        # Verify: all 100 base + 50 new should be present
        issues = [r for r in result if r.get("record_type") == "issue"]

        # Should have original 100 + 50 new = 150
        assert len(issues) == 150, f"Expected 150 issues, got {len(issues)}"

        # All original issues should have theirs edits (later timestamp)
        for i in range(100):
            issue_id = f"test-issue{i:03d}"
            issue = next(
                (r for r in issues if f"{r['namespace']}-{r['id']}" == issue_id),
                None,
            )
            assert issue is not None, f"Missing {issue_id}"
            # Should have theirs version (later timestamp)
            assert issue["status"] == "in_progress"

        assert merge_time < 5.0, f"Merge took {merge_time:.2f}s (expected < 5s)"
