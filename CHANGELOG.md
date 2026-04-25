# CHANGELOG

## [Unreleased]

### Added

- **`dcat doctor --check-id-distribution`** — opt-in flag prints per-namespace ID-collision statistics (`p_step` per generation, `p_all` cumulative birthday-paradox) and warns when cumulative collision probability ≥ 5%. New `address_space`, `collision_probability`, and `cumulative_collision_probability` helpers in `idgen.py`; the module docstring documents the math behind `ID_LENGTH_THRESHOLDS` (closes dogcat-30es)
- **`dcat_version` schema-evolution check on load** — new `_schema.py` module documents the field's semantics, compatibility expectations, and how to bump the schema. `JSONLStorage._load` and `InboxStorage._load` now log a warning when records were written by a strictly newer dcat than the running tool (closes dogcat-8d5j)
- **`--manual` filter for listing commands** — inverse of `--agent-only`, shows only issues marked as manual. Available on `list`, `ready`, `blocked`, `in-progress`, `in-review`, `open`, `deferred`, `snoozed`, `stale`, `pr`, `recently-added`, `recently-closed`, and `search`. `--agent-only` also added to `search`, `pr`, `recently-added`, and `recently-closed` for parity. `--manual` and `--agent-only` are mutually exclusive (closes dogcat-1iqx)
- **`--has-comments` / `--without-comments` filter for listing commands** — show only issues with (or without) at least one comment. Available on `list`, `ready`, `blocked`, `in-progress`, `in-review`, `open`, `deferred`, `snoozed`, `stale`, `pr`, `recently-added`, `recently-closed`, and `search`. The two flags are mutually exclusive and combine with other filters such as `--agent-only` (closes dogcat-4rip)
- **`DCAT_WEB_HOST` / `DCAT_WEB_PORT` env vars for `dcat web`** — host and port defaults can now be overridden via environment for deployments that don't want to pass CLI flags. CLI flags still take precedence; constants live in `constants.py` (closes dogcat-ev39)

### Changed

- **Documented merge driver invariants in `merge_driver.py`** — module docstring now spells out the merge algebra per record kind: LWW + monotonicity for issues, finality-ranked LWW for proposals (tombstone is absorbing), three-way diff with "delete-wins-against-silence" for deps/links, and grow-only union for events. Includes scope notes on whole-record LWW, audit-metadata collapse for dep/link identity, and the explicit out-of-scope items (closes dogcat-5dzc)
- **`deps.py` pre-builds lookup dicts to remove N+1 patterns** — `get_ready_work`, `get_blocked_issues`, `detect_cycles`, and `would_create_cycle` now build an `issues_by_id` map and a `dep_map` once per call instead of repeatedly invoking `storage.get()`/`storage.get_dependencies()` inside loops and recursion; `_has_deferred_ancestor` is memoized across the ancestor chain (closes dogcat-3s0c)
- **Renamed `Issue.close_reason`/`delete_reason` to `closed_reason`/`deleted_reason`** — fields now match the suffix style of `closed_at`/`closed_by`/`deleted_at`/`deleted_by`. The same rename applies to `Proposal.closed_reason`. JSONL written from now on uses the new keys; `dict_to_issue()` and `dict_to_proposal()` accept both old and new keys so existing data files load unchanged (closes dogcat-1auf)
- **`stream.py` change tracking uses a typed `FieldChange` dataclass** — `StreamEvent.changes` is now `dict[str, FieldChange]` instead of `dict[str, dict[str, Any]]`, replacing implicit `"old"`/`"new"` dict keys with explicit `.old`/`.new` attributes. `to_dict()` still emits the legacy `{"old": ..., "new": ...}` shape for JSON output (closes dogcat-60zp)
- **Renamed CLI command functions to drop `_cmd`/`_command` suffixes** — `new_issue_cmd` → `new_issue`, `remove_cmd` → `remove`, `diff_cmd` → `diff`, `link_command` → `link`, matching the dominant convention across the rest of the CLI (closes dogcat-1zj4)
- **Narrowed broad `except Exception` blocks in storage and TUI** — `storage.py` write/event-log/inbox-load/config-load handlers now catch the specific exception classes that can actually be raised (`OSError`, `orjson.JSONEncodeError`, `RuntimeError`, `ValueError`); `tui/dashboard.py` catches `NoMatches` for `query_one` and `(IndexError, AttributeError)` for `OptionList.get_option_at_index`. Real bugs no longer hide behind blanket handlers (closes dogcat-1e6m)
- **`storage.list()` accepts a typed `FilterSpec` dataclass** — replaces the implicit `dict[str, Any]` filter argument with explicit fields (status, priority, type, label, owner, ...) for IDE autocomplete and key validation. Legacy dict input is still accepted via `FilterSpec.from_dict()` for back-compat (closes dogcat-29gk)
- **`dcat update` builds a typed `UpdateRequest` instead of a dict accumulator** — `_cmd_update.py` now constructs an `UpdateRequest` dataclass whose fields match `UPDATABLE_FIELDS`, catching unknown keys and wrong value types at construction time before they reach `storage.update()` (closes dogcat-mt3c)
- **`Link.link_type` accepts a `LinkType` enum** — built-in relations (`relates_to`, `duplicates`, `blocks`, …) are now an enum, matching the existing `DependencyType` pattern. Custom user-defined relation strings still work via a `LinkType | str` union (closes dogcat-1jl8)
- **Typed `Issue.metadata`** — replaced `dict[str, Any]` with a typed alternative so strict pyright no longer treats every metadata access as `Any` (closes dogcat-1rzm)
- **`EventLog` and `InboxEventLog` share a `_BaseEventLog`** — the ~120 lines of duplicated append/read/file-lock logic are now in one parameterized base class; the two subclasses differ only by file path (closes dogcat-2ngk)
- **`storage.py` split into focused modules** — extracted compaction logic into `_compaction.py` and index management into `_indexes.py`, shrinking the storage module's surface area (closes dogcat-6djm)
- **`format_issue_table()` simplified** — nested closures (`_add_issue_row`, `_add_summary_row`) extracted to module-level helpers so the function reads top-to-bottom without 4+ levels of indentation (closes dogcat-1fgr)
- **Shared `load_open_inbox_proposals()` helper in `_helpers.py`** — `_cmd_read.py`, `_cmd_workflow.py`, and `_cmd_admin.py` previously each had their own try/except + `InboxStorage` init + namespace filter block; they now call one helper (closes dogcat-oqvz)
- **TUI dashboard uses O(1) dict lookup for selected-row → full_id** — `_full_id_by_label_plain` is built once during `_load_issues()`, replacing three linear scans of `_issues` per keystroke/selection in `dashboard.py` (closes dogcat-5ib0)
- **Consolidated DRY review findings (epic dogcat-ep16)** — twelve focused refactors hoisted duplication into shared helpers and removed wrong abstractions. New shared modules: `_jsonl_io.py` (atomic-rewrite + append primitives now used by both `JSONLStorage` and `InboxStorage`), `_id_resolve.py` (single `resolve_partial_id` using `rsplit` so multi-segment namespaces like `dogcat-inbox-X` resolve correctly — fixes a latent bug in storage that used `split('-', 1)`), and `_diff.py` (shared `field_value` / `tracked_changes` for event-log change detection). New CLI helpers: `with_ns_shim` decorator (replaces 14 repetitions of the 13-line hidden `--namespace`/`--all-namespaces` shim block, removing 28 `noqa: ARG001` markers), `apply_to_each` (collapsed seven `_*_one(storage, id, ..., json_output)` wrappers into closures across close/delete/reopen/update and inbox close/delete/reject), `resolve_dogcats_dir` (replaces six inline `if not Path(d).is_dir(): d = find_dogcats_dir()` walks in `_cmd_inbox.py`), and `load_remote_inbox_proposals` (collapses the local + remote inbox loading block in two commands). `_BaseEventLog.emit()` now owns the best-effort change-event append pattern that storage and inbox both used. `is_manual_issue(metadata)` is now used at all 14 inline `metadata.get("manual") or metadata.get("no_agent")` call sites (cli, formatting, tui). `_json_state.py` is split into pure `is_json()` + explicit `set_json(value)` (no more `is_json_output(...)  # sync local flag for echo_error` ritual); the global Typer callback resets state per invocation so test isolation works. `apply_common_filters` is now used by `recently_added`, `pr/progress_review`, and `list` commands (the holdouts that re-implemented the same manual/agent/comments loops); the redundant `check_*_exclusive` calls in those commands have been dropped since `apply_common_filters` already validates. (closes dogcat-ep16, dogcat-30a6, dogcat-3u8x, dogcat-259j, dogcat-56ol, dogcat-2ucq, dogcat-4g12, dogcat-is20, dogcat-68od, dogcat-vs8j, dogcat-1buj, dogcat-6h5s, dogcat-n4ua)

### Fixed

- **TUI dashboard issue list no longer clips bottom rows** — the `OptionList` in `dashboard.py` relied on Textual's default `height: auto; max-height: 100%`, which resolves against the parent's full height rather than the space remaining after the search `Input` above it. With many issues the list extended past the footer and the parent `Vertical`'s `overflow: hidden` silently clipped the bottom rows with no scrollbar. Setting `height: 1fr` on `#issue-list` constrains it to the remaining vertical space so its inherited `overflow-y: auto` shows a scrollbar (closes dogcat-1ygm)
- **Compaction race condition in storage layer** — `_maybe_compact()` previously ran *after* the append lock was released and only re-acquired the lock inside `_save()`, allowing two concurrent processes to both decide to compact based on stale line counts. Refactored `_save` into `_save` + `_save_locked`; the eligibility check and compaction now run inside the same lock the append used (closes dogcat-h0tt)
- **`dcat web propose` blocked the event loop on every submission** — the FastAPI handler did synchronous JSONL appends inline, so concurrent requests were serialized. `InboxStorage()` construction, `inbox.create()`, and the new namespace-persist write now run via `asyncio.to_thread()` (closes dogcat-34j7)
- **`dcat web propose` lost dynamically-created namespaces on restart** — when `allow_creating_namespaces=true`, new namespaces were appended to a runtime list only and vanished when the server stopped. They are now appended to `pinned_namespaces` in `config.local.toml`, which `get_namespaces()` already loads on boot (closes dogcat-5a2f)
- **ARIA semantics on the web proposal form** — the namespace dropdown was a plain `<div role="button">` with no `aria-expanded`/`aria-controls`/`aria-labelledby`, no live region for form errors, and no `aria-invalid`/`aria-required` on inputs. The form now uses `combobox`/`listbox`/`option` roles with state synced from JS (Esc closes), an `aria-live` status region for submission outcomes, hidden labels for every input, and `role="alert"` + `aria-invalid` on validation failures (closes dogcat-5vsb)
- **Metadata field changes are now tracked in `dcat diff` and `dcat history`** — toggling `--manual`/`--no-manual` (and any other `metadata.*` flag, e.g. `no_agent`) previously left no record in the audit log or diff output because `metadata` was not in `TRACKED_FIELDS`. Storage now diffs the metadata dict key-by-key on update and emits per-key changes as `metadata.<key>` entries; `dcat diff` does the same comparison against the git baseline (closes dogcat-4ze1)
- **`dcat label add`/`remove` now emit history events** — the commands mutated `issue.labels` in place before calling `storage.update()`, so the old/new comparison saw the same already-mutated list reference and suppressed the event. Both subcommands now build a fresh list and pass that to `storage.update()`, producing a proper `labels: [...] -> [...]` event in `dcat history` and `dcat diff` (closes dogcat-ogb1)
- **Lock file open failures now produce a clear error** — `storage.py`, `inbox.py`, and `event_log.py` previously crashed with a raw `OSError` traceback when the `.dogcats/` directory was missing or unwritable. All three lock implementations now wrap `open("w")` in `try/except OSError` and raise a `RuntimeError` naming the lock path and remediation (closes dogcat-11w4)
- **Unknown `record_type` values no longer silently misclassify as `"issue"`** — `classify_record()` now logs a warning and returns `"unknown"` when it sees a `record_type` outside the known set (`issue`, `dependency`, `link`, `event`, `proposal`). Callers that compare against specific strings now skip the record instead of merging it with the wrong semantics — protecting against silent data loss when a future record type is added without updating the merge driver (closes dogcat-5dc8)
- **Malformed JSONL inside merge conflict sections now produces warning logs** — `parse_conflicted_jsonl()` in `merge_driver.py` previously suppressed `JSONDecodeError` silently in both the shared and conflict-section parsers, so corrupted records were dropped without trace during `dcat git rebase`. Each parser now logs the line number and section (ours/base/theirs/shared), matching the pattern already used in `_parse_jsonl()` (closes dogcat-6cjt)
- **Tightened CSP `script-src` for the web proposal endpoint** — replaced `'unsafe-inline'` with `'self'` and moved the inline IIFE to `static/js/propose.js`, so the form's JS is served as an external file and CSP can fully block inline script injection (closes dogcat-2v7d)

### Security

- **Per-session CSRF tokens on `dcat web propose`** — the previous token was generated once at app startup via `secrets.token_urlsafe(32)` and shared across every browser session, so any client that ever obtained it could reuse it indefinitely until restart. Replaced with a double-submit cookie (`dcat_csrf`, HttpOnly, SameSite=Strict, 1h max-age): each session gets its own token, and tokens expire (closes dogcat-5dd4)
- **Whitelisted namespace format on the web proposal form** — the form previously accepted arbitrary strings for `namespace`, including spaces, control characters, and Unicode homoglyphs that could spoof an existing namespace visually. Input is now NFKC-normalized then matched against `^[A-Za-z0-9_-]{1,64}$`; fullwidth ASCII folds to plain ASCII before the check, but Cyrillic look-alikes (and similar) are rejected (closes dogcat-1819)

### Development

- **Upgraded GitHub Actions to Node.js 24** — bumped `actions/checkout` from v4 to v5 and `astral-sh/setup-uv` from v4 to v7 (both native Node 24), and added `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24` env var for `softprops/action-gh-release@v2` which has no Node 24 release yet (closes dogcat-1e2t)
- **Fixed `@contextmanager` pyright deprecation warnings** — changed `Iterator[None]` return types to `Generator[None, None, None]` in `storage.py` and `inbox.py` so `just lint-all` passes cleanly
- **Removed unused `httpx` dev dependency** — `httpx` was declared in `pyproject.toml` but never imported (FastAPI's `TestClient` ships with FastAPI itself), so dropping it shrinks the dev install (closes dogcat-3x7x)
- **Removed duplicate `pytest-xdist` declaration in `pyproject.toml`** — the dev group had both `pytest-xdist[psutil]` and `pytest-xdist==3.8.0`; kept only the `[psutil]` extra entry (closes dogcat-54je)
- **Added tests for `storage.update()` status transition edge cases** — covers CLOSED→OPEN→CLOSED round-trip, closing without `closed_by`, CLOSED→BLOCKED→CLOSED, and bulk status updates, closing the gap that allowed the dogcat-36bt regression (closes dogcat-3frh)
- **Added adversarial tests for `parse_conflicted_jsonl()`** — covers malformed JSON inside conflict markers, nested/repeated conflict markers, conflicts with only dependency/link records (no issues), and dependency records with typos in `issue_id` (closes dogcat-4ket)
- **Added tests for `storage.delete()` cascading cleanup** — verifies that deleting an issue with incoming and outgoing dependencies removes all of them, that links referencing it on either side are dropped, and that the cleanup persists across a reload from disk (closes dogcat-5wux)
- **Added edge-case tests for `parse_duration()`** — covers `'0d'` zero duration, decimal amounts (rejected), empty string (rejected), large `'999d'` durations, ISO8601 with timezone offsets, and past dates (closes dogcat-2enu)
- **Removed unused `--full` parameter from `dcat show`** — the option was a hidden no-op suppressed with `# noqa: ARG001`; the obsolete acceptance test was removed too (closes dogcat-29lw)
- **Extracted `advisory_file_lock()` to a shared `dogcat/locking.py`** — `storage`, `inbox`, and `event_log` previously had three near-identical fcntl lock implementations; they now share one context manager (closes dogcat-3bqe)
- **Extracted `_validate_timestamps()` helper in `_validate.py`** — `validate_issue` and `validate_proposal_record` shared the same datetime-parsing loop; both now delegate to the helper (closes dogcat-59hk)
- **Extracted `ISSUE_STATUS_EMOJIS` and `PROPOSAL_STATUS_EMOJIS` module constants** — `Issue.get_status_emoji()` and `Proposal.get_status_emoji()` no longer rebuild emoji dicts on every call (closes dogcat-22jd)
- **Collapsed four `_is_*_shorthand()` functions into a single `_classify_shorthand()` lookup** — replaces `_is_priority_shorthand`/`_is_type_shorthand`/`_is_status_shorthand`/`_is_shorthand` with a dictionary-driven dispatch in `_helpers.py` (closes dogcat-5zcx)
- **Extracted `_complete_issues_by_status()` shared helper in `_completions.py`** — `complete_issue_ids` and `complete_closed_issue_ids` now both delegate to a single routine that takes a status predicate (closes dogcat-4du4)
- **Split migration branches out of `dict_to_issue()`** — extracted `_migrate_namespace`, `_migrate_issue_type`, and `_migrate_original_type` helpers so the main function is focused on construction (closes dogcat-iaah)

## 0.11.7 (2026-04-02)

### Added

- **Snooze/postpone issues** — temporarily hide issues from `list` and `ready` without changing their status. `dcat snooze <id> 7d` hides an issue for 7 days (supports `Nd`, `Nw`, `Nm`, or ISO dates), `dcat unsnooze <id>` reveals it early, and `dcat snoozed` lists all currently snoozed issues. Snoozed issues reappear automatically when the snooze expires. Also available via `dcat update --snooze-until`/`--unsnooze` and visible with `--include-snoozed` or `--all` flags (closes dogcat-28vf)
- **Epic completion notification on close** — when closing the last open child of a parent issue, `dcat close` now prints a message with a command to close the parent (closes dogcat-3o79)
- **`--no-parent` filter for listing commands** — filters to top-level issues (no parent set). Available on `list`, `ready`, `open`, `blocked`, `in-progress`, `in-review`, `deferred`, `manual`, `export`, and `pr` (closes dogcat-4i7x)

### Fixed

- **Fixed namespace filter showing all namespaces in shared database setups** — when using `.dogcatrc` without explicit `visible_namespaces`/`hidden_namespaces` config, `get_namespace_filter()` now defaults to the repo's primary namespace instead of showing issues from all namespaces (closes #20, thanks @fredrik-lindseth)
- **Fixed `get_storage()` bypassing `.dogcatrc` when local `.dogcats/` exists** — always resolve via `find_dogcats_dir()` for the default path so `.dogcatrc` takes priority over a local `.dogcats/` directory that may only contain `config.local.toml` (closes #18, thanks @fredrik-lindseth)
- **Fixed agnix linter warnings in CLAUDE.md and example-md template** — replaced ambiguous "Generally" phrasing with explicit priority order, reframed negative-only instructions ("Do NOT", "NEVER") as positive alternatives, moved critical sections out of the "lost in the middle" zone, and removed trailing commas in `.vscode/settings.json` (closes dogcat-15gy)
- **Fixed `storage.update()` not handling closed field transitions** — updating status away from `closed` now clears `closed_at`, `close_reason`, and `closed_by`; updating status to `closed` now sets `closed_at`. Previously, `dcat update --status in_review` on a closed issue left stale closed fields, causing issues to appear in both in-review lists and with closed annotations (closes dogcat-36bt)

## 0.11.6 (2026-03-10)

### Added

- **Searchable parent picker in TUI editor** — replaced the dropdown with a modal picker that supports type-ahead filtering by ID or title, displays issues with colored formatting matching `dcat list`, excludes closed issues (unless they have open children), and adds a `p` keybinding to open the picker in edit mode (closes dogcat-4zlt)

### Changed

- **Relaxed `.dogcatrc` boundary check** — removed the restriction that prevented `.dogcatrc` from pointing to a `.dogcats` directory outside the project root, since external paths are the whole point of the feature
- **Per-repo `config.local.toml` with shared databases** — when using `.dogcatrc` to share a database across repos, each repo can now have its own `.dogcats/config.local.toml` for settings like `namespace` and `visible_namespaces`, enabling multi-repo workflows where each repo has its own default namespace (closes dogcat-3xz1)

## 0.11.5 (2026-03-09)

### Changed

- **Tightened agent workflow rules** — added explicit guidance for parallel dcat calls, issue status discipline (mark `in_progress` only when starting work), and requiring issue creation before code changes

## 0.11.4 (2026-03-08)

### Changed

- **Shortened `dcat prime --opinionated` in_review verification rule** — condensed verbose multi-sentence instruction into a single concise line (closes dogcat-10dk)

## 0.11.3 (2026-03-08)

### Added

- **`dcat update` supports multiple issue IDs** — apply the same updates (status, priority, owner, labels, type, manual) to several issues at once, e.g. `dcat update id1 id2 id3 --status in_progress`. Single-issue options like `--title` and `--description` are guarded and rejected when multiple IDs are given (closes dogcat-4jll)

### Changed

- **`dcat prime --opinionated` now includes labels, batch-marking, and parallel calls rules** — adds guidance on setting `--labels` when creating issues, not batch-marking `in_progress`, and using parallel tool calls for multiple dcat commands (closes dogcat-2i10)
- **`dcat example-md` template slimmed down** — removed instructions already covered by `dcat prime --opinionated` to reduce token waste and avoid redundancy (closes dogcat-1vjo, dogcat-5iad)

## 0.11.2 (2026-03-08)

### Added

- **`dcat prime --opinionated` now includes context-rich issue writing rule** — instructs agents to write issues with enough detail (why, file paths, error messages, acceptance criteria) so a fresh agent can pick them up without prior context (closes dogcat-4t9s)
- **`dcat prime --opinionated` enforces 'create issue first' rule** — adds an explicit rule that agents must ask to create an issue before writing any code, with no exceptions for small tasks. Opinionated rules reordered to match workflow: create issue → write it well → verify before review (closes dogcat-2c1w)

## 0.11.1 (2026-03-07)

### Fixed

- **PreCompact hook now preserves `--opinionated` flag** — `dcat prime` saves its flags to `$XDG_CACHE_HOME/dogcat/` and the hook uses `dcat prime --replay` to restore them after compaction. `dcat doctor` detects old hooks without `--replay` and `--fix` upgrades them (closes dogcat-4469)

### Added

- **`dcat cache clean` and `dcat cache list` commands** — `dcat cache list` shows cached entries with their origin project and staleness status; `dcat cache clean` removes stale entries (or all with `--all`) (closes dogcat-gmsd)

## 0.11.0 (2026-03-07)

### Fixed

- **`dcat recently-closed` and `dcat recently-added` no longer claim `-n` for `--limit`** — removes the short flag conflict so `-n` is reserved for `--namespace` across the CLI (closes dogcat-sj9g)

### Added

- **`dcat doctor` detects missing Claude Code PreCompact hook** — when a `.claude/` directory exists, doctor checks whether a PreCompact hook is configured to run `dcat prime`. If missing, `--fix` installs it automatically into `settings.local.json` (preferred) or `settings.json`, merging with existing config. This preserves workflow context during context compaction (closes dogcat-323y)
- **`dcat git rebase` command** — auto-resolves JSONL merge conflicts in `.dogcats/` files using the semantic merge driver logic. Scans `issues.jsonl` and `inbox.jsonl` for conflict markers, resolves them, and stages the result with `git add` (closes dogcat-1mer)

### Changed

- **`dcat prime` skips output in non-dogcat repos** — when no `.dogcats/` directory is found, `dcat prime` prints a short message and exits cleanly instead of dumping the full workflow guide

## 0.10.3 (2026-02-28)

### Fixed

- **`dcat web propose` preserves selected namespace after submission** — the POST-Redirect-GET flow now passes the namespace in the query string, so the form stays on the chosen namespace instead of resetting to the default (closes dogcat-51h6)
- **`dcat init` now adds `.issues.lock` to `.gitignore`** — the lockfile is added alongside `config.local.toml` during initialization, matching what `dcat doctor` already checks for (closes dogcat-50d7)

### Changed

- **`dcat prime --opinionated` now requires verification before status changes** — replaced the old TodoWrite/TaskCreate rule with a project-agnostic verification gate: verify your work following the project's guidelines and cite actual output before setting `in_review` (closes dogcat-oq90)
- **`dcat ir` and `dcat ip` now list issues by status** — `dcat ir` lists all in-review issues and `dcat ip` lists all in-progress issues, instead of setting an issue's status. Both support standard filters (`--type`, `--priority`, `--label`, `--owner`, `--tree`, `--table`, `--json`) (closes dogcat-2a80, dogcat-3its)
- **`dcat inbox list` groups proposals by namespace** — when proposals span multiple namespaces, they are sorted and grouped under bold namespace headers with counts. Single-namespace output remains flat (closes dogcat-3t9d)
- **`dcat web propose` confirmation now shows proposal ID** — the success message displays the full proposal ID alongside the title (e.g. `testns-inbox-2hix My proposal`) (closes dogcat-4596)
- **`dcat web propose` header links to `/`** — the page title is now a clickable link back to the clean form (closes dogcat-18la)
- **`dcat recently-closed` and `dcat recently-added` support `--limit`** — cap the number of results shown (closes dogcat-5e84)

### Added

- **`dcat open` command** — shows only issues with `status=open`, with standard filters (`--type`, `--priority`, `--label`, `--owner`, `--tree`, `--table`, `--json`). Aliased as `dcat o` (closes dogcat-5jmp)
- **`dcat chart` command** — displays a horizontal bar chart of issue distribution by status, type, or priority. Supports `--by`, `--all`, `--json`, and standard filters (closes dogcat-2qb8)
- **`dcat chart` shows all categories by default and supports label grouping** — running `dcat chart` without `--by` now displays all four distributions (status, type, priority, label). Added `--by label` to group issues by label/tag, sorted by frequency (closes dogcat-4ry9)
- **Remote inbox support in `dcat inbox list`** — read and display proposals from a remote inbox alongside local proposals. Configure with `dcat config set inbox_remote <path>`. Remote proposals are namespace-filtered and marked with `(remote)` source in JSON output (closes dogcat-2obs)
- **`dcat inbox accept` command** — promote a remote inbox proposal to a local issue. Copies title, description, and supports `--priority` and `--labels` overrides. Automatically closes the remote proposal after acceptance (closes dogcat-17sg)
- **`dcat inbox reject` command** — reject a remote inbox proposal with an optional reason, closing it without creating a local issue (closes dogcat-4cqo)
- **`dcat inbox show` remote fallback** — when a proposal ID is not found locally, `dcat inbox show` now falls back to the remote inbox (closes dogcat-40r7)
- **Tab completions for remote proposal IDs** — proposal ID completers now include remote proposals with `(remote)` suffix, with deduplication against local proposals (closes dogcat-d1zp)
- **Remote inbox section in `dcat prime` output** — `dcat prime` now includes remote inbox commands in its guide when a remote inbox is configured (closes dogcat-3l35)
- **`config.local.toml` for per-machine settings** — machine-specific configuration (e.g. `inbox_remote`) is stored in `.dogcats/config.local.toml`, which is automatically added to `.gitignore`. Local-only keys are auto-redirected to this file (closes dogcat-4fli)
- **Gitignore warning for `config.local.toml`** — `dcat doctor` now warns when `config.local.toml` exists but is not gitignored (closes dogcat-6291)
- **`pinned_namespaces` config option** — list namespaces in `pinned_namespaces` to keep them visible even when they have no issues or proposals. Supported in `dcat namespaces`, `dcat web propose`, tab completions, and `dcat rename-namespace` (closes dogcat-34c0)

### Development

- **Tests for remote inbox triage workflow** — comprehensive test coverage for accept, reject, remote fallback, namespace filtering, and tab completions (closes dogcat-2red)

## 0.10.2 (2026-02-21)

### Fixed

- **`dcat inbox close` and `dcat inbox delete` now accept multiple IDs** — both commands accept variadic proposal IDs for consistency with `dcat close` and `dcat delete`. Partial failures are reported individually and the command exits 1 if any failed (closes dogcat-52tr)
- **TUI compatibility with Textual 8.0.0** — replace `Select.BLANK` with `Select.NULL` and pin `textual>=8.0.0` to fix `InvalidSelectValueError` crash on TUI mount (closes dogcat-16i1)
- **TUI issue picker sorting** — `dcat edit` picker now sorts issues by priority then ID, matching `dcat list` and the dashboard (closes dogcat-45ab)
- **Namespace resolution from subdirectories** — running `dcat` from a subfolder no longer creates issues under the wrong namespace. `get_issue_prefix` now walks up the directory tree to find the parent `.dogcats/` directory, matching the behavior of `get_storage` (closes dogcat-ahdx)
- **`--include-inbox` now respects namespace filtering** — `dcat list`, `ready`, and `export` with `--include-inbox` no longer show proposals from all namespaces; they default to the primary namespace and require `-A`/`--all-namespaces` to show foreign proposals (closes dogcat-67cg)

### Added

- **`--label` alias for `--labels`** — `create` and `update` now accept `--label` as a synonym for `--labels` (closes dogcat-531p)
- **`dcat t` alias** — hidden shorthand for `dcat tui` (closes dogcat-528h)
- **`dcat graph` command** — visualize the dependency graph as an ASCII DAG with Unicode box-drawing. Parent-child edges render in cyan (`├── `), blocking edges in red (`├─▶ `). Supports `dcat graph <id>` for subgraph view, `--agent-only` filtering, `--json` output, and all standard filters (closes dogcat-2o4w)

### Development

- **Add v0.10.1 fixtures and inbox regression tests** — extend `generate_fixture.py` to capture `inbox.jsonl` alongside `issues.jsonl` for tags that include the inbox system. Add `test_inbox_regression.py` with full proposal field coverage (statuses, timestamps, closed/tombstone fields, get-by-ID). Generate v0.10.1 fixture files (closes dogcat-2sis)

## 0.10.1 (2026-02-19)

### Fixed

- **`dcat web propose` now fails if db is not initialized** — running the command without an initialized `.dogcats` directory now shows a clear error instead of launching the server (closes dogcat-3noz)
- **`dcat web propose` no longer allows namespace creation by default** — the "New..." namespace option is now hidden unless explicitly enabled via `--allow-creating-namespaces` or `allow_creating_namespaces` config (closes dogcat-284g)

## 0.10.0 (2026-02-19)

### Added

- **`dcat stale` command** — list issues with no recent activity. Default threshold is 7 days; supports `--days N`, `--hours N`, and positional shorthand syntax (`7d`, `3h`, `1d12h`). Includes age display, standard filters, and all output modes (closes dogcat-57oq)
- **`dcat rename-namespace` command** — rename all issues in a namespace at once, cascading updates to all references (parent, duplicate_of, dependencies, links), inbox proposals, and config (primary namespace, visible/hidden namespace lists) (closes dogcat-2ssc)
- **`--include-inbox` flag on `dcat list` and `dcat ready`** — show pending inbox proposals alongside issues (closes dogcat-3y3d)
- **`--inbox` flag on `dcat prime`** — inbox section is now hidden by default unless `--inbox` is passed (closes dogcat-4iog)
- **`--allow-creating-namespaces` / `--disable-creating-namespaces` on `dcat web propose`** — control whether the web form allows creating new namespaces, with CLI flag > config > default (False) precedence. Adds `allow_creating_namespaces` config key and "New..." option in the namespace dropdown (closes dogcat-23z4)
- **Inbox proposals in `dcat export`** — export now includes inbox proposals in both JSON (`"proposals"` key) and JSONL formats. Use `--no-inbox` to exclude them (closes dogcat-109b)
- **Inbox events in `dcat history`** — proposal lifecycle events (create, close, delete) are now recorded and shown in history alongside issue events. Supports `--issue` filtering by proposal ID and `--no-inbox` to exclude inbox events (closes dogcat-o6ym)
- **Item counts in status listing headers** — all listing commands (`dcat list`, `dcat ready`, `dcat blocked`, `dcat deferred`, `dcat in-progress`, `dcat in-review`, `dcat manual`, `dcat recently-added`, `dcat recently-closed`, `dcat pr`) now show item counts in their headers, e.g. "Ready (3):" (closes dogcat-63au)
- **`--body` alias for `--description`** — `dcat create` and `dcat update` now accept `--body` as a hidden alias for `--description`/`-d` (closes dogcat-4jpv)
- **Hidden `--full` flag on `dcat show`** — preparatory no-op hook for future functionality (closes dogcat-ns83)
- **Inbox system** — cross-repo lightweight proposals via `dcat propose` and `dcat inbox` commands. Send proposals to other repos (`dcat propose "Title" -d "Details" --to ~/other-repo`), manage incoming proposals with `dcat inbox list/show/close/delete`. Includes archive support for closed proposals, merge driver support for `inbox.jsonl`, tab completions, demo data, and inbox counts in `dcat status`
- **Web proposal form** — `dcat web propose` launches a FastAPI server with an HTML form for submitting proposals via browser. Includes CSRF protection, input validation, security headers, namespace selection, and input size limits
- **FastAPI, uvicorn, jinja2 as optional `[web]` dependencies** — install with `pip install dogcat[web]`
- **Status symbols in `dcat diff` output** — diff now shows the current status symbol (●, ◐, ?, etc.) alongside the event type symbol, giving at-a-glance status context when reviewing changes (closes dogcat-5rdf)

### Changed

- **Trimmed `dcat prime` output** — reduced token count from ~1249 to ~1052 (~200 tokens saved) by deduplicating Quick Start and Essential Commands sections, shortening descriptions, and condensing prose without losing essential information (closes dogcat-oyo9)

### Fixed

- **`dcat namespaces` now includes inbox proposals** — namespaces from inbox proposals are visible immediately, with separate issue/inbox counts shown (e.g. `proj (3 issues, 1 inbox)`) (closes dogcat-51p3)
- **`dcat info` now shows inbox statuses** — the info command displays available inbox statuses in both text and JSON output (closes dogcat-57w5)
- **Add `--by` flag to `dcat inbox delete`** — all inbox mutation commands now support `--by` for attribution, matching `inbox close` behavior. Also adds `deleted_at`/`deleted_by` fields to the Proposal model (closes dogcat-4xjq)
- **`dcat prune` now handles inbox tombstones** — prune removes tombstoned proposals from `inbox.jsonl` in addition to tombstoned issues from `issues.jsonl` (closes dogcat-5n8k)
- **Fix redundant 'changed -> changed' in diff output for long-form fields** — when description, notes, acceptance, or design fields are edited, diff now shows `(edited)`, `(added)`, or `(removed)` instead of the confusing `changed -> changed` (closes dogcat-2595)
- **`dcat diff` now shows inbox.jsonl changes** — proposals (new, updated, closed, deleted) are included alongside issue changes in diff output, including `--staged`, `--unstaged`, and `--json` modes (closes dogcat-15zr)
- **`dcat doctor` now validates inbox.jsonl** — when inbox.jsonl exists, doctor checks JSON validity and validates proposal records for required fields, valid statuses, and well-formed timestamps (closes dogcat-1fek)
- **Fix web propose refresh showing POST-only error** — moved POST endpoint to `/` and applied Post/Redirect/Get pattern so refreshing after submission no longer fails (closes dogcat-4gb7)
- **Fix blocked status overriding advanced statuses in display** — issues with status `in_review`, `deferred`, or `closed` now display their own status symbol instead of being unconditionally shown as blocked when they have open dependencies (closes dogcat-5wd2)
- **Fix `dcat stream` not showing events for inbox proposals** — stream now includes proposal events alongside issue events with standardized event naming (closes dogcat-5ond)
- **Fix inbox list tombstone filtering** — deleted proposals no longer appear in `dcat inbox list` (closes dogcat-66pi)
- **Fix silent namespace filtering failures in inbox CLI** — namespace filter errors are now surfaced instead of silently returning empty results (closes dogcat-19bk)
- **Fix inconsistent malformed line handling in InboxStorage** — malformed JSONL lines are now handled consistently with the issue storage (closes dogcat-3952)

### Changed

- **Add `updated_at` field to Proposal model** — proposals now track their last modification time (closes dogcat-3wy6)
- **Include proposal namespaces in namespace completer** — tab completion for `--namespace` now includes namespaces from inbox proposals (closes dogcat-4rmr)
- **Include closed proposals in tab completions** — proposal ID completers now suggest closed proposals where appropriate (closes dogcat-4w8x)
- **Add `validate_proposal()` function** — proposals are validated on creation and update, matching issue validation behavior (closes dogcat-1iku)
- **Add `generate_proposal_id()` to ID generation** — proposal IDs use their own generator instead of reusing the issue ID function (closes dogcat-ehl7)
- **Replace type assertions with proper validation in CLI** — inbox CLI commands now use explicit validation instead of assert statements (closes dogcat-5jhs)
- **Reduce coupling of archive to InboxStorage.path** — archive module uses a cleaner interface for inbox storage access (closes dogcat-ue1e)
- **Extract shared `get_namespaces()` utility** — namespace collection logic consolidated into `storage.get_namespaces()`, used by CLI, web propose, and tab completions (closes dogcat-21lr)

### Security

- **CSRF protection on web proposal form** — form submissions are protected against cross-site request forgery (closes dogcat-3ku2)
- **Security headers on web server** — responses include standard security headers (X-Content-Type-Options, X-Frame-Options, etc.) (closes dogcat-3xls)
- **Namespace validation on web proposal submission** — the web endpoint validates namespace values before creating proposals (closes dogcat-496q)
- **Replace broad `except Exception` in web routes** — web error handling now catches specific exceptions instead of blanket catches (closes dogcat-5qrr)

### Development

- **Add eslint, stylelint, and djlint for web linting** — set up eslint 9 (flat config), stylelint 16 (standard config), and djlint (jinja profile) with pnpm. Extracted inline CSS from `propose.html` to `static/css/propose.css`, mounted static files in FastAPI, and updated CSP to `style-src 'self'`. `just lint` and `just fmt` now run all web linters in parallel (closes dogcat-3lbi)
- **Document proposal merge conflict resolution rules** — README documents how inbox.jsonl conflicts are resolved by the merge driver (closes dogcat-2ah1)
- **Tests for inbox system, CLI commands, web server, and proposal integration** — comprehensive test coverage across `test_inbox.py`, `test_cmd_inbox.py`, `test_cmd_propose.py`, `test_web_propose.py`, and additions to `test_archive.py`, `test_stream.py`, `test_merge_driver.py`, `test_formatting.py`, and `test_demo.py`

## 0.9.3 (2026-02-17)

### Added

- **PyPI publishing** — dogcat is now published to PyPI on each release via trusted OIDC publishing. Users can install with `pipx install dogcat`, `uv tool install dogcat`, or `pip install dogcat` (closes dogcat-d0m9)
- **`dogcat` CLI alias** — the package now registers both `dcat` and `dogcat` as entry points, so `uvx dogcat` works out of the box

## 0.9.2 (2026-02-17)

### Added

- **`dcat example-md` command** — outputs a ready-to-use CLAUDE.md template with recommended dcat workflow instructions for AI agents (closes dogcat-45nl)

### Fixed

- **Fix missing `--namespace` option on `dcat create`** — `dcat create` now supports `--namespace` to create issues in a specific namespace, matching the existing `dcat update --namespace` behavior (closes dogcat-1b55)
- **Fix misleading `dcat doctor` PATH check message** — when dcat is available as a shell function/alias but not as a binary in PATH, the check now shows an informational note (○) instead of a confusing failure (✗) that read "dcat command is available in PATH" (closes dogcat-2fsd)

## 0.9.1 (2026-02-16)

### Added

- **Tab completion for all commands** — added missing autocompletion to `comment`, `label`, `search`, `dep`, and `link` commands. Completions now respect namespace filtering (matching `dcat list` behavior) and support `-A`/`--namespace` flags. Short ID matching lets you type e.g. `dcat show 1g<tab>` without the namespace prefix.
- **Nice-to-have tab completions** — `--older-than` suggests common durations (7d–90d), `--closed-after`/`--closed-before` suggest recent dates, and `config set VALUE` offers context-dependent suggestions (true/false for bools, namespaces for namespace lists)

### Fixed

- **Fix `dcat doctor` failing when run from a subdirectory** — doctor now uses `find_dogcats_dir()` to walk up the directory tree, matching the behavior of all other commands (closes dogcat-5v86)
- **Fix tab completion gaps across CLI** — added missing completers for `--namespace`, `--owner`, `--format`, config keys, dep/link types, and export formats. Fixed `reopen` suggesting open issues instead of closed ones. (closes dogcat-56nl)
- **Add `dcat comment` docs to `dcat prime` and fix `dcat guide`** — added comment commands (add, list, delete) to the Essential Commands section of `dcat prime`, and fixed incorrect syntax in `dcat guide` which showed a positional argument instead of the `add -t` action form

### Changed

- **Show comment timestamps in `dcat show` and TUI** — comments now display their creation timestamp alongside the author, with blank-line separation between comments for readability
- **Show comments in TUI edit mode** — comments are now visible (read-only) when editing an issue, not just in view mode

### Development

- **Convert loop-based tests to `@pytest.mark.parametrize`** — replaced manual `for` loops in `test_cmd_create`, `test_idgen`, and `test_models` with parametrized tests so each case appears individually in test reports
- **Strengthen tests with trivial assertions** — added meaningful assertions to 6 tests that previously had no assertions or only checked truthiness (in `test_storage`, `test_migrate`, `test_stream`, `test_config`)
- **Add `tabcomp.py` dev utility** — simulates tab completion for any `dcat` command line, showing what completions would appear. Useful for debugging shell completion issues without a live shell.
- **Speed up test suite ~22%** — worksteal scheduler, `COVERAGE_CORE=sysmon`, plugin pruning, optimized git fixtures, removed unnecessary `time.sleep()` calls
- **Add `just test-changed`** — incremental test runs via pytest-testmon, only re-runs tests affected by code changes
- **Simplify test commands** — merged TUI tests into `just test`, removed tox and `just matrix`/`test-py`
- **`just release-prep` now runs `test-all`** as a prerequisite

## 0.9.0 (2026-02-15)

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
- **Orphaned events not cleaned up by prune or namespace changes** — `prune_tombstones()` now removes event records for pruned issues (and any pre-existing orphans), and `change_namespace()` rewrites `issue_id` in event records to match the new namespace.

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
