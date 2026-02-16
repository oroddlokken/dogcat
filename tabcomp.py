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
# ]
# ///

"""Dev utility: show what tab completion would produce for a given dcat command.

Usage:
    python tabcomp.py "dcat show "
    python tabcomp.py "dcat update --status "
    python tabcomp.py "dcat show dog"
    python tabcomp.py "dcat "

A trailing space means "complete the next argument".
No trailing space means "complete the current partial word".
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path


def _parse_zsh_completions(raw: str) -> list[tuple[str, str]]:
    """Parse zsh completion output into (value, description) pairs.

    Zsh format: _arguments '*: :(("val":"desc" "val2":"desc2" ...))'
    """
    return [
        (match.group(1), match.group(2))
        for match in re.finditer(r'"([^"]*?)":"([^"]*?)"', raw)
    ]


def main() -> None:  # noqa: D103
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        raise SystemExit(0)

    cmd = sys.argv[1]

    # Use the dcat.py script in the same directory so we don't need an install.
    # The prog_name seen by Typer is "dcat.py", so the complete env var
    # becomes _DCAT.PY_COMPLETE (Typer only replaces hyphens, not dots).
    dcat_script = Path(__file__).resolve().parent / "dcat.py"
    exe = [sys.executable, str(dcat_script)]

    result = subprocess.run(
        exe,
        env={
            **os.environ,
            "_TYPER_COMPLETE_ARGS": cmd,
            "_DCAT.PY_COMPLETE": "complete_zsh",
        },
        capture_output=True,
        text=True,
    )

    stdout = result.stdout.strip()
    if not stdout:
        print("(no completions)")
        raise SystemExit(0)

    pairs = _parse_zsh_completions(stdout)
    if pairs:
        max_val = max(len(v) for v, _ in pairs)
        col_w = min(max_val + 2, 40)
        print(f"{'VALUE':<{col_w}} DESCRIPTION")
        print("-" * (col_w + 40))
        for value, desc in pairs:
            print(f"{value:<{col_w}} {desc}")
        print(f"\n({len(pairs)} completions)")
    else:
        # Fallback: print raw output
        print(stdout)

    if result.stderr:
        print(f"\nstderr: {result.stderr}", file=sys.stderr)


if __name__ == "__main__":
    main()
