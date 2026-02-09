"""Initialization commands for dogcat CLI."""

from __future__ import annotations

from pathlib import Path

import typer

from dogcat.config import set_issue_prefix
from dogcat.constants import DOGCATRC_FILENAME

from ._helpers import get_storage


def register(app: typer.Typer) -> None:
    """Register init and import-beads commands."""

    @app.command()
    def init(
        prefix: str | None = typer.Option(
            None,
            "--prefix",
            "-p",
            help="Issue prefix (default: auto-detect from directory name)",
        ),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
        external_dir: str | None = typer.Option(
            None,
            "--dir",
            help="External path for .dogcats directory (creates .dogcatrc)",
        ),
        use_existing: str | None = typer.Option(
            None,
            "--use-existing-folder",
            help="Link to an existing .dogcats directory (creates .dogcatrc)",
        ),
    ) -> None:
        """Initialize a new Dogcat repository.

        If --prefix is not specified, the prefix is auto-detected from the
        directory name (e.g., folder 'myproject' -> prefix 'myproject').

        Use --dir to place the .dogcats directory at an external location.
        This creates a .dogcatrc file in the current directory pointing to the
        specified path.

        Use --use-existing-folder to link to an existing .dogcats directory
        without reinitializing it. Only creates the .dogcatrc file.
        """
        if use_existing is not None and external_dir is not None:
            typer.echo(
                "Error: --dir and --use-existing-folder are mutually exclusive",
                err=True,
            )
            raise SystemExit(1)

        if use_existing is not None:
            existing_path = Path(use_existing)
            if not existing_path.is_dir():
                typer.echo(
                    f"Error: directory does not exist: {existing_path}",
                    err=True,
                )
                raise SystemExit(1)
            issues_file = existing_path / "issues.jsonl"
            if not issues_file.exists():
                typer.echo(
                    f"Error: not a valid dogcat directory "
                    f"(missing issues.jsonl): {existing_path}",
                    err=True,
                )
                raise SystemExit(1)
            rc_path = Path.cwd() / DOGCATRC_FILENAME
            rc_path.write_text(f"{use_existing}\n")
            typer.echo(f"✓ Created {rc_path} -> {use_existing}")
            typer.echo(f"\n✓ Linked to existing dogcat repository at {use_existing}")
            return

        if external_dir is not None:
            dogcats_dir = external_dir
            # Write .dogcatrc in current directory
            rc_path = Path.cwd() / DOGCATRC_FILENAME
            rc_path.write_text(f"{external_dir}\n")
            typer.echo(f"✓ Created {rc_path} -> {external_dir}")

        dogcats_path = Path(dogcats_dir)

        # Use storage with create_dir=True to initialize the directory
        get_storage(dogcats_dir, create_dir=True)

        # Create empty issues file if it doesn't exist
        issues_file = dogcats_path / "issues.jsonl"
        if not issues_file.exists():
            issues_file.touch()
            typer.echo(f"✓ Created {issues_file}")
        else:
            typer.echo(f"✓ {issues_file} already exists")

        # Determine and save the issue prefix
        if prefix is None:
            # Auto-detect from directory name
            project_dir = dogcats_path.resolve().parent
            prefix = project_dir.name
            # Sanitize: only allow alphanumeric and hyphens
            prefix = "".join(
                c if c.isalnum() or c == "-" else "-" for c in prefix.lower()
            )
            prefix = prefix.strip("-")
            if not prefix:
                prefix = "dc"  # Fallback to default

        # Strip trailing hyphens (the hyphen is added during ID generation)
        prefix = prefix.rstrip("-")

        # Save prefix to config
        set_issue_prefix(dogcats_dir, prefix)
        typer.echo(f"✓ Set issue prefix: {prefix}")

        typer.echo(f"\n✓ Dogcat repository initialized in {dogcats_dir}")
        typer.echo(f"  Issues will be named: {prefix}-<hash> (e.g., {prefix}-a3f2)")

    @app.command("import-beads")
    def import_beads(
        beads_jsonl: str = typer.Argument(..., help="Path to beads issues.jsonl file"),
        dogcats_dir: str = typer.Option(
            ".dogcats",
            help="Output directory for dogcat (will be created)",
        ),
        force: bool = typer.Option(
            False,
            "--force",
            "-f",
            help="Import into existing project (merge issues, keep current prefix)",
        ),
        verbose: bool = typer.Option(
            False,
            "--verbose",
            "-v",
            help="Show import progress",
        ),
    ) -> None:
        """Import issues from beads format into dogcat.

        By default, requires a fresh project (no existing issues.jsonl).
        Use --force to import into an existing project
        (merges issues, skips duplicates).
        """
        try:
            from dogcat.migrate import migrate_from_beads

            # Check if dogcat project already exists
            dogcats_path = Path(dogcats_dir)
            issues_file = dogcats_path / "issues.jsonl"
            has_existing_project = issues_file.exists()
            has_existing_data = has_existing_project and issues_file.stat().st_size > 0

            if has_existing_data:
                if force:
                    # Merge mode: import into existing project
                    if verbose:
                        typer.echo("Importing into existing project (merge mode)...")
                else:
                    typer.echo(
                        "Error: .dogcats/issues.jsonl already exists.\n"
                        "  Use --force to import into existing project (merge)",
                        err=True,
                    )
                    raise typer.Exit(1)

            # When --force is used on existing project, merge (even if empty)
            merge_mode = force and has_existing_project

            # Perform import
            migrated, failed, skipped = migrate_from_beads(
                beads_jsonl,
                dogcats_dir,
                verbose=verbose,
                merge=merge_mode,
            )

            # Only set prefix if this is a fresh import (not merging)
            if migrated > 0 and not merge_mode:
                storage = get_storage(dogcats_dir)
                all_issues = storage.list()
                if all_issues:
                    # Sort by created_at descending to get newest
                    sorted_issues = sorted(
                        all_issues,
                        key=lambda i: i.created_at,
                        reverse=True,
                    )
                    newest_issue = sorted_issues[0]
                    detected_prefix = newest_issue.namespace
                    if detected_prefix:
                        set_issue_prefix(dogcats_dir, detected_prefix)
                        typer.echo(f"✓ Set issue prefix: {detected_prefix}")

            typer.echo("\n✓ Import complete!")
            typer.echo(f"  Imported: {migrated} issues")
            if skipped > 0:
                typer.echo(f"  Skipped (already exist): {skipped} issues")
            if failed > 0:
                typer.echo(f"  Failed: {failed} issues")

        except FileNotFoundError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)
        except ValueError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)
        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)
