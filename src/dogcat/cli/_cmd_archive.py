"""Archive command for dogcat CLI."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import orjson
import typer

from dogcat._jsonl_io import split_and_rewrite_jsonl
from dogcat.models import Status

from ._completions import complete_durations, complete_namespaces
from ._helpers import get_storage
from ._json_state import echo_error, is_json, set_json


def _archive_inbox(
    dogcats_dir: str,
    archive_dir: Path,
    timestamp: str,
    namespace: str | None,
    days: int | None,
) -> int:
    """Archive closed inbox proposals to archive/inbox-closed-<ts>.jsonl.

    Returns the number of proposals archived.
    """
    from datetime import timedelta

    from dogcat.inbox import InboxStorage
    from dogcat.models import ProposalStatus

    try:
        inbox = InboxStorage(dogcats_dir=dogcats_dir)
    except (ValueError, RuntimeError):
        return 0

    proposals = inbox.list(include_tombstones=False)
    closed = [p for p in proposals if p.status == ProposalStatus.CLOSED]

    if namespace is not None:
        closed = [p for p in closed if p.namespace == namespace]

    if days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        closed = [
            p
            for p in closed
            if p.closed_at and p.closed_at.astimezone(timezone.utc) <= cutoff
        ]

    if not closed:
        return 0

    closed_ids = {p.full_id for p in closed}
    inbox_path = inbox.get_file_path()
    archive_path = archive_dir / f"inbox-closed-{timestamp}.jsonl"

    def classify(stripped: bytes) -> bool:
        try:
            data = orjson.loads(stripped)
        except orjson.JSONDecodeError:
            return False
        ns = data.get("namespace", "dc")
        pid = data.get("id", "")
        return f"{ns}-inbox-{pid}" in closed_ids

    # Hold the inbox file lock across read+rewrite so a concurrent
    # ``dcat propose`` append cannot race the atomic-replace and lose data.
    with inbox._file_lock():
        archived_count, _ = split_and_rewrite_jsonl(
            inbox_path,
            inbox_path.parent,
            archive_path,
            archive_dir,
            classify,
        )

    return len(closed) if archived_count > 0 else 0


def register(app: typer.Typer) -> None:
    """Register archive command."""

    @app.command()
    def archive(
        dry_run: bool = typer.Option(
            False,
            "--dry-run",
            help="Preview what would be archived without making changes",
        ),
        older_than: str = typer.Option(
            None,
            "--older-than",
            help="Only archive issues closed more than N days ago (e.g. 30d)",
            autocompletion=complete_durations,
        ),
        namespace: str | None = typer.Option(
            None,
            "--namespace",
            help="Only archive issues from this namespace",
            autocompletion=complete_namespaces,
        ),
        yes: bool = typer.Option(
            False,
            "--yes",
            "-y",
            help="Skip confirmation prompt",
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Archive closed issues to reduce startup load.

        Moves closed issues from the main storage file to an archive file
        at .dogcats/archive/closed-<timestamp>.jsonl.

        Issues are NOT archived if:
        - They have any open (non-closed) child issues
        - They have dependencies or links pointing to issues NOT being archived

        Examples:
            dcat archive                      # Archive all closed issues
            dcat archive --dry-run            # Preview what would be archived
            dcat archive --older-than 30d     # Only archive if closed 30+ days ago
            dcat archive --namespace myproj   # Archive only 'myproj' namespace
            dcat archive --yes                # Skip confirmation prompt
        """
        set_json(json_output)
        import re
        from datetime import timedelta

        # Validate --older-than format early
        days: int | None = None
        if older_than:
            match = re.match(r"^(\d+)d$", older_than)
            if not match:
                echo_error("--older-than must be in format Nd (e.g. 30d)")
                raise typer.Exit(1)
            days = int(match.group(1))

        try:
            storage = get_storage(dogcats_dir)
            actual_dogcats_dir = str(storage.dogcats_dir)

            closed_issues = [
                i
                for i in storage.list()
                if i.status == Status.CLOSED and not i.is_tombstone()
            ]

            if not closed_issues:
                typer.echo("No closed issues to archive.")
                return

            if namespace is not None:
                closed_issues = [i for i in closed_issues if i.namespace == namespace]
                if not closed_issues:
                    typer.echo(
                        f"No closed issues in namespace '{namespace}' to archive."
                    )
                    return

            if days is not None:
                cutoff = datetime.now(timezone.utc) - timedelta(days=days)
                closed_issues = [
                    i
                    for i in closed_issues
                    if i.closed_at and i.closed_at.astimezone(timezone.utc) <= cutoff
                ]

                if not closed_issues:
                    typer.echo(f"No closed issues older than {days} days to archive.")
                    return

            partition = storage.archivable_partition(closed_issues)
            archivable = partition.archivable
            skipped = partition.skipped

            if not archivable:
                typer.echo("No issues can be archived.")
                if skipped:
                    typer.echo("\nSkipped issues:")
                    for issue, reason in skipped:
                        typer.echo(f"  {issue.full_id}: {reason}")
                return

            typer.echo(f"\nWill archive {len(archivable)} issue(s):")
            for issue in archivable[:10]:
                typer.echo(f"  {issue.full_id}: {issue.title}")
            if len(archivable) > 10:
                typer.echo(f"  ... and {len(archivable) - 10} more")

            if skipped:
                typer.echo(f"\nSkipping {len(skipped)} issue(s):")
                for issue, reason in skipped[:5]:
                    typer.echo(f"  {issue.full_id}: {reason}")
                if len(skipped) > 5:
                    typer.echo(f"  ... and {len(skipped) - 5} more")

            if dry_run:
                typer.echo("\n(dry run - no changes made)")
                return

            if not yes:
                typer.echo("")
                proceed = typer.confirm(
                    f"Archive {len(archivable)} issue(s)?",
                    default=False,
                )
                if not proceed:
                    typer.echo("Aborted.")
                    return

            archive_dir = Path(actual_dogcats_dir) / "archive"
            archive_dir.mkdir(exist_ok=True)
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
            archive_path = archive_dir / f"closed-{timestamp}.jsonl"

            stats = storage.archive({i.full_id for i in archivable}, archive_path)

            inbox_archived = _archive_inbox(
                actual_dogcats_dir,
                archive_dir,
                timestamp,
                namespace,
                days,
            )

            if is_json():
                output: dict[str, object] = {
                    "archived": stats.issues,
                    "skipped": len(skipped),
                    "archive_path": str(stats.archive_path),
                }
                if inbox_archived:
                    output["inbox_archived"] = inbox_archived
                typer.echo(orjson.dumps(output).decode())
            else:
                typer.echo(
                    f"\n✓ Archived {stats.issues} issue(s) to {stats.archive_path}"
                )
                if stats.dependencies:
                    typer.echo(f"  Including {stats.dependencies} dependency record(s)")
                if stats.links:
                    typer.echo(f"  Including {stats.links} link record(s)")
                if inbox_archived:
                    typer.echo(f"  Archived {inbox_archived} inbox proposal(s)")

        except typer.Exit:
            raise
        except Exception as e:
            echo_error(str(e))
            raise typer.Exit(1)
