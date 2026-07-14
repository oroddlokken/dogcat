"""Tests for dogcat._persistence.compact_snapshot — the compaction writer.

This is the ``_write`` closure formerly nested inside
``JSONLStorage._save_locked``, hoisted to a module-level free function
(dogcat-63tf) so the rewrite body can be exercised directly with an in-memory
buffer and a fixture source file — no storage instance, no file lock.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import orjson

from dogcat._persistence import compact_snapshot
from dogcat.models import (
    Dependency,
    DependencyType,
    Issue,
    IssueType,
    Link,
    LinkType,
    Status,
    classify_record,
)

if TYPE_CHECKING:
    from pathlib import Path

_TS = datetime(2026, 7, 14, 12, 0, 0, tzinfo=timezone.utc)


def _issue(issue_id: str, namespace: str = "dc", title: str = "T") -> Issue:
    return Issue(
        id=issue_id,
        title=title,
        namespace=namespace,
        status=Status.OPEN,
        issue_type=IssueType.TASK,
        created_at=_TS,
        updated_at=_TS,
    )


def _dep(a: str, b: str) -> Dependency:
    return Dependency(
        issue_id=a,
        depends_on_id=b,
        dep_type=DependencyType.BLOCKS,
        created_at=_TS,
        created_by="alice",
    )


def _link(a: str, b: str) -> Link:
    return Link(
        from_id=a,
        to_id=b,
        link_type=LinkType.RELATES_TO,
        created_at=_TS,
        created_by="alice",
    )


def _event(issue_id: str, event_type: str = "updated") -> bytes:
    return orjson.dumps(
        {
            "record_type": "event",
            "event_type": event_type,
            "issue_id": issue_id,
            "timestamp": _TS.isoformat(),
            "by": "alice",
            "changes": {},
        }
    )


def _lines(buf: io.BytesIO) -> list[dict[str, object]]:
    return [orjson.loads(ln) for ln in buf.getvalue().splitlines() if ln.strip()]


class TestCompactSnapshotContent:
    """The snapshot serializes current state and returns an accurate count."""

    def test_writes_issues_deps_links_and_counts(self, tmp_path: Path) -> None:
        """Issues, then deps, then links are emitted; count matches lines."""
        source = tmp_path / "issues.jsonl"
        source.write_bytes(b"")  # exists but has no events
        buf = io.BytesIO()

        count = compact_snapshot(
            buf,
            issues=[_issue("a"), _issue("b")],
            dependencies=[_dep("dc-a", "dc-b")],
            links=[_link("dc-a", "dc-b")],
            source=source,
        )

        records = _lines(buf)
        assert count == 4  # noqa: PLR2004
        assert len(records) == 4  # noqa: PLR2004
        kinds = [classify_record(r) for r in records]
        # Emission order: issues, then dependencies, then links.
        assert kinds == ["issue", "issue", "dependency", "link"]

    def test_empty_state_and_missing_source(self, tmp_path: Path) -> None:
        """No records and a nonexistent source yields an empty, zero-count file."""
        buf = io.BytesIO()
        count = compact_snapshot(
            buf,
            issues=[],
            dependencies=[],
            links=[],
            source=tmp_path / "does-not-exist.jsonl",
        )
        assert count == 0
        assert buf.getvalue() == b""


class TestEventPreservation:
    """Event records from the source file survive compaction."""

    def test_events_are_copied_after_data_records(self, tmp_path: Path) -> None:
        """Events follow the data records; stale issue lines are not copied."""
        source = tmp_path / "issues.jsonl"
        # A stale issue line plus two events. Only the events are preserved
        # from source; the stale issue line is superseded by current state.
        stale_issue = orjson.dumps({"id": "dc-a", "title": "old"})
        source.write_bytes(
            stale_issue + b"\n" + _event("dc-a") + b"\n" + _event("dc-b") + b"\n"
        )
        buf = io.BytesIO()

        count = compact_snapshot(
            buf,
            issues=[_issue("a")],
            dependencies=[],
            links=[],
            source=source,
        )

        records = _lines(buf)
        # 1 current issue + 2 preserved events; the source's stale issue line
        # is NOT copied (only events are preserved from source).
        assert count == 3  # noqa: PLR2004
        assert [classify_record(r) for r in records] == ["issue", "event", "event"]
        assert {r["issue_id"] for r in records if r.get("record_type") == "event"} == {
            "dc-a",
            "dc-b",
        }

    def test_prune_event_ids_drops_matching_events(self, tmp_path: Path) -> None:
        """Events whose issue_id is pruned are omitted from the snapshot."""
        source = tmp_path / "issues.jsonl"
        source.write_bytes(_event("dc-a") + b"\n" + _event("dc-b") + b"\n")
        buf = io.BytesIO()

        count = compact_snapshot(
            buf,
            issues=[],
            dependencies=[],
            links=[],
            source=source,
            prune_event_ids={"dc-a"},
        )

        records = _lines(buf)
        assert count == 1
        assert [r["issue_id"] for r in records] == ["dc-b"]

    def test_rename_event_ids_rewrites_issue_id(self, tmp_path: Path) -> None:
        """A renamed issue_id is rewritten in preserved event records."""
        source = tmp_path / "issues.jsonl"
        source.write_bytes(_event("dc-a") + b"\n" + _event("dc-c") + b"\n")
        buf = io.BytesIO()

        count = compact_snapshot(
            buf,
            issues=[],
            dependencies=[],
            links=[],
            source=source,
            rename_event_ids={"dc-a": "ns-a"},
        )

        records = _lines(buf)
        assert count == 2  # noqa: PLR2004
        assert [r["issue_id"] for r in records] == ["ns-a", "dc-c"]


class TestMalformedTolerance:
    """A corrupt line in the source must not abort the rewrite (dogcat-5tix)."""

    def test_corrupt_last_line_is_skipped(self, tmp_path: Path) -> None:
        """A malformed JSON line between events is skipped, not fatal."""
        source = tmp_path / "issues.jsonl"
        source.write_bytes(
            _event("dc-a") + b"\n" + b"{not valid json\n" + _event("dc-b") + b"\n"
        )
        buf = io.BytesIO()

        count = compact_snapshot(
            buf,
            issues=[],
            dependencies=[],
            links=[],
            source=source,
        )

        records = _lines(buf)
        assert count == 2  # noqa: PLR2004
        assert [r["issue_id"] for r in records] == ["dc-a", "dc-b"]

    def test_non_object_json_line_is_skipped(self, tmp_path: Path) -> None:
        """A valid-JSON but non-object line (a list) is skipped."""
        source = tmp_path / "issues.jsonl"
        source.write_bytes(b"[1, 2, 3]\n" + _event("dc-a") + b"\n")
        buf = io.BytesIO()

        count = compact_snapshot(
            buf,
            issues=[],
            dependencies=[],
            links=[],
            source=source,
        )

        records = _lines(buf)
        assert count == 1
        assert records[0]["issue_id"] == "dc-a"
