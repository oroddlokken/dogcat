# Web UI and the node toolchain

Read this before editing anything under `src/dogcat/web/` or touching the lint toolchain.

## The node half of the toolchain

oxlint, oxfmt and stylelint are pnpm devDependencies, and `just lint` and `just fmt` shell out to
`pnpm run` for each. Run `pnpm install --frozen-lockfile` once per checkout. Without `node_modules`,
both recipes fail on the pnpm branches even when you touched no JavaScript, and because `lint-all`
runs `lint` first, pyright never gets to run. `node_modules` is gitignored, so a fresh clone needs
this step again.

`just lint` fans out over four file types: ruff for Python, djlint for the Jinja templates under
`src/dogcat/web`, oxlint and oxfmt for `src/dogcat/web/static/js`, and stylelint for the CSS. Editing
`propose.html`, `propose.css` or `propose.js` therefore still means running `just lint` — pyright and
the Python tests never see those files.

The TUI has no stylesheet file. Textual CSS lives in `CSS = """..."""` class attributes inside
`src/dogcat/tui/*.py`, so stylelint does not cover it and ruff's formatting rules apply to the
surrounding Python instead.

## Content Security Policy

The propose server sends `default-src 'none'; style-src 'self'; script-src 'self'`
(`WEB_CSP_HEADER` in `constants.py`). No inline `<script>`, no `onclick=` attributes, no inline
`style=` attributes,
and no CDN URLs — the browser drops them silently, and a test asserts the policy carries no
`unsafe-inline`. New behavior goes in `propose.js`; new styling goes in `propose.css`.

## Assets and structure

The propose server is FastAPI plus Jinja2: one template
(`src/dogcat/web/propose/templates/propose.html`), one stylesheet, one script. Assets live under
`src/dogcat/web/static/` and mount at `/static`, so reference them as
`{{ url_for('static', path='css/propose.css') }}`.

`dcat web propose` binds `127.0.0.1` unless `DCAT_WEB_HOST` overrides it, and has no
authentication; CSRF nonces cap abuse but do not identify the submitter. An exported
`DCAT_WEB_HOST=0.0.0.0` therefore puts an unauthenticated submission form on every interface with
nothing on the command line to say so. It also blocks until quit, so verify web behavior with
`TestClient` rather than by starting the server (see `docs/testing.md`).

| Env var | Default | Effect |
| --- | --- | --- |
| `DCAT_WEB_HOST` | `127.0.0.1` | Bind address. A CLI `--host` still wins. |
| `DCAT_WEB_PORT` | `48042` | Bind port. A CLI `--port` still wins; an unparseable value warns and falls back. |

## Deferred imports

`import dogcat.cli` must not pull in `textual`, `fastapi` or `uvicorn`. Keep every import of those
packages inside the function that needs it — `src/dogcat/cli/_cmd_tui.py` and `_cmd_web.py` show the
pattern. `textual.app` alone costs about as much as the whole CLI import, so hoisting one import to
module scope roughly doubles what every `dcat` invocation pays. Ruff cannot catch this: `PLC0415` is
disabled globally, and no test asserts it.

## Proposals

The web form writes through `InboxStorage` rather than shelling out to `dcat`; in-process callers own
the locking and the event append. A proposal moves `open` → `closed` → `tombstone` and never back —
`close()` refuses a tombstoned proposal outright.

`.dogcats/inbox.jsonl` also accumulates `event` records from the shared emitter, but `InboxStorage`
indexes only `proposal` records on load and its compaction rewrite emits only proposals, so an inbox
compaction erases that event history. Do not build tooling that depends on those events surviving.

A namespace created through the web form is persisted to `.dogcats/config.local.toml`, which is
gitignored, so it does not travel with the repo.
