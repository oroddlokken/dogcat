"""Label and namespace commands for dogcat CLI."""

from __future__ import annotations

from typing import Any

import orjson
import typer

from dogcat.config import get_issue_prefix, load_config

from ._completions import complete_issue_ids, complete_labels, complete_subcommands
from ._helpers import get_storage
from ._json_state import echo_error, is_json_output


def register(app: typer.Typer) -> None:
    """Register label and namespace commands."""

    @app.command()
    def label(
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
        label_name: str = typer.Option(
            None,
            "--label",
            "-l",
            help="Label to add/remove",
            autocompletion=complete_labels,
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        by: str = typer.Option(None, "--by", help="Who is managing labels"),
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
        """Manage issue labels."""
        try:
            is_json_output(json_output)  # sync local flag for echo_error
            storage = get_storage(dogcats_dir)

            if subcommand == "add":
                if not label_name:
                    echo_error("--label required for add")
                    raise typer.Exit(1)

                issue = storage.get(issue_id)
                if issue is None:
                    echo_error(f"Issue {issue_id} not found")
                    raise typer.Exit(1)

                if label_name not in issue.labels:
                    issue.labels.append(label_name)
                    updates: dict[str, Any] = {"labels": issue.labels}
                    if by:
                        updates["updated_by"] = by
                    storage.update(issue_id, updates)
                    typer.echo(f"✓ Added label '{label_name}' to {issue.full_id}")
                else:
                    typer.echo(f"Label '{label_name}' already on {issue.full_id}")

            elif subcommand == "remove":
                if not label_name:
                    echo_error("--label required for remove")
                    raise typer.Exit(1)

                issue = storage.get(issue_id)
                if issue is None:
                    echo_error(f"Issue {issue_id} not found")
                    raise typer.Exit(1)

                if label_name in issue.labels:
                    issue.labels.remove(label_name)
                    updates: dict[str, Any] = {"labels": issue.labels}
                    if by:
                        updates["updated_by"] = by
                    storage.update(issue_id, updates)
                    typer.echo(f"✓ Removed label '{label_name}' from {issue.full_id}")
                else:
                    typer.echo(f"Label '{label_name}' not on {issue.full_id}")

            elif subcommand == "list":
                issue = storage.get(issue_id)
                if issue is None:
                    echo_error(f"Issue {issue_id} not found")
                    raise typer.Exit(1)

                if is_json_output(json_output):
                    typer.echo(orjson.dumps(issue.labels).decode())
                else:
                    if issue.labels:
                        for lbl in issue.labels:
                            typer.echo(f"  {lbl}")
                    else:
                        typer.echo("No labels")
            else:
                echo_error(f"Unknown subcommand: {subcommand}")
                raise typer.Exit(1)

        except typer.Exit:
            raise
        except Exception as e:
            echo_error(str(e))
            raise typer.Exit(1)

    @app.command("labels")
    def labels_list(
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """List all labels used across issues with counts."""
        try:
            storage = get_storage(dogcats_dir)
            issues = storage.list()

            label_counts: dict[str, int] = {}
            for issue in issues:
                if issue.is_tombstone():
                    continue
                for lbl in issue.labels:
                    label_counts[lbl] = label_counts.get(lbl, 0) + 1

            if is_json_output(json_output):
                result = [
                    {"label": lbl, "count": count}
                    for lbl, count in sorted(label_counts.items())
                ]
                typer.echo(orjson.dumps(result).decode())
            else:
                if label_counts:
                    for lbl, count in sorted(label_counts.items()):
                        typer.echo(f"  {lbl} ({count})")
                else:
                    typer.echo("No labels found")

        except typer.Exit:
            raise
        except Exception as e:
            echo_error(str(e))
            raise typer.Exit(1)

    @app.command("namespaces")
    def namespaces_list(
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """List all namespaces used across issues with counts."""
        try:
            storage = get_storage(dogcats_dir)
            actual_dogcats_dir = str(storage.dogcats_dir)
            issues = storage.list()

            ns_counts: dict[str, int] = {}
            for issue in issues:
                if issue.is_tombstone():
                    continue
                ns_counts[issue.namespace] = ns_counts.get(issue.namespace, 0) + 1

            # Determine annotations
            primary = get_issue_prefix(actual_dogcats_dir)
            config = load_config(actual_dogcats_dir)
            visible: list[str] | None = config.get("visible_namespaces")
            hidden: list[str] | None = config.get("hidden_namespaces")

            def _annotation(ns: str) -> str:
                if ns == primary:
                    return "primary"
                if visible:
                    return "visible" if ns in visible else "hidden"
                if hidden:
                    return "hidden" if ns in hidden else "visible"
                return ""

            if is_json_output(json_output):
                result = [
                    {
                        "namespace": ns,
                        "count": count,
                        "visibility": _annotation(ns) or "visible",
                    }
                    for ns, count in sorted(ns_counts.items())
                ]
                typer.echo(orjson.dumps(result).decode())
            else:
                if ns_counts:
                    for ns, count in sorted(ns_counts.items()):
                        ann = _annotation(ns)
                        suffix = f" ({ann})" if ann else ""
                        typer.echo(f"  {ns} ({count}){suffix}")
                else:
                    typer.echo("No namespaces found")

        except typer.Exit:
            raise
        except Exception as e:
            echo_error(str(e))
            raise typer.Exit(1)
