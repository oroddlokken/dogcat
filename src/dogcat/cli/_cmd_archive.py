"""Archive command for dogcat CLI."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import orjson
import typer

from dogcat.models import Issue, Status, classify_record

from ._completions import complete_durations, complete_namespaces
from ._helpers import get_storage
from ._json_state import echo_error, is_json_output


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
        import re
        import tempfile
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

            # Get all closed issues (not tombstoned)
            all_issues = storage.list()
            closed_issues = [
                i
                for i in all_issues
                if i.status == Status.CLOSED and not i.is_tombstone()
            ]

            if not closed_issues:
                typer.echo("No closed issues to archive.")
                return

            # Apply namespace filter if specified
            if namespace is not None:
                closed_issues = [i for i in closed_issues if i.namespace == namespace]
                if not closed_issues:
                    typer.echo(
                        f"No closed issues in namespace '{namespace}' to archive."
                    )
                    return

            # Apply age filter if specified
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

            # Build set of IDs we want to archive
            candidate_ids = {i.full_id for i in closed_issues}

            # Determine which issues can actually be archived
            archivable: list[Issue] = []
            skipped: list[tuple[Issue, str]] = []

            for issue in closed_issues:
                # Check for open children
                children = storage.get_children(issue.full_id)
                open_children = [c for c in children if c.status != Status.CLOSED]
                if open_children:
                    skipped.append(
                        (
                            issue,
                            f"has {len(open_children)} open child(ren): "
                            + ", ".join(c.full_id for c in open_children[:3]),
                        ),
                    )
                    continue

                # Check if parent is still open (not being archived)
                if issue.parent and issue.parent not in candidate_ids:
                    parent_issue = storage.get(issue.parent)
                    parent_status = (
                        parent_issue.status.value if parent_issue else "unknown"
                    )
                    skipped.append(
                        (
                            issue,
                            f"parent {issue.parent} is not being archived"
                            f" (status: {parent_status})",
                        ),
                    )
                    continue

                # Check dependencies pointing to non-archived issues
                deps = storage.get_dependencies(issue.full_id)
                bad_deps = [d for d in deps if d.depends_on_id not in candidate_ids]
                if bad_deps:
                    skipped.append(
                        (
                            issue,
                            "depends on non-archived issue(s): "
                            + ", ".join(d.depends_on_id for d in bad_deps[:3]),
                        ),
                    )
                    continue

                # Check dependents (issues that depend on this one)
                dependents = storage.get_dependents(issue.full_id)
                bad_dependents = [
                    d for d in dependents if d.issue_id not in candidate_ids
                ]
                if bad_dependents:
                    skipped.append(
                        (
                            issue,
                            "is depended on by non-archived issue(s): "
                            + ", ".join(d.issue_id for d in bad_dependents[:3]),
                        ),
                    )
                    continue

                # Check links from this issue to non-archived issues
                links = storage.get_links(issue.full_id)
                bad_links = [link for link in links if link.to_id not in candidate_ids]
                if bad_links:
                    skipped.append(
                        (
                            issue,
                            "has links to non-archived issue(s): "
                            + ", ".join(link.to_id for link in bad_links[:3]),
                        ),
                    )
                    continue

                # Check incoming links from non-archived issues
                incoming_links = storage.get_incoming_links(issue.full_id)
                bad_incoming = [
                    link for link in incoming_links if link.from_id not in candidate_ids
                ]
                if bad_incoming:
                    skipped.append(
                        (
                            issue,
                            "has incoming links from non-archived issue(s): "
                            + ", ".join(link.from_id for link in bad_incoming[:3]),
                        ),
                    )
                    continue

                archivable.append(issue)

            # Update candidate_ids to only include actually archivable issues
            archivable_ids = {i.full_id for i in archivable}

            if not archivable:
                typer.echo("No issues can be archived.")
                if skipped:
                    typer.echo("\nSkipped issues:")
                    for issue, reason in skipped:
                        typer.echo(f"  {issue.full_id}: {reason}")
                return

            # Show summary
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

            # Confirm unless --yes flag is passed
            if not yes:
                typer.echo("")
                proceed = typer.confirm(
                    f"Archive {len(archivable)} issue(s)?",
                    default=False,
                )
                if not proceed:
                    typer.echo("Aborted.")
                    return

            # Create archive directory
            archive_dir = Path(actual_dogcats_dir) / "archive"
            archive_dir.mkdir(exist_ok=True)

            # Generate timestamp for archive file
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
            archive_filename = f"closed-{timestamp}.jsonl"
            archive_path = archive_dir / archive_filename

            # Split raw JSONL lines into archive vs keep buckets to preserve
            # the full append-only event history for both sets of issues.
            archived_lines: list[bytes] = []
            remaining_lines: list[bytes] = []
            archived_dep_count = 0
            archived_link_count = 0

            with storage.path.open("rb") as f:
                for raw_line in f:
                    stripped = raw_line.strip()
                    if not stripped:
                        continue

                    try:
                        data = orjson.loads(stripped)
                    except orjson.JSONDecodeError:
                        remaining_lines.append(raw_line)
                        continue

                    rtype = classify_record(data)
                    if rtype == "link":
                        if (
                            data["from_id"] in archivable_ids
                            and data["to_id"] in archivable_ids
                        ):
                            archived_lines.append(raw_line)
                            archived_link_count += 1
                        else:
                            remaining_lines.append(raw_line)
                    elif rtype == "dependency":
                        if (
                            data["issue_id"] in archivable_ids
                            and data["depends_on_id"] in archivable_ids
                        ):
                            archived_lines.append(raw_line)
                            archived_dep_count += 1
                        else:
                            remaining_lines.append(raw_line)
                    elif rtype == "event":
                        # Event record — follow issue_id
                        if data.get("issue_id") in archivable_ids:
                            archived_lines.append(raw_line)
                        else:
                            remaining_lines.append(raw_line)
                    else:
                        # Issue record — resolve full_id from raw dict
                        if "namespace" in data:
                            full_id = f"{data['namespace']}-{data['id']}"
                        elif "-" in str(data.get("id", "")):
                            full_id = data["id"]
                        else:
                            full_id = f"dc-{data['id']}"

                        if full_id in archivable_ids:
                            archived_lines.append(raw_line)
                        else:
                            remaining_lines.append(raw_line)

            # Write archived lines to archive file atomically
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=archive_dir,
                delete=False,
                suffix=".jsonl",
            ) as tmp_file:
                tmp_path = Path(tmp_file.name)

                try:
                    for line in archived_lines:
                        tmp_file.write(line if line.endswith(b"\n") else line + b"\n")
                    tmp_file.flush()
                except typer.Exit:
                    raise
                except Exception as e:
                    tmp_path.unlink(missing_ok=True)
                    msg = f"Failed to write archive file: {e}"
                    raise RuntimeError(msg) from e

            # Atomic rename to final archive path
            try:
                tmp_path.replace(archive_path)
            except OSError as e:
                tmp_path.unlink(missing_ok=True)
                msg = f"Failed to create archive file: {e}"
                raise RuntimeError(msg) from e

            # Rewrite main file with only remaining lines (preserving history)
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=storage.dogcats_dir,
                delete=False,
                suffix=".jsonl",
            ) as tmp_file:
                tmp_main_path = Path(tmp_file.name)

                try:
                    for line in remaining_lines:
                        tmp_file.write(line if line.endswith(b"\n") else line + b"\n")
                    tmp_file.flush()
                except typer.Exit:
                    raise
                except Exception as e:
                    tmp_main_path.unlink(missing_ok=True)
                    msg = f"Failed to rewrite storage file: {e}"
                    raise RuntimeError(msg) from e

            try:
                tmp_main_path.replace(storage.path)
            except OSError as e:
                tmp_main_path.unlink(missing_ok=True)
                msg = f"Failed to write storage file: {e}"
                raise RuntimeError(msg) from e

            # Update in-memory state
            storage.remove_archived(archivable_ids, len(remaining_lines))

            if is_json_output(json_output):
                output = {
                    "archived": len(archivable),
                    "skipped": len(skipped),
                    "archive_path": str(archive_path),
                }
                typer.echo(orjson.dumps(output).decode())
            else:
                typer.echo(f"\n✓ Archived {len(archivable)} issue(s) to {archive_path}")
                if archived_dep_count:
                    typer.echo(f"  Including {archived_dep_count} dependency record(s)")
                if archived_link_count:
                    typer.echo(f"  Including {archived_link_count} link record(s)")

        except typer.Exit:
            raise
        except Exception as e:
            echo_error(str(e))
            raise typer.Exit(1)
