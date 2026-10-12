"""Shared helpers for tests that drive Textual worker threads."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from textual.app import App
    from textual.geometry import Size
    from textual.pilot import Pilot


async def wait_for_workers(app: App[Any]) -> None:
    """Await every running worker on ``app``.

    Textual types ``wait_for_complete`` over ``Worker[Unknown]``, so pyright
    reports a partially unknown member at each call site. Routing every wait
    through here keeps that one suppression out of the tests themselves.

    Wrap the call in ``asyncio.wait_for`` when a test holds the store lock —
    an unbounded wait there hangs the suite instead of failing it.
    """
    await app.workers.wait_for_complete()  # pyright: ignore[reportUnknownMemberType]


async def wait_for_app_size(pilot: Pilot[Any], size: Size, *, tries: int = 50) -> None:
    """Pause until the app has handled a posted ``Resize``.

    ``Pilot.pause`` returns once the event loop goes idle, which does not mean
    a posted message has been processed, and ``App.size`` only changes when
    ``App._on_resize`` handles one. Reading the size after a single pause
    passes on a fast machine and loses the race on a loaded CI runner
    (dogcat-1mvy).
    """
    for _ in range(tries):
        await pilot.pause()
        if pilot.app.size == size:
            return
    msg = f"resize not processed: app.size is {pilot.app.size}, expected {size}"
    raise AssertionError(msg)


async def wait_until(
    pilot: Pilot[Any],
    condition: Callable[[], bool],
    what: str,
    *,
    tries: int = 50,
) -> None:
    """Pause until ``condition()`` holds, failing after ``tries`` pauses.

    A worker finishing does not mean the messages it posts have been handled:
    a save hops through ``_SaveComplete`` and ``Saved`` before the app's
    handler runs, and that handler awaits a re-render before touching split
    mode. One pause after ``wait_for_workers`` loses that race on a slow
    runner (dogcat-1nav).
    """
    for _ in range(tries):
        await pilot.pause()
        if condition():
            return
    msg = f"timed out waiting for {what}"
    raise AssertionError(msg)
