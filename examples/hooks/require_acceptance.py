#!/usr/bin/env python3
"""Require acceptance criteria for in-progress issues in a write batch."""

import json
import sys
from typing import cast


def main() -> int:
    """Validate each JSONL record and name the rule that failed.

    dcat shows this hook's stderr to the user, so each refusal says which
    rule failed and which issue broke it, without echoing the record.
    """
    try:
        for line in sys.stdin:
            parsed: object = json.loads(line)
            if not isinstance(parsed, dict):
                print("require_acceptance: input is not JSONL records", file=sys.stderr)
                return 1
            record = cast("dict[str, object]", parsed)
            if (
                record.get("record_type") != "issue"
                or record.get("status") != "in_progress"
            ):
                continue
            acceptance = record.get("acceptance")
            if not isinstance(acceptance, str) or not acceptance.strip():
                issue_id = f"{record.get('namespace')}-{record.get('id')}"
                print(
                    f"require_acceptance: {issue_id} is in_progress "
                    "without acceptance criteria",
                    file=sys.stderr,
                )
                return 10
    except (ValueError, UnicodeError):
        print("require_acceptance: input is not JSONL records", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
