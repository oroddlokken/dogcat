"""Diff command for dogcat CLI - shows issue changes in git working tree."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import orjson
import typer

from dogcat.constants import TRACKED_FIELDS, TRACKED_PROPOSAL_FIELDS

from ._formatting import format_event, get_event_legend
from ._helpers import get_storage
from ._json_state import echo_error, is_json_output


def _get_git_root(cwd: Path | None = None) -> Path | None:
    """Get the root directory of the current git repository."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(cwd) if cwd else None,
    )
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip())


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
    result = subprocess.run(
        ["git", "show", git_ref],
        capture_output=True,
        check=False,
        cwd=str(git_root),
    )

    if result.returncode != 0:
        return None
    return result.stdout


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


def _field_value(value: Any) -> Any:
    """Normalize a field value for comparison."""
    if hasattr(value, "value"):
        return value.value
    return value


def register(app: typer.Typer) -> None:
    """Register diff command."""

    @app.command("diff")
    def diff_cmd(
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
            from dogcat.event_log import EventRecord, _serialize

            is_json_output(json_output)  # sync local flag for echo_error
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

            # Check for new and updated issues
            for issue_id, new_state in new.items():
                if issue_id not in old:
                    # New issue
                    changes: dict[str, dict[str, Any]] = {}
                    for field_name in TRACKED_FIELDS:
                        value = new_state.get(field_name)
                        if value is not None and value != [] and value != "":
                            changes[field_name] = {
                                "old": None,
                                "new": _field_value(value),
                            }
                    status = _field_value(new_state.get("status"))
                    if status == "closed":
                        event_type = "closed"
                    elif status == "tombstone":
                        event_type = "deleted"
                    else:
                        event_type = "created"
                    events.append(
                        EventRecord(
                            event_type=event_type,
                            issue_id=issue_id,
                            timestamp=new_state.get("created_at", ""),
                            by=new_state.get("created_by"),
                            title=new_state.get("title"),
                            changes=changes,
                        ),
                    )
                else:
                    # Existing issue - check for changes
                    old_state = old[issue_id]
                    changes = {}
                    for field_name in TRACKED_FIELDS:
                        old_val = _field_value(old_state.get(field_name))
                        new_val = _field_value(new_state.get(field_name))
                        if old_val != new_val:
                            changes[field_name] = {
                                "old": old_val,
                                "new": new_val,
                            }
                    if changes:
                        event_type = "updated"
                        if "status" in changes and changes["status"]["new"] == "closed":
                            event_type = "closed"
                        elif (
                            "status" in changes
                            and changes["status"]["new"] == "tombstone"
                        ):
                            event_type = "deleted"
                        events.append(
                            EventRecord(
                                event_type=event_type,
                                issue_id=issue_id,
                                timestamp=new_state.get("updated_at", ""),
                                by=new_state.get("updated_by"),
                                title=new_state.get("title"),
                                changes=changes,
                            ),
                        )

            # Check for deleted issues (in old but not in new)
            events.extend(
                EventRecord(
                    event_type="deleted",
                    issue_id=issue_id,
                    timestamp="",
                    title=old[issue_id].get("title"),
                    changes={
                        "status": {
                            "old": old[issue_id].get("status"),
                            "new": "removed",
                        },
                    },
                )
                for issue_id in old
                if issue_id not in new
            )

            # Check for new and updated proposals
            for prop_id, new_state in new_proposals.items():
                if prop_id not in old_proposals:
                    changes = {}
                    for field_name in TRACKED_PROPOSAL_FIELDS:
                        value = new_state.get(field_name)
                        if value is not None and value != "":
                            changes[field_name] = {
                                "old": None,
                                "new": _field_value(value),
                            }
                    status = _field_value(new_state.get("status"))
                    if status == "closed":
                        event_type = "closed"
                    elif status == "tombstone":
                        event_type = "deleted"
                    else:
                        event_type = "created"
                    events.append(
                        EventRecord(
                            event_type=event_type,
                            issue_id=prop_id,
                            timestamp=new_state.get("created_at", ""),
                            by=new_state.get("proposed_by"),
                            title=new_state.get("title"),
                            changes=changes,
                        ),
                    )
                else:
                    old_state = old_proposals[prop_id]
                    changes = {}
                    for field_name in TRACKED_PROPOSAL_FIELDS:
                        old_val = _field_value(old_state.get(field_name))
                        new_val = _field_value(new_state.get(field_name))
                        if old_val != new_val:
                            changes[field_name] = {
                                "old": old_val,
                                "new": new_val,
                            }
                    if changes:
                        event_type = "updated"
                        if "status" in changes and changes["status"]["new"] == "closed":
                            event_type = "closed"
                        elif (
                            "status" in changes
                            and changes["status"]["new"] == "tombstone"
                        ):
                            event_type = "deleted"
                        events.append(
                            EventRecord(
                                event_type=event_type,
                                issue_id=prop_id,
                                timestamp=new_state.get("updated_at", ""),
                                by=new_state.get("closed_by"),
                                title=new_state.get("title"),
                                changes=changes,
                            ),
                        )

            # Check for deleted proposals (in old but not in new)
            events.extend(
                EventRecord(
                    event_type="deleted",
                    issue_id=prop_id,
                    timestamp="",
                    title=old_proposals[prop_id].get("title"),
                    changes={
                        "status": {
                            "old": old_proposals[prop_id].get("status"),
                            "new": "removed",
                        },
                    },
                )
                for prop_id in old_proposals
                if prop_id not in new_proposals
            )

            # Sort oldest first (chronological)
            events.sort(key=lambda e: e.timestamp)

            if is_json_output(json_output):
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
