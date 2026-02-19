"""Rename-namespace command for dogcat CLI."""

from __future__ import annotations

import orjson
import typer

from dogcat.config import (
    get_issue_prefix,
    load_config,
    save_config,
    set_issue_prefix,
)

from ._completions import complete_namespaces
from ._helpers import get_storage
from ._json_state import echo_error, is_json_output


def register(app: typer.Typer) -> None:
    """Register the rename-namespace command."""

    @app.command("rename-namespace")
    def rename_namespace(
        old_namespace: str = typer.Argument(
            ...,
            help="Namespace to rename from",
            autocompletion=complete_namespaces,
        ),
        new_namespace: str = typer.Argument(
            ...,
            help="New namespace name",
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        by: str = typer.Option(None, "--by", help="Who is performing the rename"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Rename a namespace, updating all issues and references."""
        try:
            is_json_output(json_output)  # sync local flag for echo_error

            if old_namespace == new_namespace:
                echo_error("Old and new namespace are the same")
                raise typer.Exit(1)

            storage = get_storage(dogcats_dir)
            actual_dir = str(storage.dogcats_dir)

            # Rename issues
            renamed_issues = storage.rename_namespace(
                old_namespace, new_namespace, updated_by=by
            )

            # Rename inbox proposals
            inbox_count = 0
            try:
                from dogcat.inbox import InboxStorage

                inbox = InboxStorage(dogcats_dir=actual_dir)
                inbox_count = inbox.rename_namespace(old_namespace, new_namespace)
            except Exception:
                pass  # inbox may not exist

            # Update config references
            config = load_config(actual_dir)
            config_changed = False

            # Update primary namespace
            primary = get_issue_prefix(actual_dir)
            if primary == old_namespace:
                set_issue_prefix(actual_dir, new_namespace)
                config = load_config(actual_dir)  # reload after set_issue_prefix
                config_changed = True

            # Update visible_namespaces
            visible: list[str] | None = config.get("visible_namespaces")
            if visible and old_namespace in visible:
                visible[visible.index(old_namespace)] = new_namespace
                config_changed = True

            # Update hidden_namespaces
            hidden: list[str] | None = config.get("hidden_namespaces")
            if hidden and old_namespace in hidden:
                hidden[hidden.index(old_namespace)] = new_namespace
                config_changed = True

            if config_changed:
                save_config(actual_dir, config)

            if is_json_output(json_output):
                result = {
                    "old_namespace": old_namespace,
                    "new_namespace": new_namespace,
                    "issues_renamed": len(renamed_issues),
                    "proposals_renamed": inbox_count,
                    "config_updated": config_changed,
                }
                typer.echo(orjson.dumps(result).decode())
            else:
                typer.echo(f"✓ Renamed namespace '{old_namespace}' → '{new_namespace}'")
                typer.echo(f"  {len(renamed_issues)} issue(s) renamed")
                if inbox_count:
                    typer.echo(f"  {inbox_count} proposal(s) renamed")
                if config_changed:
                    typer.echo("  Config updated")

        except typer.Exit:
            raise
        except Exception as e:
            echo_error(str(e))
            raise typer.Exit(1)
