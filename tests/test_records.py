"""Tests for dogcat._records — JSONL record (de)serialization & classification.

These pure functions were extracted from ``JSONLStorage`` (dogcat-4cza) so the
serialization / classification rules could be exercised directly rather than
only through the end-to-end archive command.
"""

from datetime import datetime, timezone

import orjson

from dogcat._records import (
    ArchiveClassification,
    classify_archived_line,
    dependency_to_record,
    link_to_record,
    parse_dependency_record,
    parse_link_record,
)
from dogcat._version import version as _dcat_version
from dogcat.models import Dependency, DependencyType, Link, LinkType

_TS = datetime(2026, 7, 14, 12, 0, 0, tzinfo=timezone.utc)


class TestDependencyToRecord:
    """Serialization of dependencies to JSONL dict form."""

    def test_add_record_shape(self) -> None:
        """A plain add serializes every field and carries no op key."""
        dep = Dependency(
            issue_id="t-a",
            depends_on_id="t-b",
            dep_type=DependencyType.BLOCKS,
            created_at=_TS,
            created_by="alice",
        )
        record = dependency_to_record(dep)
        assert record == {
            "record_type": "dependency",
            "dcat_version": _dcat_version,
            "issue_id": "t-a",
            "depends_on_id": "t-b",
            "type": "blocks",
            "created_at": _TS.isoformat(),
            "created_by": "alice",
        }
        assert "op" not in record

    def test_remove_op_adds_op_key(self) -> None:
        """A non-default op is recorded under the ``op`` key."""
        dep = Dependency(
            issue_id="t-a",
            depends_on_id="t-b",
            dep_type=DependencyType.BLOCKS,
            created_at=_TS,
        )
        record = dependency_to_record(dep, op="remove")
        assert record["op"] == "remove"


class TestLinkToRecord:
    """Serialization of links to JSONL dict form."""

    def test_add_record_shape(self) -> None:
        """A plain add serializes every field and carries no op key."""
        link = Link(
            from_id="t-a",
            to_id="t-b",
            link_type=LinkType.RELATES_TO,
            created_at=_TS,
            created_by="bob",
        )
        record = link_to_record(link)
        assert record == {
            "record_type": "link",
            "dcat_version": _dcat_version,
            "from_id": "t-a",
            "to_id": "t-b",
            "link_type": LinkType.RELATES_TO,
            "created_at": _TS.isoformat(),
            "created_by": "bob",
        }
        assert "op" not in record

    def test_remove_op_adds_op_key(self) -> None:
        """A non-default op is recorded under the ``op`` key."""
        link = Link(from_id="t-a", to_id="t-b", created_at=_TS)
        record = link_to_record(link, op="remove")
        assert record["op"] == "remove"

    def test_custom_string_link_type_preserved(self) -> None:
        """A free-form (non-enum) link type is serialized verbatim."""
        link = Link(from_id="t-a", to_id="t-b", link_type="duplicates", created_at=_TS)
        assert link_to_record(link)["link_type"] == "duplicates"


class TestParseLinkRecord:
    """Replay of link records into the in-memory link map."""

    def test_add_then_roundtrips_through_serializer(self) -> None:
        """Serialize -> parse reconstructs an equal Link."""
        link = Link(from_id="t-a", to_id="t-b", link_type="relates_to", created_at=_TS)
        link_map: dict[tuple[str, str, str], Link] = {}
        parse_link_record(link_to_record(link), link_map)
        assert list(link_map.values()) == [link]

    def test_remove_cancels_prior_add(self) -> None:
        """A remove op deletes the previously-added entry."""
        link_map: dict[tuple[str, str, str], Link] = {}
        parse_link_record(
            {"from_id": "t-a", "to_id": "t-b", "created_at": _TS.isoformat()}, link_map
        )
        assert len(link_map) == 1
        parse_link_record({"from_id": "t-a", "to_id": "t-b", "op": "remove"}, link_map)
        assert link_map == {}

    def test_missing_link_type_defaults_to_relates_to(self) -> None:
        """An absent link_type replays as the relates_to default."""
        link_map: dict[tuple[str, str, str], Link] = {}
        parse_link_record(
            {"from_id": "t-a", "to_id": "t-b", "created_at": _TS.isoformat()}, link_map
        )
        assert next(iter(link_map)) == ("t-a", "t-b", "relates_to")


class TestParseDependencyRecord:
    """Replay of dependency records into the in-memory dep map."""

    def test_add_then_roundtrips_through_serializer(self) -> None:
        """Serialize -> parse reconstructs an equal Dependency."""
        dep = Dependency(
            issue_id="t-a",
            depends_on_id="t-b",
            dep_type=DependencyType.BLOCKS,
            created_at=_TS,
        )
        dep_map: dict[tuple[str, str, str], Dependency] = {}
        parse_dependency_record(dependency_to_record(dep), dep_map)
        assert list(dep_map.values()) == [dep]

    def test_remove_cancels_prior_add(self) -> None:
        """A remove op deletes the previously-added entry."""
        dep_map: dict[tuple[str, str, str], Dependency] = {}
        parse_dependency_record(
            {
                "issue_id": "t-a",
                "depends_on_id": "t-b",
                "type": "blocks",
                "created_at": _TS.isoformat(),
            },
            dep_map,
        )
        assert len(dep_map) == 1
        parse_dependency_record(
            {
                "issue_id": "t-a",
                "depends_on_id": "t-b",
                "type": "blocks",
                "op": "remove",
            },
            dep_map,
        )
        assert dep_map == {}

    def test_unknown_dep_type_coerced_to_unknown_sentinel(self) -> None:
        """An unrecognized dep type coerces to the UNKNOWN sentinel, not a crash."""
        dep_map: dict[tuple[str, str, str], Dependency] = {}
        parse_dependency_record(
            {
                "issue_id": "t-a",
                "depends_on_id": "t-b",
                "type": "future-relation",
                "created_at": _TS.isoformat(),
            },
            dep_map,
        )
        assert next(iter(dep_map.values())).dep_type == DependencyType.UNKNOWN


def _line(record: dict[str, object]) -> bytes:
    return orjson.dumps(record)


_IDS: set[str] = {"t-a", "t-b"}


class TestClassifyArchivedLine:
    """Archive-membership decision for a single raw JSONL line."""

    def test_issue_with_namespace_in_set(self) -> None:
        """An issue whose namespace-id is in the set is archived."""
        line = _line({"record_type": "issue", "id": "a", "namespace": "t"})
        assert classify_archived_line(line, _IDS) == ArchiveClassification(
            archive=True, record_type="issue"
        )

    def test_issue_with_namespace_not_in_set(self) -> None:
        """An issue outside the set is kept in the source partition."""
        line = _line({"record_type": "issue", "id": "z", "namespace": "t"})
        result = classify_archived_line(line, _IDS)
        assert result.archive is False

    def test_issue_full_id_in_id_field(self) -> None:
        """Older records carry the full id (with dash) directly in ``id``."""
        line = _line({"record_type": "issue", "id": "t-a"})
        assert classify_archived_line(line, _IDS).archive is True

    def test_issue_bare_id_uses_default_namespace(self) -> None:
        """A bare id with no namespace and no dash gets the DEFAULT_NAMESPACE prefix."""
        line = _line({"record_type": "issue", "id": "a"})
        assert classify_archived_line(line, {"dc-a"}).archive is True

    def test_dependency_both_endpoints_in_set(self) -> None:
        """A dependency with both endpoints in the set is archived."""
        line = _line(
            {"record_type": "dependency", "issue_id": "t-a", "depends_on_id": "t-b"}
        )
        assert classify_archived_line(line, _IDS) == ArchiveClassification(
            archive=True, record_type="dependency"
        )

    def test_dependency_one_endpoint_outside_set(self) -> None:
        """A dependency reaching outside the set is kept, not archived."""
        line = _line(
            {"record_type": "dependency", "issue_id": "t-a", "depends_on_id": "t-z"}
        )
        assert classify_archived_line(line, _IDS).archive is False

    def test_link_both_endpoints_in_set(self) -> None:
        """A link with both endpoints in the set is archived."""
        line = _line({"record_type": "link", "from_id": "t-a", "to_id": "t-b"})
        assert classify_archived_line(line, _IDS) == ArchiveClassification(
            archive=True, record_type="link"
        )

    def test_link_one_endpoint_outside_set(self) -> None:
        """A link reaching outside the set is kept, not archived."""
        line = _line({"record_type": "link", "from_id": "t-a", "to_id": "t-z"})
        assert classify_archived_line(line, _IDS).archive is False

    def test_event_matches_on_issue_id(self) -> None:
        """An event is archived when its issue_id is in the set."""
        line = _line({"record_type": "event", "issue_id": "t-a"})
        assert classify_archived_line(line, _IDS) == ArchiveClassification(
            archive=True, record_type="event"
        )

    def test_event_without_issue_id_not_archived(self) -> None:
        """An event lacking an issue_id is kept, not archived."""
        line = _line({"record_type": "event"})
        assert classify_archived_line(line, _IDS).archive is False

    def test_unparseable_json_kept(self) -> None:
        """A non-JSON line is kept with no record type."""
        result = classify_archived_line(b"{not json", _IDS)
        assert result == ArchiveClassification(archive=False, record_type=None)

    def test_malformed_record_missing_key_kept(self) -> None:
        """A link missing from_id classifies as link but is kept, not raised (4258)."""
        line = _line({"record_type": "link", "to_id": "t-a"})
        result = classify_archived_line(line, _IDS)
        assert result == ArchiveClassification(archive=False, record_type=None)

    def test_malformed_issue_missing_id_kept(self) -> None:
        """An issue record missing ``id`` is kept in the source partition."""
        line = _line({"record_type": "issue", "namespace": "t"})
        assert classify_archived_line(line, _IDS).archive is False
