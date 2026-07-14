# Remove the out-of-tree `.dogcatrc` warning (dogcat-4w2b)

## Problem

`warn_if_rc_target_foreign` (`src/dogcat/config.py`) prints a stderr warning on
every command whenever a `.dogcatrc` target resolves outside the rc file's own
directory. But `docs/sharing-a-database.md` documents exactly that setup as a
first-class, recommended way to share a store: `dcat init --use-existing-folder`
creates a committed `.dogcatrc` pointing at a sibling shared `.dogcats/`. So the
documented happy path warns on every invocation.

Two consequences:

1. Perpetual noise for every repo using the documented `.dogcatrc` sharing.
2. The warning goes to stderr, so `dcat --json ... 2>&1 | parse` (a common agent
   pattern) breaks with a JSON parse error even though the command succeeded.

The warning was meant to catch a planted `.dogcatrc` silently re-rooting reads
and writes. But that threat is already covered by two other mechanisms that stay:

- **Walk-up boundary** (`get_rc_walkup_boundary`) bounds the ancestor walk to the
  git toplevel / `$HOME`, so a planted `/tmp/.dogcatrc` or `$HOME/.dogcatrc` is
  never picked up from deep in a repo.
- **Cross-user ownership refusal**: when the rc file and its target are owned by
  different uids, the rc is refused with an error (override:
  `DCAT_UNSAFE_CROSS_USER=1`). This is the real security boundary.

The residual case the warning uniquely covered is a same-user `.dogcatrc`
pointing to another same-user directory within the boundary, which is the
documented happy path. A wrong path still errors separately (`walkup_find_store`
raises on a nonexistent target dir).

## Decision

Remove the out-of-tree advisory warning. Keep the walk-up boundary and the
cross-user refusal unchanged.

Out of scope: the `-m` comment-flag trap (tracked in dogcat-3qt2, separate PR),
and any precedence change for an explicit `--dogcats-dir` (not needed under the
documented model).

## Changes

- `src/dogcat/config.py`
  - `warn_if_rc_target_foreign`: drop the out-of-tree warning block (the
    `is_within` check and the stderr `print`). Keep the `DCAT_UNSAFE_CROSS_USER`
    short-circuit and the uid-mismatch refusal.
  - Rename the function to `refuse_if_rc_target_cross_user` — after the change it
    only refuses on cross-user ownership, never warns; a `warn_*` name that never
    warns is misleading. Update the one call site in `cli/_helpers.py`.
  - Remove `is_within` — it becomes dead once the warning block is gone (no other
    caller). Confirm with grep before deleting.
  - Update the function docstring to describe only the refusal.
- `DCAT_RC_WALKUP_UNRESTRICTED` stays: it still disables the walk-up boundary in
  `get_rc_walkup_boundary`. Only its mention in the removed warning message goes.
- `tests/test_helpers.py`
  - Replace `test_warn_if_rc_target_outside_rc_dir` (asserts the warning fires)
    with a test asserting a same-user out-of-tree target produces no stderr
    output.
  - Keep the three cross-user tests unchanged except for the function rename.
- `CHANGELOG.md`: one `Fixed` entry under `[Unreleased]`.

## Testing

TDD order:

1. Rewrite the out-of-tree test to assert no warning is emitted for a same-user
   external target. It fails against current code (warning still prints).
2. Remove the warning block. Test goes green.
3. Confirm the three cross-user tests still pass (behavior unchanged).
4. `just test-changed`, then `just lint-all` before pushing.

Manual check: in a repo whose `.dogcatrc` points at an out-of-tree same-user
store, `dcat --json list 2>&1 | python -c "import sys,json; json.load(sys.stdin)"`
parses cleanly (no warning line on the merged stream).
