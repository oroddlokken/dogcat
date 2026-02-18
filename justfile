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
    uv run djlint src/dogcat/web --reformat --quiet & eslint --no-error-on-unmatched-pattern --fix 'src/dogcat/web/**/static/**/*js' & pnpm run --silent stylelint-fix & wait

# lint the code
lint:
    uv run ruff format --check --diff src tests dcat.py benchmark.py tabcomp.py
    uv run ruff check src tests dcat.py benchmark.py tabcomp.py
    uv run djlint src/dogcat/web & eslint --no-error-on-unmatched-pattern 'src/dogcat/web/**/static/**/*js' & pnpm run --silent stylelint & wait

# lint using pyright
lint-pyright:
    PYRIGHT_PYTHON_FORCE_VERSION=latest uv run pyright src tests dcat.py benchmark.py tabcomp.py

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

# generate JSONL fixture for a specific tag (or all tags)
generate-fixture tag="":
    python tests/generate_fixture.py {{tag}}

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
