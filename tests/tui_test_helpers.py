"""Shared helpers for tests that drive Textual worker threads."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from textual.app import App


async def wait_for_workers(app: App[Any]) -> None:
    """Await every running worker on ``app``.

    Textual types ``wait_for_complete`` over ``Worker[Unknown]``, so pyright
    reports a partially unknown member at each call site. Routing every wait
    through here keeps that one suppression out of the tests themselves.

    Wrap the call in ``asyncio.wait_for`` when a test holds the store lock —
    an unbounded wait there hangs the suite instead of failing it.
    """
    await app.workers.wait_for_complete()  # pyright: ignore[reportUnknownMemberType]
