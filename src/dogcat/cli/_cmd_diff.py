"""Diff command for dogcat CLI - shows issue changes in git working tree."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import orjson
import typer

from dogcat.constants import TRACKED_FIELDS

from ._formatting import format_event, get_event_legend
from ._helpers import get_storage


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


def _get_committed_issues(
    storage_path: Path,
    git_root: Path,
) -> dict[str, dict[str, Any]]:
    """Get issue states from the last git commit (HEAD)."""
    from dogcat.models import classify_record, dict_to_issue, issue_to_dict

    # Compute relative path from git root
    try:
        rel_path = storage_path.resolve().relative_to(git_root.resolve())
    except ValueError:
        return {}

    result = subprocess.run(
        ["git", "show", f"HEAD:{rel_path}"],
        capture_output=True,
        check=False,
        cwd=str(git_root),
    )

    if result.returncode != 0:
        return {}  # No committed version (new file or new repo)

    states: dict[str, dict[str, Any]] = {}
    for line in result.stdout.splitlines():
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


def _get_current_issues(
    dogcats_dir: str,
) -> dict[str, dict[str, Any]]:
    """Get current issue states from storage."""
    from dogcat.models import issue_to_dict

    storage = get_storage(dogcats_dir)
    return {issue.full_id: issue_to_dict(issue) for issue in storage.list()}


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
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Show issue changes in the git working tree.

        Compares the current .dogcats/issues.jsonl against the last
        committed version (HEAD), showing created, updated, and closed
        issues with field-level changes.
        """
        try:
            from dogcat.event_log import EventRecord, _serialize

            storage = get_storage(dogcats_dir)
            storage_path = storage.path

            git_root = _get_git_root(cwd=storage.dogcats_dir)
            if git_root is None:
                typer.echo("Error: Not in a git repository", err=True)
                raise typer.Exit(1)

            committed = _get_committed_issues(storage_path, git_root)
            current = _get_current_issues(dogcats_dir)

            events: list[EventRecord] = []

            # Check for new and updated issues
            for issue_id, new_state in current.items():
                if issue_id not in committed:
                    # New issue
                    changes: dict[str, dict[str, Any]] = {}
                    for field_name in TRACKED_FIELDS:
                        value = new_state.get(field_name)
                        if value is not None and value != [] and value != "":
                            changes[field_name] = {
                                "old": None,
                                "new": _field_value(value),
                            }
                    events.append(
                        EventRecord(
                            event_type="created",
                            issue_id=issue_id,
                            timestamp=new_state.get("created_at", ""),
                            by=new_state.get("created_by"),
                            title=new_state.get("title"),
                            changes=changes,
                        ),
                    )
                else:
                    # Existing issue - check for changes
                    old_state = committed[issue_id]
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

            # Check for deleted issues (in committed but not in current)
            events.extend(
                EventRecord(
                    event_type="deleted",
                    issue_id=issue_id,
                    timestamp="",
                    title=committed[issue_id].get("title"),
                    changes={
                        "status": {
                            "old": committed[issue_id].get("status"),
                            "new": "removed",
                        },
                    },
                )
                for issue_id in committed
                if issue_id not in current
            )

            # Sort newest first
            events.sort(key=lambda e: e.timestamp, reverse=True)

            if json_output:
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
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1) from e
