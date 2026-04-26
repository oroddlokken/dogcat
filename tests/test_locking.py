"""Tests for the advisory file lock used across storage, inbox, and event log."""

from __future__ import annotations

import multiprocessing
import time
from pathlib import Path

import pytest

from dogcat.locking import (
    DEFAULT_LOCK_TIMEOUT_SECS,
    LOCK_TIMEOUT_ENV_VAR,
    advisory_file_lock,
)


def test_default_timeout_constant_is_positive() -> None:
    """The configured default timeout must be positive."""
    assert DEFAULT_LOCK_TIMEOUT_SECS > 0


def _hold_lock_and_signal(lock_path: str, started: object, hold_secs: float) -> None:
    """Acquire the lock in a child process, signal, then sleep."""
    with advisory_file_lock(Path(lock_path)):
        started.set()  # type: ignore[attr-defined]
        time.sleep(hold_secs)


def test_timeout_raises_runtimeerror_with_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the lock is held, a fresh acquirer times out with a clear error.

    Uses a multiprocessing child to actually take fcntl.LOCK_EX (advisory
    locks are per-process, so a second acquire in the same process from a
    threading would not block).

    Timeout is set to 1.0s — large enough to be stable under ``-n 8`` CI
    where fork/IPC latency can exceed the contender's deadline before
    the child's ``started.set()`` is observed, while still well under
    the 30s default so the test stays fast. (dogcat-1ypi)
    """
    monkeypatch.setenv(LOCK_TIMEOUT_ENV_VAR, "1.0")
    lock_path = tmp_path / ".issues.lock"

    ctx = multiprocessing.get_context("fork")
    started = ctx.Event()
    proc = ctx.Process(
        target=_hold_lock_and_signal,
        args=(str(lock_path), started, 10.0),
    )
    proc.start()
    try:
        assert started.wait(timeout=5), "child failed to acquire lock"

        # The error message should name the lock path so the user knows
        # where to investigate a stuck holder.
        with (
            pytest.raises(RuntimeError, match=str(lock_path)) as excinfo,
            advisory_file_lock(lock_path),
        ):
            pass
        assert "Timed out" in str(excinfo.value)
    finally:
        proc.terminate()
        proc.join(timeout=5)


def test_env_var_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """DCAT_LOCK_TIMEOUT_SECS overrides the default wait.

    Asserts both an upper bound (much faster than the 30s default) and
    a lower bound (the contender actually waited at least the configured
    timeout, not less). The lower bound prevents a regression where the
    timeout calculation collapses to zero. (dogcat-1ypi)
    """
    configured_timeout = 1.0
    monkeypatch.setenv(LOCK_TIMEOUT_ENV_VAR, str(configured_timeout))
    lock_path = tmp_path / ".issues.lock"

    ctx = multiprocessing.get_context("fork")
    started = ctx.Event()
    proc = ctx.Process(
        target=_hold_lock_and_signal,
        args=(str(lock_path), started, 10.0),
    )
    proc.start()
    try:
        assert started.wait(timeout=5), "child failed to acquire lock"
        start = time.monotonic()
        with (
            pytest.raises(RuntimeError, match="Timed out"),
            advisory_file_lock(lock_path),
        ):
            pass
        elapsed = time.monotonic() - start
        # Must wait at least the configured timeout — minus a small
        # tolerance for the polling cadence rounding down — so the
        # configured timeout is actually being honored.
        assert elapsed >= configured_timeout - 0.1, (
            f"Timed out before configured {configured_timeout}s: {elapsed:.2f}s"
        )
        # Should still fail far faster than the 30s default.
        assert elapsed < 5.0, f"Expected fast timeout, took {elapsed:.2f}s"
    finally:
        proc.terminate()
        proc.join(timeout=5)


def test_lock_acquired_when_uncontended(tmp_path: Path) -> None:
    """An uncontended lock acquisition completes immediately."""
    lock_path = tmp_path / ".issues.lock"
    with advisory_file_lock(lock_path):
        assert lock_path.exists()


def test_invalid_env_var_falls_back_to_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-numeric env value is ignored and the default is used."""
    monkeypatch.setenv(LOCK_TIMEOUT_ENV_VAR, "not-a-number")
    lock_path = tmp_path / ".issues.lock"
    # Should not raise even though env value is bogus.
    with advisory_file_lock(lock_path):
        pass


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("inf", 30.0),
        ("Infinity", 30.0),
        ("-inf", 30.0),
        ("nan", 30.0),
        ("0", 30.0),
        ("-1", 30.0),
        ("60", 60.0),
        ("0.5", 0.5),
    ],
)
def test_resolve_timeout_clamps_non_finite_and_non_positive(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: float
) -> None:
    """Non-finite / non-positive env values fall back to the default.

    Regression for dogcat-1z5u: ``inf`` slipped past the ``> 0`` check
    and disabled the stale-lock timeout. ``isfinite`` now blocks all
    of ``inf``, ``-inf``, ``nan`` (and the textual aliases that
    ``float`` accepts).
    """
    from dogcat.locking import _resolve_timeout

    monkeypatch.setenv(LOCK_TIMEOUT_ENV_VAR, raw)
    assert _resolve_timeout() == expected
