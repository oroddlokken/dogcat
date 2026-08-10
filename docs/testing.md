# Testing

Read this before writing or debugging a test. `AGENTS.md` carries the day-to-day commands; this
file carries what those commands do not tell you.

## Isolation is autouse, and a test can escape it

`tests/conftest.py` is the only conftest. Three autouse fixtures isolate every test:
`_isolate_cwd` chdirs to `tmp_path`, `_isolate_xdg_cache` and `_isolate_global_config` redirect
`XDG_CACHE_HOME` and `XDG_CONFIG_HOME`. Storage and config resolution walk *up* from the cwd, so a
test that chdirs back into the checkout, or shells out with `cwd=` pointing at the repo root,
escapes the isolation and writes to this repo's real `.dogcats/`. Conftest's own docstring records
what happens without the guards: failures in bulk, and writes into the live `config.local.toml`.

Pass an explicit `--dogcats-dir` (see `tests/cli_test_helpers.py`) or take the `git_repo` /
`temp_dogcats_dir` fixtures rather than relying on the cwd.

## Running one test

No `just` recipe accepts a test selector. Run pytest directly:

```bash
uv run pytest tests/test_merge_driver.py::TestMergeJSONL::test_deps_union
uv run pytest tests/test_merge_driver.py
```

Most tests are methods on a `Test*` class, so a bare `file.py::test_name` node id fails to collect.
Get the real id with `uv run pytest --collect-only -q <file>`.

## Where local runs diverge from CI

CI runs `uv run pytest --timeout 30 -n 8 tests` on Python 3.10 and 3.14
(`.github/workflows/ci.yml`). Three gaps follow:

- `just test-all` uses `--timeout 60` plus coverage, so a test taking between 30 and 60 seconds
  passes locally and fails CI. Run the CI line directly to reproduce.
- `just test` passes `--ignore=tests/test_regression.py`, and CI runs those tests. Use `just test-all`
  before committing. When a schema change breaks a fixture, regenerate it with
  `just generate-fixture <tag>` rather than editing the fixture by hand.
- No interpreter is pinned, so the local `.venv` is whatever uv resolved and a green local run
  proves neither CI leg. For a version-sensitive change run `uv run --python 3.10 pytest -n 8 tests`.

`just test-changed` selects tests through pytest-testmon, which consults `.testmondata`, a gitignored
SQLite cache of per-test file dependencies. A fresh clone runs the whole suite once to build it.
Because testmon deselects, a green `test-changed` means nothing it *chose* to run failed — it is not
a green suite.

There is no coverage threshold and CI measures no coverage, so the HTML report from `just test-all`
is advisory. "Tested" here means an assertion that reads state back from disk after a CLI mutation;
`tests/cli_test_helpers.py` documents the convention.

The timing budgets in `tests/test_merge_scale.py` are no-ops unless `DCAT_RUN_PERF_TESTS=1`, because
runner speed varies several-fold. Run them with `just test-perf` when touching `merge_driver.py`;
CI never does, so a green pipeline does not rule out a perf regression.

## TUI tests

TUI tests drive the real Textual app rather than mocking it:

```python
async with app.run_test(size=(cols, rows)) as pilot:
    await pilot.press("j")
    await pilot.pause()
```

`asyncio_mode = "strict"`, so every async test needs an explicit `@pytest.mark.asyncio` or it
silently does not run. Build storage as `MagicMock(spec=JSONLStorage)` so a renamed storage method
fails the test instead of passing, and point `storage.dogcats_dir` at a real directory — the
namespace lookup falls back to defaults on a missing path without erroring. Layout tests need a
`size=` that straddles `SPLIT_PANE_MIN_COLS` / `SPLIT_PANE_MIN_ROWS`. See `tests/test_tui_split_pane.py`
and `tests/test_tui_dashboard.py`.

Storage mutations run in a Textual thread worker, so a test that asserts on the result has to wait
for the worker rather than for a repaint. Use `wait_for_workers(app)` from `tests/tui_test_helpers.py`;
`pilot.pause()` alone returns before the write lands. Wrap it in `asyncio.wait_for` whenever the test
holds the store lock, since an unbounded wait hangs the suite instead of failing it.
`tests/test_tui_concurrency.py` holds the advisory lock from the test process to prove the app keeps
handling keystrokes while a save waits.

## Web tests

Use `fastapi.testclient.TestClient`, as `tests/test_web_propose.py` does. There is no JavaScript
test runner in this project — `package.json` defines only lint scripts. A change to
`src/dogcat/web/static/js/propose.js` is verified by `just lint` plus a server-side assertion over
the rendered HTML, and `jsconfig.json`'s `checkJs` is editor-only, so a green `just lint` is not a
type check.
