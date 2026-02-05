#!/usr/bin/env -S uv run --script
#
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "typer",
#   "pydantic",
#   "rich",
#   "orjson",
#   "watchdog",
#   "toml",
# ]
# ///

"""Entry point for Dogcat CLI."""

import sys
from pathlib import Path

# Add src directory to Python path for proper imports
src_path = Path(__file__).resolve().parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from dogcat.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
