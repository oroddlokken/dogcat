"""Admin commands for dogcat CLI."""

from __future__ import annotations

from typing import Any

import orjson
import typer

from dogcat.config import get_issue_prefix

from ._completions import (
    complete_export_formats,
    complete_issue_ids,
    complete_labels,
    complete_namespaces,
    complete_owners,
    complete_priorities,
    complete_statuses,
    complete_types,
)
from ._helpers import apply_common_filters, get_storage
from ._json_state import echo_error, is_json_output


def register(app: typer.Typer) -> None:
    """Register admin commands."""

    @app.command()
    def prune(
        dry_run: bool = typer.Option(
            False,
            "--dry-run",
            "-n",
            help="Show what would be removed without actually removing",
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Remove tombstoned (deleted) issues and proposals from storage permanently.

        This command permanently removes issues and inbox proposals with
        tombstone status from their storage files. Use --dry-run to preview
        what would be removed.
        """
        try:
            from dogcat.inbox import InboxStorage

            storage = get_storage(dogcats_dir)
            issues = storage.list()

            # Find tombstoned issues
            tombstones = [i for i in issues if i.status.value == "tombstone"]

            # Find tombstoned inbox proposals
            inbox_tombstones = []
            try:
                inbox = InboxStorage(dogcats_dir=str(storage.dogcats_dir))
                inbox_tombstones = [
                    p for p in inbox.list(include_tombstones=True) if p.is_tombstone()
                ]
            except (ValueError, RuntimeError):
                inbox = None

            if not tombstones and not inbox_tombstones:
                if is_json_output(json_output):
                    typer.echo(
                        orjson.dumps(
                            {
                                "pruned": 0,
                                "ids": [],
                                "inbox_pruned": 0,
                                "inbox_ids": [],
                            },
                        ).decode(),
                    )
                else:
                    typer.echo("No tombstoned issues or proposals to prune")
                return

            if dry_run:
                if is_json_output(json_output):
                    output: dict[str, Any] = {
                        "dry_run": True,
                        "count": len(tombstones),
                        "ids": [i.full_id for i in tombstones],
                        "inbox_count": len(inbox_tombstones),
                        "inbox_ids": [p.full_id for p in inbox_tombstones],
                    }
                    typer.echo(orjson.dumps(output).decode())
                else:
                    if tombstones:
                        typer.echo(
                            f"Would remove {len(tombstones)} tombstoned issue(s):"
                        )
                        for issue in tombstones:
                            typer.echo(f"  ☠ {issue.full_id}: {issue.title}")
                    if inbox_tombstones:
                        n = len(inbox_tombstones)
                        typer.echo(
                            f"Would remove {n} tombstoned proposal(s):",
                        )
                        for proposal in inbox_tombstones:
                            typer.echo(f"  ☠ {proposal.full_id}: {proposal.title}")
                    if not tombstones and not inbox_tombstones:
                        typer.echo("Nothing to prune")
            else:
                # Remove tombstones from storage using public API
                pruned_ids = storage.prune_tombstones() if tombstones else []
                inbox_pruned_ids = (
                    inbox.prune_tombstones()
                    if inbox is not None and inbox_tombstones
                    else []
                )
                if is_json_output(json_output):
                    output = {
                        "pruned": len(pruned_ids),
                        "ids": list(pruned_ids),
                        "inbox_pruned": len(inbox_pruned_ids),
                        "inbox_ids": list(inbox_pruned_ids),
                    }
                    typer.echo(orjson.dumps(output).decode())
                else:
                    if pruned_ids:
                        typer.echo(f"✓ Pruned {len(pruned_ids)} tombstoned issue(s)")
                    if inbox_pruned_ids:
                        typer.echo(
                            f"✓ Pruned {len(inbox_pruned_ids)} tombstoned proposal(s)",
                        )

        except typer.Exit:
            raise
        except Exception as e:
            echo_error(str(e))
            raise typer.Exit(1)

    @app.command()
    def stream(
        by: str = typer.Option(None, "--by", help="Attribution name for events"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Stream issue changes in real-time (JSONL format).

        Watches for changes to issues and outputs events as JSONL lines.
        Press Ctrl+C to stop streaming.
        """
        try:
            from dogcat.stream import StreamWatcher

            storage_path = f"{dogcats_dir}/issues.jsonl"
            watcher = StreamWatcher(storage_path=storage_path, by=by)

            typer.echo("Streaming events... (Press Ctrl+C to stop)", err=True)
            watcher.stream()
            typer.echo("", err=True)

        except KeyboardInterrupt:
            typer.echo("", err=True)
        except typer.Exit:
            raise
        except Exception as e:
            echo_error(str(e))
            raise typer.Exit(1)

    @app.command()
    def export(
        format_type: str = typer.Option(
            "json",
            "--format",
            "-f",
            help="Export format: json or jsonl",
            autocompletion=complete_export_formats,
        ),
        status: str | None = typer.Option(
            None,
            "--status",
            "-s",
            help="Filter by status",
            autocompletion=complete_statuses,
        ),
        issue_type: str | None = typer.Option(
            None,
            "--type",
            "-t",
            help="Filter by type",
            autocompletion=complete_types,
        ),
        priority: int | None = typer.Option(
            None,
            "--priority",
            "-p",
            help="Filter by priority",
            autocompletion=complete_priorities,
        ),
        label: str | None = typer.Option(
            None,
            "--label",
            "-l",
            help="Filter by label",
            autocompletion=complete_labels,
        ),
        owner: str | None = typer.Option(
            None,
            "--owner",
            "-o",
            help="Filter by owner",
            autocompletion=complete_owners,
        ),
        parent: str | None = typer.Option(
            None,
            "--parent",
            help="Filter by parent issue ID",
            autocompletion=complete_issue_ids,
        ),
        namespace: str | None = typer.Option(
            None,
            "--namespace",
            help="Filter by namespace",
            autocompletion=complete_namespaces,
        ),
        all_namespaces: bool = typer.Option(
            False,
            "--all-namespaces",
            "--all-ns",
            "-A",
            help="Export issues from all namespaces",
        ),
        include_inbox: bool = typer.Option(
            True,
            "--include-inbox/--no-inbox",
            help="Include inbox proposals in export",
        ),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Export issues, dependencies, links, and inbox proposals to stdout.

        By default exports all issues and inbox proposals.
        Use filters to narrow the export.

        Supported formats:
        - json: JSON object with issues, dependencies, links, and proposals
        - jsonl: JSON Lines (one record per line)
        """
        try:
            storage = get_storage(dogcats_dir)
            issues = storage.list()

            # Apply status filter
            if status:
                issues = [i for i in issues if i.status.value == status]

            # Apply common filters
            issues = apply_common_filters(
                issues,
                issue_type=issue_type,
                priority=priority,
                label=label,
                owner=owner,
                parent=parent,
                namespace=namespace,
                all_namespaces=all_namespaces,
                dogcats_dir=str(storage.dogcats_dir),
                storage=storage,
            )

            from dogcat.models import issue_to_dict, proposal_to_dict

            # Get all deps and links (avoids per-issue iteration dups).
            # When filters are active, scope to exported issues.
            exported_ids = {i.full_id for i in issues}
            has_filters = bool(
                status
                or issue_type
                or priority is not None
                or label
                or owner
                or parent
                or namespace
            )

            all_deps: list[dict[str, Any]] = [
                {
                    "issue_id": dep.issue_id,
                    "depends_on_id": dep.depends_on_id,
                    "type": dep.dep_type.value,
                    "created_at": dep.created_at.isoformat(),
                    "created_by": dep.created_by,
                }
                for dep in storage.all_dependencies
                if not has_filters
                or (dep.issue_id in exported_ids or dep.depends_on_id in exported_ids)
            ]
            all_links: list[dict[str, Any]] = [
                {
                    "from_id": link.from_id,
                    "to_id": link.to_id,
                    "link_type": link.link_type,
                    "created_at": link.created_at.isoformat(),
                    "created_by": link.created_by,
                }
                for link in storage.all_links
                if not has_filters
                or (link.from_id in exported_ids or link.to_id in exported_ids)
            ]

            # Load inbox proposals
            all_proposals: list[dict[str, Any]] = []
            if include_inbox:
                try:
                    from dogcat.inbox import InboxStorage

                    inbox = InboxStorage(dogcats_dir=str(storage.dogcats_dir))
                    proposals = inbox.list(include_tombstones=True)

                    # Apply namespace filter
                    if namespace:
                        proposals = [p for p in proposals if p.namespace == namespace]
                    elif not all_namespaces:
                        from dogcat.config import get_issue_prefix, get_namespace_filter

                        ns_filter = get_namespace_filter(str(storage.dogcats_dir))
                        if ns_filter is not None:
                            proposals = [p for p in proposals if ns_filter(p.namespace)]
                        else:
                            primary = get_issue_prefix(str(storage.dogcats_dir))
                            proposals = [p for p in proposals if p.namespace == primary]

                    all_proposals = [proposal_to_dict(p) for p in proposals]
                except (ValueError, RuntimeError):
                    pass  # No inbox file — skip silently

            if format_type == "json":
                # table-printed JSON object with all data
                output: dict[str, Any] = {
                    "issues": [issue_to_dict(issue) for issue in issues],
                    "dependencies": all_deps,
                    "links": all_links,
                }
                if include_inbox:
                    output["proposals"] = all_proposals
                typer.echo(orjson.dumps(output, option=orjson.OPT_INDENT_2).decode())
            elif format_type == "jsonl":
                # JSON Lines format - one record per line
                for issue in issues:
                    issue_dict = issue_to_dict(issue)
                    typer.echo(orjson.dumps(issue_dict).decode())
                for dep in all_deps:
                    typer.echo(orjson.dumps(dep).decode())
                for link in all_links:
                    typer.echo(orjson.dumps(link).decode())
                for proposal in all_proposals:
                    typer.echo(orjson.dumps(proposal).decode())
            else:
                echo_error(f"Unknown format '{format_type}'")
                typer.echo("Supported formats: json, jsonl", err=True)
                raise typer.Exit(1)

        except typer.Exit:
            raise
        except Exception as e:
            echo_error(str(e))
            raise typer.Exit(1)

    @app.command()
    def info(
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """Show valid issue types, statuses, and priorities.

        Displays all valid values for issue fields, useful for
        understanding what options are available.
        """
        from dogcat.constants import (
            INBOX_STATUS_OPTIONS,
            PRIORITY_OPTIONS,
            STATUS_OPTIONS,
            STATUS_SHORTHANDS,
            TYPE_OPTIONS,
            TYPE_SHORTHANDS,
        )

        if is_json_output(json_output):
            output = {
                "types": [
                    {"label": label, "value": value} for label, value in TYPE_OPTIONS
                ],
                "type_shorthands": TYPE_SHORTHANDS,
                "status_shorthands": STATUS_SHORTHANDS,
                "statuses": [
                    {"label": label, "value": value} for label, value in STATUS_OPTIONS
                ],
                "priorities": [
                    {"label": label, "value": value}
                    for label, value in PRIORITY_OPTIONS
                ],
                "inbox_statuses": [
                    {"label": label, "value": value}
                    for label, value in INBOX_STATUS_OPTIONS
                ],
            }
            typer.echo(orjson.dumps(output, option=orjson.OPT_INDENT_2).decode())
        else:
            typer.echo("Issue Types:")
            for label, value in TYPE_OPTIONS:
                shorthand = next(
                    (k for k, v in TYPE_SHORTHANDS.items() if v == value),
                    None,
                )
                shorthand_str = f" (shorthand: {shorthand})" if shorthand else ""
                typer.echo(f"  {value:<10} - {label}{shorthand_str}")

            typer.echo("\nStatuses:")
            for label, value in STATUS_OPTIONS:
                shorthand = next(
                    (k for k, v in STATUS_SHORTHANDS.items() if v == value),
                    None,
                )
                shorthand_str = f" (shorthand: {shorthand})" if shorthand else ""
                typer.echo(f"  {value:<12} - {label}{shorthand_str}")

            typer.echo("\nInbox Statuses:")
            for label, value in INBOX_STATUS_OPTIONS:
                typer.echo(f"  {value:<12} - {label}")

            typer.echo("\nPriorities:")
            for label, value in PRIORITY_OPTIONS:
                typer.echo(f"  {value}  - {label}")

            typer.echo("\nShorthands for c (create alias) command:")
            type_shorthand_list = ", ".join(
                f"{k}={v}" for k, v in sorted(TYPE_SHORTHANDS.items())
            )
            status_shorthand_list = ", ".join(
                f"{k}={v}" for k, v in sorted(STATUS_SHORTHANDS.items())
            )
            typer.echo(f"  Type: {type_shorthand_list}")
            typer.echo(f"  Status: {status_shorthand_list}")
            typer.echo("  Priority: 0-4 (0=Critical, 4=Minimal)")

    @app.command()
    def status(
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Show repository status: prefix and issue counts.

        Displays the configured issue prefix and counts of issues by status.

        Examples:
            dcat status         # Show prefix and counts
            dcat status --json  # Output as JSON
        """
        try:
            storage = get_storage(dogcats_dir)
            # Get the actual dogcats_dir from storage (in case it was found by search)
            actual_dogcats_dir = str(storage.dogcats_dir)
            prefix = get_issue_prefix(actual_dogcats_dir)

            # Count issues by status and type
            all_issues = storage.list()
            status_counts: dict[str, int] = {}
            type_counts: dict[str, int] = {}
            for issue in all_issues:
                status_val = issue.status.value
                status_counts[status_val] = status_counts.get(status_val, 0) + 1
                type_val = issue.issue_type.value
                type_counts[type_val] = type_counts.get(type_val, 0) + 1

            total = len(all_issues)

            # Count inbox proposals
            from dogcat.inbox import InboxStorage

            inbox_counts: dict[str, int] = {}
            inbox_total = 0
            try:
                inbox = InboxStorage(dogcats_dir=actual_dogcats_dir)
                for proposal in inbox.list(include_tombstones=True):
                    sv = proposal.status.value
                    inbox_counts[sv] = inbox_counts.get(sv, 0) + 1
                    inbox_total += 1
            except (ValueError, RuntimeError):
                pass  # No inbox file or invalid — just skip

            if is_json_output(json_output):
                output: dict[str, object] = {
                    "prefix": prefix,
                    "total": total,
                    "by_status": status_counts,
                    "by_type": type_counts,
                }
                if inbox_total:
                    output["inbox_total"] = inbox_total
                    output["inbox_by_status"] = inbox_counts
                typer.echo(orjson.dumps(output, option=orjson.OPT_INDENT_2).decode())
            else:
                typer.echo(f"Prefix: {prefix}")
                typer.echo(f"Total issues: {total}")
                if status_counts:
                    typer.echo("\nBy status:")
                    for status_val, count in sorted(status_counts.items()):
                        typer.echo(f"  {status_val:<12} {count}")
                if type_counts:
                    typer.echo("\nBy type:")
                    for type_val, count in sorted(type_counts.items()):
                        typer.echo(f"  {type_val:<12} {count}")
                if inbox_total:
                    typer.echo(f"\nInbox: {inbox_total} proposal(s)")
                    for sv, count in sorted(inbox_counts.items()):
                        typer.echo(f"  {sv:<12} {count}")

        except ValueError as e:
            echo_error(str(e))
            raise typer.Exit(1) from None

    @app.command(name="backfill-history")
    def backfill_history(
        dry_run: bool = typer.Option(
            False,
            "--dry-run",
            help="Preview without writing events",
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Backfill event history from existing JSONL records.

        Replays the issues.jsonl file and generates event records for all
        intermediate states. Should be run once after upgrading to populate
        the event log for existing issues.
        """
        try:
            from dogcat.constants import TRACKED_FIELDS
            from dogcat.event_log import EventLog, EventRecord, _serialize
            from dogcat.models import classify_record, dict_to_issue, issue_to_dict

            storage = get_storage(dogcats_dir)
            event_log = EventLog(storage.dogcats_dir)

            # Warn if event records already exist
            existing = event_log.read(limit=1)
            if existing:
                typer.echo(
                    "Warning: event records already exist. "
                    "Backfill may create duplicates.",
                    err=True,
                )
                if not dry_run:
                    typer.echo("Use --dry-run to preview first.", err=True)
                    raise typer.Exit(1)

            # Replay issues.jsonl to reconstruct history
            issue_states: dict[str, dict[str, Any]] = {}
            events_generated = 0
            storage_path = storage.path

            with storage_path.open("rb") as f:
                for line_bytes in f:
                    line_bytes = line_bytes.strip()
                    if not line_bytes:
                        continue
                    data = orjson.loads(line_bytes)
                    rtype = classify_record(data)
                    if rtype != "issue":
                        continue

                    issue = dict_to_issue(data)
                    new_state = issue_to_dict(issue)
                    full_id = issue.full_id

                    if full_id not in issue_states:
                        # First occurrence -> "created" event
                        changes: dict[str, dict[str, Any]] = {}
                        for field_name in TRACKED_FIELDS:
                            value = new_state.get(field_name)
                            if value is not None and value != [] and value != "":
                                if field_name == "description":
                                    changes[field_name] = {
                                        "old": None,
                                        "new": "changed",
                                    }
                                else:
                                    changes[field_name] = {
                                        "old": None,
                                        "new": value,
                                    }
                        event = EventRecord(
                            event_type="created",
                            issue_id=full_id,
                            timestamp=new_state.get(
                                "created_at",
                                issue.created_at.isoformat(),
                            ),
                            by=new_state.get("created_by"),
                            title=issue.title,
                            changes=changes,
                        )
                    else:
                        # Subsequent occurrence -> compute diff
                        old_state = issue_states[full_id]
                        changes = {}
                        for field_name in TRACKED_FIELDS:
                            old_val = old_state.get(field_name)
                            new_val = new_state.get(field_name)
                            if old_val != new_val:
                                if field_name == "description":
                                    changes[field_name] = {
                                        "old": "changed",
                                        "new": "changed",
                                    }
                                else:
                                    changes[field_name] = {
                                        "old": old_val,
                                        "new": new_val,
                                    }
                        if not changes:
                            issue_states[full_id] = new_state
                            continue

                        # Determine event type
                        event_type = "updated"
                        if "status" in changes and changes["status"]["new"] == "closed":
                            event_type = "closed"
                        elif (
                            "status" in changes
                            and changes["status"]["new"] == "tombstone"
                        ):
                            event_type = "deleted"

                        event = EventRecord(
                            event_type=event_type,
                            issue_id=full_id,
                            timestamp=new_state.get(
                                "updated_at",
                                issue.updated_at.isoformat(),
                            ),
                            by=new_state.get("updated_by"),
                            title=issue.title,
                            changes=changes,
                        )

                    if dry_run:
                        data = _serialize(event)
                        typer.echo(orjson.dumps(data).decode())
                    else:
                        event_log.append(event)
                    events_generated += 1
                    issue_states[full_id] = new_state

            if is_json_output(json_output):
                output = {
                    "dry_run": dry_run,
                    "events_generated": events_generated,
                }
                typer.echo(orjson.dumps(output).decode())
            elif dry_run:
                typer.echo(
                    f"\nDry run: would generate {events_generated} event(s)",
                    err=True,
                )
            else:
                typer.echo(f"✓ Backfilled {events_generated} event(s)")

        except typer.Exit:
            raise
        except Exception as e:
            echo_error(str(e))
            raise typer.Exit(1) from e
