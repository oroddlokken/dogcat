# Agent Instructions

## Issue Closure Workflow

Wait for explicit user approval before closing any issue. When work is complete:

1. Set status to `in_review`: `dcat update --status in_review $issueId`
2. Ask the user to test
3. Ask if we can close it: "Can I close issue [id] '[title]'?"
4. Only run `dcat close` after user confirms
5. Ask: "Should I add this to CHANGELOG.md?" — update if yes, always under the `[Unreleased]` section

## Issue tracking

This project uses **dcat** for issue tracking and **git** for version control. Run `dcat prime --opinionated` at the start of each session — it outputs the full workflow guide (issue types, statuses, priorities, and command reference). Then run `dcat list --agent-only` to see the current backlog. Work on bugs before features, high priority first.

When running multiple `dcat` commands, make separate parallel Bash tool calls instead of chaining them with `&&` and `echo` separators.

Mark each issue `in_progress` only when you begin active work on it — one at a time, not the whole backlog at once. Set `in_review` when that issue's work is done before moving on. Status should reflect what you are *actually* working on right now.

It is okay to work on multiple related issues at the same time. If there is a priority conflict, ask the user which to focus on first.

If the user brings up a new bug, feature or anything else that warrants changes to the code, ask whether to create an issue before starting code work. When creating issues, set appropriate labels using `--labels` based on the issue content (e.g. `cli`, `tui`, `api`, `docs`, `testing`, `refactor`, `ux`, `performance`, etc.).

When research or discussion produces findings relevant to an existing issue, ask these as **separate questions in order**:

1. First ask: "Should I update issue [id] with these findings?"
2. Only after that, separately ask: "Should I start working on the implementation?"
Always ask these as separate questions — the user may want to update the issue without starting work.

## Data files

`.dogcats/issues.jsonl` is the append-only JSONL store for all issue data. It contains three record types: `issue` (the issues themselves), `dependency` (blocks/depends-on relationships between issues), and `event` (audit log entries recording every change). The file is loaded by `JSONLStorage` in `src/dogcat/storage.py`.

`.dogcats/inbox.jsonl` is the append-only JSONL store for proposals — lightweight suggestions submitted from the web UI (or other sources) that haven't been triaged into full issues yet. Each `proposal` record has its own lifecycle (`open` → `closed`/`tombstone`). Managed by `src/dogcat/inbox.py`.

Use `dcat` CLI commands for all issue and proposal mutations. Never edit `.dogcats/issues.jsonl` or `.dogcats/inbox.jsonl` directly — the append-only audit log depends on records written in order by the CLI.

## Constants

Import shared values (statuses, priorities, labels, paths, etc.) from `src/dogcat/constants.py`. Hardcoding these values elsewhere causes drift when they change.

## Tab Completions

Every CLI option that accepts a constrained set of values (status, type, priority, owner, namespace, labels, config keys, export formats, dep/link types, etc.) MUST have an `autocompletion=` callback registered via Typer. Completers live in `src/dogcat/cli/_completions.py` and return `list[tuple[str, str]]` (value, description) pairs. Use `tabcomp.py` (run via `uv run ./tabcomp.py "dcat <command> --option "`) to verify completions work. If a new option accepts values from a known set, add a completer for it.

## Development

Always write tests for new features or when changing functionality.

Use `just test-changed` during development for fast feedback — it only runs tests affected by code changes since the last run. Use `just test-all` to confirm all tests are passing before committing or pushing.

Use `just lint` to check for linting errors. Run `just fmt` to automatically fix formatting issues. Run `just lint-all` (includes pyright) before committing or pushing — the CI pipeline will fail if linting errors are present, so they must be caught locally first.

Use uv for all dependency management — pip is not used in this project.

We distribute the software with Homebrew. The formula is at `../homebrew-tap/Formula/dogcat.rb`. Wait for user confirmation before updating the formula. Inform the user when CLI changes affect dependencies, entry points, or command structure — these may require a formula update.

## Merge driver changes

`docs/merge-coverage.md` maps every claim in `src/dogcat/merge_driver.py` module docstring to the test that exercises it. When you change the docstring or add a merge-driver test, update the matrix in the same change so the two stay aligned. If you add a row marked `gap`, link an open issue tracking the gap.

## Changelog

`CHANGELOG.md` follows [Keep a Changelog](https://keepachangelog.com/) format. Add all changelog entries under `[Unreleased]` at the top, never under historical version headings — release automation uses this section to determine what ships next. Use these section tags under each version heading:

- **Added** — new features
- **Changed** — changes to existing functionality
- **Deprecated** — features that will be removed
- **Removed** — features that were removed
- **Fixed** — bug fixes
- **Security** — vulnerability fixes
- **Development** — tooling, CI, dev workflow (custom extension)
