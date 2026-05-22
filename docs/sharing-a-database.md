# Sharing a dogcat database between multiple repos

This guide covers two ways to share one dogcat database across several repos: a machine-wide setup via global config, or a per-repo setup via `.dogcatrc`. The two can coexist.

## Quick start (recommended): global config

If you want every new repo on the machine to use the same shared store automatically, set the user-global config once:

```bash
dcat config set --global default_storage /path/to/shared/.dogcats
```

After that, every repo without its own `.dogcats/` or `.dogcatrc` resolves to the shared store. Namespace is derived from the repo's directory name (e.g. `~/dev/læring/` → `laering`). No per-repo `.dogcatrc` or `config.local.toml` needed.

The config lives at `$XDG_CONFIG_HOME/dogcat/config.toml` (or `~/.config/dogcat/config.toml`).

The `.dogcatrc` / `config.local.toml` setup below is still supported. Use it when you want a specific repo to opt into a different namespace, or to share between just a few repos rather than machine-wide.

## Example layout (per-repo setup)

```
~/dev/issues/              # shared database lives here
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

### 1. Initialize the shared database

```bash
cd ~/dev/issues
dcat init --namespace issues
```

### 2. Link each repo

In each app repo, link to the shared database:

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
dcat config set visible_namespaces '["backend"]' --local
```

You can always see all issues with `--all-namespaces` or a specific namespace with `--namespace frontend`.

### 5. Add `.gitignore` entries

Add to each repo's `.gitignore`:

```
.dogcats/config.local.toml
```

The `.dogcatrc` file should be committed; it tells everyone where the shared database lives. The `config.local.toml` should not, since the path in `.dogcatrc` is machine-specific.

## Migrating existing repos

If you already have multiple repos each with their own `.dogcats/issues.jsonl`, the `migrate-dogcats.sh` script in this directory merges them into one shared database, backing up the originals first. Edit the `REPOS` array near the top of the script to match your layout, then run with `--dry-run` first to preview.

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

1. **Local `.dogcats/`** in the current directory
2. **Walk-up `.dogcatrc`** in any ancestor directory
3. **Global `default_storage`** from `~/.config/dogcat/config.toml`

Within the chosen storage directory, config is merged in this order (later wins):

1. **Shared `config.toml`** in the shared `.dogcats/` directory
2. **Shared `config.local.toml`** in the shared `.dogcats/` directory
3. **Repo-local `config.local.toml`** in `.dogcats/` next to the repo's `.dogcatrc` (when using `.dogcatrc` setup)

Repo-local settings (namespace, visible_namespaces) always take precedence.

When using global config, the namespace resolves as: repo-local `config.local.toml`, then the slug of the cwd folder name, then the shared store's `config.toml` namespace.
