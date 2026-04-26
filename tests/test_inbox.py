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
        expected_values = {"open", "closed", "tombstone", "unknown"}
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
        assert proposal.closed_reason is None
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
            closed_reason="Accepted",
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
        assert data["closed_reason"] == "Accepted"
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
        assert proposal.closed_reason == "Accepted"
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
        """Test creating a proposal in storage.

        Reload from disk so an in-memory return value can't be confused
        with persistence — a regression that returned the constructed
        proposal without writing it would still satisfy ``result.full_id``.
        (dogcat-4tud)
        """
        from dogcat.inbox import InboxStorage

        s = storage
        assert isinstance(s, InboxStorage)
        proposal = Proposal(id="4kzj", title="Add feature X", namespace="test")
        result = s.create(proposal)
        assert result.full_id == "test-inbox-4kzj"

        reloaded = InboxStorage(dogcats_dir=str(s.dogcats_dir)).get("test-inbox-4kzj")
        assert reloaded is not None
        assert reloaded.title == "Add feature X"

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
        assert result.closed_reason == "Accepted"
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

    def test_close_refuses_tombstoned_proposal(self, storage: object) -> None:
        """Closing a tombstoned proposal raises rather than overwriting it.

        Without the finality guard, ``close`` would replace
        ``deleted_at``/``deleted_by`` with ``closed_at``/``closed_by``
        and resurrect the proposal from ``list()``. Mirrors the
        ``JSONLStorage.close`` tombstone guard. (dogcat-5o1m)
        """
        from dogcat.inbox import InboxStorage

        s = storage
        assert isinstance(s, InboxStorage)
        s.create(Proposal(id="dead", title="Will be tombstoned", namespace="test"))
        s.delete("test-inbox-dead", deleted_by="admin@example.com")

        with pytest.raises(ValueError, match="tombstoned"):
            s.close("test-inbox-dead", reason="late close")

        # State unchanged: still a tombstone, no closed_at written.
        proposal = s.get("test-inbox-dead")
        assert proposal is not None
        assert proposal.status == ProposalStatus.TOMBSTONE
        assert proposal.closed_at is None
        assert proposal.deleted_by == "admin@example.com"

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
        assert result.closed_reason == "Done"

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

    def test_file_lock_open_failure_raises_runtimeerror(self, inbox_dir: str) -> None:
        """OSError opening the inbox lock file is wrapped in RuntimeError."""
        from pathlib import Path

        from dogcat.inbox import InboxStorage

        s = InboxStorage(dogcats_dir=inbox_dir)
        s._lock_path = Path(inbox_dir) / "missing-dir" / "subdir" / ".issues.lock"

        with (
            pytest.raises(RuntimeError, match="Failed to open lock file"),
            s._file_lock(),
        ):
            pass


class TestCreateProposalFactory:
    """Test ``InboxStorage.create_proposal`` factory.

    Regression for dogcat-6a1g: the IDGenerator + Proposal-construction
    pattern was duplicated across the propose CLI, the web propose endpoint,
    and the demo. Centralized here.
    """

    @pytest.fixture
    def inbox(self, tmp_path: object) -> object:
        """Create an empty InboxStorage."""
        from pathlib import Path

        from dogcat.inbox import InboxStorage

        dogcats = Path(str(tmp_path)) / ".dogcats"
        dogcats.mkdir()
        return InboxStorage(dogcats_dir=str(dogcats))

    def test_create_proposal_generates_id(self, inbox: object) -> None:
        """Factory mints an inbox-prefixed id under the given namespace."""
        from dogcat.inbox import InboxStorage

        s = inbox
        assert isinstance(s, InboxStorage)
        proposal = s.create_proposal(title="Idea", namespace="t")
        assert proposal.namespace == "t"
        assert proposal.full_id.startswith("t-inbox-")
        assert proposal.title == "Idea"

    def test_create_proposal_persists(self, inbox: object) -> None:
        """Returned proposal is stored and resolvable by full_id."""
        from dogcat.inbox import InboxStorage

        s = inbox
        assert isinstance(s, InboxStorage)
        proposal = s.create_proposal(title="Saved", namespace="t")
        loaded = s.get(proposal.full_id)
        assert loaded is not None
        assert loaded.title == "Saved"

    def test_create_proposal_passes_through_optional_fields(
        self, inbox: object
    ) -> None:
        """description, proposed_by, source_repo land on the Proposal."""
        from dogcat.inbox import InboxStorage

        s = inbox
        assert isinstance(s, InboxStorage)
        proposal = s.create_proposal(
            title="Full",
            namespace="t",
            description="desc",
            proposed_by="user@example.com",
            source_repo="/some/repo",
        )
        assert proposal.description == "desc"
        assert proposal.proposed_by == "user@example.com"
        assert proposal.source_repo == "/some/repo"


class TestInboxBatchContextManager:
    """Direct coverage for ``inbox.batch()`` write coalescing. (dogcat-29nz)."""

    def test_batch_writes_all_records_in_one_disk_write(
        self, tmp_path: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """N inbox creates inside batch produce one disk write."""
        from pathlib import Path

        from dogcat import _jsonl_io as io_mod
        from dogcat.inbox import InboxStorage

        dogcats = Path(str(tmp_path)) / ".dogcats"
        dogcats.mkdir()
        s = InboxStorage(dogcats_dir=str(dogcats))

        write_count = {"n": 0}
        original_write = io_mod.append_jsonl_payload

        def counting_write(target: Path, payload: bytes) -> None:
            write_count["n"] += 1
            return original_write(target, payload)

        monkeypatch.setattr("dogcat.inbox.append_jsonl_payload", counting_write)

        with s.batch():
            for i in range(4):
                s.create(Proposal(id=f"a{i:03d}", title=f"Batched {i}", namespace="ns"))

        assert write_count["n"] == 1, (
            f"expected exactly one disk write inside batch, got {write_count['n']}"
        )

        # All 4 proposals persisted.
        reloaded = InboxStorage(dogcats_dir=str(dogcats))
        assert len([p for p in reloaded.list() if p.id.startswith("a")]) == 4

    def test_batch_nested_is_noop(
        self, tmp_path: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A nested inbox batch does not flush the outer batch early."""
        from pathlib import Path

        from dogcat import _jsonl_io as io_mod
        from dogcat.inbox import InboxStorage

        dogcats = Path(str(tmp_path)) / ".dogcats"
        dogcats.mkdir()
        s = InboxStorage(dogcats_dir=str(dogcats))

        write_count = {"n": 0}
        original_write = io_mod.append_jsonl_payload

        def counting_write(target: Path, payload: bytes) -> None:
            write_count["n"] += 1
            return original_write(target, payload)

        monkeypatch.setattr("dogcat.inbox.append_jsonl_payload", counting_write)

        with s.batch():
            s.create(Proposal(id="out1", title="O1", namespace="ns"))
            with s.batch():
                s.create(Proposal(id="inn1", title="I1", namespace="ns"))
            assert write_count["n"] == 0
            s.create(Proposal(id="out2", title="O2", namespace="ns"))
        assert write_count["n"] == 1

    def test_batch_flushes_pending_on_exception(self, tmp_path: object) -> None:
        """Exception inside batch flushes buffered records (best-effort save)."""
        from pathlib import Path

        from dogcat.inbox import InboxStorage

        dogcats = Path(str(tmp_path)) / ".dogcats"
        dogcats.mkdir()
        s = InboxStorage(dogcats_dir=str(dogcats))

        class _BoomError(RuntimeError):
            pass

        def _raise_inside_batch() -> None:
            with s.batch():
                s.create(Proposal(id="prep", title="Should persist", namespace="ns"))
                raise _BoomError

        with pytest.raises(_BoomError):
            _raise_inside_batch()

        reloaded = InboxStorage(dogcats_dir=str(dogcats))
        assert reloaded.get("ns-inbox-prep") is not None


class TestInboxInputCapEnforcement:
    """validate_proposal caps are enforced at the inbox storage boundary."""

    def test_oversized_title_rejected_on_create(self, tmp_path: object) -> None:
        """A title above MAX_TITLE_LEN is rejected on InboxStorage.create()."""
        from pathlib import Path

        from dogcat.constants import MAX_TITLE_LEN
        from dogcat.inbox import InboxStorage
        from dogcat.models import Proposal

        dogcats = Path(str(tmp_path)) / ".dogcats"
        dogcats.mkdir()
        s = InboxStorage(dogcats_dir=str(dogcats))
        with pytest.raises(ValueError, match="title exceeds"):
            s.create(
                Proposal(id="aaaa", title="x" * (MAX_TITLE_LEN + 1), namespace="ns"),
            )

    def test_invalid_namespace_rejected_on_create(self, tmp_path: object) -> None:
        """A control-byte namespace is rejected on InboxStorage.create()."""
        from pathlib import Path

        from dogcat.inbox import InboxStorage
        from dogcat.models import Proposal

        dogcats = Path(str(tmp_path)) / ".dogcats"
        dogcats.mkdir()
        s = InboxStorage(dogcats_dir=str(dogcats))
        with pytest.raises(ValueError, match="namespace"):
            s.create(Proposal(id="aaaa", title="OK", namespace="bad ns"))

    def test_title_at_exact_limit_accepted(self, tmp_path: object) -> None:
        """A title at exactly MAX_TITLE_LEN is accepted on InboxStorage.create().

        Pins the inbox bound so a typo loosening ``>`` to ``>=`` is
        caught (parity with the storage / web tests). (dogcat-3d29)
        """
        from pathlib import Path

        from dogcat.constants import MAX_TITLE_LEN
        from dogcat.inbox import InboxStorage
        from dogcat.models import Proposal

        dogcats = Path(str(tmp_path)) / ".dogcats"
        dogcats.mkdir()
        s = InboxStorage(dogcats_dir=str(dogcats))
        title = "x" * MAX_TITLE_LEN
        proposal = s.create(Proposal(id="exct", title=title, namespace="ns"))
        assert len(proposal.title) == MAX_TITLE_LEN

    def test_description_at_exact_limit_accepted(self, tmp_path: object) -> None:
        """A description at exactly MAX_DESC_LEN is accepted. (dogcat-3d29)."""
        from pathlib import Path

        from dogcat.constants import MAX_DESC_LEN
        from dogcat.inbox import InboxStorage
        from dogcat.models import Proposal

        dogcats = Path(str(tmp_path)) / ".dogcats"
        dogcats.mkdir()
        s = InboxStorage(dogcats_dir=str(dogcats))
        body = "x" * MAX_DESC_LEN
        proposal = s.create(
            Proposal(id="excd", title="OK", namespace="ns", description=body),
        )
        assert proposal.description is not None
        assert len(proposal.description) == MAX_DESC_LEN


class TestInboxLoadStrictness:
    """Regression tests for dogcat-3jth: malformed mid-file lines must raise.

    InboxStorage previously skipped any malformed line silently, so a
    corrupt mid-file proposal vanished on next compaction. The strict
    policy mirrors JSONLStorage: a corrupt last line is tolerated (likely
    crash artifact), anything else raises so the user can recover from git.
    """

    def test_malformed_mid_file_line_skipped(self, tmp_path: object) -> None:
        """A malformed mid-file line is skipped and recorded for repair."""
        from pathlib import Path

        from dogcat.inbox import InboxStorage

        dogcats = Path(str(tmp_path)) / ".dogcats"
        dogcats.mkdir()
        inbox_path = dogcats / "inbox.jsonl"
        first = (
            '{"record_type": "proposal", "id": "aaaa", "namespace": "test", '
            '"title": "first", "created_at": "2026-04-25T12:00:00+00:00", '
            '"updated_at": "2026-04-25T12:00:00+00:00", "status": "open"}'
        )
        second = (
            '{"record_type": "proposal", "id": "bbbb", "namespace": "test", '
            '"title": "ok", "created_at": "2026-04-25T12:00:01+00:00", '
            '"updated_at": "2026-04-25T12:00:01+00:00", "status": "open"}'
        )
        inbox_path.write_text(first + "\n" + "{not json\n" + second + "\n")

        s = InboxStorage(dogcats_dir=str(dogcats))
        ids = sorted(p.id for p in s.list())
        assert ids == ["aaaa", "bbbb"]
        assert len(s._bad_lines) == 1
        assert s._needs_compaction is True

    def test_malformed_last_line_tolerated(self, tmp_path: object) -> None:
        """A malformed LAST line is tolerated (crash/disk-full artifact)."""
        from pathlib import Path

        from dogcat.inbox import InboxStorage

        dogcats = Path(str(tmp_path)) / ".dogcats"
        dogcats.mkdir()
        inbox_path = dogcats / "inbox.jsonl"
        good = (
            '{"record_type": "proposal", "id": "aaaa", "namespace": "test", '
            '"title": "ok", "created_at": "2026-04-25T12:00:00+00:00", '
            '"updated_at": "2026-04-25T12:00:00+00:00", "status": "open"}'
        )
        inbox_path.write_text(good + "\n" + "{half-written")

        s = InboxStorage(dogcats_dir=str(dogcats))
        assert len(s.list()) == 1
        assert s._needs_compaction is True

    @pytest.mark.parametrize(
        "non_dict_payload", ["null", "42", "[]", '"string"', "true"]
    )
    def test_non_dict_mid_file_line_skipped(
        self, tmp_path: object, non_dict_payload: str
    ) -> None:
        """A non-dict mid-file line is skipped and tracked for repair."""
        from pathlib import Path

        from dogcat.inbox import InboxStorage

        dogcats = Path(str(tmp_path)) / ".dogcats"
        dogcats.mkdir()
        inbox_path = dogcats / "inbox.jsonl"
        good = (
            '{"record_type": "proposal", "id": "aaaa", "namespace": "test", '
            '"title": "ok", "created_at": "2026-04-25T12:00:00+00:00", '
            '"updated_at": "2026-04-25T12:00:00+00:00", "status": "open"}'
        )
        inbox_path.write_text(good + "\n" + non_dict_payload + "\n" + good + "\n")

        s = InboxStorage(dogcats_dir=str(dogcats))
        assert len(s.list()) == 1
        assert len(s._bad_lines) == 1
        assert s._needs_compaction is True

    @pytest.mark.parametrize(
        "non_dict_payload", ["null", "42", "[]", '"string"', "true"]
    )
    def test_non_dict_last_line_tolerated(
        self, tmp_path: object, non_dict_payload: str
    ) -> None:
        """A non-dict last line is tolerated as crash artifact."""
        from pathlib import Path

        from dogcat.inbox import InboxStorage

        dogcats = Path(str(tmp_path)) / ".dogcats"
        dogcats.mkdir()
        inbox_path = dogcats / "inbox.jsonl"
        good = (
            '{"record_type": "proposal", "id": "aaaa", "namespace": "test", '
            '"title": "ok", "created_at": "2026-04-25T12:00:00+00:00", '
            '"updated_at": "2026-04-25T12:00:00+00:00", "status": "open"}'
        )
        inbox_path.write_text(good + "\n" + non_dict_payload + "\n")

        s = InboxStorage(dogcats_dir=str(dogcats))
        assert len(s.list()) == 1
        assert s._needs_compaction is True
