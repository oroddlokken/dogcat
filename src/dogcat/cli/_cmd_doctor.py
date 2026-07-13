"""Doctor command for dogcat CLI."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import orjson
import typer

from dogcat.config import (
    get_config_path,
    get_namespace,
    load_config,
    migrate_config_keys,
    save_config,
)
from dogcat.idgen import (
    collision_probability,
    cumulative_collision_probability,
    get_id_length_for_count,
)

from ._health import HealthCheck, HealthReport
from ._helpers import find_dogcats_dir, get_storage, is_gitignored
from ._json_state import is_json, set_json
from ._validate import (
    ValidationError,
    detect_concurrent_edits,
    validate_inbox_jsonl,
    validate_jsonl,
)


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
        check_id_distribution: bool = typer.Option(
            False,
            "--check-id-distribution",
            help=(
                "Report ID-collision probability per namespace"
                " (informational; warns if cumulative probability is high)"
            ),
        ),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Diagnose dogcat installation, data integrity, and configuration.

        Performs health checks on the installation, validates JSONL data
        integrity (fields, references, cycles), and suggests fixes.
        Use --post-merge to detect concurrent edits after a git merge.
        Use --check-id-distribution to inspect collision probability for
        the active ID-length thresholds.
        Exit code 0 = all OK, 1 = issues found.
        """
        set_json(json_output)

        report = HealthReport()
        validation_details: list[ValidationError] = []

        # Resolve dogcats_dir via directory walk when using the default
        if dogcats_dir == ".dogcats" and not Path(dogcats_dir).exists():
            dogcats_dir = find_dogcats_dir()

        # Check: global config status (~/.config/dogcat/config.toml)
        from dogcat.config import check_toml_parseable
        from dogcat.global_config import (
            get_global_config_path,
            load_global_config,
        )

        global_cfg_path = get_global_config_path()
        global_parse_error = check_toml_parseable(global_cfg_path)
        global_cfg = load_global_config()
        if global_parse_error is not None:
            # load_global_config degrades a malformed file to defaults;
            # doctor is where the parse failure must become visible.
            report.add(
                "global_config",
                HealthCheck(
                    description=(
                        f"global config at {global_cfg_path}: "
                        f"parse error ({global_parse_error})"
                    ),
                    passed=False,
                    fix=f"Fix the TOML syntax in {global_cfg_path}",
                ),
            )
        elif global_cfg_path.is_file():
            if global_cfg.default_storage is None:
                report.add(
                    "global_config",
                    HealthCheck(
                        description=(
                            f"global config at {global_cfg_path}: "
                            "default_storage not set"
                        ),
                        passed=True,
                        optional=True,
                    ),
                )
            else:
                global_storage_ok = global_cfg.default_storage.is_dir()
                description = (
                    f"global config at {global_cfg_path}: "
                    f"default_storage={global_cfg.default_storage}"
                )
                report.add(
                    "global_config",
                    HealthCheck(
                        description=description,
                        passed=global_storage_ok,
                        fix=(
                            None
                            if global_storage_ok
                            else "Set or update default_storage with "
                            "`dcat config set --global default_storage <path>`"
                        ),
                    ),
                )
        else:
            report.add(
                "global_config",
                HealthCheck(
                    description="global config: not configured",
                    passed=True,
                    optional=True,
                ),
            )

        # Check 1: .dogcats directory exists
        dogcats_path = Path(dogcats_dir)
        report.add("dogcats_dir", _check_dogcats_dir(dogcats_dir))

        # Check 2: issues.jsonl exists and is valid JSON
        issues_file = dogcats_path / "issues.jsonl"
        issues_bad_count = 0
        issues_valid = False
        if issues_file.exists():
            try:
                with issues_file.open() as f:
                    for line in f:
                        stripped = line.strip()
                        if not stripped:
                            continue
                        try:
                            payload = orjson.loads(stripped)
                        except orjson.JSONDecodeError:
                            issues_bad_count += 1
                            continue
                        if not isinstance(payload, dict):
                            issues_bad_count += 1
                issues_valid = issues_bad_count == 0
            except OSError:
                pass

        report.add(
            "issues_jsonl",
            HealthCheck(
                description=f"{dogcats_dir}/issues.jsonl is valid JSON",
                fail_description=(
                    f"{dogcats_dir}/issues.jsonl is valid JSON "
                    f"({issues_bad_count} malformed line(s))"
                    if issues_bad_count
                    else f"{dogcats_dir}/issues.jsonl is valid JSON"
                ),
                passed=issues_file.exists() and issues_valid,
                fix=(
                    "Run 'dcat repair-jsonl' to copy malformed lines to a "
                    ".bad sidecar and compact the file"
                    if issues_bad_count
                    else "Restore from backup or run 'dcat init' to reset"
                ),
            ),
        )

        # Check 2-inbox: inbox.jsonl is valid JSON (if it exists)
        inbox_file = dogcats_path / "inbox.jsonl"
        inbox_bad_count = 0
        inbox_valid = False
        inbox_exists = inbox_file.exists()
        if inbox_exists:
            try:
                with inbox_file.open() as f:
                    for line in f:
                        stripped = line.strip()
                        if not stripped:
                            continue
                        try:
                            payload = orjson.loads(stripped)
                        except orjson.JSONDecodeError:
                            inbox_bad_count += 1
                            continue
                        if not isinstance(payload, dict):
                            inbox_bad_count += 1
                inbox_valid = inbox_bad_count == 0
            except OSError:
                pass

        if inbox_exists:
            report.add(
                "inbox_jsonl",
                HealthCheck(
                    description=f"{dogcats_dir}/inbox.jsonl is valid JSON",
                    fail_description=(
                        f"{dogcats_dir}/inbox.jsonl is valid JSON "
                        f"({inbox_bad_count} malformed line(s))"
                    ),
                    passed=inbox_valid,
                    fix=(
                        "Run 'dcat repair-jsonl' to copy malformed lines "
                        "to a .bad sidecar and compact the file"
                    ),
                ),
            )

        # Check 2a: config.toml exists
        config_path = get_config_path(dogcats_dir)
        config_exists = config_path.exists()

        if fix and not config_exists and dogcats_path.exists():
            detected_prefix = get_namespace(dogcats_dir)
            save_config(dogcats_dir, {"namespace": detected_prefix})
            config_exists = True
            typer.echo(
                f"Fixed: Created {config_path.name} with namespace='{detected_prefix}'",
            )

        report.add(
            "config_toml",
            HealthCheck(
                description=f"{dogcats_dir}/config.toml exists",
                fail_description=f"{dogcats_dir}/config.toml not found",
                passed=config_exists,
                fix="Run 'dcat doctor --fix' to create config.toml",
            ),
        )

        # Check 2a-bis: config.toml is parseable as TOML
        # _load_toml swallows TOMLDecodeError and returns {}, so without an
        # explicit check the user gets "all defaults" with no signal that
        # their config is broken.
        if config_exists:
            from dogcat.config import check_toml_parseable

            config_parse_error = check_toml_parseable(config_path)
            report.add(
                "config_toml_parseable",
                HealthCheck(
                    description=f"{dogcats_dir}/config.toml is valid TOML",
                    fail_description=(
                        f"{dogcats_dir}/config.toml has a TOML parse error: "
                        f"{config_parse_error}"
                    ),
                    passed=config_parse_error is None,
                    fix="Edit config.toml to fix the TOML syntax error",
                ),
            )

        # Check 2b: namespace is set and non-empty in config
        # Only check if config.toml exists (skip if Check 2a failed)
        if config_exists:
            config = load_config(dogcats_dir)
            prefix_value = config.get("namespace") or config.get("issue_prefix")
            prefix_ok = bool(prefix_value)

            if fix and not prefix_ok:
                detected_prefix = get_namespace(dogcats_dir)
                config["namespace"] = detected_prefix
                save_config(dogcats_dir, config)
                prefix_ok = True
                typer.echo(
                    f"Fixed: Set namespace='{detected_prefix}' in config.toml",
                )

            report.add(
                "config_namespace",
                HealthCheck(
                    description="namespace is configured in config.toml",
                    fail_description="namespace is not configured in config.toml",
                    passed=prefix_ok,
                    fix="Run 'dcat config set namespace <prefix>'",
                ),
            )

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

            report.add(
                "config_deprecated_keys",
                HealthCheck(
                    description="No deprecated config keys",
                    fail_description=(
                        "Config uses deprecated 'issue_prefix' key "
                        "(renamed to 'namespace')"
                    ),
                    passed=deprecated_ok,
                    fix="Run 'dcat doctor --fix' to migrate",
                ),
            )

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

            report.add(
                "namespace_config_mutual",
                HealthCheck(
                    description="Namespace visibility config is not contradictory",
                    fail_description=(
                        "Both 'visible_namespaces' and 'hidden_namespaces' are set"
                        " (mutually exclusive)"
                    ),
                    passed=mutual_ok,
                    fix="Run 'dcat doctor --fix' to remove hidden_namespaces",
                ),
            )

        # Check 2e: config.local.toml gitignored (if it exists)
        local_config_file = dogcats_path / "config.local.toml"
        if local_config_file.exists():
            local_gitignored = is_gitignored(str(local_config_file))
            report.add(
                "local_config_gitignored",
                HealthCheck(
                    description="config.local.toml is gitignored",
                    fail_description=(
                        "config.local.toml exists but is not in .gitignore"
                    ),
                    passed=local_gitignored,
                    optional=True,
                    note=(
                        "Add '.dogcats/config.local.toml' to .gitignore"
                        " to avoid committing machine-specific settings"
                    ),
                ),
            )

        # Check 3: Deep data validation (fields, refs, cycles)
        data_valid = True
        data_error_count = 0
        if issues_file.exists() and issues_valid:
            validation_details = validate_jsonl(issues_file)
            data_error_count = sum(1 for e in validation_details if e.level == "error")
            if data_error_count > 0:
                data_valid = False

        report.add(
            "data_integrity",
            HealthCheck(
                description="Data integrity (fields, references, cycles)",
                fail_description=(f"Data integrity: {data_error_count} error(s) found"),
                passed=data_valid,
                fix="Review errors above and fix issues.jsonl",
            ),
        )

        # Check 3b: Inbox data integrity
        inbox_data_valid = True
        inbox_error_count = 0
        inbox_validation_details: list[ValidationError] = []
        if inbox_exists and inbox_valid:
            inbox_validation_details = validate_inbox_jsonl(inbox_file)
            inbox_error_count = sum(
                1 for e in inbox_validation_details if e.level == "error"
            )
            if inbox_error_count > 0:
                inbox_data_valid = False

        if inbox_exists:
            report.add(
                "inbox_data_integrity",
                HealthCheck(
                    description="Inbox data integrity (proposal fields)",
                    fail_description=(
                        f"Inbox data integrity: {inbox_error_count} error(s) found"
                    ),
                    passed=inbox_data_valid,
                    fix="Review errors above and fix inbox.jsonl",
                ),
            )

        # Check 4: dcat in PATH
        report.add("dogcat_in_path", _check_dcat_in_path())

        # Check 6: Issue ID uniqueness
        issue_ids_unique = True
        if issues_file.exists() and issues_valid:
            try:
                storage = get_storage(dogcats_dir)
                issue_ids_unique = storage.check_id_uniqueness()
            except Exception:
                issue_ids_unique = False

        report.add(
            "issue_ids",
            HealthCheck(
                description="All issue IDs are unique",
                passed=issue_ids_unique,
                fix="Review and fix duplicate IDs in issues.jsonl",
            ),
        )

        # Check 6b: ID distribution / collision probability (opt-in)
        id_distribution: list[IdDistributionRow] = []
        if check_id_distribution and issues_file.exists() and issues_valid:
            id_distribution = _collect_id_distribution(dogcats_dir)
            warn_threshold = 0.05  # 5% cumulative collision probability
            warn = any(row.p_cumulative >= warn_threshold for row in id_distribution)
            report.add(
                "id_distribution",
                HealthCheck(
                    description=(
                        "ID collision probability is below "
                        f"{warn_threshold * 100:.0f}% in every namespace"
                    ),
                    fail_description=(
                        "Cumulative ID collision probability is high in at least"
                        " one namespace — consider raising ID_LENGTH_THRESHOLDS"
                    ),
                    passed=not warn,
                    optional=True,
                    note=(
                        "Each retry resolves transparently via nonce, so this is"
                        " informational. Numbers below."
                    ),
                ),
            )

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

        report.add(
            "dependencies",
            HealthCheck(
                description="Dependency references are valid",
                fail_description="Found dangling dependency references",
                passed=deps_ok,
                fix="Run 'dcat doctor --fix' to clean up",
            ),
        )

        # Check 8: Claude Code PreCompact hook
        claude_dir = _find_claude_dir()
        if claude_dir is not None:
            hook_status = _check_precompact_hook(claude_dir)

            if fix and hook_status == "missing":
                _install_precompact_hook(claude_dir)
                hook_status = "replay"
                typer.echo("Fixed: Installed PreCompact hook for dcat prime --replay")
            elif fix and hook_status == "old":
                _upgrade_precompact_hook(claude_dir)
                hook_status = "replay"
                typer.echo("Fixed: Upgraded PreCompact hook to use dcat prime --replay")

            if hook_status == "missing":
                report.add(
                    "claude_precompact",
                    HealthCheck(
                        description="Claude Code PreCompact hook is configured",
                        fail_description=(
                            "Claude Code PreCompact hook not found"
                            " (agents lose context after compaction)"
                        ),
                        passed=False,
                        optional=True,
                        fix="Run 'dcat doctor --fix' to install",
                        note=(
                            "Run 'dcat doctor --fix' to add a PreCompact hook"
                            " that preserves workflow context during compaction"
                        ),
                    ),
                )
            elif hook_status == "old":
                report.add(
                    "claude_precompact",
                    HealthCheck(
                        description="Claude Code PreCompact hook uses --replay",
                        fail_description=(
                            "PreCompact hook uses 'dcat prime' without --replay"
                            " (flags like --opinionated are lost after compaction)"
                        ),
                        passed=False,
                        optional=True,
                        fix="Run 'dcat doctor --fix' to upgrade",
                        note=(
                            "Run 'dcat doctor --fix' to upgrade the hook"
                            " so prime flags are preserved across compaction"
                        ),
                    ),
                )
            else:
                report.add(
                    "claude_precompact",
                    HealthCheck(
                        description="Claude Code PreCompact hook is configured",
                        passed=True,
                    ),
                )

        # Render straight from the typed HealthCheck objects — no flatten
        # to dicts, so pyright catches field typos in the renderers below.
        checks: dict[str, HealthCheck] = report.checks
        all_passed = report.all_passed

        # Post-merge concurrent edit detection
        merge_warnings: list[dict[str, Any]] = []
        post_merge_skip_reason: str | None = None
        if post_merge:
            import dogcat.git as git_helpers

            # storage_rel must be relative to the git repo root
            repo_root_path = git_helpers.repo_root()
            if repo_root_path is None:
                post_merge_skip_reason = (
                    "post-merge skipped: not inside a git repository"
                )
            else:
                try:
                    storage_rel = str(
                        dogcats_path.resolve().relative_to(repo_root_path)
                        / "issues.jsonl",
                    )
                except ValueError:
                    post_merge_skip_reason = (
                        f"post-merge skipped: {dogcats_path} is outside the "
                        f"git repo at {repo_root_path}; concurrent-edit "
                        "detection requires .dogcats inside the tracked tree."
                    )
                else:
                    merge_warnings = detect_concurrent_edits(
                        storage_rel=storage_rel,
                    )

        # Surface the skip reason loudly — the previous silent ``pass``
        # made --post-merge appear to succeed cleanly even when no
        # detection ran at all. (dogcat-40t6)
        if post_merge_skip_reason and not is_json():
            typer.echo(post_merge_skip_reason, err=True)

        # Output results
        all_validation = validation_details + inbox_validation_details
        if is_json():
            _render_doctor_json(
                checks,
                all_passed=all_passed,
                validation=all_validation,
                merge_warnings=merge_warnings,
                post_merge_skip_reason=post_merge_skip_reason,
                id_distribution=id_distribution,
            )
        else:
            _render_doctor_text(
                checks,
                all_passed=all_passed,
                validation=all_validation,
                merge_warnings=merge_warnings,
                id_distribution=id_distribution,
            )

        raise typer.Exit(0 if all_passed else 1)


def _check_dogcats_dir(dogcats_dir: str) -> HealthCheck:
    """Check that the ``.dogcats`` store directory exists."""
    return HealthCheck(
        description=f"{dogcats_dir}/ directory exists",
        passed=Path(dogcats_dir).exists(),
        fix=f"Run 'dcat init' to create {dogcats_dir}",
    )


def _check_dcat_in_path() -> HealthCheck:
    """Check that ``dcat`` resolves as a PATH binary (tab-completion needs it)."""
    if shutil.which("dcat"):
        return HealthCheck(
            description="dcat command is available in PATH",
            passed=True,
        )
    # dcat doctor is running, so dcat works — just not as a PATH binary.
    # It's likely a shell function or alias.
    return HealthCheck(
        description="dcat command is available in PATH",
        fail_description=(
            "dcat is available as a shell function/alias, not as a binary in PATH"
        ),
        passed=False,
        optional=True,
        note="Tab completions may not work",
    )


def _render_doctor_json(
    checks: dict[str, HealthCheck],
    *,
    all_passed: bool,
    validation: list[ValidationError],
    merge_warnings: list[dict[str, Any]],
    post_merge_skip_reason: str | None,
    id_distribution: list[IdDistributionRow],
) -> None:
    """Emit the ``dcat doctor --json`` report."""
    output_data: dict[str, Any] = {
        "status": "ok" if all_passed else "issues_found",
        "checks": {
            name: {
                "passed": check.passed,
                "description": check.description,
                **({"optional": True} if check.optional else {}),
                "fix": (check.fix if not check.passed else None),
                **({"note": check.note} if check.note is not None else {}),
            }
            for name, check in checks.items()
        },
    }
    if validation:
        output_data["validation_details"] = [e.to_dict() for e in validation]
    if merge_warnings:
        output_data["concurrent_edits"] = merge_warnings
    if post_merge_skip_reason:
        output_data["post_merge_skipped"] = post_merge_skip_reason
    if id_distribution:
        output_data["id_distribution"] = [r.to_dict() for r in id_distribution]
    typer.echo(orjson.dumps(output_data, option=orjson.OPT_INDENT_2).decode())


def _render_doctor_text(
    checks: dict[str, HealthCheck],
    *,
    all_passed: bool,
    validation: list[ValidationError],
    merge_warnings: list[dict[str, Any]],
    id_distribution: list[IdDistributionRow],
) -> None:
    """Emit the human-readable ``dcat doctor`` report."""
    # Print validation detail errors first
    if validation:
        for entry in validation:
            lvl = entry.level.upper()
            typer.echo(f"  [{lvl}] {entry.message}")
        typer.echo()

    # Summary checks
    typer.echo("Dogcat Health Check\n")
    for check in checks.values():
        is_optional = check.optional
        if check.passed:
            line = typer.style(f"✓ {check.description}", fg="green")
        elif is_optional:
            desc = check.fail_description or check.description
            line = typer.style(f"○ {desc}", fg="yellow")
        else:
            desc = check.fail_description or check.description
            line = typer.style(f"✗ {desc}", fg="red")
        typer.echo(line)
        if not check.passed and not is_optional:
            typer.echo(typer.style(f"  Fix: {check.fix}", fg="yellow"))
        if not check.passed and is_optional and check.note is not None:
            typer.echo(typer.style(f"  Note: {check.note}", fg="yellow"))
        typer.echo()

    # ID distribution table
    if id_distribution:
        typer.echo("ID distribution:")
        typer.echo(
            f"  {'namespace':<14} {'count':>6} {'L':>2}  {'p_step':>10} {'p_all':>10}",
        )
        for row in id_distribution:
            typer.echo(
                f"  {row.namespace:<14} {row.count:>6} "
                f"{row.length:>2}  "
                f"{row.p_step * 100:>9.4f}% "
                f"{row.p_cumulative * 100:>9.4f}%",
            )
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


@dataclass
class IdDistributionRow:
    """One namespace's ID-collision statistics row. (dogcat-3s3h).

    ``length`` is the ID length the generator would currently use for a
    database of that size; ``p_step`` is the per-generation collision
    probability for the next ID; ``p_cumulative`` is the birthday-paradox
    probability that any collision has already occurred.
    """

    namespace: str
    count: int
    length: int
    p_step: float
    p_cumulative: float

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the flat dict the doctor JSON output emits."""
        return {
            "namespace": self.namespace,
            "count": self.count,
            "length": self.length,
            "p_step": self.p_step,
            "p_cumulative": self.p_cumulative,
        }


def _collect_id_distribution(dogcats_dir: str) -> list[IdDistributionRow]:
    """Compute per-namespace ID-collision statistics for the current database.

    Returns rows sorted by namespace name.
    """
    from dogcat.storage import JSONLStorage

    try:
        storage = JSONLStorage(path=str(Path(dogcats_dir) / "issues.jsonl"))
    except (OSError, ValueError, RuntimeError):
        return []

    counts: dict[str, int] = {}
    for issue in storage.list():
        if issue.is_tombstone():
            continue
        counts[issue.namespace] = counts.get(issue.namespace, 0) + 1

    rows: list[IdDistributionRow] = []
    for namespace in sorted(counts):
        count = counts[namespace]
        length = get_id_length_for_count(count)
        rows.append(
            IdDistributionRow(
                namespace=namespace,
                count=count,
                length=length,
                p_step=collision_probability(count, length),
                p_cumulative=cumulative_collision_probability(count, length),
            ),
        )
    return rows


def _find_claude_dir() -> Path | None:
    """Find .claude/ directory by walking up from cwd. Returns None if not found."""
    current = Path.cwd()
    while True:
        candidate = current / ".claude"
        if candidate.is_dir():
            return candidate
        parent = current.parent
        if parent == current:
            return None
        current = parent


def _check_precompact_hook(claude_dir: Path) -> str:
    """Check PreCompact hook status.

    Returns:
        "replay" if hook uses --replay, "old" if hook exists without --replay,
        "missing" if no hook found.
    """
    for name in ("settings.local.json", "settings.json"):
        settings_path = claude_dir / name
        if not settings_path.exists():
            continue
        try:
            data_raw = orjson.loads(settings_path.read_bytes())
        except (OSError, orjson.JSONDecodeError):
            continue
        # Tolerate non-dict settings.json (``[]``, ``null``, scalar)
        # — doctor IS the recovery tool, so it must not crash on a
        # malformed user file. (dogcat-2yho)
        if not isinstance(data_raw, dict):
            continue
        data: dict[str, Any] = cast("dict[str, Any]", data_raw)
        hooks_obj_raw: Any = data.get("hooks", {})
        if not isinstance(hooks_obj_raw, dict):
            continue
        hooks_obj: dict[str, Any] = cast("dict[str, Any]", hooks_obj_raw)
        precompact_raw: Any = hooks_obj.get("PreCompact", [])
        if not isinstance(precompact_raw, list):
            continue
        precompact: list[Any] = cast("list[Any]", precompact_raw)
        for group_raw in precompact:
            if not isinstance(group_raw, dict):
                continue
            group: dict[str, Any] = cast("dict[str, Any]", group_raw)
            inner_raw: Any = group.get("hooks", []) or []
            if not isinstance(inner_raw, list):
                continue
            for hook_raw in cast("list[Any]", inner_raw):
                if not isinstance(hook_raw, dict):
                    continue
                hook: dict[str, Any] = cast("dict[str, Any]", hook_raw)
                cmd_raw: Any = hook.get("command", "")
                if not isinstance(cmd_raw, str):
                    continue
                cmd: str = cmd_raw
                if "dcat prime" in cmd:
                    if "--replay" in cmd:
                        return "replay"
                    return "old"
    return "missing"


def _install_precompact_hook(claude_dir: Path) -> None:
    """Install a PreCompact hook for dcat prime --replay into Claude settings."""
    # Prefer settings.local.json (gitignored), fall back to settings.json
    local_path = claude_dir / "settings.local.json"
    project_path = claude_dir / "settings.json"
    settings_path = local_path if local_path.exists() else project_path

    try:
        data_raw = orjson.loads(settings_path.read_bytes())
    except (OSError, orjson.JSONDecodeError):
        data_raw = {}
    # Replace a non-dict file with an empty dict so the install path
    # produces a well-formed file. (dogcat-2yho)
    data: dict[str, Any] = (
        cast("dict[str, Any]", data_raw) if isinstance(data_raw, dict) else {}
    )

    hooks: dict[str, Any] = data.setdefault("hooks", {})
    pre_compact: list[dict[str, Any]] = hooks.setdefault("PreCompact", [])

    from dogcat.constants import PRECOMPACT_HOOK_COMMAND, PRECOMPACT_HOOK_RECORD

    # Don't duplicate if already present with --replay
    for group in pre_compact:
        for hook in group.get("hooks", []):
            if PRECOMPACT_HOOK_COMMAND in hook.get("command", ""):
                return

    # Deep-copy the canonical record so caller mutations can't reach the
    # constants module.
    import copy

    pre_compact.append(copy.deepcopy(PRECOMPACT_HOOK_RECORD))

    _atomic_write_json(settings_path, data)


def _atomic_write_json(target: Path, data: dict[str, Any]) -> None:
    """Write ``data`` to ``target`` as pretty-printed JSON atomically.

    Mirrors the write-temp + fsync + replace pattern used by
    ``atomic_rewrite_jsonl``. Two concurrent ``dcat doctor --fix`` runs (or
    doctor racing against another writer of settings.json) would otherwise
    risk a partial file or last-writer-wins clobber.
    """
    payload = orjson.dumps(data, option=orjson.OPT_INDENT_2 | orjson.OPT_APPEND_NEWLINE)
    import os
    import tempfile

    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=parent,
        delete=False,
        suffix=".json",
    ) as tmp_file:
        tmp_path = Path(tmp_file.name)
        try:
            tmp_file.write(payload)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise
    try:
        tmp_path.replace(target)
    except OSError:
        tmp_path.unlink(missing_ok=True)
        raise


def _upgrade_precompact_hook(claude_dir: Path) -> None:
    """Upgrade old 'dcat prime' hook to 'dcat prime --replay'.

    Replaces any hook ``command`` whose entire value is ``dcat prime``
    (with no ``--replay``) with the canonical
    :data:`PRECOMPACT_HOOK_COMMAND`. The previous implementation used a
    substring ``cmd.replace`` which would have corrupted any settings
    file where ``"dcat prime"`` appeared as a substring of an unrelated
    command.
    """
    from dogcat.constants import PRECOMPACT_HOOK_COMMAND

    for name in ("settings.local.json", "settings.json"):
        settings_path = claude_dir / name
        if not settings_path.exists():
            continue
        try:
            data_raw = orjson.loads(settings_path.read_bytes())
        except (OSError, orjson.JSONDecodeError):
            continue
        if not isinstance(data_raw, dict):
            continue
        data: dict[str, Any] = cast("dict[str, Any]", data_raw)
        hooks_obj_raw: Any = data.get("hooks", {})
        if not isinstance(hooks_obj_raw, dict):
            continue
        hooks_obj: dict[str, Any] = cast("dict[str, Any]", hooks_obj_raw)
        precompact_raw: Any = hooks_obj.get("PreCompact", [])
        if not isinstance(precompact_raw, list):
            continue
        precompact: list[Any] = cast("list[Any]", precompact_raw)
        modified = False
        for group_raw in precompact:
            if not isinstance(group_raw, dict):
                continue
            group: dict[str, Any] = cast("dict[str, Any]", group_raw)
            inner_raw: Any = group.get("hooks", []) or []
            if not isinstance(inner_raw, list):
                continue
            for hook_raw in cast("list[Any]", inner_raw):
                if not isinstance(hook_raw, dict):
                    continue
                hook: dict[str, Any] = cast("dict[str, Any]", hook_raw)
                cmd_raw: Any = hook.get("command", "")
                if isinstance(cmd_raw, str) and cmd_raw.strip() == "dcat prime":
                    hook["command"] = PRECOMPACT_HOOK_COMMAND
                    modified = True
        if modified:
            _atomic_write_json(settings_path, data)
            return
