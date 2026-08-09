"""Feature flags registry for Dogcat.

Flags are checked via environment variables: DCAT_FEATURE_<NAME>=1
(also accepts 'true', 'yes', case-insensitive).

The FeatureFlag enum is where a flag gets registered. It is empty today, so
nothing in this module is reachable — see :class:`FeatureFlag`.
"""

from __future__ import annotations

import os
from enum import Enum

_TRUTHY_VALUES = frozenset({"1", "true", "yes"})


class FeatureFlag(str, Enum):
    """Registry of all feature flags — intentionally empty.

    The emptiness is a decision, not an oversight: dogcat-15vs removed the
    ``dcat guide`` copy that advertised flags and deliberately kept the enum
    with no members. So :func:`feature_enabled` is currently unreachable and
    ``dcat features`` always takes its empty branch.

    Add a member here to register a flag. Its value is the suffix in the env
    var name: ``DCAT_FEATURE_<VALUE>``.
    """


def _env_var_name(flag: FeatureFlag) -> str:
    """Return the environment variable name for a flag."""
    return f"DCAT_FEATURE_{flag.value}"


def feature_enabled(flag: FeatureFlag, *, default: bool = False) -> bool:
    """Check whether *flag* is enabled.

    Looks up ``DCAT_FEATURE_<NAME>`` in the environment.
    Accepts ``1``, ``true``, or ``yes`` (case-insensitive) as enabled.
    Falls back to *default* when the variable is unset or empty.
    """
    raw = os.environ.get(_env_var_name(flag), "").strip().lower()
    if not raw:
        return default
    return raw in _TRUTHY_VALUES
