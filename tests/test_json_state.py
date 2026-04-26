"""Direct tests for the JSON-output flag and ``echo_error`` formatting.

The module is a process-wide singleton: a missed reset between
invocations leaks JSON mode into the next test (or worse, into a real
CLI run that didn't pass ``--json``). The stickiness rule (subcommand
``set_json(False)`` does NOT downgrade after a global ``True``) is
subtle and shapes every command's --json behaviour. (dogcat-r58w)
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import orjson
import pytest

from dogcat.cli._json_state import echo_error, is_json, reset_json, set_json

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture(autouse=True)
def _isolate_json_state() -> Generator[None, None, None]:
    """Reset the module-global flag before AND after each test.

    Without an explicit reset, leakage from another test would mask
    set_json/reset_json bugs (a "passing" test could be reading state
    set by an earlier test).
    """
    reset_json()
    yield
    reset_json()


class TestStickiness:
    """The set_json(True) flag persists until reset_json clears it."""

    def test_set_true_then_set_false_stays_on(self) -> None:
        """A subcommand passing False must not downgrade an enabled flag.

        Documented contract: after the global callback turns JSON on,
        a subcommand body that didn't receive --json calls
        ``set_json(False)`` — but that call must be a no-op.
        """
        set_json(True)
        assert is_json() is True
        set_json(False)
        assert is_json() is True

    def test_starts_off_by_default(self) -> None:
        """The fixture resets state — without ``set_json(True)`` we're off."""
        assert is_json() is False

    def test_reset_clears_after_set(self) -> None:
        """``reset_json`` is the only way to turn the flag off."""
        set_json(True)
        assert is_json() is True
        reset_json()
        assert is_json() is False

    def test_double_reset_is_idempotent(self) -> None:
        """Resetting an already-off flag stays off."""
        reset_json()
        reset_json()
        assert is_json() is False


class TestEchoError:
    """echo_error renders JSON or plain text depending on flag state."""

    def test_plain_mode_writes_error_prefix(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Off-mode wraps the message with the ``Error:`` prefix on stderr."""
        echo_error("something broke")
        captured = capsys.readouterr()
        assert "Error: something broke" in captured.err
        assert captured.out == ""

    def test_json_mode_writes_json_object(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """JSON mode writes a parseable ``{"error": ...}`` object on stderr."""
        set_json(True)
        echo_error("nope")
        captured = capsys.readouterr()
        # Must be valid JSON, not a free-form string.
        data = json.loads(captured.err.strip())
        assert data == {"error": "nope"}
        assert captured.out == ""

    def test_json_mode_payload_round_trips(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """``orjson`` is used to encode — payload must be exactly that shape."""
        set_json(True)
        msg = 'a "quoted" — é unicode message'
        echo_error(msg)
        captured = capsys.readouterr()
        # The exact bytes orjson would emit, modulo the trailing newline.
        expected = orjson.dumps({"error": msg}).decode() + "\n"
        assert captured.err == expected


class TestStateIsolation:
    """The fixture reset means each test starts clean."""

    def test_first_test_sets_flag(self) -> None:
        """Set the flag — the next test should still see it as off."""
        set_json(True)
        assert is_json() is True

    def test_second_test_sees_clean_state(self) -> None:
        """If the fixture didn't reset, this would inherit ``True``."""
        assert is_json() is False
