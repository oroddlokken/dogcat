"""Tests for inbox proposal system (data model and storage)."""

from datetime import datetime, timezone

import pytest

from dogcat.models import (
    Proposal,
    ProposalStatus,
    classify_record,
    dict_to_proposal,
    proposal_to_dict,
)


class TestProposalStatusEnum:
    """Test ProposalStatus enumeration."""

    def test_all_status_values_valid(self) -> None:
        """Test that all ProposalStatus values are valid strings."""
        expected_values = {"open", "closed", "tombstone"}
        actual_values = {s.value for s in ProposalStatus}
        assert actual_values == expected_values

    def test_status_string_enum(self) -> None:
        """Test that ProposalStatus is a string enum."""
        assert isinstance(ProposalStatus.OPEN, str)
        assert ProposalStatus.OPEN == "open"


class TestProposalModel:
    """Test Proposal dataclass."""

    def test_creation_minimal(self) -> None:
        """Test creating a proposal with only required fields."""
        proposal = Proposal(id="4kzj", title="Add feature X")
        assert proposal.id == "4kzj"
        assert proposal.title == "Add feature X"
        assert proposal.status == ProposalStatus.OPEN
        assert proposal.namespace == "dc"

    def test_creation_full(self) -> None:
        """Test creating a proposal with all fields."""
        proposal = Proposal(
            id="4kzj",
            title="Add feature X",
            namespace="dogcat",
            description="Detailed description",
            proposed_by="user@example.com",
            source_repo="/path/to/other/repo",
            status=ProposalStatus.OPEN,
        )
        assert proposal.description == "Detailed description"
        assert proposal.proposed_by == "user@example.com"
        assert proposal.source_repo == "/path/to/other/repo"

    def test_defaults(self) -> None:
        """Test that proposal field defaults are correct."""
        proposal = Proposal(id="4kzj", title="Test")
        assert proposal.description is None
        assert proposal.proposed_by is None
        assert proposal.source_repo is None
        assert proposal.closed_at is None
        assert proposal.closed_by is None
        assert proposal.close_reason is None
        assert proposal.resolved_issue is None

    def test_full_id(self) -> None:
        """Test full_id property with custom namespace."""
        proposal = Proposal(id="4kzj", title="Test", namespace="dogcat")
        assert proposal.full_id == "dogcat-inbox-4kzj"

    def test_full_id_default_namespace(self) -> None:
        """Test full_id property with default namespace."""
        proposal = Proposal(id="4kzj", title="Test")
        assert proposal.full_id == "dc-inbox-4kzj"

    def test_is_closed(self) -> None:
        """Test the is_closed() convenience method."""
        open_p = Proposal(id="1", title="Test")
        assert not open_p.is_closed()

        closed_p = Proposal(id="2", title="Test", status=ProposalStatus.CLOSED)
        assert closed_p.is_closed()

    def test_is_tombstone(self) -> None:
        """Test the is_tombstone() convenience method."""
        normal_p = Proposal(id="1", title="Test")
        assert not normal_p.is_tombstone()

        tombstone_p = Proposal(
            id="2",
            title="Test",
            status=ProposalStatus.TOMBSTONE,
        )
        assert tombstone_p.is_tombstone()

    def test_get_status_emoji(self) -> None:
        """Test the get_status_emoji() method."""
        assert Proposal(id="1", title="T").get_status_emoji() == "\u25cf"
        assert (
            Proposal(
                id="1",
                title="T",
                status=ProposalStatus.CLOSED,
            ).get_status_emoji()
            == "\u2713"
        )

    def test_datetime_auto_generated(self) -> None:
        """Test that created_at is auto-generated."""
        before = datetime.now(timezone.utc)
        proposal = Proposal(id="1", title="Test")
        after = datetime.now(timezone.utc)
        assert before <= proposal.created_at <= after


class TestProposalSerialization:
    """Test proposal serialization and deserialization."""

    def test_proposal_to_dict_minimal(self) -> None:
        """Test converting minimal proposal to dict."""
        proposal = Proposal(id="4kzj", title="Test")
        data = proposal_to_dict(proposal)

        assert data["record_type"] == "proposal"
        assert data["id"] == "4kzj"
        assert data["title"] == "Test"
        assert data["status"] == "open"
        assert "dcat_version" in data

    def test_proposal_to_dict_full(self) -> None:
        """Test converting full proposal to dict."""
        now = datetime.now(timezone.utc)
        proposal = Proposal(
            id="4kzj",
            title="Add feature X",
            namespace="dogcat",
            description="Detailed",
            proposed_by="user@example.com",
            source_repo="/path/to/repo",
            status=ProposalStatus.CLOSED,
            created_at=now,
            closed_at=now,
            closed_by="admin@example.com",
            close_reason="Accepted",
            resolved_issue="dogcat-abc1",
        )
        data = proposal_to_dict(proposal)

        assert data["namespace"] == "dogcat"
        assert data["description"] == "Detailed"
        assert data["proposed_by"] == "user@example.com"
        assert data["source_repo"] == "/path/to/repo"
        assert data["status"] == "closed"
        assert data["closed_at"] == now.isoformat()
        assert data["closed_by"] == "admin@example.com"
        assert data["close_reason"] == "Accepted"
        assert data["resolved_issue"] == "dogcat-abc1"

    def test_proposal_to_dict_none_dates(self) -> None:
        """Test that None dates serialize as None."""
        proposal = Proposal(id="4kzj", title="Test")
        data = proposal_to_dict(proposal)
        assert data["closed_at"] is None

    def test_dict_to_proposal_minimal(self) -> None:
        """Test converting minimal dict to proposal."""
        data = {
            "record_type": "proposal",
            "id": "4kzj",
            "title": "Test",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        proposal = dict_to_proposal(data)

        assert proposal.id == "4kzj"
        assert proposal.title == "Test"
        assert proposal.status == ProposalStatus.OPEN
        assert proposal.namespace == "dc"

    def test_dict_to_proposal_full(self) -> None:
        """Test converting full dict to proposal."""
        now = datetime.now(timezone.utc)
        data = {
            "record_type": "proposal",
            "namespace": "dogcat",
            "id": "4kzj",
            "title": "Add feature X",
            "description": "Detailed",
            "proposed_by": "user@example.com",
            "source_repo": "/path/to/repo",
            "status": "closed",
            "created_at": now.isoformat(),
            "closed_at": now.isoformat(),
            "closed_by": "admin@example.com",
            "close_reason": "Accepted",
            "resolved_issue": "dogcat-abc1",
        }
        proposal = dict_to_proposal(data)

        assert proposal.namespace == "dogcat"
        assert proposal.description == "Detailed"
        assert proposal.proposed_by == "user@example.com"
        assert proposal.source_repo == "/path/to/repo"
        assert proposal.status == ProposalStatus.CLOSED
        assert proposal.closed_by == "admin@example.com"
        assert proposal.close_reason == "Accepted"
        assert proposal.resolved_issue == "dogcat-abc1"

    def test_roundtrip_serialization(self) -> None:
        """Test that proposal survives roundtrip serialization."""
        original = Proposal(
            id="4kzj",
            title="Add feature X",
            namespace="dogcat",
            description="Detailed description",
            proposed_by="user@example.com",
            source_repo="/path/to/repo",
        )

        data = proposal_to_dict(original)
        restored = dict_to_proposal(data)

        assert restored.id == original.id
        assert restored.title == original.title
        assert restored.namespace == original.namespace
        assert restored.description == original.description
        assert restored.proposed_by == original.proposed_by
        assert restored.source_repo == original.source_repo
        assert restored.status == original.status

    def test_classify_record_proposal(self) -> None:
        """Test classify_record with explicit record_type='proposal'."""
        data = {"record_type": "proposal", "id": "4kzj", "title": "Test"}
        assert classify_record(data) == "proposal"


class TestInboxStorage:
    """Test InboxStorage class."""

    @pytest.fixture
    def inbox_dir(self, tmp_path: object) -> str:
        """Create a temporary .dogcats directory."""
        from pathlib import Path

        dogcats = Path(str(tmp_path)) / ".dogcats"
        dogcats.mkdir()
        return str(dogcats)

    @pytest.fixture
    def storage(self, inbox_dir: str) -> object:
        """Create an InboxStorage instance."""
        from dogcat.inbox import InboxStorage

        return InboxStorage(dogcats_dir=inbox_dir)

    def test_create_proposal(self, storage: object) -> None:
        """Test creating a proposal in storage."""
        from dogcat.inbox import InboxStorage

        s = storage
        assert isinstance(s, InboxStorage)
        proposal = Proposal(id="4kzj", title="Add feature X", namespace="test")
        result = s.create(proposal)
        assert result.full_id == "test-inbox-4kzj"

    def test_create_duplicate_raises(self, storage: object) -> None:
        """Test that creating a duplicate ID raises ValueError."""
        from dogcat.inbox import InboxStorage

        s = storage
        assert isinstance(s, InboxStorage)
        proposal = Proposal(id="4kzj", title="Test", namespace="test")
        s.create(proposal)

        duplicate = Proposal(id="4kzj", title="Duplicate", namespace="test")
        with pytest.raises(ValueError, match="already exists"):
            s.create(duplicate)

    def test_create_empty_title_raises(self, storage: object) -> None:
        """Test that creating a proposal with empty title raises ValueError."""
        from dogcat.inbox import InboxStorage

        s = storage
        assert isinstance(s, InboxStorage)
        proposal = Proposal(id="4kzj", title="")
        with pytest.raises(ValueError, match="non-empty title"):
            s.create(proposal)

    def test_get_proposal(self, storage: object) -> None:
        """Test retrieving a proposal by full ID."""
        from dogcat.inbox import InboxStorage

        s = storage
        assert isinstance(s, InboxStorage)
        proposal = Proposal(id="4kzj", title="Test", namespace="test")
        s.create(proposal)

        result = s.get("test-inbox-4kzj")
        assert result is not None
        assert result.title == "Test"

    def test_get_proposal_not_found(self, storage: object) -> None:
        """Test that get returns None for nonexistent proposals."""
        from dogcat.inbox import InboxStorage

        s = storage
        assert isinstance(s, InboxStorage)
        assert s.get("nonexistent") is None

    def test_resolve_id_full(self, storage: object) -> None:
        """Test resolving a full proposal ID."""
        from dogcat.inbox import InboxStorage

        s = storage
        assert isinstance(s, InboxStorage)
        proposal = Proposal(id="4kzj", title="Test", namespace="test")
        s.create(proposal)

        assert s.resolve_id("test-inbox-4kzj") == "test-inbox-4kzj"

    def test_resolve_id_partial(self, storage: object) -> None:
        """Test resolving a partial proposal ID."""
        from dogcat.inbox import InboxStorage

        s = storage
        assert isinstance(s, InboxStorage)
        proposal = Proposal(id="4kzj", title="Test", namespace="test")
        s.create(proposal)

        assert s.resolve_id("4kzj") == "test-inbox-4kzj"

    def test_list_proposals(self, storage: object) -> None:
        """Test listing all proposals."""
        from dogcat.inbox import InboxStorage

        s = storage
        assert isinstance(s, InboxStorage)
        s.create(Proposal(id="aaa1", title="First", namespace="test"))
        s.create(Proposal(id="bbb2", title="Second", namespace="test"))

        proposals = s.list()
        assert len(proposals) == 2

    def test_list_excludes_tombstones(self, storage: object) -> None:
        """Test that list excludes tombstoned proposals by default."""
        from dogcat.inbox import InboxStorage

        s = storage
        assert isinstance(s, InboxStorage)
        s.create(Proposal(id="aaa1", title="Active", namespace="test"))
        s.create(
            Proposal(
                id="bbb2",
                title="Deleted",
                namespace="test",
                status=ProposalStatus.TOMBSTONE,
            ),
        )

        proposals = s.list()
        assert len(proposals) == 1
        assert proposals[0].title == "Active"

    def test_list_includes_tombstones_when_requested(
        self,
        storage: object,
    ) -> None:
        """Test that list includes tombstones when explicitly requested."""
        from dogcat.inbox import InboxStorage

        s = storage
        assert isinstance(s, InboxStorage)
        s.create(Proposal(id="aaa1", title="Active", namespace="test"))
        s.create(
            Proposal(
                id="bbb2",
                title="Deleted",
                namespace="test",
                status=ProposalStatus.TOMBSTONE,
            ),
        )

        proposals = s.list(include_tombstones=True)
        assert len(proposals) == 2

    def test_list_filter_by_namespace(self, storage: object) -> None:
        """Test filtering proposals by namespace."""
        from dogcat.inbox import InboxStorage

        s = storage
        assert isinstance(s, InboxStorage)
        s.create(Proposal(id="aaa1", title="Alpha", namespace="alpha"))
        s.create(Proposal(id="bbb2", title="Beta", namespace="beta"))

        alpha_proposals = s.list(namespace="alpha")
        assert len(alpha_proposals) == 1
        assert alpha_proposals[0].namespace == "alpha"

    def test_close_proposal(self, storage: object) -> None:
        """Test closing a proposal with reason and resolved issue."""
        from dogcat.inbox import InboxStorage

        s = storage
        assert isinstance(s, InboxStorage)
        s.create(Proposal(id="4kzj", title="Test", namespace="test"))

        result = s.close(
            "test-inbox-4kzj",
            reason="Accepted",
            closed_by="admin@example.com",
            resolved_issue="test-abc1",
        )
        assert result.status == ProposalStatus.CLOSED
        assert result.close_reason == "Accepted"
        assert result.closed_by == "admin@example.com"
        assert result.resolved_issue == "test-abc1"
        assert result.closed_at is not None

    def test_close_nonexistent_raises(self, storage: object) -> None:
        """Test that closing a nonexistent proposal raises ValueError."""
        from dogcat.inbox import InboxStorage

        s = storage
        assert isinstance(s, InboxStorage)
        with pytest.raises(ValueError, match="not found"):
            s.close("nonexistent")

    def test_delete_proposal(self, storage: object) -> None:
        """Test soft-deleting a proposal creates a tombstone."""
        from dogcat.inbox import InboxStorage

        s = storage
        assert isinstance(s, InboxStorage)
        s.create(Proposal(id="4kzj", title="Test", namespace="test"))

        result = s.delete("test-inbox-4kzj")
        assert result.status == ProposalStatus.TOMBSTONE

    def test_delete_with_attribution(self, storage: object) -> None:
        """Test soft-deleting a proposal tracks deleted_by."""
        from dogcat.inbox import InboxStorage

        s = storage
        assert isinstance(s, InboxStorage)
        s.create(Proposal(id="4kzj", title="Test", namespace="test"))

        result = s.delete("test-inbox-4kzj", deleted_by="admin@example.com")
        assert result.status == ProposalStatus.TOMBSTONE
        assert result.deleted_by == "admin@example.com"
        assert result.deleted_at is not None

    def test_delete_nonexistent_raises(self, storage: object) -> None:
        """Test that deleting a nonexistent proposal raises ValueError."""
        from dogcat.inbox import InboxStorage

        s = storage
        assert isinstance(s, InboxStorage)
        with pytest.raises(ValueError, match="not found"):
            s.delete("nonexistent")

    def test_prune_tombstones(self, storage: object) -> None:
        """Test that prune_tombstones removes tombstoned proposals."""
        from dogcat.inbox import InboxStorage

        s = storage
        assert isinstance(s, InboxStorage)
        s.create(Proposal(id="aaa1", title="Active", namespace="test"))
        s.create(Proposal(id="bbb2", title="To delete", namespace="test"))
        s.delete("test-inbox-bbb2")

        pruned = s.prune_tombstones()
        assert len(pruned) == 1
        assert "test-inbox-bbb2" in pruned

        # Verify the proposal is gone
        assert s.get("test-inbox-bbb2") is None
        assert s.get("test-inbox-aaa1") is not None

    def test_prune_tombstones_persists(self, inbox_dir: str) -> None:
        """Test that prune_tombstones changes persist across reloads."""
        from dogcat.inbox import InboxStorage

        s = InboxStorage(dogcats_dir=inbox_dir)
        s.create(Proposal(id="aaa1", title="Active", namespace="test"))
        s.create(Proposal(id="bbb2", title="To delete", namespace="test"))
        s.delete("test-inbox-bbb2")
        s.prune_tombstones()

        # Reload from disk
        s2 = InboxStorage(dogcats_dir=inbox_dir)
        assert s2.get("test-inbox-bbb2") is None
        assert s2.get("test-inbox-aaa1") is not None

    def test_prune_no_tombstones(self, storage: object) -> None:
        """Test that prune_tombstones with no tombstones is a no-op."""
        from dogcat.inbox import InboxStorage

        s = storage
        assert isinstance(s, InboxStorage)
        s.create(Proposal(id="aaa1", title="Active", namespace="test"))

        pruned = s.prune_tombstones()
        assert pruned == []

    def test_count(self, storage: object) -> None:
        """Test counting proposals with optional status filter."""
        from dogcat.inbox import InboxStorage

        s = storage
        assert isinstance(s, InboxStorage)
        s.create(Proposal(id="aaa1", title="Open", namespace="test"))
        s.create(
            Proposal(
                id="bbb2",
                title="Closed",
                namespace="test",
                status=ProposalStatus.CLOSED,
            ),
        )

        assert s.count() == 2  # excludes tombstones only
        assert s.count(status=ProposalStatus.OPEN) == 1
        assert s.count(status=ProposalStatus.CLOSED) == 1

    def test_get_proposal_ids(self, storage: object) -> None:
        """Test getting all proposal IDs."""
        from dogcat.inbox import InboxStorage

        s = storage
        assert isinstance(s, InboxStorage)
        s.create(Proposal(id="aaa1", title="First", namespace="test"))
        s.create(Proposal(id="bbb2", title="Second", namespace="test"))

        ids = s.get_proposal_ids()
        assert ids == {"test-inbox-aaa1", "test-inbox-bbb2"}

    def test_persistence_across_reload(self, inbox_dir: str) -> None:
        """Test that proposals persist across storage instances."""
        from dogcat.inbox import InboxStorage

        s1 = InboxStorage(dogcats_dir=inbox_dir)
        s1.create(Proposal(id="4kzj", title="Persistent", namespace="test"))

        s2 = InboxStorage(dogcats_dir=inbox_dir)
        result = s2.get("test-inbox-4kzj")
        assert result is not None
        assert result.title == "Persistent"

    def test_last_write_wins(self, inbox_dir: str) -> None:
        """Test that the last write for an ID wins on reload."""
        from dogcat.inbox import InboxStorage

        s = InboxStorage(dogcats_dir=inbox_dir)
        s.create(Proposal(id="4kzj", title="Original", namespace="test"))
        s.close("test-inbox-4kzj", reason="Done")

        s2 = InboxStorage(dogcats_dir=inbox_dir)
        result = s2.get("test-inbox-4kzj")
        assert result is not None
        assert result.status == ProposalStatus.CLOSED
        assert result.close_reason == "Done"

    def test_reload(self, inbox_dir: str) -> None:
        """Test reloading storage picks up external changes."""
        from dogcat.inbox import InboxStorage

        s = InboxStorage(dogcats_dir=inbox_dir)
        s.create(Proposal(id="4kzj", title="Test", namespace="test"))

        # Simulate external modification
        s2 = InboxStorage(dogcats_dir=inbox_dir)
        s2.create(Proposal(id="bbb2", title="External", namespace="test"))

        # s still only sees one
        assert len(s.list()) == 1

        # After reload, sees both
        s.reload()
        assert len(s.list()) == 2

    def test_nonexistent_dir_raises(self, tmp_path: object) -> None:
        """Test that missing directory raises ValueError."""
        from pathlib import Path

        from dogcat.inbox import InboxStorage

        with pytest.raises(ValueError, match="does not exist"):
            InboxStorage(dogcats_dir=str(Path(str(tmp_path)) / "nope"))

    def test_create_dir_option(self, tmp_path: object) -> None:
        """Test that create_dir=True creates the directory."""
        from pathlib import Path

        from dogcat.inbox import InboxStorage

        new_dir = str(Path(str(tmp_path)) / "new_dogcats")
        s = InboxStorage(dogcats_dir=new_dir, create_dir=True)
        assert Path(new_dir).is_dir()

        s.create(Proposal(id="4kzj", title="Test"))
        assert s.get("dc-inbox-4kzj") is not None
