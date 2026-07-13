"""Shared health-check record for doctor and git-integration checks.

Both the ``dcat doctor`` report and the ``dcat git check`` /
``dcat prime --opinionated`` git-integration checks describe the same
thing — one named row with a pass/fail state, a fix hint, and optional
metadata. Sharing :class:`HealthCheck` gives every renderer typed
attribute access (so pyright catches ``check.passecd`` typos) instead of
untyped ``dict[str, dict[str, object]]`` string-key lookups. (dogcat-483i)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class HealthCheck:
    """One row in a health report (doctor or git-integration).

    The optional fields default to ``None`` / ``False`` so a passing check
    only has to supply ``description`` and ``passed``; renderers branch on
    ``optional`` to decide whether a failure is an error or a warning.
    """

    description: str
    passed: bool
    fix: str | None = None
    fail_description: str | None = None
    optional: bool = False
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a flat dict, omitting unset optional fields."""
        out: dict[str, Any] = {
            "description": self.description,
            "passed": self.passed,
        }
        if self.fix is not None:
            out["fix"] = self.fix
        if self.fail_description is not None:
            out["fail_description"] = self.fail_description
        if self.optional:
            out["optional"] = True
        if self.note is not None:
            out["note"] = self.note
        return out


@dataclass
class HealthReport:
    """Accumulator for health checks plus the all-passed roll-up."""

    checks: dict[str, HealthCheck] = field(default_factory=dict[str, "HealthCheck"])
    all_passed: bool = True

    def add(self, name: str, check: HealthCheck) -> None:
        """Record a check and roll up its pass state.

        Optional checks never fail the overall report (they render as a
        warning instead of an error) — the roll-up only flips when a
        non-optional check fails.
        """
        self.checks[name] = check
        if not check.passed and not check.optional:
            self.all_passed = False
