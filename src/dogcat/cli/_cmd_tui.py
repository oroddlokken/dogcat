"""TUI dashboard command for dogcat CLI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._list_options import (
    DogcatsDirOpt,
)

if TYPE_CHECKING:
    import typer


def register(app: typer.Typer) -> None:
    """Register the TUI dashboard command."""

    @app.command("tui")
    def tui(
        dogcats_dir: DogcatsDirOpt = ".dogcats",
    ) -> None:
        """Launch the interactive TUI dashboard."""
        from dogcat.cli._helpers import get_storage
        from dogcat.tui.dashboard import DogcatTUI

        storage = get_storage(dogcats_dir)
        tui_app = DogcatTUI(storage)
        tui_app.run()

    app.command(name="t", hidden=True)(tui)
