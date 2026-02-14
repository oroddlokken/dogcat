# Automatically load environment variables from a .env file.
# set dotenv-load

# list all targets
default:
    @just --list

# list all variables
var:
    @just --evaluate

# run formatters
fmt:
    uv run ruff check --select I --fix src tests dcat.py benchmark.py
    uv run ruff format src tests dcat.py benchmark.py
    uv run ruff check --fix --unsafe-fixes src tests dcat.py benchmark.py

# lint the code
lint:
    uv run ruff format --check --diff src tests dcat.py benchmark.py
    uv run ruff check src tests dcat.py benchmark.py

# lint using pyright
lint-pyright:
    PYRIGHT_PYTHON_FORCE_VERSION=latest uv run pyright src tests dcat.py benchmark.py

# run all linters
lint-all:
    just lint
    just lint-pyright

# find dead code with vulture
vulture:
    uv run vulture src tests dcat.py benchmark.py vulture_whitelist.py --ignore-decorators "@app.command" --ignore-names "on_modified,on_moved,RELATED,reload"

# run tests (excludes regression tests)
test:
    uv run pytest --timeout 30 -n 8 tests --ignore=tests/test_regression.py

# run regression tests only
test-regression:
    uv run pytest --timeout 60 -n 8 tests/test_regression.py

# run all tests (including regression)
test-all:
    uv run pytest --timeout 60 -n 8 tests --cov-config=.coveragerc --cov-report=html --cov=src/dogcat

# run tests across Python 3.10-3.14 (installs missing interpreters automatically)
test-matrix *args:
    tox {{args}}

# run tests on a single Python version (e.g. just test-py 3.12)
test-py version *args:
    tox -e py{{replace(version, ".", "")}} {{args}}

# generate JSONL fixture for a specific tag (or all tags)
generate-fixture tag="":
    python tests/generate_fixture.py {{tag}}

# prepare a release: create RC tag, push branch, open PR (stays on current branch)
release-prep version:
    #!/usr/bin/env bash
    set -euo pipefail
    VERSION="{{version}}"
    BRANCH="release/v${VERSION}"
    TAG_PREFIX="v${VERSION}-rc"
    WORKTREE_DIR=".release-worktree"

    # Determine next RC number
    LAST_RC=$(git tag -l "${TAG_PREFIX}.*" | sed "s/${TAG_PREFIX}\.//" | sort -n | tail -1)
    if [ -z "$LAST_RC" ]; then
        RC=1
    else
        RC=$((LAST_RC + 1))
    fi
    RC_TAG="${TAG_PREFIX}.${RC}"

    echo "Preparing ${RC_TAG} on branch ${BRANCH}"

    # Clean up any stale worktree
    if [ -d "$WORKTREE_DIR" ]; then
        git worktree remove --force "$WORKTREE_DIR" 2>/dev/null || true
    fi

    # Create or reuse release branch in a temporary worktree
    if git show-ref --verify --quiet "refs/heads/${BRANCH}"; then
        git worktree add "$WORKTREE_DIR" "${BRANCH}"
    else
        git worktree add -b "${BRANCH}" "$WORKTREE_DIR"
    fi

    trap 'git worktree remove --force "$WORKTREE_DIR" 2>/dev/null || true' EXIT

    # Stamp CHANGELOG: insert version header after [Unreleased]
    DATE=$(date +%Y-%m-%d)
    if ! grep -q "^## ${VERSION}" "${WORKTREE_DIR}/CHANGELOG.md"; then
        sed -i.bak "s/^## \[Unreleased\]/## [Unreleased]\n\n## ${VERSION} (${DATE})/" "${WORKTREE_DIR}/CHANGELOG.md"
        rm -f "${WORKTREE_DIR}/CHANGELOG.md.bak"
        git -C "$WORKTREE_DIR" add CHANGELOG.md
        git -C "$WORKTREE_DIR" commit -m "Prepare changelog for v${VERSION}"
    fi

    # Skip if HEAD already has an RC tag (nothing changed)
    EXISTING_TAG=$(git -C "$WORKTREE_DIR" tag --points-at HEAD | grep "^${TAG_PREFIX}\." || true)
    if [ -n "$EXISTING_TAG" ]; then
        echo "HEAD already tagged as ${EXISTING_TAG} — nothing changed, skipping."
        exit 0
    fi

    # Tag and push
    git -C "$WORKTREE_DIR" tag -a "${RC_TAG}" -m "Release candidate ${RC_TAG}"
    git push -u origin "${BRANCH}" --tags

    # Open PR if one doesn't exist yet
    if ! gh pr view "${BRANCH}" > /dev/null 2>&1; then
        gh pr create \
            --head "${BRANCH}" \
            --title "Release v${VERSION}" \
            --body "$(cat <<EOF
    ## Release v${VERSION}

    Release candidate: \`${RC_TAG}\`

    Merging this PR will:
    1. Create the final \`v${VERSION}\` tag
    2. Build and publish the release
    3. Update the Homebrew formula
    EOF
    )" \
            --base main
    else
        echo "PR already exists for ${BRANCH}"
    fi

    echo ""
    echo "Done! RC tag ${RC_TAG} pushed."
    echo "Review the PR, then merge to publish the final release."
