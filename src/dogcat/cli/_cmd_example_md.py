"""Example CLAUDE.md generation command for dogcat CLI."""

from __future__ import annotations

import typer

_CLAUDE_MD_TEMPLATE = """\
# Agent Instructions

## Issue tracking

This project uses **dcat** for issue tracking. \
You MUST run `dcat prime --opinionated` for instructions.
Then run `dcat list --agent-only` to see the list of issues. Generally we work \
on bugs first, and always on high priority issues first.

Mark each issue `in_progress` right when you start working on it — not before. \
Set `in_review` when work on that issue is done before moving on. The status \
should reflect what you are *actually* working on right now.

It is okay to work on multiple related issues at the same time, but do NOT \
batch-mark an entire backlog as `in_progress` upfront. If there is a priority \
conflict, ask the user which to focus on first.

If the user brings up a new bug, feature or anything else that warrants \
changes to the code, ALWAYS ask if we should create an issue for it before \
you start working on the code. When creating issues, set appropriate labels \
using `--labels` based on the issue content (e.g. `cli`, `tui`, `api`, \
`docs`, `testing`, `refactor`, `ux`, `performance`, etc.).

When research or discussion produces findings relevant to an existing issue, \
ask these as **separate questions in order**:

1. First ask: "Should I update issue [id] with these findings?"
2. Only after that, separately ask: "Should I start working on the \
implementation?"
Do NOT combine these into one question. The user may want to update the \
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
