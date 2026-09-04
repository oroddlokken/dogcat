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
    uv run ruff format src tests dcat.py benchmark.py tabcomp.py
    uv run ruff check --fix --unsafe-fixes src tests dcat.py benchmark.py tabcomp.py
    # djlint --reformat exits non-zero whenever it rewrites a file, so `|| true`
    # keeps `fmt` (an apply step) green. Genuine djlint issues are still caught
    # by `lint`, which runs djlint in check mode. The `rc` loop below is what
    # makes a failing branch fail the recipe — a bare `wait` returns the last
    # job's status and silently swallowed the others.
    uv run djlint src/dogcat/web --reformat --quiet || true & d=$!; \
    pnpm run --silent oxfmt-fix & o=$!; \
    pnpm run --silent oxlint-fix & l=$!; \
    pnpm run --silent stylelint-fix & s=$!; \
    rc=0; for p in $d $o $l $s; do wait $p || rc=1; done; exit $rc

# run all formatters
fmt-all:
    just fmt

# lint the code
lint:
    uv run ruff format --check --diff src tests dcat.py benchmark.py tabcomp.py
    uv run ruff check src tests dcat.py benchmark.py tabcomp.py
    uv run djlint src/dogcat/web & d=$!; \
    pnpm run --silent oxfmt & o=$!; \
    pnpm run --silent oxlint & l=$!; \
    pnpm run --silent stylelint & s=$!; \
    rc=0; for p in $d $o $l $s; do wait $p || rc=1; done; exit $rc

# lint using pyright
lint-pyright:
    PYRIGHT_PYTHON_FORCE_VERSION=latest uv run pyright src tests dcat.py benchmark.py tabcomp.py

# --locked fails when pyproject.toml has drifted from uv.lock, so a stale lock
# surfaces here instead of at the next `uv sync`.
# audit dependencies for known vulnerabilities (needs network)
audit:
    uv audit --preview-features audit-command --locked
    pnpm audit --audit-level high

# run all linters
lint-all:
    just lint
    just lint-pyright

# find dead code with vulture
vulture:
    uv run vulture src tests dcat.py benchmark.py tabcomp.py vulture_whitelist.py --ignore-decorators "@app.command" --ignore-names "on_modified,on_moved,RELATED,reload"

# run tests (excludes regression tests)
test:
    uv run pytest --timeout 30 -n 8 tests --ignore=tests/test_regression.py

# run only tests affected by code changes since last run
test-changed:
    uv run pytest --testmon --timeout 60 -n 8 tests

# run regression tests only
test-regression:
    uv run pytest --timeout 60 -n 8 tests/test_regression.py

# run all tests (including regression)
test-all:
    COVERAGE_CORE=sysmon uv run pytest --timeout 60 -n 8 tests --cov-report=html --cov=src/dogcat

# run merge_driver perf budget tests (gated behind DCAT_RUN_PERF_TESTS)
test-perf:
    DCAT_RUN_PERF_TESTS=1 uv run pytest --timeout 60 tests/test_merge_scale.py

# generate JSONL fixture for a specific tag (or all tags)
generate-fixture tag="":
    python tests/generate_fixture.py {{tag}}

# build an sdist and check it for unexpected contents and size
check-sdist:
    #!/usr/bin/env bash
    set -euo pipefail
    # Built into a temp dir rather than dist/, which holds artifacts from
    # earlier builds that would make the tarball ambiguous.
    out=$(mktemp -d)
    trap 'rm -rf "$out"' EXIT
    uv build --sdist --out-dir "$out" -q
    ./scripts/check-sdist "$out"/*.tar.gz

# show next possible versions (patch or minor bump)
next:
    #!/usr/bin/env bash
    set -euo pipefail
    LATEST=$(git tag -l 'v[0-9]*.[0-9]*.[0-9]*' | sed 's/^v//; s/-rc\..*//' | sort -t. -k1,1n -k2,2n -k3,3n -u | tail -1)
    IFS='.' read -r MAJOR MINOR PATCH <<< "$LATEST"
    RC=$(git tag -l "v${LATEST}-rc.*" | sort -V | tail -1 | sed -n 's/.*-rc\.//p')
    RELEASED=$(git tag -l "v${LATEST}" | head -1)
    if [ -n "$RC" ] && [ -z "$RELEASED" ]; then
        echo "Current: ${MAJOR}.${MINOR}.${PATCH} (rc.${RC}, unreleased)"
    elif [ -n "$RC" ]; then
        echo "Current: ${MAJOR}.${MINOR}.${PATCH}"
    else
        echo "Current: ${MAJOR}.${MINOR}.${PATCH}"
    fi
    echo "  patch: ${MAJOR}.${MINOR}.$((PATCH + 1))"
    echo "  minor: ${MAJOR}.$((MINOR + 1)).0"

# prepare a release: create RC tag, push branch, open PR
release-prep *args:
    ./scripts/release-prep {{args}}
    git pull origin main

uv-sync-reinstall:
    uv sync --reinstall-package dogcat
