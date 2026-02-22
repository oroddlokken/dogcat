"""TUI dashboard command for dogcat CLI."""

from __future__ import annotations

import typer


def register(app: typer.Typer) -> None:
    """Register the TUI dashboard command."""

    @app.command("tui")
    def tui(
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Launch the interactive TUI dashboard."""
        from dogcat.cli._helpers import get_storage
        from dogcat.tui.dashboard import DogcatTUI

        storage = get_storage(dogcats_dir)
        tui_app = DogcatTUI(storage)
        tui_app.run()

    app.command(name="t", hidden=True)(tui)
