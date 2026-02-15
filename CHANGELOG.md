# CHANGELOG

## [Unreleased]

### Fixed

- **Show blocker relationships in TUI issue editor** — the dependency fields now display "blocked by: ..." and "blocking: ..." labels and remain read-only in edit mode.
- **TUI now respects `visible_namespaces` / `hidden_namespaces` config** — the TUI dashboard and issue picker were showing issues from all namespaces, ignoring the namespace filtering configured in `config.toml`. Both now use `get_namespace_filter()` to match CLI behavior.
- **Fix `-l` short flag collision on `ready`** — removed `-l` from `--limit` (collided with `--label` on other commands). Added positional `[LIMIT]` argument and `--limit` option (no short flag) to `ready`, `blocked`, `in-progress`, `in-review`, `deferred`, and `manual`.
- **Fix `-n` short flag collision on `history`/`recently-*`** — removed `-n` from `--limit` (collided with `--notes` on create/update). Added positional `[LIMIT]` argument and `--limit` option to `history`, `recently-closed`, `recently-added`, and their aliases.
- **Rename `archive --confirm` to `--yes`/`-y`** — the old `--confirm` name was misleading (it meant "skip confirmation"). Renamed to `--yes`/`-y` to match common CLI conventions.
- **Remove non-standard `-ns` short flag from `list --namespace`** — two-character short flags violate POSIX convention. Use `--namespace` (long form) instead.
- **Rename `init --prefix` to `--namespace`** — aligned with the terminology used by every other command. New short flag is `-n`.
- **`dcat pr` command now visible in CLI help** — removed `hidden=True` so the progress-review command appears in the help output.
- **Archive no longer archives children whose parent is still open** — a closed child issue is now skipped if its parent is not also being archived, preserving context on epics and parent issues.
- **Add `os.fsync()` to storage compaction and append** — `_save()` and `_append()` now call `os.fsync()` before completing, preventing data loss on power failure or kernel panic.
- **Tolerate malformed last line in JSONL storage** — `_load()` now skips a corrupt last line (the most common crash artifact) with a warning instead of making all data inaccessible. The file is automatically compacted on the next write to clean up the garbage.
- **Atomic append with single write** — `_append()` pre-serializes the entire payload and writes it in one call, preventing truncated JSON lines on disk-full. Also prepends a newline if the file doesn't end with one (from a prior crash).
- **Compaction tolerates corrupt lines when preserving events** — `_save()` no longer crashes when scanning for event records in a file that contains malformed lines.
- **Remove stale `manual` from `UPDATABLE_FIELDS`** — the `manual` flag lives in `metadata`, not as a top-level Issue field. The stale entry allowed `setattr()` to silently succeed but the value was lost on serialization.
- **Merge driver: proper three-way merge for deps and links** — the JSONL merge driver now uses base records to implement true three-way merge semantics. Deletions by either side are correctly honored instead of being silently resurrected by the naive union.
- **Merge driver: error handling in CLI entry point** — `dcat git merge-driver` now catches exceptions and exits non-zero so git falls back to its default merge. Uses atomic write (temp file + rename) to prevent partial output on crash.
- **Merge driver: log warnings for malformed and conflict-marked lines** — `_parse_jsonl()` now logs warnings instead of silently dropping malformed JSONL lines and explicitly detects git conflict markers.
- **Compaction preserves records appended by other processes** — `_save()` now reloads from disk under the file lock before compacting, preventing data loss when another process appended records between load and compaction.
- **Merge driver: event dedup key too coarse** — event deduplication now includes `by` and changed field names in the key, so distinct events sharing the same timestamp and type are no longer collapsed.

### Removed

- **`--editor`/`-e` flag from `create` and `update`** — three entry points to the Textual editor was unnecessary. Use `dcat edit <id>` instead.

### Changed

- **Updated `dcat prime` docs** — added `reopen`, `delete`, `pr`, `link` to essential commands; documented `list <parent_id>` positional shorthand, `--namespace`/`--all-namespaces` flags, and `--json` global flag.
- **Updated `dcat guide` docs** — added sections for namespaces, git integration, and configuration; documented `--no-git`, `--tree`/`--table`, `reopen`, `delete`, `tui`, `--expand`, `labels`, `--remove-depends-on`/`--remove-blocks`, `archive`, `stream`, `features`, `version`, `demo`, and `prime --opinionated`.
- **Updated README command cheat sheet** — reorganized into categories (creating, viewing, filtering, updating, TUI, git & maintenance) and added 20 missing commands. Fixed typos.
- **Standardize attribution flags to `--by`** — replaced `--created-by`, `--updated-by`, `--closed-by`, `--deleted-by`, `--reopened-by`, `--author`, and `--operator` with a single `--by` flag across all commands.
- **Improved git health check messaging** — fix suggestions now use "Suggestion:" instead of the misleading "Consider running:" prefix, and the agent nudge tells the agent to inform the user and ask before fixing issues.

### Added

- **`--json` output on `prune` and `backfill-history`** — both commands now support `--json` for machine-readable output, completing JSON coverage across all data-producing commands.
- **`--namespace` option on `dcat update`** — change an issue's namespace via `dcat update <id> --namespace <new>`. Cascades the rename to all references: parent fields, duplicate_of, dependencies, and links.
- **`--namespace` option on `dcat archive`** — filter archived issues by namespace (`dcat archive --namespace <ns>`), useful for shared databases with multiple namespaces.
- **`--json` output flag on all commands** — global `dcat --json <command>` and per-command `dcat <command> --json` flags output machine-readable JSON. List/search return arrays, show/create/update return objects, and errors return `{"error": "..."}` to stderr with non-zero exit.
- **`dcat reopen` command** — dedicated command to reopen closed issues (`dcat reopen <id> [--reason]`). Validates the issue is closed, transitions to open, clears closed metadata, and emits a distinct `"reopened"` event in the audit trail.
- **`--parent` filter and positional argument on `dcat list`** — filter issues by parent via `dcat list --parent <id>` or the shorthand `dcat list <id>`. Shows the parent issue plus its direct children, and combines with all existing filters.
- **`--all-namespaces`/`-A` flag on all read commands** — bypass namespace visibility filtering on `list`, `search`, `history`, `recently-closed`, `recently-added`, and `export`.
- **Common filters on shortcut commands and search** — `ready`, `blocked`, `in-progress`, `in-review`, `deferred`, and `manual` now support `--type`, `--priority`, `--label`, `--owner`, `--parent`, `--namespace`, `--all-namespaces`, `--agent-only`, `--tree`, and `--table`. `search` gains `--priority`, `--label`, `--owner`, and `--namespace`.
- **Filters on `dcat export`** — `export` now supports `--status`, `--type`, `--priority`, `--label`, `--owner`, `--parent`, `--namespace`, and `--all-namespaces`. Dependencies and links are scoped to exported issues when filters are active.

### Development

- **Split `_cmd_maintenance.py` into focused modules** — replaced the 1337-line grab-bag with `_cmd_doctor.py`, `_cmd_search.py`, `_cmd_comment.py`, `_cmd_label.py`, and `_cmd_admin.py`.
- **Split `test_dogcat_cli.py` into 13 command-aligned test modules** — replaced the 7236-line monolithic test file with focused modules matching the CLI command structure.
- **Rename `just test-matrix` to `just matrix`** — the matrix command now also runs ruff linting in each Python version environment via tox.

## 0.8.5 (2026-02-14)

### Changed

- **`dcat prime --opinionated` now active** — the `--opinionated` flag injects prescriptive rules (e.g. "Do NOT use TodoWrite/TaskCreate") into the Rules section.

### Added

- **Split-pane TUI layout** — `dcat tui` now shows a master-detail split pane on wide terminals (200+ cols, 40+ rows). Highlighting an issue displays its details on the right; pressing `e` enables inline editing, `Enter` focuses the detail panel, and `Ctrl+S` saves. Narrow terminals retain the existing modal behavior. Escape is blocked during inline editing to prevent data loss.
- **`--acceptance-criteria` alias** — `dcat create` and `dcat update` now accept `--acceptance-criteria` as an alias for `--acceptance`, matching the underlying model field name.
- **Preview subtasks under deferred parents in `dcat list`** — deferred parents now show up to 3 highest-priority subtasks indented below them, with a `[...and N more hidden subtasks]` summary when there are more. Applies to brief, tree, and table formats. `--expand` still shows all subtasks.

### Fixed

- **TUI issue labels match CLI format** — the TUI issue list now uses the same `emoji [priority] id: title [type] [labels]` format and colors as `dcat list`, including showing the blocked `■` icon for dependency-blocked issues.

### Development

- **Token limit tests for `dcat prime` output** — added `MAX_PRIME_TOKENS` (1500) and `MAX_PRIME_TOKENS_OPINIONATED` (2000) constants with tests that verify output stays within budget using a conservative char-based token estimator (chars / 4).
- **Replace isort with ruff's built-in import sorting** — removed the `isort` dependency and `[tool.isort]` config in favor of ruff's `I` rules, simplifying the toolchain.
- **Two-step release workflow** — `just release-prep <version>` creates an RC tag, stamps the changelog, and opens a PR. Merging the PR triggers `publish.yml` which creates the final tag, builds, publishes the GitHub release with changelog body, and updates the Homebrew formula.
- **CI concurrency groups** — concurrent CI and release workflow runs on the same ref are cancelled automatically.

## 0.8.4 (2026-02-14)

### Added

- **`dcat list --expand`** — show subtasks of deferred parents inline without also revealing closed/deleted issues. The legend now shows how many issues are hidden and hints at `--expand`.
- **Show blocked issues in `dcat show`** — `dcat show` now displays a "Blocks" section listing issues that depend on the viewed issue, making both directions of a dependency visible.
- **Remove dependencies between issues** — `dcat update` now supports `--remove-depends-on` and `--remove-blocks` to remove dependency relationships.
- **`disable_legend_colors` config option** — `dcat config set disable_legend_colors true` turns off legend colors for users who prefer plain text.

### Changed

- **Dim closed issues in `dcat show`** — closed children, dependencies, and blocks are now fully dimmed (bright_black) to visually distinguish them from active issues.
- **Colored legend in `dcat list`** — status symbols and priority levels in the legend now use the same colors as the issue list. All five priority levels are listed individually.
- **Rich dependency display in `dcat show`** — Dependencies and Blocks sections now show full issue details (status, priority, title, type) instead of bare IDs with an ambiguous `(blocks)` label.

### Fixed

- **Fix `dcat ready` showing children of deferred parents** — `dcat ready` now walks up the parent chain and excludes issues whose parent (or any ancestor) is deferred, matching the behavior of `dcat list`.
- **Fix validator false circular dependency errors** — the JSONL validator now correctly handles dependency removals instead of reporting false cycles from stale edges.

### Development

- **Remove `black` formatter** — replaced `black` with `ruff format` as the sole code formatter. Resolves formatting conflicts between `black` and `ruff format` on assert statements. `isort` is retained for import sorting.

## 0.8.3

- **Collapse deferred subtrees in `dcat list`** — children of deferred parents are hidden with a `[N hidden subtasks]` summary; external issues blocked by deferred subtrees are annotated. JSON output is unaffected.
- **TUI is now generally available** — removed the feature gate; `dcat tui` works without enabling experimental flags.
  - **Create and edit from the dashboard** — press `n` to create a new issue and `e` to edit the selected issue directly from the TUI dashboard.
  - **Delete from the dashboard** — press `d` to delete with confirmation or `D` to delete immediately.
  - **View mode replaces detail screen** — selecting an issue opens the editor in read-only view mode; press `e` to switch to editing.
- **Status colors from constants** — CLI and TUI now use `STATUS_COLORS` from `constants.py` instead of hardcoded styles, keeping status coloring consistent and centralized.
- **Remove unused `compact()` method** — removed the unused `compact()` method from `JSONLStorage`.

## 0.8.2

- **Namespace visibility** — control which namespaces appear in `list`, `search`, `recently-added`, and `recently-closed`. Set `visible_namespaces` (whitelist) or `hidden_namespaces` (blocklist) via `dcat config set`. The primary namespace is always visible.
- **`dcat namespaces`** — new command that lists all namespaces with issue counts and visibility annotations (`primary`, `visible`, `hidden`). Supports `--json`.
- **`dcat list --namespace <ns>`** — filter the issue list to a single namespace, overriding any config-based visibility rules.
- **Array config keys** — `dcat config set visible_namespaces "a,b,c"` stores comma/space-separated values as arrays. `dcat config list` and `--json` display them correctly.
- **Doctor: mutual exclusivity check** — `dcat doctor` warns when both `visible_namespaces` and `hidden_namespaces` are set; `--fix` removes `hidden_namespaces`.
- **Renamed `issue_prefix` config key to `namespace`** — aligns the config key with the data model. Existing configs using `issue_prefix` are read transparently; `dcat doctor --fix` migrates the key automatically.
- **`dcat config keys`** — lists all available configuration keys with their type, default value, allowed values, and description. Supports `--json`.

## 0.8.1

- **Chronological display order** — `recently-closed`, `recently-added`, `rc`, `history`, and `diff` now show entries oldest-first so the timeline reads top-to-bottom.

## 0.8.0

- **Draft is now a status, not an issue type** — `draft` describes readiness, not the kind of work. The workflow is now `draft → open → in_progress → in_review → closed`. Existing draft-type issues are migrated transparently on load.
- **`dcat c d "title"`** — the `d` shorthand now sets status to draft instead of type. All three shorthands can be combined: `dcat c 0 d e "Design v2"`.
- **Removed `subtask` issue type** — subtask was redundant; any issue type can have a parent via `--parent`. Existing subtask-type issues are migrated to `task` on load.

## 0.7.3

- **Git health checks in standard `dcat prime`** — git integration checks now run by default (previously required `--opinionated`). Skipped when `git_tracking = false` in config.
- **`dcat init --no-git`** — initializes a dogcat repo with git tracking disabled: sets `git_tracking = false` and adds `.dogcats/` to `.gitignore`.

## 0.7.2

- **Merge driver is now a `dcat` subcommand** — replaced the separate `dcat-merge-jsonl` script with `dcat git merge-driver`, eliminating PATH/venv issues. `dcat git check` now validates the exact driver command.

## 0.7.1

- **`dcat prime --opinionated`** — new flag that adds prescriptive workflow guidelines and runs inline git health checks with actionable fix suggestions.

## 0.7.0

### Multi-team collaboration

Parallel branch work on `.dogcats/` no longer breaks on merge.

**What's new:**

- **Custom JSONL merge driver** — auto-resolves most merge conflicts. Run `dcat git setup` to install it.
- **Branch-safe compaction** — auto-compaction only runs on main/master, preventing merge conflicts from both branches compacting.
- **`dcat git` subcommands** — `dcat git setup` (install merge driver), `dcat git check` (verify config), `dcat git guide` (integration docs).
- **Deep data validation in `dcat doctor`** — checks field integrity, referential integrity, and circular dependencies.
- **Post-merge concurrent edit detection** — `dcat doctor --post-merge` warns when a merge silently resolved same-issue edits via last-write-wins.
