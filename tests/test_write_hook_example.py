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
    """Only in_progress issue records are checked; everything else passes."""
    result = run_hook(
        {"record_type": "event", "status": "in_progress"},
        {"record_type": "dependency"},
        {"record_type": "issue", "status": "draft"},
        {"record_type": "issue", "status": "in_progress", "acceptance": "Works"},
    )
    assert result.returncode == 0


def test_missing_acceptance_in_any_issue_rejects_batch() -> None:
    """One bad issue refuses the batch, named by id without echoing the record."""
    result = run_hook(
        {"record_type": "issue", "status": "in_progress", "acceptance": "Works"},
        {
            "record_type": "issue",
            "namespace": "demo",
            "id": "a1b2",
            "status": "in_progress",
            "acceptance": "  ",
            "description": "private text",
        },
    )
    assert result.returncode == 10
    assert not result.stdout
    assert "demo-a1b2" in result.stderr
    assert "acceptance criteria" in result.stderr
    assert "private text" not in result.stderr


def test_malformed_input_fails_without_printing_record() -> None:
    """Unparseable input is refused without echoing what was read."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input='{"secret":',
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert not result.stdout
    assert "not JSONL" in result.stderr
    assert "secret" not in result.stderr
