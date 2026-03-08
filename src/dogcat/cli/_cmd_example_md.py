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

When research or discussion produces findings relevant to an existing issue, \
ask these as **separate questions in order**:

1. First ask: "Should I update issue [id] with these findings?"
2. Only after that, separately ask: "Should I start working on the \
implementation?"
Do NOT combine these into one question. The user may want to update the \
issue without starting work.

### Closing Issues - IMPORTANT

NEVER close issues without explicit user approval. When work is complete:

1. Set status to `in_review`: `dcat update --status in_review $issueId`
2. Ask the user to test
3. Ask if we can close it: "Can I close issue [id] '[title]'?"
4. Only run `dcat close` after user confirms
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
