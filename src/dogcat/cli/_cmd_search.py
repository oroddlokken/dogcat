"""Search command for dogcat CLI."""

from __future__ import annotations

import re

import orjson
import typer

from ._completions import (
    complete_labels,
    complete_namespaces,
    complete_owners,
    complete_priorities,
    complete_statuses,
    complete_types,
)
from ._formatting import format_issue_brief
from ._helpers import apply_common_filters, get_storage
from ._json_state import echo_error, is_json_output


def _extract_snippet(text: str, pattern: re.Pattern[str], context: int = 40) -> str:
    """Extract a context snippet around the first match in text."""
    match = pattern.search(text)
    if not match:
        return ""
    start = max(0, match.start() - context)
    end = min(len(text), match.end() + context)
    snippet = text[start:end].replace("\n", " ")
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{snippet}{suffix}"


def register(app: typer.Typer) -> None:
    """Register search commands."""

    @app.command()
    def search(
        query: str = typer.Argument(
            ...,
            help="Search query (searches all text fields)",
        ),
        case_sensitive: bool = typer.Option(
            False,
            "--case-sensitive",
            "-c",
            help="Case-sensitive search",
        ),
        status: str = typer.Option(
            None,
            "--status",
            "-s",
            help="Filter by status",
            autocompletion=complete_statuses,
        ),
        issue_type: str = typer.Option(
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
            help="Show issues from all namespaces",
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Search issues by text content across all fields.

        Searches for the query string in issue titles, descriptions,
        notes, acceptance criteria, design, and comments.
        By default, search is case-insensitive.

        Examples:
            dcat search "login"              # Find issues mentioning login
            dcat search "bug" --type bug     # Find bug issues mentioning bug
            dcat search "API" -c             # Case-sensitive search
        """
        from dogcat.models import Issue

        try:
            storage = get_storage(dogcats_dir)
            issues = storage.list()

            # Apply status/type filters first
            if status:
                issues = [i for i in issues if i.status.value == status]
            if issue_type:
                issues = [i for i in issues if i.issue_type.value == issue_type]

            # Exclude closed/tombstone by default
            if not status:
                issues = [
                    i for i in issues if i.status.value not in ("closed", "tombstone")
                ]

            # Apply common filters (namespace, priority, label, owner)
            issues = apply_common_filters(
                issues,
                priority=priority,
                label=label,
                owner=owner,
                namespace=namespace,
                all_namespaces=all_namespaces,
                dogcats_dir=str(storage.dogcats_dir),
                storage=storage,
            )

            # Search across all text fields
            flags = 0 if case_sensitive else re.IGNORECASE
            pattern = re.compile(re.escape(query), flags)

            # Fields to search: (attribute_name, display_label)
            search_fields = [
                ("title", "Title"),
                ("description", "Description"),
                ("notes", "Notes"),
                ("acceptance", "Acceptance"),
                ("design", "Design"),
            ]

            matches: list[tuple[Issue, list[tuple[str, str]]]] = []
            for issue in issues:
                matched_fields: list[tuple[str, str]] = []
                for attr, label in search_fields:
                    text = getattr(issue, attr, None)
                    if text and pattern.search(text):
                        snippet = _extract_snippet(text, pattern)
                        matched_fields.append((label, snippet))
                # Also search comments
                for comment in issue.comments:
                    if comment.text and pattern.search(comment.text):
                        snippet = _extract_snippet(comment.text, pattern)
                        matched_fields.append(("Comment", snippet))
                        break  # One comment match is enough
                if matched_fields:
                    matches.append((issue, matched_fields))

            # Sort by priority
            matches = sorted(matches, key=lambda m: (m[0].priority, m[0].id))

            if is_json_output(json_output):
                from dogcat.models import issue_to_dict

                output = [issue_to_dict(issue) for issue, _ in matches]
                typer.echo(orjson.dumps(output).decode())
            else:
                if not matches:
                    typer.echo(f"No issues found matching '{query}'")
                else:
                    typer.echo(f"Found {len(matches)} issue(s) matching '{query}':\n")
                    for issue, matched_fields in matches:
                        typer.echo(format_issue_brief(issue))
                        for field_name, snippet in matched_fields:
                            if field_name == "Title":
                                continue  # Title is already visible
                            styled_field = typer.style(
                                f"  {field_name}:",
                                fg="bright_black",
                            )
                            typer.echo(f"{styled_field} {snippet}")

        except typer.Exit:
            raise
        except Exception as e:
            echo_error(str(e))
            raise typer.Exit(1)
