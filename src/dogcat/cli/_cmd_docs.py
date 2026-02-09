"""Documentation commands for dogcat CLI."""

from __future__ import annotations

import typer


def register(app: typer.Typer) -> None:
    """Register documentation commands."""

    @app.command()
    def git() -> None:
        """Show guide for integrating dogcat with git."""
        guide_text = """\
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

── Resolving Merge Conflicts ───────────────────────────────────────────────

  Dogcat stores issues in .dogcats/issues.jsonl, an append-only format.
  Conflicts are rare, but when they happen:

  1. Open the conflicted file (.dogcats/issues.jsonl)
  2. In most cases, keep BOTH sides — each line is an independent event
  3. Remove the conflict markers (<<<<<<, ======, >>>>>>)
  4. Save and continue the merge

  Example conflict:
    <<<<<<< HEAD
    {"id":"abc-1","title":"Fix login","op":"update","status":"closed"}
    =======
    {"id":"abc-2","title":"Add signup","op":"create","status":"open"}
    >>>>>>> feature-branch

  Resolution: keep both lines (they are separate issues).

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

  Commit issues:          git add .dogcats/ && git commit
  Ignore issues:          echo ".dogcats/" >> .gitignore
  Log issue history:      git log --oneline -- .dogcats/
"""
        typer.echo(guide_text)

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

  Shorthands also work — single letters for type, digits for priority:

    dcat create "Crash on empty input" b 1

  Available types: task (t), bug (b), feature (f), story (s),
                   chore (c), epic (e), question (q), draft (d)

  Priority scale: 0 = Critical, 1 = High, 2 = Medium (default),
                  3 = Low, 4 = Minimal

── Viewing Issues ──────────────────────────────────────────────────────────

  List all open issues:

    dcat list

  Show as a formatted table:

    dcat list --table

  View a specific issue in detail:

    dcat show <issue_id>

  Search issues by keyword:

    dcat search "login"

  See recently closed issues:

    dcat recently-closed

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

    dcat create "Subtask" --parent <parent_id>

  Parent-child is purely organizational — children are NOT blocked by
  their parent. If a child genuinely needs its parent to finish first,
  add an explicit dependency:

    dcat dep <child_id> add --depends-on <parent_id>

  View dependencies for an issue:

    dcat dep <id> list

  See all blocked issues across the project:

    dcat blocked

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
  dcat doctor      Run health checks on your issue data
  dcat export      Export all issues (for backup or migration)
  dcat prune       Permanently remove deleted issues

── Getting Help ────────────────────────────────────────────────────────────

  dcat --help              List all commands
  dcat <command> --help    Help for a specific command
  dcat prime               Show the machine-readable workflow guide
"""
        typer.echo(guide_text)

    @app.command()
    def prime() -> None:
        """Show dogcat workflow guide and best practices for AI agents.

        This command displays guidance for effective dogcat usage and workflows.
        """
        guide = """
DOGCAT WORKFLOW GUIDE

## Quick Start for AI agents

0a. Allowed issue types, priorities, and statuses:
      Types: bug, chore, draft, epic, feature, question, story, task
      Priorities: 0 (Critical), 1 (High), 2 (Medium, default), 3 (Low), 4 (Minimal)
      Statuses: open, in_progress, in_review, blocked, deferred, closed

0b. `dcat create` and `dcat update` both support --title, --description,
    --priority, --acceptance, --notes, --labels, --parent, --manual,
    --design, --external-ref, --depends-on, --blocks, --duplicate-of,
    --editor

1. Create an issue:
   $ dcat create "My first issue" --type bug --priority 1 -d "Description"
   # All options from 0b above can be used here.

2. List issues:
   $ dcat list              - Show all open issues
   $ dcat list --closed     - Show only closed issues
   $ dcat ready             - Show issues ready to work (no blockers)

3. Update an issue:
   $ dcat update <issue_id> --status in_progress

4. Close an issue:
   $ dcat close <issue_id> --reason "Fixed"

## Essential Commands

### Creating & Updating
  dcat create <title>                       - Create a new issue
  dcat create <title> --status in_progress  - Create with status
  dcat create <title> --depends-on <id>     - Create with dependency
  dcat update <id>                          - Update an issue
  dcat update <id> --depends-on <other_id>  - Add dependency via update
  dcat update <id> --editor                 - Update then open editor
  dcat close <id>                           - Mark issue as closed

### Managing Dependencies
  dcat dep <id> add --depends-on <other_id> - Add dependency
  dcat dep <id> list                        - Show dependencies
  dcat blocked                              - Show all blocked issues

## Parent-Child vs Dependencies

Parent-child relationships are **organizational** (grouping), not **blocking**.
Child issues appear in `dcat ready` even when their parent is still open.

Use this to decide:
- Can this child task be started independently? → Keep as parent-child only
- Must the parent complete first? → Add explicit dependency:
    dcat dep <child_id> add --depends-on <parent_id>

Example: A feature with subtasks - subtasks can often be worked in parallel,
so they should NOT depend on the parent. But if subtask B needs subtask A's
output, add a dependency between them.

## Agent Integration

Use --manual to mark issues that require manual action:
  dcat create "Manual review needed" --manual

Use --agent-only in list/ready to filter out manual issues:
  dcat ready --agent-only   # Show only agent-workable issues
  dcat list --agent-only    # Hide manual issues

If you determine that an issue requires human intervention (e.g. deploying,
physical access, subjective judgment, credentials you don't have), mark it
as manual and tell the user it needs their attention:
  dcat update <id> --manual
Then notify the user: explain which issue is blocked and what user action
is needed so they can pick it up.

Do NOT attempt to work on manual issues. Leave them for the user.

## Status Workflow

Issues progress through these statuses:
  open -> in_progress -> in_review -> closed

Update status:
  dcat update <id> --status in_review

## Common Workflows

### Starting Work on an Issue
$ dcat ready              # Check available work
$ dcat show <issue_id>    # View issue details (includes parent, children, dependencies)
$ dcat update <issue_id> --status in_progress

### Submitting for Review
$ dcat update <issue_id> --status in_review  # Alternative

### Creating Related Issues
$ dcat create "Blocker task"
$ dcat create "Dependent task" --depends-on <blocker_id>

### Closing Issues
$ dcat close <issue_id> --reason "Explanation"

### Tracking Dependencies
$ dcat blocked                                       # See what's blocked
$ dcat dep <new_task> add --depends-on <blocker_id>

## Questions

Questions (type: question, shorthand: q) are special issues used to track
questions that need answers, NOT tasks to work on. Use them to:
- Document technical questions that need research
- Track decisions that need to be made
- Record questions for team discussion

## Need Help?
  dcat --help            - Show all commands
  dcat <command> --help  - Get help for a specific command
"""
        typer.echo(guide)

    @app.command()
    def version() -> None:
        """Show the dogcat version."""
        from dogcat._version import version as v

        typer.echo(v)
