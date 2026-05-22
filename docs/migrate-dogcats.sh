#!/usr/bin/env zsh
set -euo pipefail

# Merge separate per-repo dogcat databases into one shared database.
#
# What this script does:
#   1. Creates a shared .dogcats directory at SHARED_DIR
#   2. Copies each repo's issues.jsonl into the shared database
#   3. Writes .dogcatrc in each repo (points to the shared dir)
#   4. Writes namespace and visible_namespaces per repo (config.local.toml)
#   5. Adds .dogcats/config.local.toml to each repo's .gitignore
#   6. Backs up the original .dogcats directories before touching them
#
# Requires dogcat v0.11.7+ (or v0.11.6 with PR #19 applied).
# See: https://github.com/oroddlokken/dogcat/issues/18
#
# Usage: ./migrate-dogcats.sh [--dry-run]
#
# Customize SHARED_DIR, REPOS, and BASE_DIR for your layout before running.

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

# Where the shared database should live.
SHARED_DIR="$HOME/dev/issues/.dogcats"
BACKUP_DIR="$HOME/dev/issues/.dogcats-migration-backup"

# Parent directory that contains the repos in REPOS below.
BASE_DIR="$HOME/dev"

# Repo directory name -> namespace.
typeset -A REPOS
REPOS=(
  backend-app       backend
  frontend-app      frontend
  infrastructure    infra
)

info()  { echo "  -> $*"; }
warn()  { echo "  [WARN] $*"; }
err()   { echo "  [ERR]  $*" >&2; }

echo "=== Dogcat migration ==="
echo "Shared database: $SHARED_DIR"
echo "Repos:           ${#REPOS}"
echo "Dry run:         $DRY_RUN"
echo ""

# Step 1: create the shared database
echo "[1/6] Creating shared database..."
if [[ -d "$SHARED_DIR" ]]; then
  warn "Shared dir already exists: $SHARED_DIR"
  if [[ -f "$SHARED_DIR/issues.jsonl" ]] && [[ -s "$SHARED_DIR/issues.jsonl" ]]; then
    err "issues.jsonl is not empty. Aborting to avoid data loss."
    err "Delete $SHARED_DIR manually if you want to re-run the migration."
    exit 1
  fi
fi

if $DRY_RUN; then
  info "[dry-run] mkdir -p $SHARED_DIR"
else
  mkdir -p "$SHARED_DIR"
  mkdir -p "$BACKUP_DIR"
fi

# Step 2: back up and merge issues.jsonl
echo ""
echo "[2/6] Merging issues from all repos..."
total_lines=0

for repo in ${(ko)REPOS}; do
  ns="${REPOS[$repo]}"
  src="$BASE_DIR/$repo/.dogcats/issues.jsonl"

  if [[ ! -f "$src" ]]; then
    warn "$repo: no issues.jsonl, skipping"
    continue
  fi

  lines=$(wc -l < "$src" | tr -d ' ')
  if [[ "$lines" -eq 0 ]]; then
    warn "$repo: issues.jsonl is empty, skipping"
    continue
  fi

  total_lines=$((total_lines + lines))

  if $DRY_RUN; then
    info "[dry-run] $repo ($ns): $lines lines -> shared"
  else
    backup_dest="$BACKUP_DIR/$repo"
    mkdir -p "$backup_dest"
    cp -a "$BASE_DIR/$repo/.dogcats/" "$backup_dest/"
    info "$repo ($ns): $lines lines -> shared (backup: $backup_dest)"

    cat "$src" >> "$SHARED_DIR/issues.jsonl"
  fi
done

echo "  Total: $total_lines lines"

# Step 3: write the shared config
echo ""
echo "[3/6] Writing shared config..."

if $DRY_RUN; then
  info "[dry-run] write config.toml with namespace=issues"
else
  cat > "$SHARED_DIR/config.toml" << 'EOF'
namespace = "issues"
EOF
  info "config.toml written"
fi

# Step 4: set up .dogcatrc and config.local.toml per repo
echo ""
echo "[4/6] Linking repos to shared database..."

for repo in ${(ko)REPOS}; do
  ns="${REPOS[$repo]}"
  repo_dir="$BASE_DIR/$repo"
  rc_file="$repo_dir/.dogcatrc"
  local_dogcats="$repo_dir/.dogcats"
  local_config="$local_dogcats/config.local.toml"

  if $DRY_RUN; then
    info "[dry-run] $repo: .dogcatrc -> $SHARED_DIR, namespace=$ns"
    continue
  fi

  if [[ -d "$local_dogcats" ]]; then
    rm -rf "$local_dogcats"
  fi

  echo "$SHARED_DIR" > "$rc_file"
  info "$repo: .dogcatrc -> $SHARED_DIR"

  mkdir -p "$local_dogcats"
  cat > "$local_config" << EOF
namespace = "$ns"
visible_namespaces = ["$ns"]
EOF
  info "$repo: namespace=$ns, visible_namespaces=[$ns]"
done

# Step 5: gitignore the per-repo local config
echo ""
echo "[5/6] Adding .dogcats/config.local.toml to .gitignore..."

for repo in ${(ko)REPOS}; do
  repo_dir="$BASE_DIR/$repo"
  gitignore="$repo_dir/.gitignore"

  if [[ -f "$gitignore" ]] && grep -q "config.local.toml" "$gitignore" 2>/dev/null; then
    info "$repo: already in .gitignore"
    continue
  fi

  if $DRY_RUN; then
    info "[dry-run] $repo: append to .gitignore"
  else
    echo ".dogcats/config.local.toml" >> "$gitignore"
    info "$repo: added to .gitignore"
  fi
done

# Step 6: verify
echo ""
echo "[6/6] Verifying..."

if $DRY_RUN; then
  info "[dry-run] verification skipped"
else
  shared_lines=$(wc -l < "$SHARED_DIR/issues.jsonl" | tr -d ' ')
  info "Shared database: $shared_lines lines (expected: $total_lines)"

  if [[ "$shared_lines" -ne "$total_lines" ]]; then
    err "MISMATCH: expected $total_lines, got $shared_lines"
    exit 1
  fi

  python3 -c "
import json
ns = set()
with open('$SHARED_DIR/issues.jsonl') as f:
    for line in f:
        r = json.loads(line)
        if r.get('record_type') == 'issue':
            ns.add(r.get('namespace', ''))
for n in sorted(ns):
    print(f'    {n}')
print(f'  Total: {len(ns)} namespaces')
"
fi

echo ""
echo "=== Done ==="
if ! $DRY_RUN; then
  echo ""
  echo "Backup of original databases: $BACKUP_DIR"
  echo ""
  echo "Run 'dcat list --all-namespaces' from any repo to see all issues across namespaces."
fi
