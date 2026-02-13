"""Vulture whitelist — false positives that should not be flagged as dead code."""

# _make_alias() sets these dunder attrs so Typer/inspect can read them
wrapper.__signature__  # type: ignore[name-defined]  # noqa: B018
wrapper.__doc__  # type: ignore[name-defined]  # noqa: B018

# Textual TUI framework uses these via introspection
TITLE  # type: ignore[name-defined]  # noqa: B018
BINDINGS  # type: ignore[name-defined]  # noqa: B018
CSS  # type: ignore[name-defined]  # noqa: B018
compose  # type: ignore[name-defined]  # noqa: B018
on_mount  # type: ignore[name-defined]  # noqa: B018
on_button_pressed  # type: ignore[name-defined]  # noqa: B018
action_save  # type: ignore[name-defined]  # noqa: B018
action_refresh  # type: ignore[name-defined]  # noqa: B018
on_input_changed  # type: ignore[name-defined]  # noqa: B018
on_option_list_option_selected  # type: ignore[name-defined]  # noqa: B018
ENABLE_COMMAND_PALETTE  # type: ignore[name-defined]  # noqa: B018
_get_dom_base  # type: ignore[name-defined]  # noqa: B018

# Typer CLI commands registered via decorators inside register() functions
config_set  # type: ignore[name-defined]  # noqa: B018
config_get  # type: ignore[name-defined]  # noqa: B018
config_list  # type: ignore[name-defined]  # noqa: B018
config_keys  # type: ignore[name-defined]  # noqa: B018
git_guide  # type: ignore[name-defined]  # noqa: B018
git_check  # type: ignore[name-defined]  # noqa: B018
git_setup  # type: ignore[name-defined]  # noqa: B018
git_merge_driver  # type: ignore[name-defined]  # noqa: B018

# Typer CLI option parameter used as --opinionated flag
opinionated  # type: ignore[name-defined]  # noqa: B018

# Dynamically set on copied Typer parameter defaults in _make_alias()
_.help  # type: ignore[name-defined]  # noqa: B018

# Mock setup in tests — .return_value / .side_effect configure mock behavior
_.return_value  # type: ignore[name-defined]  # noqa: B018
_.side_effect  # type: ignore[name-defined]  # noqa: B018
_.__str__  # type: ignore[name-defined]  # noqa: B018
