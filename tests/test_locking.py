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
    """
    monkeypatch.setenv(LOCK_TIMEOUT_ENV_VAR, "0.2")
    lock_path = tmp_path / ".issues.lock"

    ctx = multiprocessing.get_context("fork")
    started = ctx.Event()
    proc = ctx.Process(
        target=_hold_lock_and_signal,
        args=(str(lock_path), started, 5.0),
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
    """DCAT_LOCK_TIMEOUT_SECS overrides the default wait."""
    monkeypatch.setenv(LOCK_TIMEOUT_ENV_VAR, "0.1")
    lock_path = tmp_path / ".issues.lock"

    ctx = multiprocessing.get_context("fork")
    started = ctx.Event()
    proc = ctx.Process(
        target=_hold_lock_and_signal,
        args=(str(lock_path), started, 5.0),
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
        # Should fail far faster than the default 30s.
        assert elapsed < 2.0, f"Expected fast timeout, took {elapsed:.2f}s"
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
