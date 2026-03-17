"""Example CLAUDE.md generation command for dogcat CLI."""

from __future__ import annotations

import typer

_CLAUDE_MD_TEMPLATE = """\
# Agent Instructions

## Issue Closure Workflow

Wait for explicit user approval before closing any issue. When work is complete:

1. Set status to `in_review`: `dcat update --status in_review $issueId`
2. Ask the user to test
3. Ask if we can close it: "Can I close issue [id] '[title]'?"
4. Only run `dcat close` after user confirms

## Issue tracking

This project uses **dcat** for issue tracking. Run `dcat prime --opinionated` \
at the start of each session — it outputs the full workflow guide (issue types, \
statuses, priorities, and command reference). Then run `dcat list --agent-only` \
to see the current backlog. Work on bugs before features, high priority first.

When running multiple `dcat` commands, make separate parallel Bash tool calls \
instead of chaining them with `&&` and `echo` separators.

Mark each issue `in_progress` only when you begin active work on it — one at \
a time, not the whole backlog at once. Set `in_review` when that issue's work \
is done before moving on. Status should reflect what you are *actually* \
working on right now.

It is okay to work on multiple related issues at the same time. If there is \
a priority conflict, ask the user which to focus on first.

When research or discussion produces findings relevant to an existing issue, \
ask these as **separate questions in order**:

1. First ask: "Should I update issue [id] with these findings?"
2. Only after that, separately ask: "Should I start working on the \
implementation?"
Always ask these as separate questions — the user may want to update the \
issue without starting work.
"""


def register(app: typer.Typer) -> None:
    """Register example-md command."""

    @app.command("example-md")
    def example_md() -> None:
        """Show an example CLAUDE.md with recommended dcat workflow instructions.

        Outputs a ready-to-use markdown file that configures AI agents to work
        with dcat for issue tracking. Copy or redirect the output to your
        project's CLAUDE.md.
        """
        typer.echo(_CLAUDE_MD_TEMPLATE, nl=False)
