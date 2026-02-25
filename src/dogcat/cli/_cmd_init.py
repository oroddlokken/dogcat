"""Initialization commands for dogcat CLI."""

from __future__ import annotations

from pathlib import Path

import orjson
import typer

from dogcat.config import load_shared_config, save_config, set_issue_prefix
from dogcat.constants import DOGCATRC_FILENAME

from ._helpers import get_storage
from ._json_state import echo_error, is_json_output


def _ensure_gitignore_entry(entry: str, *, quiet: bool = False) -> None:
    """Add an entry to .gitignore if not already present.

    Args:
        entry: The gitignore pattern to add.
        quiet: If True, suppress output messages.
    """
    gitignore = Path(".gitignore")
    if gitignore.exists():
        content = gitignore.read_text()
        lines = content.splitlines()
        if any(ln.strip() == entry for ln in lines):
            if not quiet:
                typer.echo(f"✓ {entry} already in .gitignore")
            return
        with gitignore.open("a") as f:
            if content and not content.endswith("\n"):
                f.write("\n")
            f.write(f"{entry}\n")
        if not quiet:
            typer.echo(f"✓ Added {entry} to .gitignore")
    else:
        gitignore.write_text(f"{entry}\n")
        if not quiet:
            typer.echo(f"✓ Created .gitignore with {entry}")


def register(app: typer.Typer) -> None:
    """Register init and import-beads commands."""

    @app.command()
    def init(
        namespace: str | None = typer.Option(
            None,
            "--namespace",
            "-n",
            help="Issue namespace (default: auto-detect from directory name)",
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
        no_git: bool = typer.Option(
            False,
            "--no-git",
            help=(
                "Disable git tracking"
                " (sets git_tracking=false, adds .dogcats/ to .gitignore)"
            ),
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """Initialize a new Dogcat repository.

        If --namespace is not specified, the namespace is auto-detected from
        the directory name (e.g., folder 'myproject' -> namespace 'myproject').

        Use --dir to place the .dogcats directory at an external location.
        This creates a .dogcatrc file in the current directory pointing to the
        specified path.

        Use --use-existing-folder to link to an existing .dogcats directory
        without reinitializing it. Only creates the .dogcatrc file.
        """
        if use_existing is not None and external_dir is not None:
            echo_error("--dir and --use-existing-folder are mutually exclusive")
            raise SystemExit(1)

        if use_existing is not None:
            existing_path = Path(use_existing)
            if not existing_path.is_dir():
                echo_error(f"directory does not exist: {existing_path}")
                raise SystemExit(1)
            issues_file = existing_path / "issues.jsonl"
            if not issues_file.exists():
                echo_error(
                    f"not a valid dogcat directory "
                    f"(missing issues.jsonl): {existing_path}"
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

        # Determine and save the namespace
        if namespace is None:
            # Auto-detect from directory name
            project_dir = dogcats_path.resolve().parent
            namespace = project_dir.name
            # Sanitize: only allow alphanumeric and hyphens
            namespace = "".join(
                c if c.isalnum() or c == "-" else "-" for c in namespace.lower()
            )
            namespace = namespace.strip("-")
            if not namespace:
                namespace = "dc"  # Fallback to default

        # Strip trailing hyphens (the hyphen is added during ID generation)
        namespace = namespace.rstrip("-")

        # Save namespace to config
        set_issue_prefix(dogcats_dir, namespace)
        typer.echo(f"✓ Set namespace: {namespace}")

        # Always add config.local.toml to .gitignore (machine-specific settings)
        _ensure_gitignore_entry(
            ".dogcats/config.local.toml",
            quiet=False,
        )

        # Always add lockfile to .gitignore (never committed)
        _ensure_gitignore_entry(
            ".dogcats/.issues.lock",
            quiet=False,
        )

        if no_git:
            config = load_shared_config(dogcats_dir)
            config["git_tracking"] = False
            save_config(dogcats_dir, config)
            typer.echo("✓ Disabled git tracking (git_tracking = false)")

            _ensure_gitignore_entry(".dogcats/", quiet=False)

        if is_json_output(json_output):
            output = {
                "status": "initialized",
                "namespace": namespace,
                "path": str(dogcats_path.resolve()),
            }
            typer.echo(orjson.dumps(output).decode())
        else:
            typer.echo(f"\n✓ Dogcat repository initialized in {dogcats_dir}")
            typer.echo(
                f"  Issues will be named: {namespace}-<hash> (e.g., {namespace}-a3f2)"
            )

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
                    echo_error(
                        ".dogcats/issues.jsonl already exists. "
                        "Use --force to import into existing project (merge)"
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
                        typer.echo(f"✓ Set namespace: {detected_prefix}")

            typer.echo("\n✓ Import complete!")
            typer.echo(f"  Imported: {migrated} issues")
            if skipped > 0:
                typer.echo(f"  Skipped (already exist): {skipped} issues")
            if failed > 0:
                typer.echo(f"  Failed: {failed} issues")

        except FileNotFoundError as e:
            echo_error(str(e))
            raise typer.Exit(1)
        except ValueError as e:
            echo_error(str(e))
            raise typer.Exit(1)
        except typer.Exit:
            raise
        except Exception as e:
            echo_error(str(e))
            raise typer.Exit(1)
