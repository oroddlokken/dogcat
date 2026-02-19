"""JSONL-based storage for inbox proposals with atomic writes."""

from __future__ import annotations

import fcntl
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

import logging

import orjson

from dogcat.constants import TRACKED_PROPOSAL_FIELDS
from dogcat.models import (
    Proposal,
    ProposalStatus,
    dict_to_proposal,
    proposal_to_dict,
)

INBOX_FILENAME = "inbox.jsonl"


class InboxStorage:
    """Manages atomic JSONL storage for inbox proposals."""

    def __init__(
        self,
        dogcats_dir: str = ".dogcats",
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

        self._lock_path = self.dogcats_dir / ".issues.lock"
        self._needs_compaction = False

        # Initialize event log for inbox change tracking
        from dogcat.event_log import InboxEventLog

        self._event_log = InboxEventLog(self.dogcats_dir)

        if self.path.exists():
            self._load()

    def _load(self) -> None:
        """Load proposals from JSONL file into memory (last-write-wins)."""
        self._proposals.clear()

        try:
            with self.path.open("rb") as f:
                lines = f.readlines()
        except OSError as e:
            msg = f"Failed to read inbox file: {e}"
            raise RuntimeError(msg) from e

        while lines and not lines[-1].strip():
            lines.pop()

        for line_idx, raw_line in enumerate(lines):
            line = raw_line.strip()
            if not line:
                continue

            try:
                data = orjson.loads(line)
                if data.get("record_type") != "proposal":
                    continue
                proposal = dict_to_proposal(data)
                self._proposals[proposal.full_id] = proposal
            except (orjson.JSONDecodeError, ValueError, KeyError) as e:
                logging.getLogger(__name__).warning(
                    "Skipping malformed line %d in %s: %s",
                    line_idx + 1,
                    self.path,
                    e,
                )
                self._needs_compaction = True

    @contextmanager
    def _file_lock(self) -> Iterator[None]:
        """Acquire an advisory file lock for exclusive writes."""
        lock_fd = self._lock_path.open("w")
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()

    def _save(self) -> None:
        """Compact: rewrite the entire file with only current state."""
        with self._file_lock():
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=self.dogcats_dir,
                delete=False,
                suffix=".jsonl",
            ) as tmp_file:
                tmp_path = Path(tmp_file.name)
                try:
                    for proposal in self._proposals.values():
                        data = proposal_to_dict(proposal)
                        tmp_file.write(orjson.dumps(data))
                        tmp_file.write(b"\n")
                    tmp_file.flush()
                    os.fsync(tmp_file.fileno())
                except Exception as e:
                    tmp_path.unlink(missing_ok=True)
                    msg = f"Failed to write to temporary file: {e}"
                    raise RuntimeError(msg) from e

            try:
                tmp_path.replace(self.path)
            except OSError as e:
                tmp_path.unlink(missing_ok=True)
                msg = f"Failed to write inbox file: {e}"
                raise RuntimeError(msg) from e

    def _append(self, records: list[dict[str, Any]]) -> None:
        """Append records to the JSONL file without rewriting it."""
        if self._needs_compaction:
            self._save()
            self._needs_compaction = False

        payload = b"".join(orjson.dumps(r) + b"\n" for r in records)

        with self._file_lock():
            try:
                if self.path.exists() and self.path.stat().st_size > 0:
                    with self.path.open("rb") as check:
                        check.seek(-1, 2)
                        if check.read(1) != b"\n":
                            payload = b"\n" + payload

                with self.path.open("ab") as f:
                    f.write(payload)
                    f.flush()
                    os.fsync(f.fileno())
            except OSError as e:
                msg = f"Failed to append to inbox file: {e}"
                raise RuntimeError(msg) from e

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
        from dogcat.event_log import EventRecord

        if not changes:
            return

        event = EventRecord(
            event_type=event_type,
            issue_id=proposal.full_id,
            timestamp=proposal.updated_at.isoformat(),
            by=by,
            title=proposal.title,
            changes=changes,
        )
        try:
            self._event_log.append(event)
        except Exception:
            logging.getLogger(__name__).debug(
                "Failed to write event for %s",
                proposal.full_id,
                exc_info=True,
            )

    @staticmethod
    def _tracked_changes(
        old_values: dict[str, Any],
        new_values: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        """Compute tracked field changes between old and new proposal values."""
        changes: dict[str, dict[str, Any]] = {}
        for field_name in TRACKED_PROPOSAL_FIELDS:
            old: Any = old_values.get(field_name)
            new: Any = new_values.get(field_name)
            if hasattr(old, "value"):
                old = old.value
            if hasattr(new, "value"):
                new = new.value
            if old != new:
                changes[field_name] = {"old": old, "new": new}
        return changes

    def create(self, proposal: Proposal) -> Proposal:
        """Create a new proposal.

        Args:
            proposal: The proposal to create.

        Returns:
            The created proposal.

        Raises:
            ValueError: If ID already exists or proposal is invalid.
        """
        if proposal.full_id in self._proposals:
            msg = f"Proposal with ID {proposal.full_id} already exists"
            raise ValueError(msg)

        if not proposal.title:
            msg = "Proposal must have a non-empty title"
            raise ValueError(msg)

        self._proposals[proposal.full_id] = proposal
        self._append([self._proposal_record(proposal)])

        # Record creation event
        changes: dict[str, dict[str, Any]] = {
            "title": {"old": None, "new": proposal.title},
        }
        if proposal.description:
            changes["description"] = {"old": None, "new": proposal.description}
        self._emit_event(
            "created",
            proposal,
            changes,
            by=proposal.proposed_by,
        )

        return proposal

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
        if partial_id in self._proposals:
            return partial_id

        matches = [
            pid
            for pid in self._proposals
            if pid.endswith(partial_id) or pid.rsplit("-", 1)[-1] == partial_id
        ]

        if len(matches) == 1:
            return matches[0]

        if len(matches) > 1:
            msg = (
                f"Ambiguous partial ID '{partial_id}' "
                f"matches {len(matches)} proposals: "
                f"{', '.join(sorted(matches)[:5])}"
                + (f" and {len(matches) - 5} more" if len(matches) > 5 else "")
            )
            raise ValueError(msg)

        return None

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
        resolved_id = self.resolve_id(proposal_id)
        if resolved_id is None:
            msg = f"Proposal {proposal_id} not found"
            raise ValueError(msg)

        proposal = self._proposals[resolved_id]
        old_data = proposal_to_dict(proposal)
        now = datetime.now().astimezone()
        proposal.status = ProposalStatus.CLOSED
        proposal.closed_at = now
        proposal.updated_at = now
        if reason:
            proposal.close_reason = reason
        if closed_by:
            proposal.closed_by = closed_by
        if resolved_issue:
            proposal.resolved_issue = resolved_issue

        self._append([self._proposal_record(proposal)])

        # Record close event
        new_data = proposal_to_dict(proposal)
        changes = self._tracked_changes(old_data, new_data)
        self._emit_event("closed", proposal, changes, by=closed_by)

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
        resolved_id = self.resolve_id(proposal_id)
        if resolved_id is None:
            msg = f"Proposal {proposal_id} not found"
            raise ValueError(msg)

        proposal = self._proposals[resolved_id]
        old_data = proposal_to_dict(proposal)
        proposal.status = ProposalStatus.TOMBSTONE
        now = datetime.now().astimezone()
        proposal.deleted_at = now
        proposal.updated_at = now
        if deleted_by:
            proposal.deleted_by = deleted_by
        self._append([self._proposal_record(proposal)])

        # Record delete event
        new_data = proposal_to_dict(proposal)
        changes = self._tracked_changes(old_data, new_data)
        self._emit_event("deleted", proposal, changes, by=deleted_by)

        return proposal

    def prune_tombstones(self) -> list[str]:
        """Permanently remove tombstoned proposals from storage.

        Returns:
            List of pruned proposal IDs.
        """
        tombstone_ids = [
            pid
            for pid, proposal in self._proposals.items()
            if proposal.status == ProposalStatus.TOMBSTONE
        ]

        for pid in tombstone_ids:
            del self._proposals[pid]

        if tombstone_ids:
            self._save()

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
        targets = [p for p in self._proposals.values() if p.namespace == old_namespace]
        if not targets:
            return 0

        now = datetime.now().astimezone()
        for proposal in targets:
            old_fid = proposal.full_id
            proposal.namespace = new_namespace
            proposal.updated_at = now
            del self._proposals[old_fid]
            self._proposals[proposal.full_id] = proposal

        self._save()
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
