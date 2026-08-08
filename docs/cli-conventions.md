# CLI conventions

Read this before adding or changing a command, an option, or a shared constant.

## Where constants actually live

`src/dogcat/constants.py` holds display metadata and layout literals: colors, symbols, the UI option
lists (`STATUS_OPTIONS`, `TYPE_OPTIONS`, `PRIORITY_OPTIONS`, `PRIORITY_NAMES`), shorthands, filenames
and limits. Import from there rather than retyping a literal. It is not the only registry, and the
split is deliberate:

- **Statuses, issue types, dependency and link types** — the canonical enums are `Status`,
  `IssueType`, `DependencyType` and `LinkType` in `src/dogcat/models.py`. `constants.STATUS_OPTIONS`
  is the user-facing subset and omits `tombstone` and `unknown`. Validate against the enum; render
  from the options list.
- **Config keys** — three registries exist and already disagree: `_KNOWN_CONFIG_KEYS`
  (`config.py:215`, runtime), `_KNOWN_KEYS` (`cli/_cmd_config.py:39`, CLI help and completion), and
  `GLOBAL_CONFIG_KEYS` (`global_config.py:33`, the two keys the global file accepts). Adding a key
  means touching all three.
- **Labels** — no label constant exists. Labels are free-form and discovered from the store.
- **Paths** — `constants.py` owns the names, and `config.py` re-declares `DOGCATS_DIR_NAME` and adds
  `CONFIG_FILENAME` / `LOCAL_CONFIG_FILENAME` of its own.

## Adding a command

One file per command area, `src/dogcat/cli/_cmd_<area>.py`, exposing a single
`def register(app: typer.Typer) -> None:` that declares the commands inside it. Add the module name
to `_COMMAND_MODULES` in `src/dogcat/cli/__init__.py` — registration is an explicit list, not
auto-discovery, so an unlisted module does not exist to the CLI.

Import and registration failures are caught per module and downgraded to a `_logger.warning`, so a
broken import makes one command vanish silently while the rest of dcat keeps working. When a command
you just added is missing from `dcat --help`, look for an exception inside `register()` or at import
time before suspecting Typer.

A command that takes an issue ID and uses `complete_issue_ids` needs the `@with_ns_shim` decorator
(`cli/_helpers.py:40`); it injects the hidden `-A` / `--namespace` options the completer reads out of
the Click context. Without it, completion ignores namespace visibility.

Any command accepting `--json` calls `set_json(json_output)` from `_json_state`. `--json` also exists
as a global option before the subcommand (`dcat --json list`), and both paths write the same
module-level flag that `is_json()` and the formatters read.

## Tab completions

Every CLI option whose values come from a fixed set — status, type, priority, owner, namespace,
labels, config keys, export formats, dep and link types — registers an `autocompletion=` callback via
Typer. Shared completers live in `src/dogcat/cli/_completions.py` and return `list[tuple[str, str]]`
(value, description) pairs. A completer used by exactly one command may stay in that command's module
(`_complete_by_values` in `_cmd_chart.py:146` is the current example); move it to `_completions.py`
the moment a second command needs it.

Two options deliberately have no callback: `dcat init --namespace` names a namespace that does not
exist yet, and the hidden `--namespace` added by `with_ns_shim` is plumbing rather than user input.

When a completer enumerates an enum, enumerate all of it. `complete_dep_types` and
`complete_link_types` currently offer a subset of `DependencyType` and `LinkType`, so valid values do
not tab-complete. That is a bug to avoid copying, not a pattern.

Verify with `uv run ./tabcomp.py "dcat <command> --option "` — the trailing space means "complete the
next argument". Nothing enforces this convention automatically: `tests/test_completions.py` unit-tests
individual completers but never asserts that a given option has one.
