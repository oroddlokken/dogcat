"""Event streaming with change detection."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import orjson
from watchdog.events import (
    DirModifiedEvent,
    DirMovedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer

from dogcat.models import issue_to_dict
from dogcat.storage import JSONLStorage

if TYPE_CHECKING:
    from collections.abc import Callable

# Retry configuration for handling race conditions during file writes
_RETRY_ATTEMPTS = 3
_RETRY_DELAY_MS = 50  # milliseconds between retries


@dataclass
class StreamEvent:
    """An event representing a change to an issue."""

    event_type: str  # "created", "updated", "closed"
    issue_id: str
    timestamp: datetime
    by: str | None = None
    changes: dict[str, dict[str, Any]] = field(default_factory=dict)  # type: ignore[arg-type]

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary for JSON serialization."""
        return {
            "event_type": self.event_type,
            "issue_id": self.issue_id,
            "timestamp": self.timestamp.isoformat(),
            "by": self.by,
            "changes": self.changes,
        }


class StreamEmitter(FileSystemEventHandler):
    """Watches for changes to the JSONL file and emits events."""

    def __init__(
        self,
        storage_path: str,
        by: str | None = None,
        on_event: Callable[[StreamEvent], None] | None = None,
    ) -> None:
        """Initialize the stream emitter.

        Args:
            storage_path: Path to the .dogcats/issues.jsonl file
            by: Optional attribution name for events
            on_event: Optional callback for each event
        """
        super().__init__()
        self.storage_path = Path(storage_path)
        self.by = by
        self.on_event = on_event
        self.current_state: dict[str, Any] = {}
        self._load_current_state()

    def _load_current_state(self) -> None:
        """Load the current state from the JSONL file."""
        self.current_state = {}
        if self.storage_path.exists():
            try:
                storage = JSONLStorage(str(self.storage_path))
                for issue in storage.list():
                    self.current_state[issue.full_id] = issue_to_dict(issue)
            except (ValueError, RuntimeError, OSError):
                # If we can't load (corrupted file, permission issues, etc.),
                # start fresh
                pass

    def _compute_diff(
        self,
        old_state: dict[str, Any],
        new_state: dict[str, Any],
    ) -> list[StreamEvent]:
        """Compute the difference between two states.

        Args:
            old_state: Previous state (issue_id -> issue_dict)
            new_state: Current state (issue_id -> issue_dict)

        Returns:
            List of events representing the changes
        """
        events: list[StreamEvent] = []
        now = datetime.now().astimezone()

        # Check for creates and updates
        for issue_id, new_issue in new_state.items():
            if issue_id not in old_state:
                # New issue created
                changes: dict[str, dict[str, Any]] = {
                    field: {"old": None, "new": value}
                    for field, value in new_issue.items()
                    if value is not None
                }
                event = StreamEvent(
                    event_type="created",
                    issue_id=issue_id,
                    timestamp=now,
                    by=self.by,
                    changes=changes,
                )
                events.append(event)
            else:
                # Check for updates
                old_issue = old_state[issue_id]
                changes: dict[str, dict[str, Any]] = {}

                for field, new_value in new_issue.items():
                    old_value = old_issue.get(field)
                    if old_value != new_value:
                        # Special handling for status changes
                        if field == "status" and new_value == "closed":
                            event_type = "closed"
                        else:
                            event_type = "updated"

                        changes[field] = {"old": old_value, "new": new_value}

                if changes:
                    # Determine event type
                    if "status" in changes and changes["status"]["new"] == "closed":
                        event_type = "closed"
                    else:
                        event_type = "updated"

                    event = StreamEvent(
                        event_type=event_type,
                        issue_id=issue_id,
                        timestamp=now,
                        by=self.by,
                        changes=changes,
                    )
                    events.append(event)

        # Check for deletes (issues in old but not new)
        for issue_id in old_state:
            if issue_id not in new_state:
                delete_changes: dict[str, dict[str, Any]] = {
                    "status": {
                        "old": old_state[issue_id].get("status"),
                        "new": "deleted",
                    },
                }
                event = StreamEvent(
                    event_type="deleted",
                    issue_id=issue_id,
                    timestamp=now,
                    by=self.by,
                    changes=delete_changes,
                )
                events.append(event)

        return events

    def on_modified(self, event: DirModifiedEvent | FileModifiedEvent) -> None:
        """Handle file modification events.

        Args:
            event: The file event
        """
        if str(event.src_path).endswith("issues.jsonl"):
            self._handle_file_change()

    def on_moved(self, event: DirMovedEvent | FileMovedEvent) -> None:
        """Handle file move/rename events (for atomic writes).

        Args:
            event: The file event
        """
        if str(event.dest_path).endswith("issues.jsonl"):
            self._handle_file_change()

    def _handle_file_change(self) -> None:
        """Load new state and emit events for any changes.

        Uses retries with small delays to handle race conditions when the file
        is being written by another process (atomic write in progress).
        """
        # Load the new state with retries
        new_state: dict[str, Any] = {}
        last_error = None

        for attempt in range(_RETRY_ATTEMPTS):
            try:
                storage = JSONLStorage(str(self.storage_path))
                for issue in storage.list():
                    new_state[issue.full_id] = issue_to_dict(issue)
                last_error = None
                break  # Success
            except (ValueError, RuntimeError, OSError) as e:
                last_error = e
                if attempt < _RETRY_ATTEMPTS - 1:
                    # Wait before retry (file may still be in atomic write)
                    time.sleep(_RETRY_DELAY_MS / 1000)

        if last_error is not None:
            # All retries failed - skip this change event
            return

        # Compute diff and emit events
        events = self._compute_diff(self.current_state, new_state)
        self.current_state = new_state

        for event_obj in events:
            if self.on_event:
                self.on_event(event_obj)


class StreamWatcher:
    """Watches the storage file and streams events."""

    def __init__(
        self,
        storage_path: str = ".dogcats/issues.jsonl",
        by: str | None = None,
    ) -> None:
        """Initialize the watcher.

        Args:
            storage_path: Path to the .dogcats/issues.jsonl file
            by: Optional attribution name for events
        """
        self.storage_path = Path(storage_path)
        self.dogcats_dir = self.storage_path.parent
        self.by = by
        self.observer = Observer()
        self.events: list[StreamEvent] = []

    def start(self) -> None:
        """Start watching for changes."""
        emitter = StreamEmitter(
            str(self.storage_path),
            by=self.by,
            on_event=self._handle_event,
        )
        self.observer.schedule(emitter, str(self.dogcats_dir), recursive=False)
        self.observer.start()

    def stop(self) -> None:
        """Stop watching for changes."""
        self.observer.stop()
        self.observer.join()

    def _handle_event(self, event: StreamEvent) -> None:
        """Handle an event.

        Args:
            event: The event to handle
        """
        self.events.append(event)
        # Emit to stdout as JSONL
        line = orjson.dumps(event.to_dict()).decode()
        print(line, flush=True)

    def stream(self) -> None:
        """Stream events until interrupted.

        This method blocks and emits events as they occur.
        """
        self.start()
        try:
            # Keep the observer running
            while True:
                self.observer.join(timeout=1)
        except KeyboardInterrupt:
            self.stop()
