# Agent Instructions

## Issue tracking

This project uses **dcat** for issue tracking and **git** for version control. You MUST run `dcat prime --opinionated` for instructions.
Then run `dcat list --agent-only` to see the list of issues. Generally we work on bugs first, and always on high priority issues first.

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
5. Ask: "Should I add this to CHANGELOG.md?" — update if yes, always under the `[Unreleased]` section

## Changelog

`CHANGELOG.md` follows [Keep a Changelog](https://keepachangelog.com/) format. Always add entries under the `[Unreleased]` section at the top — never under a released version. Use these section tags under each version heading:

- **Added** — new features
- **Changed** — changes to existing functionality
- **Deprecated** — features that will be removed
- **Removed** — features that were removed
- **Fixed** — bug fixes
- **Security** — vulnerability fixes
- **Development** — tooling, CI, dev workflow (custom extension)

## Data files

`.dogcats/issues.jsonl` is the append-only JSONL store for all issue data. It contains three record types: `issue` (the issues themselves), `dependency` (blocks/depends-on relationships between issues), and `event` (audit log entries recording every change). The file is loaded by `JSONLStorage` in `src/dogcat/storage.py`.

`.dogcats/inbox.jsonl` is the append-only JSONL store for proposals — lightweight suggestions submitted from the web UI (or other sources) that haven't been triaged into full issues yet. Each `proposal` record has its own lifecycle (`open` → `closed`/`tombstone`). Managed by `src/dogcat/inbox.py`.

## Constants

`src/dogcat/constants.py` is the single source of truth for shared values used by dogcat (CLI):

Import from this module rather than hardcoding values in multiple places.

## Tab Completions

Every CLI option that accepts a constrained set of values (status, type, priority, owner, namespace, labels, config keys, export formats, dep/link types, etc.) MUST have an `autocompletion=` callback registered via Typer. Completers live in `src/dogcat/cli/_completions.py` and return `list[tuple[str, str]]` (value, description) pairs. Use `tabcomp.py` (run via `uv run ./tabcomp.py "dcat <command> --option "`) to verify completions work. If a new option accepts values from a known set, add a completer for it.

## Development

Always write tests for new features or when changing functionality.

Use `just test-changed` during development for fast feedback — it only runs tests affected by code changes since the last run. Use `just test-all` to confirm all tests are passing before committing or pushing.

Use `just lint` to check for linting errors. Run `just fmt` to automatically fix formatting issues. Run `just lint-all` (includes pyright) before committing or pushing — the CI pipeline will fail if linting errors are present, so they must be caught locally first.

We are using uv for dependency management. NEVER use pip.

We distribute the software with Homebrew. The formula is available at "../homebrew-tap/Formula/dogcat.rb". If you make changes to the CLI that would require a change to the Formula, please inform the user and ask if you should update the formula.
