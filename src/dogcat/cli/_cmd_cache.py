"""Cache management commands for dogcat CLI."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import typer

from ._helpers import SortedGroup

cache_app = typer.Typer(
    help="Manage the dogcat local cache.",
    no_args_is_help=True,
    cls=SortedGroup,
)


def _get_cache_dir() -> Path:
    """Return the dogcat cache directory ($XDG_CACHE_HOME/dogcat)."""
    xdg_cache = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(xdg_cache) / "dogcat"


def register(app: typer.Typer) -> None:
    """Register cache commands."""
    app.add_typer(cache_app, name="cache")

    @cache_app.command("clean")
    def cache_clean(
        all_entries: bool = typer.Option(
            False,
            "--all",
            help="Remove all cache entries, not just stale ones.",
        ),
    ) -> None:
        """Remove stale cache entries (or all with --all).

        By default, only removes entries whose originating .dogcats directory
        no longer exists. Use --all to wipe the entire cache.
        """
        cache_dir = _get_cache_dir()
        if not cache_dir.exists():
            typer.echo("Cache directory does not exist, nothing to clean.")
            return

        entries = [p for p in cache_dir.iterdir() if p.is_dir()]
        if not entries:
            typer.echo("Cache is already empty.")
            return

        removed = 0
        for entry in entries:
            if all_entries:
                shutil.rmtree(entry)
                removed += 1
            else:
                # Check if the origin marker exists and points to a valid path
                origin_file = entry / ".origin"
                if origin_file.exists():
                    origin_path = origin_file.read_text().strip()
                    if Path(origin_path).is_dir():
                        continue
                # No origin marker or stale path — remove
                shutil.rmtree(entry)
                removed += 1

        if removed:
            typer.echo(f"Removed {removed} cache entr{'y' if removed == 1 else 'ies'}.")
        else:
            typer.echo("No stale cache entries found.")

    @cache_app.command("list")
    def cache_list() -> None:
        """List cache entries and their origin projects."""
        cache_dir = _get_cache_dir()
        if not cache_dir.exists():
            typer.echo("Cache directory does not exist.")
            return

        entries = sorted(p for p in cache_dir.iterdir() if p.is_dir())
        if not entries:
            typer.echo("Cache is empty.")
            return

        for entry in entries:
            origin_file = entry / ".origin"
            if origin_file.exists():
                origin = origin_file.read_text().strip()
                exists = Path(origin).is_dir()
                status = "" if exists else " (stale)"
                typer.echo(f"  {entry.name}  {origin}{status}")
            else:
                typer.echo(f"  {entry.name}  (unknown origin)")
