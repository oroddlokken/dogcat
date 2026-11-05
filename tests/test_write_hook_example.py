"""Exercise the standalone write hook as a subprocess."""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "examples/hooks/require_acceptance.py"


def run_hook(*records: object) -> subprocess.CompletedProcess[str]:
    payload = "".join(json.dumps(record) + "\n" for record in records)
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=payload,
        text=True,
        capture_output=True,
        check=False,
    )


def test_mixed_records_and_draft_are_allowed() -> None:
    result = run_hook(
        {"record_type": "event", "status": "in_progress"},
        {"record_type": "dependency"},
        {"record_type": "issue", "status": "draft"},
        {"record_type": "issue", "status": "in_progress", "acceptance": "Works"},
    )
    assert result.returncode == 0


def test_missing_acceptance_in_any_issue_rejects_batch() -> None:
    result = run_hook(
        {"record_type": "issue", "status": "in_progress", "acceptance": "Works"},
        {"record_type": "issue", "status": "in_progress", "acceptance": "  "},
    )
    assert result.returncode == 10
    assert not result.stdout
    assert not result.stderr


def test_malformed_input_fails_without_printing_record() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input='{"secret":',
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert not result.stdout
    assert not result.stderr
