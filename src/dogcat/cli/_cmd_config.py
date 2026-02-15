"""Configuration management commands for dogcat CLI."""

from __future__ import annotations

from typing import Any

import typer

from dogcat.config import load_config, save_config

from ._completions import complete_config_keys, complete_config_values
from ._helpers import SortedGroup, find_dogcats_dir
from ._json_state import echo_error, is_json_output

# Sub-app for 'dcat config' subcommands
config_app = typer.Typer(
    help="Manage dogcat configuration.",
    no_args_is_help=True,
    cls=SortedGroup,
)

# Keys that should be coerced to bool
_BOOL_KEYS = frozenset({"git_tracking", "disable_legend_colors"})

# Keys whose values are stored as arrays (list[str])
_ARRAY_KEYS = frozenset({"visible_namespaces", "hidden_namespaces"})

# All known config keys: type, description, default, and allowed values
_KNOWN_KEYS: dict[str, dict[str, Any]] = {
    "namespace": {
        "type": "str",
        "description": "Issue ID prefix / project namespace",
        "default": "auto-detected",
    },
    "git_tracking": {
        "type": "bool",
        "description": "Enable git integration for issue tracking",
        "default": True,
        "values": "true, false (also: 1/0, yes/no, on/off)",
    },
    "visible_namespaces": {
        "type": "list[str]",
        "description": "Only show issues from these namespaces",
        "default": "[] (show all)",
        "values": "comma-separated namespace list",
    },
    "hidden_namespaces": {
        "type": "list[str]",
        "description": "Hide issues from these namespaces",
        "default": "[] (show all)",
        "values": "comma-separated namespace list",
    },
    "disable_legend_colors": {
        "type": "bool",
        "description": "Disable colors in legend (status symbols and priorities)",
        "default": False,
        "values": "true, false (also: 1/0, yes/no, on/off)",
    },
}

_TRUE_VALUES = frozenset({"true", "1", "yes", "on"})
_FALSE_VALUES = frozenset({"false", "0", "no", "off"})


def _coerce_value(key: str, value: str) -> Any:
    """Coerce a string value to the appropriate type for a known key."""
    if key in _BOOL_KEYS:
        lower = value.lower()
        if lower in _TRUE_VALUES:
            return True
        if lower in _FALSE_VALUES:
            return False
        msg = f"Invalid boolean value '{value}' for key '{key}'. Use true/false."
        raise typer.BadParameter(msg)
    if key in _ARRAY_KEYS:
        from dogcat.constants import parse_labels

        return parse_labels(value)
    return value


def register(app: typer.Typer) -> None:
    """Register config commands."""
    app.add_typer(config_app, name="config")

    @config_app.command("set")
    def config_set(
        key: str = typer.Argument(
            ...,
            help="Configuration key to set",
            autocompletion=complete_config_keys,
        ),
        value: str = typer.Argument(
            ...,
            help="Value to set",
            autocompletion=complete_config_values,
        ),
    ) -> None:
        """Set a configuration value."""
        dogcats_dir = find_dogcats_dir()
        config = load_config(dogcats_dir)
        coerced = _coerce_value(key, value)
        config[key] = coerced
        save_config(dogcats_dir, config)
        typer.echo(f"Set {key} = {coerced}")

    @config_app.command("get")
    def config_get(
        key: str = typer.Argument(
            ...,
            help="Configuration key to read",
            autocompletion=complete_config_keys,
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """Get a configuration value."""
        import orjson

        is_json_output(json_output)  # sync local flag for echo_error
        dogcats_dir = find_dogcats_dir()
        config = load_config(dogcats_dir)
        if key not in config:
            echo_error(f"Key '{key}' not found in config")
            raise typer.Exit(1)
        val = config[key]
        if is_json_output(json_output):
            typer.echo(orjson.dumps({key: val}).decode())
        elif isinstance(val, list):
            typer.echo(", ".join(str(i) for i in val))  # type: ignore[reportUnknownArgumentType, reportUnknownVariableType]
        else:
            typer.echo(val)

    @config_app.command("list")
    def config_list(
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """List all configuration values."""
        import orjson

        dogcats_dir = find_dogcats_dir()
        config = load_config(dogcats_dir)
        if is_json_output(json_output):
            typer.echo(orjson.dumps(config, option=orjson.OPT_INDENT_2).decode())
        else:
            if not config:
                typer.echo("No configuration values set.")
            else:
                for k, v in sorted(config.items()):
                    if isinstance(v, list):
                        typer.echo(f"{k} = {', '.join(str(i) for i in v)}")  # type: ignore[reportUnknownArgumentType, reportUnknownVariableType]
                    else:
                        typer.echo(f"{k} = {v}")

    @config_app.command("keys")
    def config_keys(
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """List all available configuration keys and their descriptions."""
        import orjson

        if is_json_output(json_output):
            typer.echo(orjson.dumps(_KNOWN_KEYS, option=orjson.OPT_INDENT_2).decode())
            return

        from rich import box
        from rich.console import Console
        from rich.table import Table

        table = Table(
            show_header=True,
            header_style="bold",
            box=box.ROUNDED,
            pad_edge=False,
            show_edge=False,
        )
        table.add_column("Key", no_wrap=True)
        table.add_column("Type", no_wrap=True)
        table.add_column("Default", no_wrap=True)
        table.add_column("Description", overflow="fold")
        table.add_column("Values", overflow="fold")

        for key, info in _KNOWN_KEYS.items():
            default = info["default"]
            if isinstance(default, bool):
                default = str(default).lower()
            else:
                default = str(default)
            table.add_row(
                key,
                info["type"],
                default,
                info["description"],
                info.get("values", ""),
            )

        Console().print(table)
