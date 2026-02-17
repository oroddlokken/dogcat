"""Demo command for dogcat CLI."""

from __future__ import annotations

from pathlib import Path

import typer

from ._helpers import get_storage


def register(app: typer.Typer) -> None:
    """Register demo command."""

    @app.command()
    def demo(
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
        force: bool = typer.Option(
            False,
            "--force",
            "-f",
            help="Force creation even if dogcats exists (dangerous)",
        ),
    ) -> None:
        """Generate demo issues for testing and exploration.

        Creates ~50 sample issues including epics, features, tasks, bugs, stories,
        and questions with various priorities, parent-child relationships, dependencies,
        labels, external references (Jira-style), and comments.

        The demo simulates a realistic team environment with:
        - Product Owner, Project Manager, Tech Lead, and Developers
        - Multiple epics with features, stories, and tasks
        - Bugs with reproduction steps and discussion
        - Questions with decisions and rationale
        - Full metadata: created_by, updated_by, closed_by, deleted_by

        Safety: By default, refuses to run if .dogcats already exists. Use --force
        to override (will add to existing issues).
        """
        from dogcat.demo import generate_demo_issues

        dogcats_path = Path(dogcats_dir)

        # Safety check: refuse to run if dogcats exists (unless --force)
        if dogcats_path.exists() and not force:
            typer.echo(
                "Error: .dogcats directory already exists. This command is for new "
                "projects only.",
                err=True,
            )
            typer.echo(
                "Use --force to add demo issues to an existing "
                "project (not recommended).",
                err=True,
            )
            raise typer.Exit(1)

        try:
            storage = get_storage(dogcats_dir, create_dir=True)
            typer.echo("Creating demo issues...")

            created_issues = generate_demo_issues(storage, dogcats_dir)

            typer.echo(f"\n✓ Created {len(created_issues)} demo issues")
            typer.echo("  - 4 epics (Platform, UX, Performance, Analytics)")
            typer.echo("  - Features, stories, tasks, bugs, chores, and questions")
            typer.echo("  - With parent-child relationships and dependencies")
            typer.echo("  - Labels, external refs (Jira-style), and comments")
            typer.echo(
                "  - Full metadata: created_by, updated_by, closed_by, deleted_by",
            )

            from dogcat.demo import generate_demo_inbox

            inbox_count = generate_demo_inbox(dogcats_dir)
            typer.echo(f"\n✓ Created {inbox_count} demo inbox proposals")
            typer.echo("  - 3 open, 2 closed (accepted + rejected), 1 tombstoned")

            typer.echo("\nTry: dcat list --table")
            typer.echo("     dcat inbox list")

        except typer.Exit:
            raise
        except Exception as e:
            typer.echo(f"Error creating demo issues: {e}", err=True)
            raise typer.Exit(1)
