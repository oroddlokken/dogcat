# Agent Instructions

## Issue tracking

This project uses **dcat** for issue tracking and **git** for version control. You MUST run `dcat prime` for instructions.
Then run `dcat list --agent-only` to see the list of issues. Generally we work on bugs first, and always on high priority issues first.

ALWAYS run `dcat update --status in_progress $issueId` when you start working on an issue.

It is okay to work on multiple issues at the same time - just mark all of them as in_progress, and ask the user which one to prioritize if there is a conflict.

If the user brings up a new bug, feature or anything else that warrants changes to the code, ALWAYS ask if we should create an issue for it before you start working on the code.

### Closing Issues - IMPORTANT

NEVER close issues without explicit user approval. When work is complete:

1. Set status to `in_review`: `dcat update --status in_review $issueId`
2. Ask the user to test
3. Ask if we can close it: "Can I close issue [id] '[title]'?"
4. Only run `dcat close` after user confirms

## Constants

`src/dogcat/constants.py` is the single source of truth for shared values used by dogcat (CLI):

Import from this module rather than hardcoding values in multiple places.

## Development

Remember to run "$PROJECT_FOLDER/.venv/bin/activate &&" before running any commands that runs Python. This is to ensure the virtual environment is loaded and all dependencies are installed.

Always write tests for new features or when changing functionality.

Use `just test` during development for fast feedback (excludes regression tests). Run `just test-regression` once you're happy with the changes to verify nothing is broken across versions. Use `just test-all` to run everything.

Use `just lint` to check for linting errors. Run `just fmt-all` to automatically fix formatting issues. The CICD pipeline will fail if linting errors are present, so they must be fixed before pushing code.

We are using uv for dependency management. Never call out to pip.

## Rules

**NEVER** run any git operations on the .dogcats folder.
