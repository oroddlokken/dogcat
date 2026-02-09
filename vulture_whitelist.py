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
on_input_changed  # type: ignore[name-defined]  # noqa: B018
on_option_list_option_selected  # type: ignore[name-defined]  # noqa: B018

# Mock setup in tests — .return_value / .side_effect configure mock behavior
_.return_value  # type: ignore[name-defined]  # noqa: B018
_.side_effect  # type: ignore[name-defined]  # noqa: B018
