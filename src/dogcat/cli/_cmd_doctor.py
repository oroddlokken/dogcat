"""Doctor command for dogcat CLI."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import orjson
import typer

from dogcat.config import (
    get_config_path,
    get_issue_prefix,
    load_config,
    migrate_config_keys,
    save_config,
)

from ._helpers import find_dogcats_dir, get_storage, is_gitignored
from ._json_state import is_json_output
from ._validate import detect_concurrent_edits, validate_inbox_jsonl, validate_jsonl


def register(app: typer.Typer) -> None:
    """Register doctor commands."""

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

        # Resolve dogcats_dir via directory walk when using the default
        if dogcats_dir == ".dogcats" and not Path(dogcats_dir).exists():
            dogcats_dir = find_dogcats_dir()

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

        # Check 2-inbox: inbox.jsonl is valid JSON (if it exists)
        inbox_file = dogcats_path / "inbox.jsonl"
        inbox_valid = False
        inbox_exists = inbox_file.exists()
        if inbox_exists:
            try:
                with inbox_file.open() as f:
                    for line in f:
                        if line.strip():
                            orjson.loads(line)
                inbox_valid = True
            except (OSError, orjson.JSONDecodeError):
                pass

        if inbox_exists:
            checks["inbox_jsonl"] = {
                "description": f"{dogcats_dir}/inbox.jsonl is valid JSON",
                "passed": inbox_valid,
                "fix": "Review and fix malformed lines in inbox.jsonl",
            }
            if not inbox_valid:
                all_passed = False

        # Check 2a: config.toml exists
        config_path = get_config_path(dogcats_dir)
        config_exists = config_path.exists()

        if fix and not config_exists and dogcats_path.exists():
            detected_prefix = get_issue_prefix(dogcats_dir)
            save_config(dogcats_dir, {"namespace": detected_prefix})
            config_exists = True
            typer.echo(
                f"Fixed: Created {config_path.name} with namespace='{detected_prefix}'",
            )

        checks["config_toml"] = {
            "description": f"{dogcats_dir}/config.toml exists",
            "fail_description": f"{dogcats_dir}/config.toml not found",
            "passed": config_exists,
            "fix": "Run 'dcat doctor --fix' to create config.toml",
        }
        if not checks["config_toml"]["passed"]:
            all_passed = False

        # Check 2b: namespace is set and non-empty in config
        # Only check if config.toml exists (skip if Check 2a failed)
        if config_exists:
            config = load_config(dogcats_dir)
            prefix_value = config.get("namespace") or config.get("issue_prefix")
            prefix_ok = bool(prefix_value)

            if fix and not prefix_ok:
                detected_prefix = get_issue_prefix(dogcats_dir)
                config["namespace"] = detected_prefix
                save_config(dogcats_dir, config)
                prefix_ok = True
                typer.echo(
                    f"Fixed: Set namespace='{detected_prefix}' in config.toml",
                )

            checks["config_namespace"] = {
                "description": "namespace is configured in config.toml",
                "fail_description": "namespace is not configured in config.toml",
                "passed": prefix_ok,
                "fix": "Run 'dcat config set namespace <prefix>'",
            }
            if not prefix_ok:
                all_passed = False

        # Check 2c: deprecated issue_prefix key
        if config_exists:
            config = load_config(dogcats_dir)
            has_deprecated = "issue_prefix" in config
            deprecated_ok = not has_deprecated

            if fix and has_deprecated:
                migrate_config_keys(config)
                save_config(dogcats_dir, config)
                deprecated_ok = True
                typer.echo(
                    "Fixed: Renamed 'issue_prefix' to 'namespace' in config.toml",
                )

            checks["config_deprecated_keys"] = {
                "description": "No deprecated config keys",
                "fail_description": (
                    "Config uses deprecated 'issue_prefix' key (renamed to 'namespace')"
                ),
                "passed": deprecated_ok,
                "fix": "Run 'dcat doctor --fix' to migrate",
            }
            if not deprecated_ok:
                all_passed = False

        # Check 2d: mutual exclusivity of visible/hidden namespaces
        if config_exists:
            config = load_config(dogcats_dir)
            has_both = bool(
                config.get("visible_namespaces") and config.get("hidden_namespaces"),
            )
            mutual_ok = not has_both

            if fix and has_both:
                del config["hidden_namespaces"]
                save_config(dogcats_dir, config)
                mutual_ok = True
                typer.echo(
                    "Fixed: Removed 'hidden_namespaces'"
                    " (kept 'visible_namespaces' as whitelist)",
                )

            checks["namespace_config_mutual"] = {
                "description": "Namespace visibility config is not contradictory",
                "fail_description": (
                    "Both 'visible_namespaces' and 'hidden_namespaces' are set"
                    " (mutually exclusive)"
                ),
                "passed": mutual_ok,
                "fix": "Run 'dcat doctor --fix' to remove hidden_namespaces",
            }
            if not mutual_ok:
                all_passed = False

        # Check 2e: config.local.toml gitignored (if it exists)
        local_config_file = dogcats_path / "config.local.toml"
        if local_config_file.exists():
            local_gitignored = is_gitignored(str(local_config_file))
            checks["local_config_gitignored"] = {
                "description": "config.local.toml is gitignored",
                "fail_description": (
                    "config.local.toml exists but is not in .gitignore"
                ),
                "passed": local_gitignored,
                "optional": True,
                "note": (
                    "Add '.dogcats/config.local.toml' to .gitignore"
                    " to avoid committing machine-specific settings"
                ),
            }

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

        # Check 3b: Inbox data integrity
        inbox_data_valid = True
        inbox_error_count = 0
        inbox_validation_details: list[dict[str, str]] = []
        if inbox_exists and inbox_valid:
            inbox_validation_details = validate_inbox_jsonl(inbox_file)
            inbox_error_count = sum(
                1 for e in inbox_validation_details if e["level"] == "error"
            )
            if inbox_error_count > 0:
                inbox_data_valid = False

        if inbox_exists:
            checks["inbox_data_integrity"] = {
                "description": "Inbox data integrity (proposal fields)",
                "fail_description": (
                    f"Inbox data integrity: {inbox_error_count} error(s) found"
                ),
                "passed": inbox_data_valid,
                "fix": "Review errors above and fix inbox.jsonl",
            }
            if not inbox_data_valid:
                all_passed = False

        # Check 4: dcat in PATH
        dogcat_in_path = bool(shutil.which("dcat"))
        if dogcat_in_path:
            checks["dogcat_in_path"] = {
                "description": "dcat command is available in PATH",
                "passed": True,
            }
        else:
            # dcat doctor is running, so dcat works — just not as a PATH binary.
            # It's likely a shell function or alias.
            checks["dogcat_in_path"] = {
                "description": "dcat command is available in PATH",
                "fail_description": (
                    "dcat is available as a shell function/alias,"
                    " not as a binary in PATH"
                ),
                "passed": False,
                "optional": True,
                "note": "Tab completions may not work",
            }

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
            except typer.Exit:
                raise
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
        if is_json_output(json_output):
            output_data: dict[str, Any] = {
                "status": "ok" if all_passed else "issues_found",
                "checks": {
                    name: {
                        "passed": check["passed"],
                        "description": check["description"],
                        **({"optional": True} if check.get("optional") else {}),
                        "fix": (check.get("fix") if not check["passed"] else None),
                        **({"note": check["note"]} if "note" in check else {}),
                    }
                    for name, check in checks.items()
                },
            }
            all_validation = validation_details + inbox_validation_details
            if all_validation:
                output_data["validation_details"] = all_validation
            if merge_warnings:
                output_data["concurrent_edits"] = merge_warnings
            typer.echo(
                orjson.dumps(output_data, option=orjson.OPT_INDENT_2).decode(),
            )
        else:
            # Print validation detail errors first
            all_validation = validation_details + inbox_validation_details
            if all_validation:
                for entry in all_validation:
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
                if not check["passed"] and is_optional and "note" in check:
                    typer.echo(typer.style(f"  Note: {check['note']}", fg="yellow"))
                typer.echo()

            # Post-merge concurrent edit warnings
            if merge_warnings:
                typer.echo(
                    f"\nConcurrent edits detected ({len(merge_warnings)} issue(s)):",
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
