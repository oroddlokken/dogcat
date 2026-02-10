"""TUI dashboard command for dogcat CLI (feature-gated)."""

from __future__ import annotations

import typer

from dogcat.feature_flags import FeatureFlag, feature_enabled


def register(app: typer.Typer) -> None:
    """Register the TUI command only when DCAT_FEATURE_TUI is enabled."""
    if not feature_enabled(FeatureFlag.TUI):
        return

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
