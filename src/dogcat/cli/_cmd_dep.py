"""Dependency and link commands for dogcat CLI."""

from __future__ import annotations

import orjson
import typer

from ._completions import (
    complete_dep_types,
    complete_issue_ids,
    complete_link_types,
    complete_subcommands,
)
from ._helpers import get_storage
from ._json_state import echo_error, is_json_output


def register(app: typer.Typer) -> None:
    """Register dep and link commands."""

    @app.command("dep")
    def dependency(
        issue_id: str = typer.Argument(
            ...,
            help="Issue ID",
            autocompletion=complete_issue_ids,
        ),
        subcommand: str = typer.Argument(
            ...,
            help="add, remove, or list",
            autocompletion=complete_subcommands,
        ),
        depends_on_id: str = typer.Option(
            None,
            "--depends-on",
            "-d",
            help="Issue ID it depends on",
            autocompletion=complete_issue_ids,
        ),
        dep_type: str = typer.Option(
            "blocks",
            "--type",
            "-t",
            help="Dependency type",
            autocompletion=complete_dep_types,
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        by: str = typer.Option(None, "--by", help="Who is making this change"),
        all_namespaces: bool = typer.Option(  # noqa: ARG001
            False,
            "--all-namespaces",
            "--all-ns",
            "-A",
            hidden=True,
        ),
        namespace: str | None = typer.Option(  # noqa: ARG001
            None,
            "--namespace",
            hidden=True,
        ),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Manage issue dependencies."""
        try:
            storage = get_storage(dogcats_dir)

            if subcommand == "add":
                if not depends_on_id:
                    echo_error("--depends-on required for add")
                    raise typer.Exit(1)

                dep = storage.add_dependency(
                    issue_id,
                    depends_on_id,
                    dep_type,
                    created_by=by,
                )
                typer.echo(
                    f"✓ Added dependency: {depends_on_id} "
                    f"{dep.dep_type.value} {issue_id}",
                )

            elif subcommand == "remove":
                if not depends_on_id:
                    echo_error("--depends-on required for remove")
                    raise typer.Exit(1)

                storage.remove_dependency(issue_id, depends_on_id)
                typer.echo(f"✓ Removed dependency: {issue_id} {depends_on_id}")

            elif subcommand == "list":
                deps = storage.get_dependencies(issue_id)

                if is_json_output(json_output):
                    output = [
                        {
                            "issue_id": dep.issue_id,
                            "depends_on_id": dep.depends_on_id,
                            "type": dep.dep_type.value,
                        }
                        for dep in deps
                    ]
                    typer.echo(orjson.dumps(output).decode())
                else:
                    if deps:
                        for dep in deps:
                            typer.echo(
                                f"  → {dep.depends_on_id} ({dep.dep_type.value})",
                            )
                    else:
                        typer.echo("No dependencies")
            else:
                echo_error(f"Unknown subcommand: {subcommand}")
                raise typer.Exit(1)

        except ValueError as e:
            echo_error(str(e))
            raise typer.Exit(1)
        except typer.Exit:
            raise
        except Exception as e:
            echo_error(str(e))
            raise typer.Exit(1)

    @app.command("link")
    def link_command(
        issue_id: str = typer.Argument(
            ...,
            help="Issue ID",
            autocompletion=complete_issue_ids,
        ),
        subcommand: str = typer.Argument(
            ...,
            help="add, remove, or list",
            autocompletion=complete_subcommands,
        ),
        related_id: str = typer.Option(
            None,
            "--related",
            "-r",
            help="Issue ID to link to",
            autocompletion=complete_issue_ids,
        ),
        link_type: str = typer.Option(
            "relates_to",
            "--type",
            "-t",
            help="Link type",
            autocompletion=complete_link_types,
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        by: str = typer.Option(None, "--by", help="Who is making this change"),
        all_namespaces: bool = typer.Option(  # noqa: ARG001
            False,
            "--all-namespaces",
            "--all-ns",
            "-A",
            hidden=True,
        ),
        namespace: str | None = typer.Option(  # noqa: ARG001
            None,
            "--namespace",
            hidden=True,
        ),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Manage issue links (general relationships)."""
        try:
            storage = get_storage(dogcats_dir)

            if subcommand == "add":
                if not related_id:
                    echo_error("--related required for add")
                    raise typer.Exit(1)

                link = storage.add_link(
                    issue_id,
                    related_id,
                    link_type,
                    created_by=by,
                )
                typer.echo(
                    f"✓ Added link: {issue_id} {link.link_type} {related_id}",
                )

            elif subcommand == "remove":
                if not related_id:
                    echo_error("--related required for remove")
                    raise typer.Exit(1)

                storage.remove_link(issue_id, related_id)
                typer.echo(f"✓ Removed link: {issue_id} {related_id}")

            elif subcommand == "list":
                links = storage.get_links(issue_id)
                incoming = storage.get_incoming_links(issue_id)

                if is_json_output(json_output):
                    output = {
                        "outgoing": [
                            {
                                "from_id": link.from_id,
                                "to_id": link.to_id,
                                "type": link.link_type,
                            }
                            for link in links
                        ],
                        "incoming": [
                            {
                                "from_id": link.from_id,
                                "to_id": link.to_id,
                                "type": link.link_type,
                            }
                            for link in incoming
                        ],
                    }
                    typer.echo(orjson.dumps(output).decode())
                else:
                    if links or incoming:
                        if links:
                            typer.echo("Outgoing links:")
                            for link in links:
                                typer.echo(f"  → {link.to_id} ({link.link_type})")
                        if incoming:
                            typer.echo("Incoming links:")
                            for link in incoming:
                                typer.echo(f"  ← {link.from_id} ({link.link_type})")
                    else:
                        typer.echo("No links")
            else:
                echo_error(f"Unknown subcommand: {subcommand}")
                raise typer.Exit(1)

        except ValueError as e:
            echo_error(str(e))
            raise typer.Exit(1)
        except typer.Exit:
            raise
        except Exception as e:
            echo_error(str(e))
            raise typer.Exit(1)
