"""Configuration management commands for dogcat CLI."""

from __future__ import annotations

from typing import Any

import typer

from dogcat.config import load_config, save_config

from ._helpers import SortedGroup, find_dogcats_dir

# Sub-app for 'dcat config' subcommands
config_app = typer.Typer(
    help="Manage dogcat configuration.",
    no_args_is_help=True,
    cls=SortedGroup,
)

# Keys that should be coerced to bool
_BOOL_KEYS = frozenset({"git_tracking"})

# All known config keys and their types (for help text)
_KNOWN_KEYS = {
    "namespace": "str",
    "git_tracking": "bool",
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
    return value


def register(app: typer.Typer) -> None:
    """Register config commands."""
    app.add_typer(config_app, name="config")

    @config_app.command("set")
    def config_set(
        key: str = typer.Argument(..., help="Configuration key to set"),
        value: str = typer.Argument(..., help="Value to set"),
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
        key: str = typer.Argument(..., help="Configuration key to read"),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """Get a configuration value."""
        import orjson

        dogcats_dir = find_dogcats_dir()
        config = load_config(dogcats_dir)
        if key not in config:
            typer.echo(f"Key '{key}' not found in config", err=True)
            raise typer.Exit(1)
        val = config[key]
        if json_output:
            typer.echo(orjson.dumps({key: val}).decode())
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
        if json_output:
            typer.echo(orjson.dumps(config, option=orjson.OPT_INDENT_2).decode())
        else:
            if not config:
                typer.echo("No configuration values set.")
            else:
                for k, v in sorted(config.items()):
                    typer.echo(f"{k} = {v}")
