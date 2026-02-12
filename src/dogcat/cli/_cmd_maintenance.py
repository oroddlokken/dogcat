"""Maintenance commands for dogcat CLI."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import orjson
import typer

from dogcat.config import get_config_path, get_issue_prefix, load_config, save_config

from ._formatting import format_issue_brief
from ._helpers import get_default_operator, get_storage
from ._validate import detect_concurrent_edits, validate_jsonl


def register(app: typer.Typer) -> None:
    """Register maintenance commands."""

    @app.command()
    def prune(
        dry_run: bool = typer.Option(
            False,
            "--dry-run",
            "-n",
            help="Show what would be removed without actually removing",
        ),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Remove tombstoned (deleted) issues from storage permanently.

        This command permanently removes issues with tombstone status from the
        storage file. Use --dry-run to preview what would be removed.
        """
        try:
            storage = get_storage(dogcats_dir)
            issues = storage.list()

            # Find tombstoned issues
            tombstones = [i for i in issues if i.status.value == "tombstone"]

            if not tombstones:
                typer.echo("No tombstoned issues to prune")
                return

            if dry_run:
                typer.echo(f"Would remove {len(tombstones)} tombstoned issue(s):")
                for issue in tombstones:
                    typer.echo(f"  ☠ {issue.full_id}: {issue.title}")
            else:
                # Remove tombstones from storage using public API
                pruned_ids = storage.prune_tombstones()
                typer.echo(f"✓ Pruned {len(pruned_ids)} tombstoned issue(s)")

        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
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
        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)

    @app.command()
    def label(
        issue_id: str = typer.Argument(..., help="Issue ID"),
        subcommand: str = typer.Argument(..., help="add, remove, or list"),
        label_name: str = typer.Option(
            None,
            "--label",
            "-l",
            help="Label to add/remove",
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        by: str = typer.Option(None, "--by", help="Who is managing labels"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Manage issue labels."""
        try:
            storage = get_storage(dogcats_dir)

            if subcommand == "add":
                if not label_name:
                    typer.echo("Error: --label required for add", err=True)
                    raise typer.Exit(1)

                issue = storage.get(issue_id)
                if issue is None:
                    typer.echo(f"Issue {issue_id} not found", err=True)
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
                    typer.echo("Error: --label required for remove", err=True)
                    raise typer.Exit(1)

                issue = storage.get(issue_id)
                if issue is None:
                    typer.echo(f"Issue {issue_id} not found", err=True)
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
                    typer.echo(f"Issue {issue_id} not found", err=True)
                    raise typer.Exit(1)

                if json_output:
                    typer.echo(orjson.dumps(issue.labels).decode())
                else:
                    if issue.labels:
                        for lbl in issue.labels:
                            typer.echo(f"  {lbl}")
                    else:
                        typer.echo("No labels")
            else:
                typer.echo(f"Unknown subcommand: {subcommand}", err=True)
                raise typer.Exit(1)

        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
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

            if json_output:
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

        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)

    @app.command()
    def doctor(
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        fix: bool = typer.Option(False, "--fix", help="Automatically fix issues"),
        post_merge: bool = typer.Option(
            False,
            "--post-merge",
            help="Detect same-issue concurrent edits from the latest merge",
        ),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Diagnose dogcat installation, data integrity, and configuration.

        Performs health checks on the installation, validates JSONL data
        integrity (fields, references, cycles), and suggests fixes.
        Use --post-merge to detect concurrent edits after a git merge.
        Exit code 0 = all OK, 1 = issues found.
        """
        import shutil

        checks: dict[str, dict[str, Any]] = {}
        all_passed = True
        validation_details: list[dict[str, str]] = []

        # Check 1: .dogcats directory exists
        dogcats_path = Path(dogcats_dir)
        checks["dogcats_dir"] = {
            "description": f"{dogcats_dir}/ directory exists",
            "passed": dogcats_path.exists(),
            "fix": f"Run 'dcat init' to create {dogcats_dir}",
        }
        if not checks["dogcats_dir"]["passed"]:
            all_passed = False

        # Check 2: issues.jsonl exists and is valid JSON
        issues_file = dogcats_path / "issues.jsonl"
        issues_valid = False
        if issues_file.exists():
            try:
                with issues_file.open() as f:
                    for line in f:
                        if line.strip():
                            orjson.loads(line)
                issues_valid = True
            except (OSError, orjson.JSONDecodeError):
                pass

        checks["issues_jsonl"] = {
            "description": f"{dogcats_dir}/issues.jsonl is valid JSON",
            "passed": issues_file.exists() and issues_valid,
            "fix": "Restore from backup or run 'dcat init' to reset",
        }
        if not checks["issues_jsonl"]["passed"]:
            all_passed = False

        # Check 2a: config.toml exists
        config_path = get_config_path(dogcats_dir)
        config_exists = config_path.exists()

        if fix and not config_exists and dogcats_path.exists():
            detected_prefix = get_issue_prefix(dogcats_dir)
            save_config(dogcats_dir, {"issue_prefix": detected_prefix})
            config_exists = True
            typer.echo(
                f"Fixed: Created {config_path.name}"
                f" with issue_prefix='{detected_prefix}'",
            )

        checks["config_toml"] = {
            "description": f"{dogcats_dir}/config.toml exists",
            "fail_description": f"{dogcats_dir}/config.toml not found",
            "passed": config_exists,
            "fix": "Run 'dcat doctor --fix' to create config.toml",
        }
        if not checks["config_toml"]["passed"]:
            all_passed = False

        # Check 2b: issue_prefix is set and non-empty in config
        # Only check if config.toml exists (skip if Check 2a failed)
        if config_exists:
            config = load_config(dogcats_dir)
            prefix_value = config.get("issue_prefix")
            prefix_ok = bool(prefix_value)

            if fix and not prefix_ok:
                detected_prefix = get_issue_prefix(dogcats_dir)
                config["issue_prefix"] = detected_prefix
                save_config(dogcats_dir, config)
                prefix_ok = True
                typer.echo(
                    f"Fixed: Set issue_prefix='{detected_prefix}' in config.toml",
                )

            checks["config_issue_prefix"] = {
                "description": "issue_prefix is configured in config.toml",
                "fail_description": "issue_prefix is not configured in config.toml",
                "passed": prefix_ok,
                "fix": "Run 'dcat config set issue_prefix <prefix>'",
            }
            if not prefix_ok:
                all_passed = False

        # Check 3: Deep data validation (fields, refs, cycles)
        data_valid = True
        data_error_count = 0
        if issues_file.exists() and issues_valid:
            validation_details = validate_jsonl(issues_file)
            data_error_count = sum(
                1 for e in validation_details if e["level"] == "error"
            )
            if data_error_count > 0:
                data_valid = False

        checks["data_integrity"] = {
            "description": "Data integrity (fields, references, cycles)",
            "fail_description": (f"Data integrity: {data_error_count} error(s) found"),
            "passed": data_valid,
            "fix": "Review errors above and fix issues.jsonl",
        }
        if not data_valid:
            all_passed = False

        # Check 4: dcat in PATH
        dogcat_in_path = bool(shutil.which("dcat"))
        checks["dogcat_in_path"] = {
            "description": "dcat command is available in PATH",
            "passed": dogcat_in_path,
            "fix": "Ensure dogcat is installed and dcat is in PATH",
        }
        if not checks["dogcat_in_path"]["passed"]:
            all_passed = False

        # Check 6: Issue ID uniqueness
        issue_ids_unique = True
        if issues_file.exists() and issues_valid:
            try:
                storage = get_storage(dogcats_dir)
                issue_ids_unique = storage.check_id_uniqueness()
            except Exception:
                issue_ids_unique = False

        checks["issue_ids"] = {
            "description": "All issue IDs are unique",
            "passed": issue_ids_unique,
            "fix": "Review and fix duplicate IDs in issues.jsonl",
        }
        if not checks["issue_ids"]["passed"]:
            all_passed = False

        # Check 7: Dependency integrity (via storage API)
        deps_ok = True
        dangling_deps: list[Any] = []
        if issues_file.exists() and issues_valid:
            try:
                storage = get_storage(dogcats_dir)
                dangling_deps = storage.find_dangling_dependencies()
                if dangling_deps:
                    deps_ok = False
            except Exception:
                deps_ok = False

        # Fix dangling dependencies if requested
        if fix and not deps_ok and dangling_deps:
            try:
                storage = get_storage(dogcats_dir)
                storage.remove_dependencies(dangling_deps)
                deps_ok = True
                typer.echo(
                    f"Fixed: Removed {len(dangling_deps)} "
                    "dangling dependency reference(s)",
                )
            except Exception as e:
                typer.echo(f"Error fixing dependencies: {e}")

        checks["dependencies"] = {
            "description": "Dependency references are valid",
            "fail_description": "Found dangling dependency references",
            "passed": deps_ok,
            "fix": "Run 'dcat doctor --fix' to clean up",
        }
        if not checks["dependencies"]["passed"]:
            all_passed = False

        # Post-merge concurrent edit detection
        merge_warnings: list[dict[str, Any]] = []
        if post_merge:
            # storage_rel must be relative to the git repo root
            try:
                repo_root = Path(
                    subprocess.run(
                        ["git", "rev-parse", "--show-toplevel"],
                        capture_output=True,
                        text=True,
                        check=True,
                    ).stdout.strip(),
                )
                storage_rel = str(
                    dogcats_path.resolve().relative_to(repo_root) / "issues.jsonl",
                )
                merge_warnings = detect_concurrent_edits(
                    storage_rel=storage_rel,
                )
            except (subprocess.CalledProcessError, ValueError):
                pass  # Not in a git repo or path not relative

        # Output results
        if json_output:
            output_data: dict[str, Any] = {
                "status": "ok" if all_passed else "issues_found",
                "checks": {
                    name: {
                        "passed": check["passed"],
                        "description": check["description"],
                        "fix": (check["fix"] if not check["passed"] else None),
                    }
                    for name, check in checks.items()
                },
            }
            if validation_details:
                output_data["validation_details"] = validation_details
            if merge_warnings:
                output_data["concurrent_edits"] = merge_warnings
            typer.echo(
                orjson.dumps(output_data, option=orjson.OPT_INDENT_2).decode(),
            )
        else:
            # Print validation detail errors first
            if validation_details:
                for entry in validation_details:
                    lvl = entry["level"].upper()
                    typer.echo(f"  [{lvl}] {entry['message']}")
                typer.echo()

            # Summary checks
            typer.echo("Dogcat Health Check\n")
            for check in checks.values():
                is_optional = check.get("optional", False)
                if check["passed"]:
                    desc = check["description"]
                    line = typer.style(f"✓ {desc}", fg="green")
                elif is_optional:
                    desc = check.get("fail_description", check["description"])
                    line = typer.style(f"○ {desc}", fg="yellow")
                else:
                    desc = check.get("fail_description", check["description"])
                    line = typer.style(f"✗ {desc}", fg="red")
                typer.echo(line)
                if not check["passed"] and not is_optional:
                    typer.echo(typer.style(f"  Fix: {check['fix']}", fg="yellow"))
                typer.echo()

            # Post-merge concurrent edit warnings
            if merge_warnings:
                typer.echo(
                    f"\nConcurrent edits detected"
                    f" ({len(merge_warnings)} issue(s)):",
                )
                for warn in merge_warnings:
                    typer.echo(f"  ⚠ {warn['message']}")
                    fields = warn.get("fields", {})
                    for fname, diff in fields.items():
                        typer.echo(
                            f"    {fname}:"
                            f" branch_1={diff['branch_1']!r}"
                            f"  branch_2={diff['branch_2']!r}",
                        )

            if all_passed:
                typer.echo(typer.style("\n✓ All checks passed!", fg="green"))
            else:
                typer.echo(
                    typer.style(
                        "\n✗ Some checks failed. See above for fixes.",
                        fg="red",
                    ),
                )

        raise typer.Exit(0 if all_passed else 1)

    @app.command()
    def export(
        format_type: str = typer.Option(
            "json",
            "--format",
            "-f",
            help="Export format: json or jsonl",
        ),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Export all issues, dependencies, and links to stdout in specified format.

        Supported formats:
        - json: table-printed JSON object with issues, dependencies, and links
        - jsonl: JSON Lines (one record per line)
        """
        try:
            storage = get_storage(dogcats_dir)
            issues = storage.list()

            from dogcat.models import issue_to_dict

            # Get all dependencies and links directly (avoids per-issue iteration dups)
            all_deps: list[dict[str, Any]] = [
                {
                    "issue_id": dep.issue_id,
                    "depends_on_id": dep.depends_on_id,
                    "type": dep.dep_type.value,
                    "created_at": dep.created_at.isoformat(),
                    "created_by": dep.created_by,
                }
                for dep in storage.all_dependencies
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
            ]

            if format_type == "json":
                # table-printed JSON object with all data
                output = {
                    "issues": [issue_to_dict(issue) for issue in issues],
                    "dependencies": all_deps,
                    "links": all_links,
                }
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
            else:
                typer.echo(f"Error: Unknown format '{format_type}'", err=True)
                typer.echo("Supported formats: json, jsonl", err=True)
                raise typer.Exit(1)

        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)

    @app.command()
    def comment(
        issue_id: str = typer.Argument(..., help="Issue ID"),
        action: str = typer.Argument(..., help="Action: add, list, or delete"),
        text: str = typer.Option(None, "--text", "-t", help="Comment text (for add)"),
        comment_id: str = typer.Option(
            None,
            "--comment-id",
            "-c",
            help="Comment ID (for delete)",
        ),
        author: str = typer.Option(None, "--author", help="Comment author name"),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Manage issue comments.

        Actions:
        - add: Add a comment to an issue
        - list: List all comments for an issue
        - delete: Delete a comment
        """
        try:
            from dogcat.models import Comment

            storage = get_storage(dogcats_dir)
            issue = storage.get(issue_id)

            if not issue:
                typer.echo(f"Error: Issue {issue_id} not found", err=True)
                raise typer.Exit(1)

            if action == "add":
                if not text:
                    typer.echo("Error: --text is required for add action", err=True)
                    raise typer.Exit(1)

                # Generate comment ID
                comment_counter = len(issue.comments) + 1
                new_comment_id = f"{issue_id}-c{comment_counter}"

                new_comment = Comment(
                    id=new_comment_id,
                    issue_id=issue.full_id,
                    author=author or get_default_operator(),
                    text=text,
                )

                issue.comments.append(new_comment)
                storage.update(issue_id, {"comments": issue.comments})

                if json_output:
                    from dogcat.models import issue_to_dict

                    typer.echo(orjson.dumps(issue_to_dict(issue)).decode())
                else:
                    typer.echo(f"✓ Added comment {new_comment_id}")

            elif action == "list":
                if json_output:
                    output = [
                        {
                            "id": c.id,
                            "author": c.author,
                            "text": c.text,
                            "created_at": c.created_at.isoformat(),
                        }
                        for c in issue.comments
                    ]
                    typer.echo(orjson.dumps(output).decode())
                else:
                    if not issue.comments:
                        typer.echo("No comments")
                    else:
                        for comment in issue.comments:
                            ts = comment.created_at.isoformat()
                            typer.echo(f"[{comment.id}] {comment.author} ({ts})")
                            typer.echo(f"  {comment.text}")

            elif action == "delete":
                if not comment_id:
                    typer.echo(
                        "Error: --comment-id is required for delete action",
                        err=True,
                    )
                    raise typer.Exit(1)

                comment_to_delete = None
                for c in issue.comments:
                    if c.id == comment_id:
                        comment_to_delete = c
                        break

                if not comment_to_delete:
                    typer.echo(f"Error: Comment {comment_id} not found", err=True)
                    raise typer.Exit(1)

                issue.comments.remove(comment_to_delete)
                storage.update(issue_id, {"comments": issue.comments})

                typer.echo(f"✓ Deleted comment {comment_id}")

            else:
                typer.echo(f"Error: Unknown action '{action}'", err=True)
                typer.echo("Valid actions: add, list, delete", err=True)
                raise typer.Exit(1)

        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
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
            PRIORITY_OPTIONS,
            STATUS_OPTIONS,
            TYPE_OPTIONS,
            TYPE_SHORTHANDS,
        )

        if json_output:
            output = {
                "types": [
                    {"label": label, "value": value} for label, value in TYPE_OPTIONS
                ],
                "type_shorthands": TYPE_SHORTHANDS,
                "statuses": [
                    {"label": label, "value": value} for label, value in STATUS_OPTIONS
                ],
                "priorities": [
                    {"label": label, "value": value}
                    for label, value in PRIORITY_OPTIONS
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
                typer.echo(f"  {value:<12} - {label}")

            typer.echo("\nPriorities:")
            for label, value in PRIORITY_OPTIONS:
                typer.echo(f"  {value}  - {label}")

            typer.echo("\nShorthands for c (create alias) command:")
            shorthand_list = ", ".join(
                f"{k}={v}" for k, v in sorted(TYPE_SHORTHANDS.items())
            )
            typer.echo(f"  Type: {shorthand_list}")
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

            if json_output:
                output = {
                    "prefix": prefix,
                    "total": total,
                    "by_status": status_counts,
                    "by_type": type_counts,
                }
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

        except ValueError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1) from None

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
        status: str = typer.Option(None, "--status", "-s", help="Filter by status"),
        issue_type: str = typer.Option(None, "--type", "-t", help="Filter by type"),
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

            if json_output:
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

        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)

    @app.command(name="backfill-history")
    def backfill_history(
        dry_run: bool = typer.Option(
            False,
            "--dry-run",
            help="Preview without writing events",
        ),
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

            if dry_run:
                typer.echo(
                    f"\nDry run: would generate {events_generated} event(s)",
                    err=True,
                )
            else:
                typer.echo(f"✓ Backfilled {events_generated} event(s)")

        except typer.Exit:
            raise
        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1) from e
