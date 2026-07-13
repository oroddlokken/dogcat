"""Configuration management commands for dogcat CLI."""

from __future__ import annotations

from typing import Any

import typer

from dogcat.config import (
    load_config,
    load_local_config,
    load_shared_config,
    save_config,
    save_local_config,
)

from ._completions import complete_config_keys, complete_config_values
from ._helpers import SortedGroup, find_dogcats_dir, is_gitignored
from ._json_state import echo_error, is_json, set_json

# Sub-app for 'dcat config' subcommands
config_app = typer.Typer(
    help="Manage dogcat configuration.",
    no_args_is_help=True,
    cls=SortedGroup,
)

# Keys that should be coerced to bool
_BOOL_KEYS = frozenset(
    {"git_tracking", "disable_legend_colors", "allow_creating_namespaces"}
)

# Keys whose values are stored as arrays (list[str])
_ARRAY_KEYS = frozenset(
    {"visible_namespaces", "hidden_namespaces", "pinned_namespaces"}
)

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
    "pinned_namespaces": {
        "type": "list[str]",
        "description": "Always show these namespaces even when empty",
        "default": "[]",
        "values": "comma-separated namespace list",
    },
    "disable_legend_colors": {
        "type": "bool",
        "description": "Disable colors in legend (status symbols and priorities)",
        "default": False,
        "values": "true, false (also: 1/0, yes/no, on/off)",
    },
    "allow_creating_namespaces": {
        "type": "bool",
        "description": "Allow creating new namespaces in web propose form",
        "default": True,
        "values": "true, false (also: 1/0, yes/no, on/off)",
    },
    "inbox_remote": {
        "type": "str",
        "description": "Path to shared remote inbox .dogcats directory",
        "default": "(none)",
        "local_only": True,
    },
    "default_storage": {
        "type": "str",
        "description": "Path to .dogcats used as global fallback (global only)",
        "default": "(unset)",
        "global_only": True,
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
        local: bool = typer.Option(
            False,
            "--local",
            help="Save to config.local.toml (gitignored, machine-specific)",
        ),
        global_: bool = typer.Option(
            False,
            "--global",
            help="Save to ~/.config/dogcat/config.toml (user-global)",
        ),
    ) -> None:
        """Set a configuration value."""
        if local and global_:
            echo_error("--local and --global are mutually exclusive")
            raise typer.Exit(2)

        coerced = _coerce_value(key, value)
        key_info = _KNOWN_KEYS.get(key, {})

        if global_:
            from dogcat.global_config import (
                GLOBAL_CONFIG_KEYS,
                save_global_config_value,
            )

            # Only keys the runtime reads globally may be set globally;
            # anything else would sit in the file looking configured
            # while never taking effect.
            if key not in GLOBAL_CONFIG_KEYS:
                echo_error(
                    f"'{key}' is not a global config key. "
                    f"Global keys: {', '.join(sorted(GLOBAL_CONFIG_KEYS))}"
                )
                raise typer.Exit(2)

            save_global_config_value(key, coerced)
            typer.echo(f"Set {key} = {coerced} (global)")
            return

        if key_info.get("global_only"):
            echo_error(
                f"'{key}' is a global-only setting and has no effect in "
                f"repo config. Use 'dcat config set --global {key} <value>'."
            )
            raise typer.Exit(2)

        dogcats_dir = find_dogcats_dir()

        if key_info.get("local_only") and not local:
            typer.echo(
                f"Note: '{key}' is a machine-specific setting. "
                f"Saving to config.local.toml.",
            )
            local = True

        if local:
            config = load_local_config(dogcats_dir)
            config[key] = coerced
            save_local_config(dogcats_dir, config)
            typer.echo(f"Set {key} = {coerced} (local)")
            from pathlib import Path

            local_file = Path(dogcats_dir) / "config.local.toml"
            if not is_gitignored(str(local_file)):
                typer.echo(
                    "Warning: .dogcats/config.local.toml is not in .gitignore. "
                    "Add it to avoid committing machine-specific settings.",
                    err=True,
                )
        else:
            config = load_shared_config(dogcats_dir)
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
        global_: bool = typer.Option(
            False,
            "--global",
            help="Read from ~/.config/dogcat/config.toml",
        ),
    ) -> None:
        """Get a configuration value."""
        import orjson

        set_json(json_output)

        if global_:
            from dogcat.global_config import load_global_config_raw

            data = load_global_config_raw()
            if key not in data:
                echo_error(f"Key '{key}' not found in global config")
                raise typer.Exit(1)
            val = data[key]
            if is_json():
                typer.echo(orjson.dumps({key: val}).decode())
            elif isinstance(val, list):
                typer.echo(", ".join(str(i) for i in val))  # type: ignore[reportUnknownArgumentType, reportUnknownVariableType]
            else:
                typer.echo(val)
            return

        dogcats_dir = find_dogcats_dir()
        config = load_config(dogcats_dir)
        if key not in config:
            echo_error(f"Key '{key}' not found in config")
            raise typer.Exit(1)
        val = config[key]
        if is_json():
            typer.echo(orjson.dumps({key: val}).decode())
        elif isinstance(val, list):
            typer.echo(", ".join(str(i) for i in val))  # type: ignore[reportUnknownArgumentType, reportUnknownVariableType]
        else:
            typer.echo(val)

    @config_app.command("unset")
    def config_unset(
        key: str = typer.Argument(
            ...,
            help="Configuration key to remove",
            autocompletion=complete_config_keys,
        ),
        local: bool = typer.Option(
            False,
            "--local",
            help="Remove from config.local.toml",
        ),
        global_: bool = typer.Option(
            False,
            "--global",
            help="Remove from ~/.config/dogcat/config.toml",
        ),
    ) -> None:
        """Remove a configuration value."""
        if local and global_:
            echo_error("--local and --global are mutually exclusive")
            raise typer.Exit(2)

        if global_:
            from dogcat.global_config import unset_global_config_value

            unset_global_config_value(key)
            typer.echo(f"Unset {key} (global)")
            return

        dogcats_dir = find_dogcats_dir()
        if local:
            config = load_local_config(dogcats_dir)
            if key in config:
                del config[key]
                save_local_config(dogcats_dir, config)
            typer.echo(f"Unset {key} (local)")
        else:
            config = load_shared_config(dogcats_dir)
            if key in config:
                del config[key]
                save_config(dogcats_dir, config)
            typer.echo(f"Unset {key}")

    @config_app.command("list")
    def config_list(
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """List all configuration values."""
        set_json(json_output)
        import orjson

        from dogcat.global_config import GLOBAL_CONFIG_KEYS, load_global_config_raw

        dogcats_dir = find_dogcats_dir()
        config = load_config(dogcats_dir)
        # Only merge in the global keys the runtime actually reads;
        # stray keys in the global file must not show up as effective.
        global_data = {
            k: v for k, v in load_global_config_raw().items() if k in GLOBAL_CONFIG_KEYS
        }
        # Local/shared config wins over global; merge for effective view.
        effective = {**global_data, **config}
        global_keys = set(global_data.keys())
        local_keys = set(load_local_config(dogcats_dir).keys())

        if is_json():
            typer.echo(orjson.dumps(effective, option=orjson.OPT_INDENT_2).decode())
        else:
            if not effective:
                typer.echo("No configuration values set.")
            else:
                for k, v in sorted(effective.items()):
                    if k in local_keys:
                        suffix = " (local)"
                    elif k in global_keys and k not in config:
                        suffix = " (global)"
                    elif k in global_keys:
                        suffix = " (shared, overrides global)"
                    else:
                        suffix = ""
                    if isinstance(v, list):
                        typer.echo(f"{k} = {', '.join(str(i) for i in v)}{suffix}")  # type: ignore[reportUnknownArgumentType, reportUnknownVariableType]
                    else:
                        typer.echo(f"{k} = {v}{suffix}")

    @config_app.command("keys")
    def config_keys(
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """List all available configuration keys and their descriptions."""
        set_json(json_output)
        import orjson

        if is_json():
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
