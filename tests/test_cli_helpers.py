"""Direct tests for ``dogcat.cli._helpers.apply_to_each``.

``apply_to_each`` powers every multi-id CLI op
(``dcat close A B C``, ``dcat reopen``, ``dcat inbox close/delete/reject``).
The error-aggregation contract — *continue on error, return True iff
any op raised, format messages as ``verb id: exc``* — is core behaviour
that previously had no regression test. (dogcat-4uez)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from dogcat.cli._helpers import apply_to_each
from dogcat.cli._json_state import reset_json

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture(autouse=True)
def _reset_json_state() -> Generator[None, None, None]:
    """Keep the global JSON flag isolated across tests.

    ``apply_to_each`` calls ``echo_error``, which checks the module-wide
    JSON flag. A leaked ``True`` from another test would change the
    error format (``{"error": ...}`` instead of ``Error: ...``) and
    make assertions on stderr brittle.
    """
    reset_json()
    yield
    reset_json()


class TestApplyToEach:
    """Cover the multi-id error-aggregation contract."""

    def test_all_success_returns_false(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """No raises means returns False with no error output."""
        seen: list[str] = []

        def op(issue_id: str) -> None:
            seen.append(issue_id)

        assert apply_to_each(["a", "b", "c"], op, verb="close") is False
        assert seen == ["a", "b", "c"]
        captured = capsys.readouterr()
        assert captured.err == ""

    def test_empty_id_list_returns_false_silently(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """An empty ids list is a no-op: False, nothing printed."""
        called = {"n": 0}

        def op(_: str) -> None:
            called["n"] += 1

        assert apply_to_each([], op, verb="close") is False
        assert called["n"] == 0
        assert capsys.readouterr().err == ""

    def test_mid_list_failure_continues_to_remaining_ids(self) -> None:
        """A mid-list raise must not abort iteration.

        The whole point of ``apply_to_each`` is that closing 5 issues
        where #3 is broken still closes the other 4. Aborting on the
        first error would silently leave #4 and #5 untouched.
        """
        seen: list[str] = []

        def op(issue_id: str) -> None:
            seen.append(issue_id)
            if issue_id == "b":
                msg = "boom"
                raise ValueError(msg)

        result = apply_to_each(["a", "b", "c", "d"], op, verb="close")
        assert result is True
        # Iteration continued past the failure to ``c`` and ``d``.
        assert seen == ["a", "b", "c", "d"]

    def test_error_message_format(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Error format is ``Error: <verb> <id>: <exception>``."""

        def op(issue_id: str) -> None:
            msg = f"id was {issue_id}"
            raise ValueError(msg)

        apply_to_each(["xyz"], op, verb="reopen")
        err = capsys.readouterr().err
        # Plain mode prefix from echo_error + verb-prefixed apply_to_each shape.
        assert "Error: reopen xyz: id was xyz" in err

    def test_returns_true_iff_any_raised(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Return is True iff at least one op raised — not "all ops"."""

        def op(issue_id: str) -> None:
            if issue_id == "bad":
                msg = "nope"
                raise RuntimeError(msg)

        # Single failure in a long list still flips the return.
        assert apply_to_each(["ok1", "ok2", "bad", "ok3"], op, verb="x") is True

        capsys.readouterr()  # flush
        # All-success.
        assert apply_to_each(["ok1", "ok2"], op, verb="x") is False

    def test_aggregates_multiple_errors(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Every failing id produces its own ``echo_error`` line."""

        def op(issue_id: str) -> None:
            msg = f"failed {issue_id}"
            raise ValueError(msg)

        result = apply_to_each(["a", "b", "c"], op, verb="delete")
        assert result is True

        err_lines = [
            line for line in capsys.readouterr().err.splitlines() if line.strip()
        ]
        assert len(err_lines) == 3
        assert "delete a" in err_lines[0]
        assert "delete b" in err_lines[1]
        assert "delete c" in err_lines[2]
