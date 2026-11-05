#!/usr/bin/env python3
"""Require acceptance criteria for in-progress issues in a write batch."""

import json
import sys
from typing import cast


def main() -> int:
    """Validate each JSONL record without echoing its contents."""
    try:
        for line in sys.stdin:
            parsed: object = json.loads(line)
            if not isinstance(parsed, dict):
                return 1
            record = cast("dict[str, object]", parsed)
            if (
                record.get("record_type") != "issue"
                or record.get("status") != "in_progress"
            ):
                continue
            acceptance = record.get("acceptance")
            if not isinstance(acceptance, str) or not acceptance.strip():
                return 10
    except (ValueError, UnicodeError):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
