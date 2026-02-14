"""Feature flags command for dogcat CLI."""

from __future__ import annotations

import orjson
import typer

from dogcat.feature_flags import FeatureFlag, _env_var_name, feature_enabled

from ._json_state import is_json_output


def register(app: typer.Typer) -> None:
    """Register feature flag commands."""

    @app.command("features")
    def features(
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """List all feature flags with their env var and current status."""
        if not list(FeatureFlag):
            typer.echo("No feature flags defined")
            return

        if is_json_output(json_output):
            output = [
                {
                    "flag": flag.value,
                    "env_var": _env_var_name(flag),
                    "enabled": feature_enabled(flag),
                }
                for flag in FeatureFlag
            ]
            typer.echo(orjson.dumps(output).decode())
        else:
            for flag in FeatureFlag:
                env_var = _env_var_name(flag)
                enabled = feature_enabled(flag)
                status = (
                    typer.style("enabled", fg="green")
                    if enabled
                    else typer.style("disabled", fg="bright_black")
                )
                typer.echo(f"  {flag.value:<20s} {env_var:<40s} {status}")
