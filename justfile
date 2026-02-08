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
    black src tests dcat.py benchmark.py
    isort src tests dcat.py benchmark.py

fmt-ruff:
    ruff check --fix --unsafe-fixes src tests dcat.py benchmark.py

# run all formatters
fmt-all:
    just fmt
    just fmt-ruff
    just fmt
    just fmt-ruff    

# lint the code
lint:
    black --check --diff src tests dcat.py benchmark.py
    isort --check-only --diff src tests dcat.py benchmark.py
    ruff check src tests dcat.py benchmark.py

# lint using pyright
lint-pyright:
    PYRIGHT_PYTHON_FORCE_VERSION=latest pyright src tests dcat.py benchmark.py

# run all linters
lint-all:
    just lint
    just lint-pyright

# find dead code with vulture
vulture:
    vulture src tests dcat.py benchmark.py --ignore-decorators "@app.command" --ignore-names "on_modified,on_moved,RELATED,reload"

# run tests
test:
    pytest --timeout 30 -n 8 tests --cov-config=.coveragerc --cov-report=html --cov=src/dogcat

# generate JSONL fixture for a specific tag (or all tags)
generate-fixture tag="":
    python tests/generate_fixture.py {{tag}}
