"""JSONL-based storage for inbox proposals with atomic writes."""

from __future__ import annotations

import contextlib
import logging
from datetime import datetime
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, cast

import orjson

from dogcat._diff import tracked_changes
from dogcat._id_resolve import resolve_partial_id
from dogcat._jsonl_io import append_jsonl_payload, atomic_rewrite_jsonl
from dogcat._schema import warn_if_records_from_newer_version
from dogcat.constants import (
    DOGCATS_DIR_NAME,
    INBOX_FILENAME,
    LOCK_FILENAME,
    TRACKED_PROPOSAL_FIELDS,
)
from dogcat.locking import advisory_file_lock
from dogcat.models import (
    Proposal,
    ProposalStatus,
    dict_to_proposal,
    proposal_to_dict,
)

if TYPE_CHECKING:
    from collections.abc import Generator
    from contextlib import AbstractContextManager


class InboxStorage:
    """Manages atomic JSONL storage for inbox proposals."""

    def __init__(
        self,
        dogcats_dir: str = DOGCATS_DIR_NAME,
        create_dir: bool = False,
    ) -> None:
        """Initialize inbox storage.

        Args:
            dogcats_dir: Path to the .dogcats directory.
            create_dir: If True, create the directory if it doesn't exist.
        """
        self.dogcats_dir = Path(dogcats_dir)
        self.path = self.dogcats_dir / INBOX_FILENAME
        self._proposals: dict[str, Proposal] = {}

        if create_dir:
            self.dogcats_dir.mkdir(parents=True, exist_ok=True)
        elif not self.dogcats_dir.exists():
            msg = (
                f"Directory '{self.dogcats_dir}' does not exist. "
                f"Run 'dcat init' first to initialize the repository."
            )
            raise ValueError(msg)

        self._lock_path = self.dogcats_dir / LOCK_FILENAME
        self._needs_compaction = False
        # Bad lines skipped during _load(); see JSONLStorage for the contract.
        self._bad_lines: list[tuple[int, bytes, str]] = []
        # When set, _append() buffers records here instead of writing to disk;
        # the batch() context manager flushes everything in one locked write.
        self._batch_records: list[dict[str, Any]] | None = None

        # Initialize event log for inbox change tracking
        from dogcat.event_log import InboxEventLog

        self._event_log = InboxEventLog(self.dogcats_dir)

        if self.path.exists():
            self._load()

    def _load(self) -> None:
        """Load proposals from JSONL file into memory (last-write-wins).

        Malformed lines (any position) are logged and skipped; see
        :meth:`JSONLStorage._load` for the recovery contract.
        """
        self._proposals.clear()
        self._bad_lines = []

        try:
            with self.path.open("rb") as f:
                lines = f.readlines()
        except OSError as e:
            msg = f"Failed to read inbox file: {e}"
            raise RuntimeError(msg) from e

        while lines and not lines[-1].strip():
            lines.pop()

        parsed_records: list[dict[str, Any]] = []
        for line_idx, raw_line in enumerate(lines):
            line = raw_line.strip()
            if not line:
                continue

            try:
                raw_data = orjson.loads(line)
                if not isinstance(raw_data, dict):
                    msg = f"expected JSON object, got {type(raw_data).__name__}"
                    raise TypeError(msg)  # noqa: TRY301
                data = cast("dict[str, Any]", raw_data)
                parsed_records.append(data)
                if data.get("record_type") != "proposal":
                    continue
                proposal = dict_to_proposal(data)
                self._proposals[proposal.full_id] = proposal
            except (
                orjson.JSONDecodeError,
                ValueError,
                KeyError,
                AttributeError,
                TypeError,
            ) as e:
                logging.getLogger(__name__).warning(
                    "Skipping malformed JSONL line %d in %s: %s",
                    line_idx + 1,
                    self.path,
                    e,
                )
                self._bad_lines.append((line_idx + 1, raw_line, str(e)))
                self._needs_compaction = True

        warn_if_records_from_newer_version(parsed_records, source=str(self.path))

    def _file_lock(self) -> AbstractContextManager[None]:
        """Acquire an advisory file lock for exclusive writes."""
        return advisory_file_lock(self._lock_path)

    @contextlib.contextmanager
    def batch(self) -> Generator[None]:
        """Defer file writes until the context exits.

        Mirror of :meth:`JSONLStorage.batch` for the inbox: every mutation
        that goes through :meth:`_append` (or :meth:`_append_with_event`)
        buffers its serialized payload in memory; on exit the full buffer
        is appended in one locked write. Re-entering an active batch is a
        no-op.
        """
        if self._batch_records is not None:
            yield
            return
        self._batch_records = []
        try:
            yield
        finally:
            pending = self._batch_records
            self._batch_records = None
            if pending:
                self._append(pending)

    def _save(self) -> None:
        """Compact: rewrite the entire file with only current state."""
        with self._file_lock():
            self._save_locked()

    def _save_locked(self) -> None:
        """Body of :meth:`_save` that assumes the file lock is already held.

        Use this from inside an existing ``self._file_lock()`` context to
        avoid re-entering the advisory lock (which would deadlock since
        ``advisory_file_lock`` opens a fresh fd each time).
        """

        def _write(tmp_file: IO[bytes]) -> int:
            count = 0
            for proposal in self._proposals.values():
                tmp_file.write(orjson.dumps(proposal_to_dict(proposal)))
                tmp_file.write(b"\n")
                count += 1
            return count

        atomic_rewrite_jsonl(self.path, self.dogcats_dir, _write)

    def _append(self, records: list[dict[str, Any]]) -> None:
        """Append records to the JSONL file without rewriting it.

        When :meth:`batch` is active the records are buffered and written
        when the batch context exits.
        """
        if self._batch_records is not None:
            self._batch_records.extend(records)
            return

        if self._needs_compaction:
            self._save()
            self._needs_compaction = False

        payload = b"".join(orjson.dumps(r) + b"\n" for r in records)

        with self._file_lock():
            append_jsonl_payload(self.path, payload)

    @staticmethod
    def _proposal_record(proposal: Proposal) -> dict[str, Any]:
        """Serialize a proposal to a dict for appending."""
        return proposal_to_dict(proposal)

    # -- Event emission helpers ------------------------------------------

    def _emit_event(
        self,
        event_type: str,
        proposal: Proposal,
        changes: dict[str, dict[str, Any]],
        by: str | None = None,
    ) -> None:
        """Emit an event to the inbox event log (best-effort)."""
        self._event_log.try_emit(
            event_type,
            proposal.full_id,
            proposal.updated_at.isoformat(),
            proposal.title,
            changes,
            by=by,
        )

    def _build_event_record(
        self,
        event_type: str,
        proposal: Proposal,
        changes: dict[str, dict[str, Any]],
        by: str | None = None,
    ) -> dict[str, Any] | None:
        """Build the event JSONL dict for a proposal mutation.

        Mirrors :meth:`JSONLStorage._build_event_record` so callers can
        bundle proposal+event records into a single locked append.
        """
        return self._event_log.build_record(
            event_type,
            proposal.full_id,
            proposal.updated_at.isoformat(),
            proposal.title,
            changes,
            by=by,
        )

    def _append_with_event(
        self,
        records: list[dict[str, Any]],
        event_record: dict[str, Any] | None,
    ) -> None:
        """Append data records and (optionally) an event record in one call.

        Single-lock equivalent of ``_append`` followed by
        ``_event_log.emit``. Halves lock acquisitions and fsyncs per
        mutation in batched flows like ``dcat inbox close A B C``.
        """
        if event_record is None:
            self._append(records)
            return
        self._append([*records, event_record])

    @staticmethod
    def _tracked_changes(
        old_values: dict[str, Any],
        new_values: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        """Compute tracked field changes between old and new proposal values."""
        return tracked_changes(old_values, new_values, TRACKED_PROPOSAL_FIELDS)

    def create(self, proposal: Proposal) -> Proposal:
        """Create a new proposal.

        Args:
            proposal: The proposal to create.

        Returns:
            The created proposal.

        Raises:
            ValueError: If ID already exists or proposal is invalid.
        """
        from dogcat.models import validate_proposal

        if proposal.full_id in self._proposals:
            msg = f"Proposal with ID {proposal.full_id} already exists"
            raise ValueError(msg)

        validate_proposal(proposal)

        self._proposals[proposal.full_id] = proposal
        changes: dict[str, dict[str, Any]] = {
            "title": {"old": None, "new": proposal.title},
        }
        if proposal.description:
            changes["description"] = {"old": None, "new": proposal.description}
        event_record = self._build_event_record(
            "created", proposal, changes, by=proposal.proposed_by
        )
        self._append_with_event([self._proposal_record(proposal)], event_record)

        return proposal

    def _resolve_or_raise(self, proposal_id: str, *, label: str = "Proposal") -> str:
        """Resolve ``proposal_id`` to a full id or raise ``ValueError``.

        Mirror of :meth:`JSONLStorage._resolve_or_raise` for the inbox so
        the close / delete / get paths share one ``resolve-or-fail``
        sentence instead of repeating it.
        """
        resolved = self.resolve_id(proposal_id)
        if resolved is None:
            msg = f"{label} {proposal_id} not found"
            raise ValueError(msg)
        return resolved

    def create_proposal(
        self,
        *,
        title: str,
        namespace: str = "dc",
        description: str | None = None,
        proposed_by: str | None = None,
        source_repo: str | None = None,
    ) -> Proposal:
        """Generate an ID, build a :class:`Proposal`, and persist it.

        Encapsulates the namespace + IDGenerator + Proposal-construction
        pattern that the propose CLI, the web propose endpoint, and the
        demo all reimplemented separately.
        """
        from dogcat.idgen import IDGenerator

        idgen = IDGenerator(
            existing_ids=self.get_proposal_ids(),
            prefix=f"{namespace}-inbox",
        )
        proposal_id = idgen.generate_proposal_id(
            title,
            namespace=f"{namespace}-inbox",
        )
        proposal = Proposal(
            id=proposal_id,
            title=title,
            namespace=namespace,
            description=description,
            proposed_by=proposed_by,
            source_repo=source_repo,
        )
        return self.create(proposal)

    def resolve_id(self, partial_id: str) -> str | None:
        """Resolve a partial ID to a full proposal ID.

        Supports multiple formats:
        - Full ID: "dogcat-inbox-4kzj" -> "dogcat-inbox-4kzj"
        - Short hash: "4kzj" -> matches if unique

        Args:
            partial_id: Full or partial proposal ID.

        Returns:
            The full proposal ID, or None if not found.

        Raises:
            ValueError: If partial ID matches multiple proposals (ambiguous).
        """
        return resolve_partial_id(partial_id, self._proposals, kind="proposals")

    def get(self, proposal_id: str) -> Proposal | None:
        """Get a proposal by ID.

        Args:
            proposal_id: The ID of the proposal to retrieve (supports partial IDs).

        Returns:
            The proposal, or None if not found.
        """
        resolved_id = self.resolve_id(proposal_id)
        if resolved_id:
            return self._proposals.get(resolved_id)
        return None

    def list(
        self,
        *,
        include_tombstones: bool = False,
        namespace: str | None = None,
    ) -> list[Proposal]:
        """List all proposals.

        Args:
            include_tombstones: If True, include tombstoned proposals.
            namespace: Optional namespace filter.

        Returns:
            List of matching proposals.
        """
        proposals = list(self._proposals.values())

        if not include_tombstones:
            proposals = [p for p in proposals if not p.is_tombstone()]

        if namespace:
            proposals = [p for p in proposals if p.namespace == namespace]

        return proposals

    def close(
        self,
        proposal_id: str,
        *,
        reason: str | None = None,
        closed_by: str | None = None,
        resolved_issue: str | None = None,
    ) -> Proposal:
        """Close a proposal.

        Args:
            proposal_id: The ID of the proposal to close.
            reason: Optional reason for closing.
            closed_by: Optional operator who closed the proposal.
            resolved_issue: Optional ID of issue created from this proposal.

        Returns:
            The closed proposal.

        Raises:
            ValueError: If proposal doesn't exist.
        """
        resolved_id = self._resolve_or_raise(proposal_id)

        proposal = self._proposals[resolved_id]
        old_data = proposal_to_dict(proposal)
        now = datetime.now().astimezone()
        proposal.status = ProposalStatus.CLOSED
        proposal.closed_at = now
        proposal.updated_at = now
        if reason:
            proposal.closed_reason = reason
        if closed_by:
            proposal.closed_by = closed_by
        if resolved_issue:
            proposal.resolved_issue = resolved_issue

        new_data = proposal_to_dict(proposal)
        changes = self._tracked_changes(old_data, new_data)
        event_record = self._build_event_record(
            "closed", proposal, changes, by=closed_by
        )
        self._append_with_event([self._proposal_record(proposal)], event_record)

        return proposal

    def delete(
        self,
        proposal_id: str,
        *,
        deleted_by: str | None = None,
    ) -> Proposal:
        """Soft delete a proposal (create tombstone).

        Args:
            proposal_id: The ID of the proposal to delete.
            deleted_by: Optional operator who deleted the proposal.

        Returns:
            The tombstoned proposal.

        Raises:
            ValueError: If proposal doesn't exist.
        """
        resolved_id = self._resolve_or_raise(proposal_id)

        proposal = self._proposals[resolved_id]
        old_data = proposal_to_dict(proposal)
        proposal.status = ProposalStatus.TOMBSTONE
        now = datetime.now().astimezone()
        proposal.deleted_at = now
        proposal.updated_at = now
        if deleted_by:
            proposal.deleted_by = deleted_by
        new_data = proposal_to_dict(proposal)
        changes = self._tracked_changes(old_data, new_data)
        event_record = self._build_event_record(
            "deleted", proposal, changes, by=deleted_by
        )
        self._append_with_event([self._proposal_record(proposal)], event_record)

        return proposal

    def prune_tombstones(self) -> list[str]:
        """Permanently remove tombstoned proposals from storage.

        Returns:
            List of pruned proposal IDs.
        """
        with self._file_lock():
            if self.path.exists():
                self._load()

            tombstone_ids = [
                pid
                for pid, proposal in self._proposals.items()
                if proposal.status == ProposalStatus.TOMBSTONE
            ]

            for pid in tombstone_ids:
                del self._proposals[pid]

            if tombstone_ids:
                self._save_locked()

        return tombstone_ids

    def rename_namespace(
        self,
        old_namespace: str,
        new_namespace: str,
    ) -> int:
        """Rename all proposals from one namespace to another.

        Args:
            old_namespace: Namespace to rename from.
            new_namespace: Namespace to rename to.

        Returns:
            Number of proposals renamed.
        """
        with self._file_lock():
            if self.path.exists():
                self._load()

            targets = [
                p for p in self._proposals.values() if p.namespace == old_namespace
            ]
            if not targets:
                return 0

            now = datetime.now().astimezone()
            for proposal in targets:
                old_fid = proposal.full_id
                proposal.namespace = new_namespace
                proposal.updated_at = now
                del self._proposals[old_fid]
                self._proposals[proposal.full_id] = proposal

            self._save_locked()
        return len(targets)

    def count(self, *, status: ProposalStatus | None = None) -> int:
        """Count proposals, optionally filtered by status.

        Args:
            status: Optional status filter.

        Returns:
            Number of matching proposals.
        """
        if status is None:
            return len(
                [p for p in self._proposals.values() if not p.is_tombstone()],
            )
        return len(
            [p for p in self._proposals.values() if p.status == status],
        )

    def get_proposal_ids(self) -> set[str]:
        """Get all proposal IDs in storage.

        Returns:
            Set of all proposal IDs.
        """
        return set(self._proposals.keys())

    def get_file_path(self) -> Path:
        """Get the path to the inbox JSONL file.

        Provided for use by archive and other tools that need to read
        the raw file. Prefer using list/get/create/close/delete for
        normal operations.
        """
        return self.path

    def reload(self) -> None:
        """Reload storage from disk."""
        self._load()
