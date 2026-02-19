"""Web server commands for dogcat CLI."""

from __future__ import annotations

import typer

from ._helpers import SortedGroup

web_app = typer.Typer(
    name="web",
    help="Web server for dogcat.",
    no_args_is_help=True,
    cls=SortedGroup,
)

DEFAULT_PORT = 48042


def register(app: typer.Typer) -> None:
    """Register the web command group."""
    app.add_typer(web_app)

    @web_app.command("propose")
    def propose(
        host: str = typer.Option("127.0.0.1", help="Host to bind to"),
        port: int = typer.Option(DEFAULT_PORT, help="Port to listen on"),
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
        try:
            import uvicorn
        except ImportError:
            typer.echo(
                "Error: web dependencies not installed. "
                "Install with: uv pip install 'dogcat[web]'",
                err=True,
            )
            raise typer.Exit(1) from None

        from pathlib import Path

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

        # Resolve allow_creating_namespaces: CLI flag > config > default (True)
        if allow_creating_namespaces is None:
            config = load_config(resolved_dir)
            resolved_allow = bool(config.get("allow_creating_namespaces", False))
        else:
            resolved_allow = allow_creating_namespaces

        fastapi_app = create_app(
            dogcats_dir=resolved_dir,
            namespace=namespace,
            allow_creating_namespaces=resolved_allow,
        )

        typer.echo(f"dogcat propose → http://{host}:{port}")
        uvicorn.run(fastapi_app, host=host, port=port, log_level="warning")
