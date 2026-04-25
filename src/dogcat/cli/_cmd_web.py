"""Web server commands for dogcat CLI."""

from __future__ import annotations

import os

import typer

from dogcat.constants import (
    WEB_DEFAULT_HOST,
    WEB_DEFAULT_PORT,
    WEB_HOST_ENV_VAR,
    WEB_PORT_ENV_VAR,
)

from ._helpers import SortedGroup

web_app = typer.Typer(
    name="web",
    help="Web server for dogcat.",
    no_args_is_help=True,
    cls=SortedGroup,
)


def _env_default_port() -> int:
    raw = os.environ.get(WEB_PORT_ENV_VAR)
    if not raw:
        return WEB_DEFAULT_PORT
    try:
        return int(raw)
    except ValueError:
        typer.echo(
            f"Warning: {WEB_PORT_ENV_VAR}={raw!r} is not an integer; "
            f"falling back to {WEB_DEFAULT_PORT}",
            err=True,
        )
        return WEB_DEFAULT_PORT


def register(app: typer.Typer) -> None:
    """Register the web command group."""
    app.add_typer(web_app)

    @web_app.command("propose")
    def propose(
        host: str = typer.Option(
            os.environ.get(WEB_HOST_ENV_VAR) or WEB_DEFAULT_HOST,
            help=f"Host to bind to (env: {WEB_HOST_ENV_VAR})",
        ),
        port: int = typer.Option(
            _env_default_port(),
            help=f"Port to listen on (env: {WEB_PORT_ENV_VAR})",
        ),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
        namespace: str = typer.Option(
            None, help="Override namespace (auto-detected by default)"
        ),
        allow_creating_namespaces: bool | None = typer.Option(
            None,
            "--allow-creating-namespaces/--disable-creating-namespaces",
            help="Allow or disallow creating new namespaces (overrides config)",
        ),
    ) -> None:
        """Start the proposal submission web server."""
        # Probe ALL web-extra deps up front so a missing jinja2 /
        # python-multipart / fastapi prints the same friendly install
        # hint as a missing uvicorn. Without this, a partial install
        # would either leak a raw ModuleNotFoundError or start the
        # server and 500 on every POST. (dogcat-5n9q)
        import importlib

        missing: list[str] = []
        for module in ("uvicorn", "fastapi", "jinja2", "multipart"):
            try:
                importlib.import_module(module)
            except ImportError:  # noqa: PERF203
                missing.append(module)
        if missing:
            typer.echo(
                "Error: web dependencies not installed: "
                + ", ".join(missing)
                + ".\nInstall with: uv pip install 'dogcat[web]'",
                err=True,
            )
            raise typer.Exit(1)

        from pathlib import Path

        import uvicorn

        from dogcat.cli._helpers import find_dogcats_dir
        from dogcat.config import load_config
        from dogcat.web.propose import create_app

        resolved_dir = find_dogcats_dir(dogcats_dir)

        if not Path(resolved_dir).is_dir():
            typer.echo(
                "Error: dogcat is not initialized. Run 'dcat init' first.",
                err=True,
            )
            raise typer.Exit(1)

        # Resolve allow_creating_namespaces: CLI flag > config > default (False).
        # Use ``is True`` so a stray string in config.toml ("false"/"no"/"0")
        # cannot silently flip this on. The config loader also validates
        # the type and drops non-bools, but defending here makes the
        # intent explicit. (dogcat-22t5)
        if allow_creating_namespaces is None:
            config = load_config(resolved_dir)
            resolved_allow = config.get("allow_creating_namespaces") is True
        else:
            resolved_allow = allow_creating_namespaces

        fastapi_app = create_app(
            dogcats_dir=resolved_dir,
            namespace=namespace,
            allow_creating_namespaces=resolved_allow,
        )

        if host in {"0.0.0.0", "::"}:
            typer.echo(
                f"warning: binding to {host} exposes the propose form to "
                "every network interface. The CSRF + nonce defenses cap "
                "abuse but do not authenticate the submitter — bind to "
                "127.0.0.1 unless you intentionally want a multi-host "
                "endpoint. (dogcat-2icd)",
                err=True,
            )

        typer.echo(f"dogcat propose → http://{host}:{port}")
        uvicorn.run(fastapi_app, host=host, port=port, log_level="warning")
