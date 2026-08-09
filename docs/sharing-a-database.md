# Sharing a dogcat database between multiple repos

This guide covers the two shared-store setups: machine-wide via global config, or per-repo via `.dogcatrc`. The two can coexist. The third setup, a repo's own local `.dogcats/`, is the default and needs no configuration.

## Quick start (recommended): global config

If you want every new repo on the machine to use the same shared store automatically, set the user-global config once:

```bash
dcat config set --global default_storage /path/to/shared/.dogcats
```

After that, every repo without its own `.dogcats/` or `.dogcatrc` resolves to the shared store. Namespace is derived from the repo directory name, e.g. `~/dev/læring/` → `laering` (see [Config precedence](#config-precedence) for the exact rule). No per-repo `.dogcatrc` or `config.local.toml` needed.

The config lives at `$XDG_CONFIG_HOME/dogcat/config.toml` (or `~/.config/dogcat/config.toml`).

**Agents:** `--global` writes to the user's home directory, not the repo, and changes storage resolution for every repo on the machine that has no `.dogcats/` or `.dogcatrc`. Show the user the current value with `dcat config get --global default_storage` and get confirmation before writing it. The same applies to `dcat init` and `dcat init --use-existing-folder` below: both create files in whatever directory you are standing in, so ask the user to run them rather than running them to try something out.

The `.dogcatrc` / `config.local.toml` setup below is still supported. Use it when you want a specific repo to opt into a different namespace, or to share between just a few repos rather than machine-wide.

## Example layout (per-repo setup)

```
~/dev/issues/              # shared store lives here
  .dogcats/
    issues.jsonl           # single source of truth
    config.toml            # shared config (namespace = "issues")

~/dev/backend-app/
  .dogcatrc                # points to ~/dev/issues/.dogcats
  .dogcats/
    config.local.toml      # namespace = "backend"

~/dev/frontend-app/
  .dogcatrc                # points to ~/dev/issues/.dogcats
  .dogcats/
    config.local.toml      # namespace = "frontend"

~/dev/infrastructure/
  .dogcatrc                # points to ~/dev/issues/.dogcats
  .dogcats/
    config.local.toml      # namespace = "infra"
```

## Per-repo setup (manual)

### 1. Initialize the shared store

```bash
cd ~/dev/issues
dcat init --namespace issues
```

### 2. Link each repo

In each app repo, link to the shared store:

```bash
cd ~/dev/backend-app
dcat init --use-existing-folder ~/dev/issues/.dogcats
```

This creates a `.dogcatrc` file containing the path to the shared `.dogcats` directory. Repeat for each repo.

### 3. Set per-repo namespace

Each repo gets its own namespace so issues are prefixed accordingly (e.g. `backend-a3f2`, `frontend-8kx1`):

```bash
cd ~/dev/backend-app
dcat config set namespace backend --local

cd ~/dev/frontend-app
dcat config set namespace frontend --local

cd ~/dev/infrastructure
dcat config set namespace infra --local
```

The `--local` flag saves to a repo-local `config.local.toml` (inside `.dogcats/` next to your `.dogcatrc`), so each repo keeps its own defaults without affecting the others.

### 4. Filter visibility per repo (optional)

So each repo only shows its own issues by default:

```bash
cd ~/dev/backend-app
dcat config set visible_namespaces backend --local
```

For multiple namespaces, separate them with commas:

```bash
dcat config set visible_namespaces backend,shared --local
```

You can always see all issues with `--all-namespaces` or a specific namespace with `--namespace frontend`.

### 5. Add `.gitignore` entries

Add to each repo's `.gitignore`:

```
.dogcats/config.local.toml
```

Commit `.dogcatrc` so every clone resolves to the same shared store, and write a path relative to the repo — `parse_dogcatrc` resolves a relative path against the `.dogcatrc` directory, while the absolute `~/dev/...` paths shown above only work on the machine that created them. Keep `config.local.toml` out of git: it holds per-checkout namespace and visibility choices, and committing it forces one developer's view onto everyone else.

## Migrating existing repos

No command merges an existing per-repo store into a shared one. Leave existing repos on their own `.dogcats/` store: a local store wins over the global fallback, so they keep working unchanged while the shared store grows from new repos. To move issues across anyway, read the old store with `dcat export` and re-create each issue in the shared store with `dcat create --namespace <ns>`. Every write goes through the CLI (see AGENTS.md, "Store safety") — a hand-concatenated `issues.jsonl` produces IDs and event ordering the merge driver cannot reconcile.

## Cross-repo issue creation

From any repo, create issues in another namespace using `--namespace`:

```bash
# Working in backend, create an issue for frontend
cd ~/dev/backend-app
dcat create --namespace frontend "Update API response parsing after endpoint change" \
  --type task --priority 2 --labels api

# Check what's pending for frontend
dcat list --namespace frontend
```

The issue gets a `frontend-xxxx` ID and shows up in the frontend repo's default view.

## Config precedence

dogcat resolves the storage directory in this order (first match wins):

1. **Walk up from the cwd, checking `.dogcatrc` before `.dogcats/` at each level.** The cwd is just the first level of that walk, not a separate step: a `.dogcatrc` in the current directory beats a `.dogcats/` in the same directory. That ordering is deliberate — a repo wired to a shared store keeps a local `.dogcats/` holding only `config.local.toml`, so preferring the directory would silently strand it on an empty store. The walk is what makes `dcat` work from a subdirectory of a repo. It stops at `get_rc_walkup_boundary` (git toplevel, else `$HOME`) rather than at the filesystem root, and it refuses a `.dogcatrc` whose target is owned by another user. Both of those guards have an environment escape hatch — see the table below.
2. **The main worktree's `.dogcats/`**, when the cwd is inside a linked git worktree. `git rev-parse --git-common-dir` resolves the main worktree root and `.dogcats/` there is used if present.
3. **Global `default_storage`** from `$XDG_CONFIG_HOME/dogcat/config.toml` (default `~/.config/dogcat/config.toml`), tried only after both of the above come up empty.

Within the chosen storage directory, config is merged in this order (later wins):

1. **Shared `config.toml`** in the shared `.dogcats/` directory
2. **Shared `config.local.toml`** in the shared `.dogcats/` directory
3. **Repo-local `config.local.toml`** in `.dogcats/` next to the repo's `.dogcatrc` (when using `.dogcatrc` setup)

Repo-local settings (namespace, visible_namespaces) always take precedence.

When storage resolves via the global fallback (no local `.dogcats/`, no `.dogcatrc`), the namespace is the slug of the git repo-root directory name when the cwd is inside a repo (so `myrepo/src/` yields `myrepo`, never `src`), or the slug of the cwd folder name when outside any repo — falling back to the shared store's `config.toml` namespace when that name isn't sluggable. Repos that reach the same store through a `.dogcatrc` — or the store's own home directory — are *not* in fallback mode and use the normal config chain above. dcat prints a one-time notice on stderr whenever the global fallback is used, so writes to the shared store are never silent.

Only two keys are read from the global config file: `default_storage` and `visible_namespaces`. `dcat config set --global` rejects anything else.

## Environment overrides

Four variables change store behaviour with nothing in `config.toml` to show for it. The first two are escape hatches: they disable a security check, so set them per-command rather than in a shell profile.

| Env var | Default | Effect |
| --- | --- | --- |
| `DCAT_UNSAFE_CROSS_USER=1` | unset | Accept a `.dogcatrc` whose target is owned by another user. Intended for shared CI, where the ownership check has no signal. |
| `DCAT_RC_WALKUP_UNRESTRICTED=1` | unset | Drop the `get_rc_walkup_boundary` limit and walk to the filesystem root, so any ancestor `.dogcatrc` — including a planted `/tmp/.dogcatrc` — can re-root the store. |
| `DCAT_LOCK_TIMEOUT_SECS` | `30` | How long a write waits for the advisory lock. Raise it for a store on slow shared storage. |
| `DCAT_GIT_TIMEOUT_SECS` | `10` | Per-`git`-subprocess timeout. Raise it when a stalled NFS `$HOME` or credential helper makes git calls hang. |
