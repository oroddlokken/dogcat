"""Regression tests for loading versioned inbox.jsonl fixtures.

Discovers all inbox fixture files in tests/fixtures/ and verifies that the
current InboxStorage can load them without errors, preserving proposals,
statuses, and all model fields.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

import pytest

from dogcat.inbox import InboxStorage
from dogcat.models import ProposalStatus

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _discover_inbox_fixtures() -> list[Path]:
    """Find all versioned inbox fixture files."""
    fixtures = sorted(FIXTURES_DIR.glob("v*_inbox.jsonl"))
    if not fixtures:
        pytest.skip("No inbox fixture files found in tests/fixtures/")
    return fixtures


def _fixture_ids(fixtures: list[Path]) -> list[str]:
    """Extract version labels for test IDs."""
    return [f.stem.replace("_inbox", "") for f in fixtures]


_fixtures = _discover_inbox_fixtures()


@pytest.fixture(params=_fixtures, ids=_fixture_ids(_fixtures))
def loaded_inbox(request: pytest.FixtureRequest, tmp_path: Path) -> InboxStorage:
    """Load an inbox fixture file into a fresh InboxStorage instance."""
    fixture_path: Path = request.param
    dogcats_dir = tmp_path / ".dogcats"
    dogcats_dir.mkdir()
    dest = dogcats_dir / "inbox.jsonl"
    shutil.copy2(fixture_path, dest)
    return InboxStorage(dogcats_dir=str(dogcats_dir))


class TestInboxFixtureRegression:
    """Verify that all versioned inbox fixtures load correctly with current code."""

    def test_loads_without_errors(self, loaded_inbox: InboxStorage) -> None:
        """Fixture loads without raising exceptions."""
        assert loaded_inbox is not None

    def test_has_proposals(self, loaded_inbox: InboxStorage) -> None:
        """Fixture contains proposals."""
        proposals = loaded_inbox.list(include_tombstones=True)
        assert len(proposals) > 0

    def test_has_open_proposals(self, loaded_inbox: InboxStorage) -> None:
        """Fixture contains open proposals."""
        proposals = loaded_inbox.list()
        open_proposals = [p for p in proposals if p.status == ProposalStatus.OPEN]
        assert len(open_proposals) > 0, "No open proposals found"

    def test_has_closed_proposals(self, loaded_inbox: InboxStorage) -> None:
        """Fixture contains closed proposals."""
        proposals = loaded_inbox.list()
        closed = [p for p in proposals if p.status == ProposalStatus.CLOSED]
        assert len(closed) > 0, "No closed proposals found"

    def test_has_tombstone_proposals(self, loaded_inbox: InboxStorage) -> None:
        """Fixture contains tombstoned proposals."""
        proposals = loaded_inbox.list(include_tombstones=True)
        tombstones = [p for p in proposals if p.status == ProposalStatus.TOMBSTONE]
        assert len(tombstones) > 0, "No tombstone proposals found"

    # --- Proposal field preservation ---

    def test_title_survives(self, loaded_inbox: InboxStorage) -> None:
        """Fixture preserves proposal titles."""
        proposals = loaded_inbox.list(include_tombstones=True)
        for proposal in proposals:
            assert proposal.title, "Proposal missing title"

    def test_namespace_survives(self, loaded_inbox: InboxStorage) -> None:
        """Fixture preserves namespace."""
        proposals = loaded_inbox.list(include_tombstones=True)
        for proposal in proposals:
            assert proposal.namespace, "Proposal missing namespace"

    def test_proposed_by_survives(self, loaded_inbox: InboxStorage) -> None:
        """Fixture preserves proposed_by field."""
        proposals = loaded_inbox.list(include_tombstones=True)
        with_author = [p for p in proposals if p.proposed_by]
        assert len(with_author) > 0, "No proposals with proposed_by found"

    def test_source_repo_survives(self, loaded_inbox: InboxStorage) -> None:
        """Fixture preserves source_repo field."""
        proposals = loaded_inbox.list(include_tombstones=True)
        with_repo = [p for p in proposals if p.source_repo]
        assert len(with_repo) > 0, "No proposals with source_repo found"

    def test_description_survives(self, loaded_inbox: InboxStorage) -> None:
        """Fixture preserves description text."""
        proposals = loaded_inbox.list(include_tombstones=True)
        with_desc = [p for p in proposals if p.description]
        assert len(with_desc) > 0, "No proposals with description found"

    def test_timestamps_are_datetimes(self, loaded_inbox: InboxStorage) -> None:
        """All timestamp fields are parsed as datetime objects."""
        proposals = loaded_inbox.list(include_tombstones=True)
        for proposal in proposals:
            assert isinstance(proposal.created_at, datetime)
            assert isinstance(proposal.updated_at, datetime)

    # --- Closed proposal fields ---

    def test_close_reason_survives(self, loaded_inbox: InboxStorage) -> None:
        """Fixture preserves close_reason on closed proposals."""
        proposals = loaded_inbox.list()
        closed = [p for p in proposals if p.status == ProposalStatus.CLOSED]
        with_reason = [p for p in closed if p.close_reason]
        assert len(with_reason) > 0, "No closed proposals with close_reason found"

    def test_closed_by_survives(self, loaded_inbox: InboxStorage) -> None:
        """Fixture preserves closed_by on closed proposals."""
        proposals = loaded_inbox.list()
        closed = [p for p in proposals if p.status == ProposalStatus.CLOSED]
        with_closer = [p for p in closed if p.closed_by]
        assert len(with_closer) > 0, "No closed proposals with closed_by found"

    def test_closed_at_survives(self, loaded_inbox: InboxStorage) -> None:
        """Fixture preserves closed_at timestamp on closed proposals."""
        proposals = loaded_inbox.list()
        closed = [p for p in proposals if p.status == ProposalStatus.CLOSED]
        with_closed_at = [p for p in closed if p.closed_at]
        assert len(with_closed_at) > 0, "No closed proposals with closed_at found"
        for proposal in with_closed_at:
            assert isinstance(proposal.closed_at, datetime)

    def test_resolved_issue_survives(self, loaded_inbox: InboxStorage) -> None:
        """Fixture preserves resolved_issue link on accepted proposals."""
        proposals = loaded_inbox.list()
        closed = [p for p in proposals if p.status == ProposalStatus.CLOSED]
        with_resolved = [p for p in closed if p.resolved_issue]
        assert len(with_resolved) > 0, "No closed proposals with resolved_issue found"

    # --- Tombstone fields ---

    def test_tombstone_deleted_at_survives(self, loaded_inbox: InboxStorage) -> None:
        """Fixture preserves deleted_at on tombstoned proposals."""
        proposals = loaded_inbox.list(include_tombstones=True)
        tombstones = [p for p in proposals if p.status == ProposalStatus.TOMBSTONE]
        with_deleted_at = [p for p in tombstones if p.deleted_at]
        for proposal in with_deleted_at:
            assert isinstance(proposal.deleted_at, datetime)

    # --- get() by ID ---

    def test_get_by_full_id(self, loaded_inbox: InboxStorage) -> None:
        """Individual proposal retrieval via get() works."""
        proposals = loaded_inbox.list(include_tombstones=True)
        for proposal in proposals[:3]:
            fetched = loaded_inbox.get(proposal.full_id)
            assert fetched is not None, f"get({proposal.full_id}) returned None"
            assert fetched.title == proposal.title

    def test_count(self, loaded_inbox: InboxStorage) -> None:
        """Count method returns correct totals (excludes tombstones by default)."""
        proposals = loaded_inbox.list()
        assert loaded_inbox.count() == len(proposals)
