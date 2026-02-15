# Agent Instructions

## Issue tracking

This project uses **dcat** for issue tracking and **git** for version control. You MUST run `dcat prime --opinionated` for instructions.
Then run `dcat list --agent-only` to see the list of issues. Generally we work on bugs first, and always on high priority issues first.

ALWAYS run `dcat update --status in_progress $issueId` as soon as you pick up an issue — before any planning, research, or exploration.

It is okay to work on multiple issues at the same time - just mark all of them as in_progress, and ask the user which one to prioritize if there is a conflict.

If the user brings up a new bug, feature or anything else that warrants changes to the code, ALWAYS ask if we should create an issue for it before you start working on the code. When creating issues, set appropriate labels using `--labels` based on the issue content (e.g. `cli`, `tui`, `api`, `docs`, `testing`, `refactor`, `ux`, `performance`, etc.).

When research or discussion produces findings relevant to an existing issue, ask these as **separate questions in order**:

1. First ask: "Should I update issue [id] with these findings?"
2. Only after that, separately ask: "Should I start working on the implementation?"
Do NOT combine these into one question. The user may want to update the issue without starting work.

### Closing Issues - IMPORTANT

NEVER close issues without explicit user approval. When work is complete:

1. Set status to `in_review`: `dcat update --status in_review $issueId`
2. Ask the user to test
3. Ask if we can close it: "Can I close issue [id] '[title]'?"
4. Only run `dcat close` after user confirms
5. Ask: "Should I add this to CHANGELOG.md?" — update if yes

## Changelog

`CHANGELOG.md` follows [Keep a Changelog](https://keepachangelog.com/) format. Use these section tags under each version heading:

- **Added** — new features
- **Changed** — changes to existing functionality
- **Deprecated** — features that will be removed
- **Removed** — features that were removed
- **Fixed** — bug fixes
- **Security** — vulnerability fixes
- **Development** — tooling, CI, dev workflow (custom extension)

## Constants

`src/dogcat/constants.py` is the single source of truth for shared values used by dogcat (CLI):

Import from this module rather than hardcoding values in multiple places.

## Development

Always write tests for new features or when changing functionality.

Use `just test` during development for fast feedback (excludes regression and TUI tests). Run `just test-tui` for TUI-specific tests. Run `just test-regression` once you're happy with the changes to verify nothing is broken across versions. Use `just test-all` to run everything.

Use `just lint` to check for linting errors. Run `just fmt` to automatically fix formatting issues. The CICD pipeline will fail if linting errors are present, so they must be fixed before pushing code.

We are using uv for dependency management. NEVER use pip.

We distribute the software with Homebrew. The formula is available at "../homebrew-tap/Formula/dogcat.rb". If you make changes to the CLI that would require a change to the Formula, please inform the user and ask if you should update the formula.
