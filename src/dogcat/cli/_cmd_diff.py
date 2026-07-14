"""Diff command for dogcat CLI - shows issue changes in git working tree."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import orjson
import typer

import dogcat.git as git_helpers
from dogcat.constants import TRACKED_FIELDS, TRACKED_PROPOSAL_FIELDS

from ._formatting import format_event, get_event_legend
from ._helpers import get_storage
from ._json_state import echo_error, is_json, set_json


def _get_git_root(cwd: Path | None = None) -> Path | None:
    """Get the root directory of the current git repository."""
    return git_helpers.repo_root(cwd=cwd)


def _get_git_file(
    file_path: Path,
    git_root: Path,
    ref: str = "HEAD",
) -> bytes | None:
    """Read a file from a git ref, returning raw bytes or None."""
    try:
        rel_path = file_path.resolve().relative_to(git_root.resolve())
    except ValueError:
        return None

    git_ref = f"{ref}:{rel_path}" if ref else f":{rel_path}"
    return git_helpers.show_file(git_ref, cwd=git_root)


def _parse_issues_from_bytes(raw: bytes) -> dict[str, dict[str, Any]]:
    """Parse issue records from raw JSONL bytes."""
    from dogcat.models import classify_record, dict_to_issue, issue_to_dict

    states: dict[str, dict[str, Any]] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = orjson.loads(line)
            rtype = classify_record(data)
            if rtype == "issue":
                issue = dict_to_issue(data)
                states[issue.full_id] = issue_to_dict(issue)
        except (orjson.JSONDecodeError, ValueError, KeyError):
            continue
    return states


def _parse_proposals_from_bytes(raw: bytes) -> dict[str, dict[str, Any]]:
    """Parse proposal records from raw JSONL bytes."""
    from dogcat.models import classify_record, dict_to_proposal, proposal_to_dict

    states: dict[str, dict[str, Any]] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = orjson.loads(line)
            rtype = classify_record(data)
            if rtype == "proposal":
                proposal = dict_to_proposal(data)
                states[proposal.full_id] = proposal_to_dict(proposal)
        except (orjson.JSONDecodeError, ValueError, KeyError):
            continue
    return states


def _get_git_issues(
    storage_path: Path,
    git_root: Path,
    ref: str = "HEAD",
) -> dict[str, dict[str, Any]]:
    """Get issue states from a git ref."""
    raw = _get_git_file(storage_path, git_root, ref)
    if raw is None:
        return {}
    return _parse_issues_from_bytes(raw)


def _get_git_proposals(
    inbox_path: Path,
    git_root: Path,
    ref: str = "HEAD",
) -> dict[str, dict[str, Any]]:
    """Get proposal states from a git ref."""
    raw = _get_git_file(inbox_path, git_root, ref)
    if raw is None:
        return {}
    return _parse_proposals_from_bytes(raw)


def _get_current_issues(
    dogcats_dir: str,
) -> dict[str, dict[str, Any]]:
    """Get current issue states from storage."""
    from dogcat.models import issue_to_dict

    storage = get_storage(dogcats_dir)
    return {issue.full_id: issue_to_dict(issue) for issue in storage.list()}


def _get_current_proposals(
    dogcats_dir: str,
) -> dict[str, dict[str, Any]]:
    """Get current proposal states from inbox storage."""
    from dogcat.inbox import InboxStorage
    from dogcat.models import proposal_to_dict

    inbox_path = Path(dogcats_dir) / "inbox.jsonl"
    if not inbox_path.exists():
        return {}
    inbox = InboxStorage(dogcats_dir)
    return {p.full_id: proposal_to_dict(p) for p in inbox.list(include_tombstones=True)}


from dogcat._diff import field_value as _field_value  # noqa: E402  (re-export)

# ``_field_value`` is now an alias for the canonical helper in ``dogcat._diff``.
# Storage and ``_validate`` already share that implementation; the inline
# duplicate here was the third copy.

if TYPE_CHECKING:
    from collections.abc import Iterable

    from dogcat.event_log import EventRecord


def _classify_event_type(status_new: str | None, *, is_new: bool) -> str:
    """Map a record's (new) status value to a diff event type.

    Single source for the closed / tombstone / created-or-updated ladder
    that the issue and proposal, new and updated paths each repeated inline.
    """
    if status_new == "closed":
        return "closed"
    if status_new == "tombstone":
        return "deleted"
    return "created" if is_new else "updated"


def _diff_records(
    old: dict[str, dict[str, Any]],
    new: dict[str, dict[str, Any]],
    tracked_fields: Iterable[str],
    *,
    created_by_field: str,
    updated_by_field: str,
    include_metadata: bool,
) -> list[EventRecord]:
    """Diff two record maps into created/updated/closed/deleted events.

    Shared by the issue and proposal paths, which differ only in their
    tracked-field set, the author field names (created_by/proposed_by,
    updated_by/closed_by), and whether records carry metadata.
    """
    from dogcat.event_log import EventRecord, diff_metadata

    events: list[EventRecord] = []
    for rec_id, new_state in new.items():
        if rec_id not in old:
            # New record.
            changes: dict[str, dict[str, Any]] = {}
            for field_name in tracked_fields:
                value = new_state.get(field_name)
                if value is not None and value != [] and value != "":
                    changes[field_name] = {"old": None, "new": _field_value(value)}
            if include_metadata:
                changes.update(diff_metadata(None, new_state.get("metadata")))
            event_type = _classify_event_type(
                _field_value(new_state.get("status")),
                is_new=True,
            )
            events.append(
                EventRecord(
                    event_type=event_type,
                    issue_id=rec_id,
                    timestamp=new_state.get("created_at", ""),
                    by=new_state.get(created_by_field),
                    title=new_state.get("title"),
                    changes=changes,
                ),
            )
        else:
            # Existing record — field-level diff.
            old_state = old[rec_id]
            changes = {}
            for field_name in tracked_fields:
                old_val = _field_value(old_state.get(field_name))
                new_val = _field_value(new_state.get(field_name))
                if old_val != new_val:
                    changes[field_name] = {"old": old_val, "new": new_val}
            if include_metadata:
                changes.update(
                    diff_metadata(
                        old_state.get("metadata"),
                        new_state.get("metadata"),
                    ),
                )
            if changes:
                status_new = changes["status"]["new"] if "status" in changes else None
                events.append(
                    EventRecord(
                        event_type=_classify_event_type(status_new, is_new=False),
                        issue_id=rec_id,
                        timestamp=new_state.get("updated_at", ""),
                        by=new_state.get(updated_by_field),
                        title=new_state.get("title"),
                        changes=changes,
                    ),
                )

    # Deleted records (in old but not in new).
    events.extend(
        EventRecord(
            event_type="deleted",
            issue_id=rec_id,
            timestamp="",
            title=old[rec_id].get("title"),
            changes={
                "status": {"old": old[rec_id].get("status"), "new": "removed"},
            },
        )
        for rec_id in old
        if rec_id not in new
    )
    return events


def register(app: typer.Typer) -> None:
    """Register diff command."""

    @app.command("diff")
    def diff(
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        verbose: bool = typer.Option(
            False,
            "--verbose",
            "-v",
            help="Show full content of long-form fields",
        ),
        staged: bool = typer.Option(
            False,
            "--staged",
            help="Compare staged changes against HEAD",
        ),
        unstaged: bool = typer.Option(
            False,
            "--unstaged",
            help="Compare working tree against staged",
        ),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Show issue and proposal changes in the git working tree.

        Compares the current .dogcats/issues.jsonl and .dogcats/inbox.jsonl
        against the last committed version (HEAD), showing created, updated,
        and closed issues/proposals with field-level changes.

        Use --staged to compare the index (staged) against HEAD.
        Use --unstaged to compare the working tree against the index.
        """
        try:
            from dogcat.event_log import _serialize

            set_json(json_output)
            if staged and unstaged:
                echo_error("--staged and --unstaged are mutually exclusive")
                raise typer.Exit(1)

            storage = get_storage(dogcats_dir)
            storage_path = storage.path
            inbox_path = Path(dogcats_dir) / "inbox.jsonl"

            git_root = _get_git_root(cwd=storage.dogcats_dir)
            if git_root is None:
                echo_error("Not in a git repository")
                raise typer.Exit(1)

            if staged:
                old = _get_git_issues(storage_path, git_root, ref="HEAD")
                new = _get_git_issues(storage_path, git_root, ref="")
                old_proposals = _get_git_proposals(inbox_path, git_root, ref="HEAD")
                new_proposals = _get_git_proposals(inbox_path, git_root, ref="")
            elif unstaged:
                old = _get_git_issues(storage_path, git_root, ref="")
                new = _get_current_issues(dogcats_dir)
                old_proposals = _get_git_proposals(inbox_path, git_root, ref="")
                new_proposals = _get_current_proposals(dogcats_dir)
            else:
                old = _get_git_issues(storage_path, git_root, ref="HEAD")
                new = _get_current_issues(dogcats_dir)
                old_proposals = _get_git_proposals(inbox_path, git_root, ref="HEAD")
                new_proposals = _get_current_proposals(dogcats_dir)

            events: list[EventRecord] = []
            events.extend(
                _diff_records(
                    old,
                    new,
                    TRACKED_FIELDS,
                    created_by_field="created_by",
                    updated_by_field="updated_by",
                    include_metadata=True,
                ),
            )
            events.extend(
                _diff_records(
                    old_proposals,
                    new_proposals,
                    TRACKED_PROPOSAL_FIELDS,
                    created_by_field="proposed_by",
                    updated_by_field="closed_by",
                    include_metadata=False,
                ),
            )

            # Sort oldest first (chronological)
            events.sort(key=lambda e: e.timestamp)

            if is_json():
                output = [_serialize(e) for e in events]
                typer.echo(orjson.dumps(output).decode())
            elif not events:
                typer.echo("No changes")
            else:
                for event in events:
                    typer.echo(format_event(event, verbose=verbose))
                typer.echo(get_event_legend())

        except typer.Exit:
            raise
        except Exception as e:
            echo_error(str(e))
            raise typer.Exit(1) from e
