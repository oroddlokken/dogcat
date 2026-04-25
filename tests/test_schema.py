"""Tests for schema-version helpers and load-time newer-version warning."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from unittest.mock import patch

import orjson

from dogcat._schema import (
    SCHEMA_BREAKING_THRESHOLD,
    current_version_tuple,
    find_newest_record_version,
    parse_version,
    warn_if_records_from_newer_version,
)
from dogcat.storage import JSONLStorage

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


class TestParseVersion:
    """Test version-string parsing."""

    def test_simple_release(self) -> None:
        """Plain release versions parse cleanly."""
        assert parse_version("1.2.3") == (1, 2, 3)

    def test_pep440_with_post_dev_local(self) -> None:
        """Post/dev/local segments are stripped, only MAJOR.MINOR.PATCH kept."""
        assert parse_version("0.11.7.post1.dev4+ga6a7d61c0.d20260425") == (0, 11, 7)

    def test_zero_zero_zero(self) -> None:
        """The 0.0.0 sentinel parses without error."""
        assert parse_version("0.0.0") == (0, 0, 0)

    def test_returns_none_for_empty(self) -> None:
        """Empty / None input is treated as unknown."""
        assert parse_version("") is None
        assert parse_version(None) is None

    def test_returns_none_for_unparseable(self) -> None:
        """Garbage strings return None instead of raising."""
        assert parse_version("not a version") is None
        assert parse_version("v1.2.3") is None
        assert parse_version("1.2") is None

    def test_current_version_tuple_is_three_int(self) -> None:
        """The running tool's version always parses to a 3-int tuple."""
        triple = current_version_tuple()
        assert triple is not None
        assert len(triple) == 3
        assert all(isinstance(v, int) for v in triple)


class TestFindNewestRecordVersion:
    """find_newest_record_version returns the highest parseable version."""

    def test_returns_none_for_empty(self) -> None:
        """Empty iterable returns None."""
        assert find_newest_record_version([]) is None

    def test_returns_none_when_no_versions(self) -> None:
        """Records without dcat_version return None."""
        assert find_newest_record_version([{"foo": "bar"}]) is None

    def test_picks_max(self) -> None:
        """Highest version wins, not first / last."""
        records: list[dict[str, object]] = [
            {"dcat_version": "0.5.0"},
            {"dcat_version": "9.9.9"},
            {"dcat_version": "1.0.0"},
        ]
        result = find_newest_record_version(records)
        assert result is not None
        assert result[0] == (9, 9, 9)
        assert result[1] == "9.9.9"

    def test_skips_unparseable(self) -> None:
        """Garbage versions are silently skipped."""
        records: list[dict[str, object]] = [
            {"dcat_version": "garbage"},
            {"dcat_version": "1.2.3"},
        ]
        result = find_newest_record_version(records)
        assert result is not None
        assert result[0] == (1, 2, 3)


class TestWarnIfRecordsFromNewerVersion:
    """End-to-end warning behavior."""

    def test_no_warning_when_records_older(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Older records produce no log output."""
        records: list[dict[str, object]] = [{"dcat_version": "0.0.1"}]
        with caplog.at_level(logging.WARNING, logger="dogcat._schema"):
            warn_if_records_from_newer_version(records, source="test.jsonl")
        assert not caplog.records

    def test_warns_when_records_newer(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Newer records emit a warning naming the offending version + source."""
        # Pin running version so the test doesn't depend on _version.py.
        with patch("dogcat._schema.current_version_tuple", return_value=(0, 1, 0)):
            records: list[dict[str, object]] = [{"dcat_version": "9.9.9"}]
            with caplog.at_level(logging.WARNING, logger="dogcat._schema"):
                warn_if_records_from_newer_version(records, source="test.jsonl")
        assert any("9.9.9" in r.getMessage() for r in caplog.records)
        assert any("test.jsonl" in r.getMessage() for r in caplog.records)

    def test_no_warning_when_versions_equal(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Records with the same MAJOR.MINOR.PATCH as the tool stay quiet."""
        with patch("dogcat._schema.current_version_tuple", return_value=(1, 2, 3)):
            records: list[dict[str, object]] = [{"dcat_version": "1.2.3.post1"}]
            with caplog.at_level(logging.WARNING, logger="dogcat._schema"):
                warn_if_records_from_newer_version(records, source="test.jsonl")
        assert not caplog.records


class TestStorageLoadWarning:
    """Storage._load emits the warning when newer records are present."""

    def _write_issue_record(self, path: Path, version: str) -> None:
        record: dict[str, object] = {
            "record_type": "issue",
            "dcat_version": version,
            "namespace": "dc",
            "id": "abcd",
            "title": "Test",
            "description": None,
            "status": "open",
            "priority": 2,
            "issue_type": "task",
            "owner": None,
            "parent": None,
            "labels": [],
            "external_ref": None,
            "design": None,
            "acceptance": None,
            "notes": None,
            "closed_reason": None,
            "created_at": "2026-01-01T00:00:00+00:00",
            "created_by": None,
            "updated_at": "2026-01-01T00:00:00+00:00",
            "updated_by": None,
            "closed_at": None,
            "closed_by": None,
            "deleted_at": None,
            "deleted_by": None,
            "deleted_reason": None,
            "original_type": None,
            "comments": [],
            "duplicate_of": None,
            "snoozed_until": None,
            "metadata": {},
        }
        path.write_bytes(orjson.dumps(record) + b"\n")

    def test_no_warning_for_older_records(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A normal database (older or equal version) loads silently."""
        dogcats_dir = tmp_path / ".dogcats"
        dogcats_dir.mkdir()
        self._write_issue_record(dogcats_dir / "issues.jsonl", "0.0.1")

        with caplog.at_level(logging.WARNING, logger="dogcat.storage"):
            JSONLStorage(path=str(dogcats_dir / "issues.jsonl"))
        assert not any("written by dcat" in r.getMessage() for r in caplog.records)

    def test_warns_for_newer_records(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A database written by a newer tool triggers a warning on load."""
        dogcats_dir = tmp_path / ".dogcats"
        dogcats_dir.mkdir()
        self._write_issue_record(dogcats_dir / "issues.jsonl", "999.9.9")

        with caplog.at_level(logging.WARNING, logger="dogcat.storage"):
            JSONLStorage(path=str(dogcats_dir / "issues.jsonl"))
        msgs = [r.getMessage() for r in caplog.records]
        assert any("999.9.9" in m for m in msgs)
        assert any("upgrade dcat" in m for m in msgs)


def test_breaking_threshold_default_is_unset() -> None:
    """No breaking schema change has shipped — threshold stays None."""
    assert SCHEMA_BREAKING_THRESHOLD is None
