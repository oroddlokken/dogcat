"""Documentation commands for dogcat CLI."""

from __future__ import annotations

import subprocess
from pathlib import Path

import typer

from dogcat.config import load_config
from dogcat.constants import (
    GITATTRIBUTES_ENTRY,
    MERGE_DRIVER_CMD,
    MERGE_DRIVER_GIT_KEY,
    MERGE_DRIVER_GIT_NAME_KEY,
    MERGE_DRIVER_NAME,
)

from ._helpers import SortedGroup, find_dogcats_dir

# Sub-app for 'dcat git' subcommands
git_app = typer.Typer(
    help="Git integration commands.",
    no_args_is_help=True,
    cls=SortedGroup,
)

_GIT_GUIDE_TEXT = """\
╔════════════════════════════════════════════════════════════════════════════╗
║                       DOGCAT + GIT INTEGRATION GUIDE                       ║
╚════════════════════════════════════════════════════════════════════════════╝

── Committing .dogcats ─────────────────────────────────────────────────────

  The .dogcats/ directory contains your issue data. To share issues with
  your team, commit it to your git repository:

    $ git add .dogcats/
    $ git commit -m "Add issue tracking with dogcat"

  From then on, treat .dogcats/ like any other tracked directory — commit
  changes alongside the code they relate to.

── Merge Driver ───────────────────────────────────────────────────────────

  Dogcat includes a custom JSONL merge driver that auto-resolves most
  merge conflicts. Install it with:

    $ dcat git setup

  This configures git to use dogcat's merge driver for .dogcats/*.jsonl
  files. Without the driver, git's default text merge will conflict
  whenever two branches both modify the issue file.

── Resolving Merge Conflicts ───────────────────────────────────────────────

  With the merge driver installed, conflicts are rare. If they happen:

  1. Open the conflicted file (.dogcats/issues.jsonl)
  2. In most cases, keep BOTH sides — each line is an independent event
  3. Remove the conflict markers (<<<<<<, ======, >>>>>>)
  4. Save and continue the merge

  If both sides modify the SAME issue, keep the more recent change
  (or keep both — dogcat replays events in order, so the last one wins).

── Using .gitignore ────────────────────────────────────────────────────────

  If you want personal-only tracking, add it to .gitignore:

    echo ".dogcats/" >> .gitignore

  Scenarios where ignoring makes sense:
    - Personal TODO tracking you don't want to share
    - Experimenting with dogcat before adopting it team-wide
    - Repos where issues are tracked elsewhere (e.g., GitHub Issues)

── Best Practices ──────────────────────────────────────────────────────────

  1. Commit issue changes with related code
     When you close a bug, commit the fix and the issue update together.
     This keeps your history meaningful:
       $ git add src/fix.py .dogcats/
       $ git commit -m "Fix login timeout bug"

  2. Review .dogcats/ diffs in PRs
     Include .dogcats/ changes in code review. They document what was
     done and why.

── Quick Reference ─────────────────────────────────────────────────────────

  Install merge driver:   dcat git setup
  Check configuration:    dcat git check
  Commit issues:          git add .dogcats/ && git commit
  Ignore issues:          echo ".dogcats/" >> .gitignore
  Validate issue data:    dcat doctor
  Log issue history:      git log --oneline -- .dogcats/

── CI Validation ──────────────────────────────────────────────────────

  Add a CI step to validate issue data on pull requests. Dogcat ships
  a ready-made GitHub Actions workflow at:

    .github/workflows/validate-issues.yml

  It runs 'dcat doctor' whenever .dogcats/ files change, catching
  broken JSON, invalid references, and corrupt data before merge.

  To use it in your own project, copy the workflow file and ensure
  dogcat is installable (e.g. via pyproject.toml or requirements.txt).

  For other CI systems, the key command is:

    dcat doctor          # exits 0 on success, 1 on errors
"""


def _git_repo_root() -> Path | None:
    """Return the git repository root, or ``None`` if not inside a repo."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip())


def _run_git_checks() -> tuple[bool, dict[str, dict[str, object]]]:
    """Run git integration checks and return (all_passed, checks_dict).

    Shared logic used by both ``dcat git check`` and ``dcat prime --opinionated``.
    """
    checks: dict[str, dict[str, object]] = {}
    all_passed = True

    # Check 1: Are we in a git repo?
    repo_root = _git_repo_root()
    in_git_repo = repo_root is not None
    checks["git_repo"] = {
        "description": "Inside a git repository",
        "fail_description": "Not in a git repository",
        "passed": in_git_repo,
        "fix": "Run 'git init' to initialize a git repository",
    }
    if not in_git_repo:
        all_passed = False

    # Resolve paths relative to repo root (fall back to CWD if not in a repo)
    root = repo_root or Path()

    # Check 2: Is .issues.lock in .gitignore?
    lock_ignored = False
    gitignore = root / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text()
        lock_ignored = ".issues.lock" in content or ".dogcats/" in content
    checks["lock_ignored"] = {
        "description": ".gitignore covers .issues.lock",
        "fail_description": ".gitignore does not include .issues.lock",
        "passed": lock_ignored,
        "fix": "Add '.dogcats/.issues.lock' to .gitignore",
    }
    if not lock_ignored:
        all_passed = False

    # Check 3: Is .dogcats/ entirely in .gitignore? (informational)
    dogcats_ignored = False
    if gitignore.exists():
        lines = gitignore.read_text().splitlines()
        dogcats_ignored = any(ln.strip() in (".dogcats/", ".dogcats") for ln in lines)
    checks["dogcats_ignored"] = {
        "description": ".dogcats/ is shared with team via git",
        "fail_description": ".dogcats/ is in .gitignore (not shared with team)",
        "passed": not dogcats_ignored,
        "fix": "Remove '.dogcats/' from .gitignore to share issues with team",
        "optional": True,
    }

    # Check 4: Is the merge driver configured with the correct command?
    driver_result = subprocess.run(
        ["git", "config", MERGE_DRIVER_GIT_KEY],
        capture_output=True,
        text=True,
        check=False,
    )
    driver_value = driver_result.stdout.strip() if driver_result.returncode == 0 else ""
    driver_correct = driver_value == MERGE_DRIVER_CMD
    checks["merge_driver"] = {
        "description": "JSONL merge driver is configured",
        "fail_description": (
            "JSONL merge driver is not configured"
            if not driver_value
            else f"JSONL merge driver has wrong command: {driver_value}"
        ),
        "passed": driver_correct,
        "fix": "Run 'dcat git setup' to install the merge driver",
    }
    if not driver_correct:
        all_passed = False

    # Check 5: Does .gitattributes have the merge driver entry?
    gitattrs = root / ".gitattributes"
    has_gitattrs = False
    if gitattrs.exists():
        has_gitattrs = "merge=dcat-jsonl" in gitattrs.read_text()
    checks["gitattributes"] = {
        "description": ".gitattributes has JSONL merge driver entry",
        "fail_description": ".gitattributes is missing JSONL merge driver entry",
        "passed": has_gitattrs,
        "fix": (
            "Run 'dcat git setup' or add"
            " '.dogcats/*.jsonl merge=dcat-jsonl' to .gitattributes"
        ),
    }
    if not has_gitattrs:
        all_passed = False

    return all_passed, checks


def register(app: typer.Typer) -> None:
    """Register documentation commands."""
    app.add_typer(git_app, name="git")

    @git_app.command("guide")
    def git_guide() -> None:
        """Show guide for integrating dogcat with git."""
        typer.echo(_GIT_GUIDE_TEXT)

    @git_app.command("check")
    def git_check(
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """Check git-related configuration for dogcat."""
        import orjson

        dogcats_dir = find_dogcats_dir()
        config = load_config(dogcats_dir)
        if config.get("git_tracking") is False:
            if json_output:
                typer.echo(
                    orjson.dumps(
                        {"status": "skipped", "reason": "git_tracking is disabled"},
                    ).decode(),
                )
            else:
                typer.echo("Git tracking is disabled (git_tracking = false).")
                typer.echo(
                    "To enable: dcat config set git_tracking true",
                )
            raise typer.Exit(0)

        all_passed, checks = _run_git_checks()

        # Output
        if json_output:
            output_data = {
                "status": "ok" if all_passed else "issues_found",
                "checks": {
                    name: {
                        "passed": check["passed"],
                        "description": check["description"],
                        "fix": check["fix"] if not check["passed"] else None,
                    }
                    for name, check in checks.items()
                },
            }
            typer.echo(orjson.dumps(output_data, option=orjson.OPT_INDENT_2).decode())
        else:
            typer.echo("\nGit Integration Check\n")
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

    @git_app.command("setup")
    def git_setup() -> None:
        """Install the JSONL merge driver for git."""
        # Check we're in a git repo and get repo root
        repo_root = _git_repo_root()
        if repo_root is None:
            typer.echo("Error: Not in a git repository", err=True)
            raise typer.Exit(1)

        # Configure the merge driver
        subprocess.run(
            ["git", "config", MERGE_DRIVER_GIT_KEY, MERGE_DRIVER_CMD],
            check=True,
        )
        subprocess.run(
            ["git", "config", MERGE_DRIVER_GIT_NAME_KEY, MERGE_DRIVER_NAME],
            check=True,
        )

        # Ensure .gitattributes exists with the merge driver entry at repo root
        gitattrs = repo_root / ".gitattributes"
        entry = GITATTRIBUTES_ENTRY
        if gitattrs.exists():
            content = gitattrs.read_text()
            if entry not in content:
                with gitattrs.open("a") as f:
                    f.write(f"\n{entry}\n")
                typer.echo(f"✓ Added '{entry}' to .gitattributes")
            else:
                typer.echo("✓ .gitattributes already configured")
        else:
            gitattrs.write_text(f"# Dogcat JSONL merge driver\n{entry}\n")
            typer.echo(f"✓ Created .gitattributes with '{entry}'")

        typer.echo("✓ Merge driver configured in local git config")
        typer.echo("\nDone! The merge driver will auto-resolve JSONL conflicts.")

    @git_app.command("merge-driver", hidden=True)
    def git_merge_driver(
        base: str = typer.Argument(..., help="Base version file path (%O)"),
        ours: str = typer.Argument(..., help="Ours version file path (%A)"),
        theirs: str = typer.Argument(..., help="Theirs version file path (%B)"),
    ) -> None:
        """JSONL merge driver invoked by git during merge conflicts."""
        import orjson

        from dogcat.merge_driver import _parse_jsonl, merge_jsonl

        base_path = Path(base)
        ours_path = Path(ours)
        theirs_path = Path(theirs)

        base_records = _parse_jsonl(base_path)
        ours_records = _parse_jsonl(ours_path)
        theirs_records = _parse_jsonl(theirs_path)

        merged = merge_jsonl(base_records, ours_records, theirs_records)

        with ours_path.open("wb") as f:
            for record in merged:
                f.write(orjson.dumps(record))
                f.write(b"\n")

        raise typer.Exit(0)

    @app.command()
    def guide() -> None:
        """Show a user-friendly guide to using dcat.

        Displays a walkthrough of dcat's core features and workflows,
        written for users rather than AI agents.
        """
        guide_text = """\
╔════════════════════════════════════════════════════════════════════════════╗
║                           DCAT USER GUIDE                                ║
╚════════════════════════════════════════════════════════════════════════════╝

  dcat is a lightweight, git-friendly issue tracker that lives inside
  your repository. Issues are stored in a single .dogcats/issues.jsonl
  file — no server, no database, no setup beyond "dcat init".

── Getting Started ─────────────────────────────────────────────────────────

  Initialize a repository (one-time):

    dcat init

  OR

  # Initialize by using a shared .dogcats directory from another repo:

    dcat init --use-existing-folder /home/me/project/.dogcats


  Create your first issue:

    dcat create "Fix login page styling"

  Create an issue with a TUI:

    dcat new

  You can set type and priority at creation time:

    dcat create "Crash on empty input" --type bug --priority 1

  For quick creation, `dcat c` supports shorthands — single letters
  for type, digits for priority:

    dcat c b 1 "Crash on empty input"

  Available types: task (t), bug (b), feature (f), story (s),
                   chore (c), epic (e), question (q)
  Status shorthand: draft (d)

  Priority scale: 0 = Critical, 1 = High, 2 = Medium (default),
                  3 = Low, 4 = Minimal

── Viewing Issues ──────────────────────────────────────────────────────────

  List all open issues:

    dcat list

  Show as a formatted table:

    dcat list --table

  View a specific issue in detail:

    dcat show <issue_id>

  Search issues by keyword across all fields (title, description,
  notes, acceptance criteria, design, comments):

    dcat search "login"
    dcat search "API" --type bug          # filter by type
    dcat search "auth" --status open      # filter by status
    dcat search "API" -c                  # case-sensitive

  See recently closed issues:

    dcat recently-closed

  View change history (who changed what, when):

    dcat history
    dcat history -i <id>           # filter by issue
    dcat history -v                # show full field content

  See uncommitted changes vs last git commit:

    dcat diff

── Working on Issues ───────────────────────────────────────────────────────

  Issues move through these statuses:

    open → in_progress → in_review → closed

  Other statuses: blocked, deferred

  Update an issue's status:

    dcat update <id> --status in_progress
    dcat ip <id>                             # shortcut
    dcat ir <id>                             # set to in_review

  Close an issue with a reason:

    dcat close <id> --reason "Fixed in commit abc123"

  To find issues that are ready to work on (no blockers):

    dcat ready

  Edit an issue with a TUI:
    dcat edit <id>

── Dependencies & Hierarchy ────────────────────────────────────────────────

  Issues can have parent-child relationships for organization:

    dcat create "Child task" --parent <parent_id>

  Parent-child is purely organizational — children are NOT blocked by
  their parent. If a child genuinely needs its parent to finish first,
  add an explicit dependency:

    dcat dep <child_id> add --depends-on <parent_id>

  View dependencies for an issue:

    dcat dep <id> list

  See all blocked issues across the project:

    dcat blocked

── Issue Links ─────────────────────────────────────────────────────────

  Links capture general relationships between issues (as opposed to
  dependencies, which imply blocking). Common link types: relates_to,
  duplicates.

  Add a link between two issues:

    dcat link <id> add --related <other_id>
    dcat link <id> add --related <other_id> --type duplicates

  Remove a link:

    dcat link <id> remove --related <other_id>

  List all links for an issue:

    dcat link <id> list
    dcat link <id> list --json

── Filtering & Advanced Usage ──────────────────────────────────────────────

  Filter by type, priority, label, or status:

    dcat list --type bug
    dcat list --priority 0
    dcat list --label "backend"
    dcat list --status in_review

  Add labels to an issue:

    dcat label <id> add "backend"

  Add a comment:

    dcat comment <id> "Needs more investigation"

  Date-based queries for closed issues:

    dcat list --closed --closed-after 2025-01-01

  JSON output for scripting:

    dcat list --json

── Manual Issues ────────────────────────────────────────────────────────────

  Some issues require user action and can't be handled by an AI agent
  (e.g. deploying to prod, physical hardware tasks, subjective reviews).
  Mark these with --manual:

    dcat create "Deploy v2.1 to production" --manual
    dcat update <id> --manual       # mark existing issue as manual
    dcat update <id> --no-manual    # remove the manual flag

  AI agents using --agent-only will skip manual issues when listing work.
  You can also toggle the Manual checkbox in the TUI editor (dcat edit).

── Questions ────────────────────────────────────────────────────────────────

  "question" is a special issue type for tracking decisions and
  open questions — not tasks to work on:

    dcat create "Which auth provider should we use?" --type question

  Close with an answer:

    dcat close <id> --reason "Going with Auth0"

── Useful Commands ─────────────────────────────────────────────────────────

  dcat info        Show valid types, statuses, and priorities
  dcat status      Show project overview and counts
  dcat history     Show change history timeline
  dcat diff        Show uncommitted issue changes
  dcat doctor      Run health checks on your issue data
  dcat link        Manage general issue relationships
  dcat export      Export all issues (for backup or migration)
  dcat prune       Permanently remove deleted issues

── Getting Help ────────────────────────────────────────────────────────────

  dcat --help              List all commands
  dcat <command> --help    Help for a specific command
  dcat prime               Show the machine-readable workflow guide
"""
        typer.echo(guide_text)

    @app.command()
    def prime(
        opinionated: bool = typer.Option(  # noqa: ARG001
            False,
            "--opinionated",
            help="Include stronger, prescriptive recommendations.",
        ),
    ) -> None:
        """Show dogcat workflow guide and best practices for AI agents.

        This command displays guidance for effective dogcat usage and workflows.
        Git health checks are included automatically when in a git repo.
        Disable with: dcat config set git_tracking false
        """
        guide = """
DOGCAT WORKFLOW GUIDE

## Quick Start for AI agents

0a. Allowed issue types, priorities, and statuses:
      Types: bug, chore, epic, feature, question, story, task
      Priorities: 0 (Critical), 1 (High), 2 (Medium, default), 3 (Low), 4 (Minimal)
      Statuses: draft, open, in_progress, in_review, blocked, deferred, closed

0b. `dcat create` and `dcat update` both support --title, --description,
    --priority, --acceptance, --notes, --labels, --parent, --manual,
    --design, --external-ref, --depends-on, --blocks, --duplicate-of,
    --editor

1. Create an issue:
   $ dcat create "My first issue" --type bug --priority 1 -d "Description"

2. List issues:
   $ dcat list              - Show all open issues
   $ dcat ready             - Show issues ready to work (no blockers)
   $ dcat blocked           - Show all blocked issues

3. Update an issue:
   $ dcat update <issue_id> --status in_progress

4. Close an issue:
   $ dcat close <issue_id> --reason "Fixed"

## Essential Commands

  dcat create <title>                       - Create a new issue
  dcat create <title> --depends-on <id>     - Create with dependency
  dcat create <title> --blocks <id>         - Create issue that blocks another
  dcat update <id> --depends-on <other_id>  - Add dependency to existing issue
  dcat update <id> --blocks <other_id>      - Mark issue as blocking another
  dcat show <id>                            - View issue details
  dcat search <query>                       - Search issues across all fields
  dcat search <query> --type bug            - Search with type filter
  dcat close <id>                           - Mark issue as closed
  dcat history                              - Show change history timeline
  dcat history -i <id>                      - History for a specific issue
  dcat diff                                 - Show uncommitted issue changes
  dcat label <id> add -l <label>            - Add a label to an issue
  dcat label <id> remove -l <label>         - Remove a label

## Parent-Child vs Dependencies

Parent-child relationships are **organizational** (grouping), not **blocking**.
Child issues appear in `dcat ready` even when their parent is still open.

- Can this child task be started independently? → Keep as parent-child only
- Must the parent complete first? → Add explicit dependency:
    dcat update <child_id> --depends-on <parent_id>

## Breaking Down Large Tasks

When the user requests a large or complex task, break it into an epic
with child tasks rather than tackling it as a single issue:

1. Create an epic for the overall goal:
   $ dcat create "Redesign auth system" --type epic

2. Create child tasks under the epic:
   $ dcat create "Add OAuth provider" --type task --parent <epic_id>
   $ dcat create "Migrate user sessions" --type task --parent <epic_id>

3. Add dependencies between child tasks where ordering matters:
   $ dcat update <task_id> --depends-on <other_task_id>

Prefer multiple small, focused issues over one large issue.
If unsure about scope, ask the user before creating the breakdown.

## Agent Integration

Use --agent-only in list/ready to filter out manual issues:
  dcat ready --agent-only   # Show only agent-workable issues
  dcat list --agent-only    # Hide manual issues

If an issue requires human intervention (e.g. deploying, credentials),
mark it as manual and tell the user:
  dcat update <id> --manual

Do NOT attempt to work on manual issues. Leave them for the user.

## Status Workflow

  draft -> open -> in_progress -> in_review -> closed

## Questions

Questions (type: question) are used to track questions that need answers,
NOT tasks to work on.

## Labels

Labels are freeform tags (e.g. "backend", "ui", "auth") that appear in
`dcat list` and `dcat show`, and can be filtered with `--label`.
"""
        typer.echo(guide)

        # Git health checks — always run unless git_tracking is disabled
        dogcats_dir = find_dogcats_dir()
        config = load_config(dogcats_dir)
        git_tracking = config.get("git_tracking", True)

        if git_tracking is not False:
            git_result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                capture_output=True,
                check=False,
            )
            if git_result.returncode == 0:
                all_passed, checks = _run_git_checks()
                typer.echo("## Git Integration Health\n")
                for check in checks.values():
                    is_optional = check.get("optional", False)
                    if check["passed"]:
                        desc = check["description"]
                        typer.echo(f"  ✓ {desc}")
                    elif is_optional:
                        desc = check.get(
                            "fail_description",
                            check["description"],
                        )
                        typer.echo(f"  ○ {desc}")
                    else:
                        desc = check.get(
                            "fail_description",
                            check["description"],
                        )
                        typer.echo(f"  ✗ {desc}")
                        typer.echo(
                            f"    Consider running: {check['fix']}",
                        )
                typer.echo()
                if not all_passed:
                    typer.echo(
                        "You may want to fix the issues above for"
                        " smoother git integration.\n"
                        "To disable git checks: dcat config set"
                        " git_tracking false\n",
                    )

    @app.command()
    def version() -> None:
        """Show the dogcat version."""
        from dogcat._version import version as v

        typer.echo(v)
