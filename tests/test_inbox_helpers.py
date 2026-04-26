"""Direct tests for ``InboxStorage.get_file_path`` and ``reload``.

These small public helpers are exercised indirectly elsewhere; the
direct tests below lock the contract so a refactor that renames the
backing path attribute can't slip through.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dogcat.inbox import InboxStorage
from dogcat.models import Proposal

if TYPE_CHECKING:
    from pathlib import Path


def test_get_file_path_points_at_inbox_jsonl(tmp_path: Path) -> None:
    """get_file_path returns the inbox.jsonl under the dogcats dir."""
    dogcats = tmp_path / ".dogcats"
    dogcats.mkdir()
    inbox = InboxStorage(dogcats_dir=str(dogcats))
    path = inbox.get_file_path()
    assert path.name == "inbox.jsonl"
    assert path.parent == dogcats


def test_reload_picks_up_external_writes(tmp_path: Path) -> None:
    """reload() re-reads disk so concurrent writers become visible."""
    dogcats = tmp_path / ".dogcats"
    dogcats.mkdir()
    inbox_a = InboxStorage(dogcats_dir=str(dogcats))
    inbox_b = InboxStorage(dogcats_dir=str(dogcats))

    # Add a proposal via inbox_a; inbox_b doesn't see it without reload.
    inbox_a.create(Proposal(id="abcd", title="From A"))
    assert inbox_b.get("dc-inbox-abcd") is None

    inbox_b.reload()
    reloaded = inbox_b.get("dc-inbox-abcd")
    assert reloaded is not None
    assert reloaded.title == "From A"
