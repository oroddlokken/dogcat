"""Property-based tests for the JSONL merge driver invariants.

Uses hypothesis to generate random sequences of mutations and verify the
invariants documented in src/dogcat/merge_driver.py module docstring.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from hypothesis import given
from hypothesis import strategies as st

from dogcat.merge_driver import merge_jsonl

# ============================================================================
# Strategies for generating record types
# ============================================================================


def _issue_record(**kwargs: Any) -> dict[str, Any]:
    """Build a minimal issue record dict."""
    defaults: dict[str, Any] = {
        "record_type": "issue",
        "namespace": "test",
        "id": "x",
        "title": "Test",
        "status": "open",
        "priority": 2,
        "issue_type": "task",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    defaults.update(kwargs)
    return defaults


def _event_record(**kwargs: Any) -> dict[str, Any]:
    """Build a minimal event record dict."""
    defaults: dict[str, Any] = {
        "record_type": "event",
        "event_type": "created",
        "issue_id": "test-x",
        "timestamp": "2026-01-01T00:00:00+00:00",
    }
    defaults.update(kwargs)
    return defaults


def _proposal_record(**kwargs: Any) -> dict[str, Any]:
    """Build a minimal proposal record dict."""
    defaults: dict[str, Any] = {
        "record_type": "proposal",
        "namespace": "test",
        "id": "p1",
        "title": "Proposal",
        "status": "open",
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    defaults.update(kwargs)
    return defaults


@st.composite
def timestamp_strategy(draw: Any) -> str:
    """Generate ISO 8601 timestamps with varying dates."""
    days_offset = draw(st.integers(min_value=0, max_value=365))
    dt = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=days_offset)
    return dt.isoformat()


@st.composite
def unique_issue_list_strategy(draw: Any) -> list[dict[str, Any]]:
    """Generate lists of issues with unique IDs."""
    num_issues = draw(st.integers(min_value=0, max_value=5))
    issues: list[dict[str, Any]] = []
    for i in range(num_issues):
        issue_id = f"issue{i}"
        updated_at = draw(timestamp_strategy())
        issues.append(_issue_record(id=issue_id, updated_at=updated_at))
    return issues


@st.composite
def unique_proposal_list_strategy(draw: Any) -> list[dict[str, Any]]:
    """Generate lists of proposals with unique IDs."""
    num_proposals = draw(st.integers(min_value=0, max_value=5))
    proposals: list[dict[str, Any]] = []
    for i in range(num_proposals):
        proposal_id = f"prop{i}"
        status = draw(st.sampled_from(["open", "closed", "tombstone"]))
        created_at = draw(timestamp_strategy())
        proposals.append(
            _proposal_record(id=proposal_id, status=status, created_at=created_at)
        )
    return proposals


@st.composite
def unique_event_list_strategy(draw: Any) -> list[dict[str, Any]]:
    """Generate lists of events with unique timestamps."""
    num_events = draw(st.integers(min_value=0, max_value=5))
    events: list[dict[str, Any]] = []
    base_dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(num_events):
        timestamp = (base_dt + timedelta(seconds=i)).isoformat()
        issue_id = f"test-{i}"
        events.append(_event_record(issue_id=issue_id, timestamp=timestamp))
    return events


# ============================================================================
# Helper functions
# ============================================================================


def _records_equal(rec1: dict[str, Any], rec2: dict[str, Any]) -> bool:
    """Check if two records are semantically equal."""
    return rec1 == rec2


def _record_set_equal(set1: list[dict[str, Any]], set2: list[dict[str, Any]]) -> bool:
    """Check if two record sets are equal (order-independent)."""
    if len(set1) != len(set2):
        return False

    # Sort both by some stable criteria for comparison
    def record_key(r: dict[str, Any]) -> tuple[str, ...]:
        rtype = r.get("record_type", "")
        if rtype == "issue" or rtype == "proposal":
            return (rtype, r.get("namespace", ""), r.get("id", ""))
        if rtype == "dependency":
            return (rtype, r.get("issue_id", ""), r.get("depends_on_id", ""))
        if rtype == "event":
            return (rtype, r.get("issue_id", ""), r.get("timestamp", ""))
        return (rtype,)

    sorted1 = sorted(set1, key=record_key)
    sorted2 = sorted(set2, key=record_key)

    return all(_records_equal(r1, r2) for r1, r2 in zip(sorted1, sorted2, strict=False))


def _get_issue_by_id(
    records: list[dict[str, Any]], namespace: str, issue_id: str
) -> dict[str, Any] | None:
    """Find an issue record by namespace and ID."""
    for r in records:
        if (
            r.get("record_type") == "issue"
            and r.get("namespace") == namespace
            and r.get("id") == issue_id
        ):
            return r
    return None


def _get_proposal_by_id(
    records: list[dict[str, Any]], namespace: str, proposal_id: str
) -> dict[str, Any] | None:
    """Find a proposal record by namespace and ID."""
    for r in records:
        if (
            r.get("record_type") == "proposal"
            and r.get("namespace") == namespace
            and r.get("id") == proposal_id
        ):
            return r
    return None


# ============================================================================
# Property tests for invariants
# ============================================================================


class TestMergeIdempotency:
    """Invariant: merge(R, R, R) == R (idempotency)."""

    @given(unique_issue_list_strategy())
    def test_issue_idempotency(self, issues: list[dict[str, Any]]) -> None:
        """Merging a record set with itself returns the same set."""
        result = merge_jsonl(issues, issues, issues)
        result_issues = [r for r in result if r.get("record_type") == "issue"]
        assert _record_set_equal(issues, result_issues)

    @given(unique_proposal_list_strategy())
    def test_proposal_idempotency(self, proposals: list[dict[str, Any]]) -> None:
        """Merging proposal records with themselves returns the same set."""
        result = merge_jsonl(proposals, proposals, proposals)
        result_proposals = [r for r in result if r.get("record_type") == "proposal"]
        assert _record_set_equal(proposals, result_proposals)

    @given(unique_event_list_strategy())
    def test_event_idempotency(self, events: list[dict[str, Any]]) -> None:
        """Merging event records with themselves returns the same set."""
        result = merge_jsonl(events, events, events)
        result_events = [r for r in result if r.get("record_type") == "event"]
        assert _record_set_equal(events, result_events)


class TestMergeConvergence:
    """Invariant: convergence/eventual consistency regardless of merge order."""

    @given(unique_issue_list_strategy(), unique_issue_list_strategy())
    def test_issue_convergence(
        self, changes_a: list[dict[str, Any]], changes_b: list[dict[str, Any]]
    ) -> None:
        """Merging in either order produces semantically equal results."""
        base: list[dict[str, Any]] = []

        # Merge ours=changes_a, theirs=changes_b
        result1 = merge_jsonl(base, changes_a, changes_b)

        # Merge ours=changes_b, theirs=changes_a
        result2 = merge_jsonl(base, changes_b, changes_a)

        # Results should be semantically equal (same records)
        result1_issues = [r for r in result1 if r.get("record_type") == "issue"]
        result2_issues = [r for r in result2 if r.get("record_type") == "issue"]
        assert _record_set_equal(result1_issues, result2_issues)


class TestMergeMonotonicityUpdatedAt:
    """Invariant: monotonicity in updated_at for issues."""

    def test_updated_at_monotonic_wins_later(self) -> None:
        """When both sides edit an issue, later timestamp wins."""
        issue_id = "test-issue"

        # Base has early timestamp
        base = [
            _issue_record(
                id=issue_id, title="original", updated_at="2026-01-01T00:00:00+00:00"
            )
        ]

        # Ours has middle timestamp
        ours = [
            _issue_record(
                id=issue_id, title="ours edit", updated_at="2026-01-02T00:00:00+00:00"
            )
        ]

        # Theirs has latest timestamp
        theirs = [
            _issue_record(
                id=issue_id, title="theirs edit", updated_at="2026-01-03T00:00:00+00:00"
            )
        ]

        result = merge_jsonl(base, ours, theirs)
        result_issue = _get_issue_by_id(result, "test", issue_id)

        assert result_issue is not None
        assert result_issue["updated_at"] == "2026-01-03T00:00:00+00:00"
        assert result_issue["title"] == "theirs edit"

    def test_updated_at_monotonic_ours_wins_later(self) -> None:
        """When both sides edit, ours wins if it has the later timestamp."""
        issue_id = "test-issue"

        base = [
            _issue_record(
                id=issue_id, title="original", updated_at="2026-01-01T00:00:00+00:00"
            )
        ]

        # Ours has latest timestamp
        ours = [
            _issue_record(
                id=issue_id, title="ours edit", updated_at="2026-01-03T00:00:00+00:00"
            )
        ]

        # Theirs has middle timestamp
        theirs = [
            _issue_record(
                id=issue_id, title="theirs edit", updated_at="2026-01-02T00:00:00+00:00"
            )
        ]

        result = merge_jsonl(base, ours, theirs)
        result_issue = _get_issue_by_id(result, "test", issue_id)

        assert result_issue is not None
        assert result_issue["updated_at"] == "2026-01-03T00:00:00+00:00"
        assert result_issue["title"] == "ours edit"


class TestProposalStatusFinality:
    """Invariant: proposal status monotonicity (open < closed < tombstone)."""

    @given(
        st.sampled_from(
            [
                ("open", "open", "open"),
                ("open", "open", "closed"),
                ("open", "open", "tombstone"),
                ("open", "closed", "open"),
                ("open", "closed", "closed"),
                ("open", "closed", "tombstone"),
                ("open", "tombstone", "open"),
                ("open", "tombstone", "closed"),
                ("open", "tombstone", "tombstone"),
                ("closed", "closed", "closed"),
                ("closed", "closed", "tombstone"),
                ("closed", "tombstone", "closed"),
                ("closed", "tombstone", "tombstone"),
                ("tombstone", "tombstone", "tombstone"),
            ]
        )
    )
    def test_proposal_finality_monotonic(self, statuses: tuple[str, str, str]) -> None:
        """More final status on either side is preserved."""
        base_status, ours_status, theirs_status = statuses

        proposal_id = "test-proposal"
        base = [_proposal_record(id=proposal_id, status=base_status)]
        ours = [_proposal_record(id=proposal_id, status=ours_status)]
        theirs = [_proposal_record(id=proposal_id, status=theirs_status)]

        result = merge_jsonl(base, ours, theirs)
        result_proposal = _get_proposal_by_id(result, "test", proposal_id)

        # The result should be the most final status
        status_rank = {"open": 0, "closed": 1, "tombstone": 2}
        max_rank = max(status_rank[ours_status], status_rank[theirs_status])
        expected_status = next(s for s, r in status_rank.items() if r == max_rank)

        assert result_proposal is not None
        assert result_proposal["status"] == expected_status


class TestDeletionWinsOverSilence:
    """Invariant: delete on one side wins over no-op on other."""

    def test_delete_issue_wins_over_no_op(self) -> None:
        """A deleted issue is not resurrected if other side doesn't observe it."""
        issue_id = "test-issue"

        base = [_issue_record(id=issue_id, title="existing")]
        # Mark as tombstone on ours (deleted)
        ours = [_issue_record(id=issue_id, title="existing", status="tombstone")]
        # Not mentioned on theirs (silent)
        theirs: list[dict[str, Any]] = []

        result = merge_jsonl(base, ours, theirs)
        result_issue = _get_issue_by_id(result, "test", issue_id)

        # Should be deleted (tombstone)
        assert result_issue is not None
        assert result_issue["status"] == "tombstone"


class TestReAddWinsOverDelete:
    """Invariant: re-add by one side wins over a stale delete."""

    def test_readd_issue_wins_over_stale_delete(self) -> None:
        """A re-add after a delete wins because it's not in base."""
        issue_id = "test-issue"

        # Base doesn't have the issue
        base: list[dict[str, Any]] = []

        ours = [_issue_record(id=issue_id, title="new issue")]

        theirs: list[dict[str, Any]] = []

        result = merge_jsonl(base, ours, theirs)
        result_issue = _get_issue_by_id(result, "test", issue_id)

        # The added issue should be preserved
        assert result_issue is not None
        assert result_issue["title"] == "new issue"


class TestNoDataLossForAdditive:
    """Invariant: no data loss for additive edits on exactly one side."""

    @given(unique_issue_list_strategy())
    def test_additive_issue_preserved(self, issues: list[dict[str, Any]]) -> None:
        """An add on one side not in base survives the merge."""
        base: list[dict[str, Any]] = []
        ours = issues
        theirs: list[dict[str, Any]] = []

        result = merge_jsonl(base, ours, theirs)
        result_issues = [r for r in result if r.get("record_type") == "issue"]

        # All added issues should be preserved
        assert _record_set_equal(ours, result_issues)

    @given(unique_proposal_list_strategy())
    def test_additive_proposal_preserved(self, proposals: list[dict[str, Any]]) -> None:
        """An add on one side not in base survives the merge."""
        base: list[dict[str, Any]] = []
        ours = proposals
        theirs: list[dict[str, Any]] = []

        result = merge_jsonl(base, ours, theirs)
        result_proposals = [r for r in result if r.get("record_type") == "proposal"]

        # All added proposals should be preserved
        assert _record_set_equal(ours, result_proposals)
