#!/usr/bin/env -S uv run --script
#
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "typer",
#   "pydantic",
#   "rich",
#   "orjson",
#   "textual",
#   "watchdog",
#   "tomli",
#   "tomli_w",
#   "fastapi>=0.115.0",
#   "uvicorn[standard]>=0.30.0",
#   "jinja2>=3.1.0",
#   "python-multipart>=0.0.9",
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
