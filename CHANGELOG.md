# CHANGELOG

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
