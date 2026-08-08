# Agent Instructions

Invoke dcat as `uv run dcat …` (or `./dcat.py …`). There is no bare `dcat` on PATH in this
checkout, so a bare invocation fails. Both forms run the working-tree source, which means this
repo dogfoods itself: every `dcat` command executes your uncommitted code against `.dogcats/`,
the project's real issue data. After editing anything under `src/dogcat/` that touches storage,
models, ids, locking, or the CLI, run the tests instead of a mutating `dcat` command. Read-only
commands (`list`, `show`, `prime`) stay safe.

## Store safety

`.dogcats/` is tracked in git — `issues.jsonl`, `inbox.jsonl`, `config.toml` and `archive/*.jsonl`
are all committed, and only `config.local.toml` and the lock file are ignored. Uncommitted issue
records exist in exactly one place, so a git command that discards working-tree changes destroys
them. Run `git status .dogcats/` before `git reset --hard`, `git checkout -- .`, `git clean`, or
`git stash`, and confirm with the user if it reports changes.

NEVER force-push `main`. The event log only grows, so a rewritten `main` drops records
collaborators have already merged and nothing recovers them once their clones re-sync.

Make every issue and proposal mutation through a `dcat` command. Editing the JSONL by any other
route corrupts the audit log, which the merge driver and compaction both read in order. The routes
that count as editing it directly: a Python or `jq` one-liner that appends a line, `sed -i`, opening
the file in an editor, hand-resolving a merge conflict inside it, restoring it with
`git checkout`/`git restore`/`git stash`, and pasting records out of `.dogcats/archive/` back into
`issues.jsonl`. For conflict markers run `uv run dcat git rebase`; for a damaged file run
`uv run dcat repair-jsonl --dry-run` first, because the next append silently drops unparseable lines.
Test fixtures under `tests/` may serialize records straight to a temp store — that precedent does
not extend to this repo's own `.dogcats/`.

Red flags — if you catch yourself thinking any of these, stop:

- "it's just JSONL, one appended line is harmless"
- "faster than finding the right dcat command"
- "`git checkout .dogcats/issues.jsonl` just undoes my mistake"
- "the conflict is trivial, I can see which side is right"

Four commands rewrite the store rather than appending to it. Run each only when the user asks for
it by name, and preview with `--dry-run` first: `dcat prune` (erases every tombstoned record and
prompts for nothing), `dcat repair-jsonl`, `dcat backfill-history`, `dcat archive`.

Five commands block until a human quits them and will hang the session: `dcat tui`, `dcat new`,
`dcat edit`, `dcat web propose`, `dcat stream`. Verify that behavior with a test instead
(see `docs/testing.md`), or ask the user to run the command when a visual check is needed.

## Issue workflow

Run `uv run dcat prime --opinionated` at the start of each session and again after any compaction
or clear — it outputs the workflow guide, and re-running plain `dcat prime` drops the strict rules.
Then run `uv run dcat list --agent-only` for the backlog. Work on bugs before features, high
priority first.

Where `dcat prime` and this file disagree, this file wins. One live divergence, and it is
deliberate: `dcat prime --opinionated` and `dcat example-md` both prescribe an `in_review` step
before closing, because that is the right default for a project whose review happens outside a pull
request. It is not the rule here. A pull request is the review surface in this repo, so take a
PR-resolved issue straight to `closed` and leave `in_review` alone. Changing the shipped default to
match this repo would be the wrong fix — it would push every other project into our workflow.

Set an issue to `in_progress` when you begin editing files for it, and move it out as soon as you
stop. Mark more than one issue `in_progress` only when a single change closes all of them;
otherwise finish the current issue first. `dcat list` is how the user sees what is live, so a stale
`in_progress` misreports the session. When two issues carry the same priority, ask the user which
to take first.

Before writing code for any new bug, feature, or change — whether the user raised it or you found
it — ask whether to create an issue first. No exceptions for small tasks; the rule exists for
traceability. Set labels with `--labels`, reusing a label already in the store.

Wait for explicit user approval before closing or deleting any issue. The gate covers every route
to a terminal status, not the `dcat close` command alone: `dcat update --status closed`, a status
change from the TUI, and `dcat archive` over unapproved issues all need the same confirmation, and
a confirmation covers the IDs named in it and nothing else. A merged PR approves code, not a
tracker write. `dcat close` is reversible with `dcat reopen`; `dcat delete` writes an absorbing
tombstone that no command undoes, so name the issue and say it cannot be undone before running it.

When work is complete:

1. Ask the user to test
2. Ask if we can close it: "Can I close issue [id] '[title]'?"
3. Run `uv run dcat close` after the user confirms
4. Ask: "Should I add this to CHANGELOG.md?" — see Changelog below

When research or discussion produces findings relevant to an existing issue, ask these as
**separate questions in order**:

1. First ask: "Should I update issue [id] with these findings?"
2. Only after that, separately ask: "Should I start working on the implementation?"

Always ask these as separate questions — the user may want to update the issue without starting work.

Issue each `dcat` command as its own shell tool call, in parallel. Separate calls keep each
command's exit code and output attributable, which a single `&&` chain with `echo` separators loses
when a command in the middle fails.

## Data files

`.dogcats/issues.jsonl` holds `issue`, `dependency`, `link` and `event` records, loaded by
`JSONLStorage` in `src/dogcat/storage.py`. `.dogcats/inbox.jsonl` holds `proposal` records
submitted from the web UI or `dcat propose --to`, managed by `src/dogcat/inbox.py`; a proposal
moves `open` → `closed` → `tombstone` and never back. Triage them with `dcat inbox`, whose
reference `dcat prime --opinionated --inbox` prints.

The store is not permanently append-only. Once appended lines exceed `COMPACTION_RATIO`, `_append`
rewrites the whole file with current state only, and that rewrite runs on a default branch alone
(`storage.py:475`). A large all-lines-changed diff on `issues.jsonl` after merging to `main` is a
compaction, not corruption — leave it. Writes take an advisory lock, so concurrent `dcat` processes
are safe and concurrent hand-edits are not.

## Version control

Work commits directly to `main`. Commit only when the user asks, and push only when the user asks —
a push to `main` runs CI, and a push of a `release/v*` branch starts the publish pipeline.
Stage `.dogcats/` alongside the code change it belongs to.

The JSONL merge driver is live in this checkout: `.gitattributes` maps `.dogcats/*.jsonl` to
`merge=dcat-jsonl`, and local git config binds that to `dcat git merge-driver`. It resolves `dcat`
from PATH rather than from `src/`, so editing `merge_driver.py` changes nothing about the next merge
unless dcat is installed from this source. When `dcat` is missing from PATH the driver exits
non-zero, git marks the path conflicted, and the file holds ours-side content only — staging it
discards the other branch's issues. Run `dcat git check` before any merge, rebase, or pull that
touches `.dogcats/`, and `dcat doctor --post-merge` after.

## Development

Run `just test-changed` during development for fast feedback and `just test-all` before committing.
Run `just lint` to check, `just fmt` to fix formatting, and `just lint-all` (adds pyright) before
committing — CI runs the same recipe, so a lint failure there reproduces locally.

`just lint` covers Python, Jinja templates, JavaScript and CSS, and shells out to pnpm for three of
those. Run `pnpm install --frozen-lockfile` once per checkout; without it `just lint` fails on the
pnpm branches even when you touched no JavaScript, and `just lint-all` never reaches pyright.
Use uv for Python dependencies and pnpm for the node ones — pip and npm are not used here.

Write tests for new features and for changed functionality. `docs/testing.md` covers the isolation
fixtures, how to run a single test, where local commands diverge from CI, and the TUI test pattern.

Import shared display values from `src/dogcat/constants.py`. It is not the only registry, and the
split matters — see `docs/cli-conventions.md` before adding a status, config key, or CLI option.

## Where the rest lives

Read the matching file before working in that area, and update it in the same change:

- `docs/cli-conventions.md` — adding a command, tab completions, where constants actually live
- `docs/testing.md` — test isolation, single tests, CI parity, TUI and web tests
- `docs/releasing.md` — `just release-prep`, PyPI, the Homebrew formula
- `docs/web-ui.md` — CSP, static assets, deferred imports, the node toolchain
- `docs/merge-coverage.md` — the claim-to-test matrix for `src/dogcat/merge_driver.py`
- `docs/sharing-a-database.md` — storage resolution and namespaces

When a change makes a rule here wrong — a renamed `just` target, a moved path, a changed CLI flag —
fix this file in the same commit.

Three files carry workflow doctrine for *users'* agents: the template in
`src/dogcat/cli/_cmd_example_md.py`, the guide in `src/dogcat/cli/_cmd_docs.py`, and the copy in
`README.md`. Those are product surface, not rules for you. When you change one, check the other two.

## Changelog

Add entries under `[Unreleased]` at the top of `CHANGELOG.md`, never under a released version
heading — release automation reads that section to decide what ships next. Section tags:
**Added**, **Changed**, **Deprecated**, **Removed**, **Fixed**, **Security**, and **Development**
(tooling, CI, dev workflow).
