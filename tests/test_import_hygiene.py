"""Guards on what a plain CLI startup is allowed to import.

`cli/__init__.py` imports every `_cmd_*` module eagerly, so a module-scope
import in any one command module is paid by every `dcat` invocation. rich is
the expensive one — importing it costs roughly a sixth of `import dogcat.cli`
— and only `dcat chart` and `dcat config --table` need it.
"""

from __future__ import annotations

import subprocess
import sys

_PROBE = (
    "import sys; import dogcat.cli; "
    "print(sorted(m for m in sys.modules if m.split('.')[0] == 'rich'))"
)


def test_cli_import_does_not_pull_in_rich() -> None:
    """Importing dogcat.cli must not import rich (dogcat-2mil)."""
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "[]", (
        f"dogcat.cli pulled in rich modules: {result.stdout.strip()}"
    )
