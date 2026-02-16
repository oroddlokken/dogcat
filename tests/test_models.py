"""Tests for Dogcat models."""

from datetime import datetime, timezone

import pytest

from dogcat.models import (
    Comment,
    Dependency,
    DependencyType,
    Issue,
    IssueType,
    Status,
    classify_record,
    dict_to_issue,
    issue_to_dict,
    validate_issue,
    validate_issue_type,
    validate_priority,
    validate_status,
)


class TestStatusEnum:
    """Test Status enumeration."""

    def test_all_status_values_valid(self) -> None:
        """Test that all Status values are valid strings."""
        expected_values = {
            "draft",
            "open",
            "in_progress",
            "in_review",
            "blocked",
            "deferred",
            "closed",
            "tombstone",
        }
        actual_values = {status.value for status in Status}
        assert actual_values == expected_values

    def test_status_string_enum(self) -> None:
        """Test that Status is a string enum."""
        assert isinstance(Status.OPEN, str)
        assert Status.OPEN == "open"


class TestIssueTypeEnum:
    """Test IssueType enumeration."""

    def test_all_issue_type_values_valid(self) -> None:
        """Test that all IssueType values are valid."""
        expected_values = {
            "task",
            "bug",
            "feature",
            "story",
            "chore",
            "epic",
            "question",
        }
        actual_values = {issue_type.value for issue_type in IssueType}
        assert actual_values == expected_values

    def test_issue_type_string_enum(self) -> None:
        """Test that IssueType is a string enum."""
        assert isinstance(IssueType.TASK, str)
        assert IssueType.TASK == "task"


class TestDependencyTypeEnum:
    """Test DependencyType enumeration."""

    def test_all_dependency_type_values_valid(self) -> None:
        """Test that all DependencyType values are valid."""
        expected_values = {"blocks", "parent-child", "related"}
        actual_values = {dep_type.value for dep_type in DependencyType}
        assert actual_values == expected_values


class TestCommentModel:
    """Test Comment dataclass."""

    def test_comment_creation(self) -> None:
        """Test creating a comment with required fields."""
        comment = Comment(
            id="comment-1",
            issue_id="issue-1",
            author="user@example.com",
            text="This is a comment",
        )
        assert comment.id == "comment-1"
        assert comment.issue_id == "issue-1"
        assert comment.author == "user@example.com"
        assert comment.text == "This is a comment"

    def test_comment_created_at_default(self) -> None:
        """Test that created_at is auto-set."""
        before = datetime.now(timezone.utc)
        comment = Comment(
            id="comment-1",
            issue_id="issue-1",
            author="user@example.com",
            text="Test",
        )
        after = datetime.now(timezone.utc)
        assert before <= comment.created_at <= after


class TestDependencyModel:
    """Test Dependency dataclass."""

    def test_dependency_creation(self) -> None:
        """Test creating a dependency."""
        dep = Dependency(
            issue_id="issue-1",
            depends_on_id="issue-2",
            dep_type=DependencyType.BLOCKS,
            created_by="user@example.com",
        )
        assert dep.issue_id == "issue-1"
        assert dep.depends_on_id == "issue-2"
        assert dep.dep_type == DependencyType.BLOCKS
        assert dep.created_by == "user@example.com"

    def test_dependency_created_at_default(self) -> None:
        """Test that created_at is auto-set."""
        before = datetime.now(timezone.utc)
        dep = Dependency(
            issue_id="issue-1",
            depends_on_id="issue-2",
            dep_type=DependencyType.PARENT_CHILD,
        )
        after = datetime.now(timezone.utc)
        assert before <= dep.created_at <= after


class TestIssueModel:
    """Test Issue dataclass."""

    def test_issue_creation_minimal(self) -> None:
        """Test creating an issue with only required fields."""
        issue = Issue(id="issue-1", title="Test issue")
        assert issue.id == "issue-1"
        assert issue.title == "Test issue"
        assert issue.status == Status.OPEN
        assert issue.priority == 2
        assert issue.issue_type == IssueType.TASK

    def test_issue_creation_full(self) -> None:
        """Test creating an issue with all fields."""
        issue = Issue(
            id="issue-1",
            title="Test issue",
            description="A detailed description",
            status=Status.IN_PROGRESS,
            priority=1,
            issue_type=IssueType.BUG,
            owner="user@example.com",
            parent="issue-0",
            labels=["bug", "urgent"],
            external_ref="https://github.com/project/issues/123",
            design="https://figma.com/file/...",
            acceptance="Should display correctly on mobile",
            notes="Testing in progress",
            created_by="user@example.com",
            updated_by="agent@bot.com",
        )
        assert issue.description == "A detailed description"
        assert issue.status == Status.IN_PROGRESS
        assert issue.priority == 1
        assert issue.issue_type == IssueType.BUG
        assert issue.owner == "user@example.com"
        assert issue.labels == ["bug", "urgent"]

    def test_issue_defaults(self) -> None:
        """Test that issue field defaults are correct."""
        issue = Issue(id="issue-1", title="Test")
        assert issue.status == Status.OPEN
        assert issue.priority == 2
        assert issue.issue_type == IssueType.TASK
        assert issue.labels == []
        assert issue.comments == []
        assert issue.owner is None
        assert issue.description is None

    def test_issue_datetime_auto_generated(self) -> None:
        """Test that created_at and updated_at are auto-generated."""
        before = datetime.now(timezone.utc)
        issue = Issue(id="issue-1", title="Test")
        after = datetime.now(timezone.utc)

        assert before <= issue.created_at <= after
        assert before <= issue.updated_at <= after

    def test_is_closed_method(self) -> None:
        """Test the is_closed() convenience method."""
        open_issue = Issue(id="issue-1", title="Test")
        assert not open_issue.is_closed()

        closed_issue = Issue(id="issue-2", title="Test", status=Status.CLOSED)
        assert closed_issue.is_closed()

    def test_is_tombstone_method(self) -> None:
        """Test the is_tombstone() convenience method."""
        normal_issue = Issue(id="issue-1", title="Test")
        assert not normal_issue.is_tombstone()

        tombstone_issue = Issue(id="issue-2", title="Test", status=Status.TOMBSTONE)
        assert tombstone_issue.is_tombstone()

    def test_is_duplicate_method(self) -> None:
        """Test the is_duplicate() convenience method."""
        original = Issue(id="issue-1", title="Test")
        assert not original.is_duplicate()

        duplicate = Issue(id="issue-2", title="Test", duplicate_of="issue-1")
        assert duplicate.is_duplicate()

    def test_get_status_emoji(self) -> None:
        """Test the get_status_emoji() method."""
        assert Issue(id="1", title="Test", status=Status.OPEN).get_status_emoji() == "●"
        assert (
            Issue(id="1", title="Test", status=Status.IN_PROGRESS).get_status_emoji()
            == "◐"
        )
        assert (
            Issue(id="1", title="Test", status=Status.CLOSED).get_status_emoji() == "✓"
        )


class TestValidation:
    """Test validation functions."""

    @pytest.mark.parametrize("priority", [0, 1, 2, 3, 4])
    def test_validate_priority_valid(self, priority: int) -> None:
        """Test that valid priorities don't raise."""
        validate_priority(priority)  # Should not raise

    @pytest.mark.parametrize("priority", [-1, 5, "high"])
    def test_validate_priority_invalid(self, priority: int) -> None:
        """Test that invalid priorities raise ValueError."""
        with pytest.raises(ValueError, match="Priority must be"):
            validate_priority(priority)  # type: ignore[arg-type]

    @pytest.mark.parametrize("status", list(Status))
    def test_validate_status_valid(self, status: Status) -> None:
        """Test that valid status doesn't raise."""
        validate_status(status)  # Should not raise

    def test_validate_status_invalid(self) -> None:
        """Test that invalid status raises TypeError."""
        with pytest.raises(TypeError, match="Status must be"):
            validate_status("invalid")  # type: ignore[arg-type]

    def test_validate_issue_type_valid(self) -> None:
        """Test that valid issue type doesn't raise."""
        for issue_type in IssueType:
            validate_issue_type(issue_type)  # Should not raise

    def test_validate_issue_type_invalid(self) -> None:
        """Test that invalid issue type raises TypeError."""
        with pytest.raises(TypeError, match="IssueType must be"):
            validate_issue_type("invalid")  # type: ignore

    def test_validate_issue_valid(self) -> None:
        """Test that valid issue doesn't raise."""
        issue = Issue(id="issue-1", title="Valid issue")
        validate_issue(issue)  # Should not raise

    def test_validate_issue_missing_title(self) -> None:
        """Test that issue without title raises."""
        issue = Issue(id="issue-1", title="")
        with pytest.raises(ValueError, match="must have a non-empty title"):
            validate_issue(issue)

    def test_validate_issue_invalid_priority(self) -> None:
        """Test that issue with invalid priority raises."""
        issue = Issue(id="issue-1", title="Test", priority=10)
        with pytest.raises(ValueError, match="Priority must be"):
            validate_issue(issue)


class TestSerialization:
    """Test issue serialization and deserialization."""

    def test_issue_to_dict_minimal(self) -> None:
        """Test converting minimal issue to dict."""
        issue = Issue(id="issue-1", title="Test")
        data = issue_to_dict(issue)

        assert data["id"] == "issue-1"
        assert data["title"] == "Test"
        assert data["status"] == "open"
        assert data["priority"] == 2
        assert data["issue_type"] == "task"

    def test_issue_to_dict_datetime_serialization(self) -> None:
        """Test that datetimes are serialized to ISO format."""
        issue = Issue(id="issue-1", title="Test")
        data = issue_to_dict(issue)

        # Should be ISO format strings
        assert isinstance(data["created_at"], str)
        assert isinstance(data["updated_at"], str)
        assert "T" in data["created_at"]  # ISO format includes T

    def test_issue_to_dict_with_comments(self) -> None:
        """Test serializing issue with comments."""
        comment = Comment(
            id="comment-1",
            issue_id="issue-1",
            author="user@example.com",
            text="A comment",
        )
        issue = Issue(id="issue-1", title="Test", comments=[comment])
        data = issue_to_dict(issue)

        assert len(data["comments"]) == 1
        assert data["comments"][0]["id"] == "comment-1"
        assert data["comments"][0]["text"] == "A comment"

    def test_dict_to_issue_minimal(self) -> None:
        """Test converting minimal dict to issue."""
        # Test new format with separate namespace
        data = {
            "namespace": "test",
            "id": "abc1",
            "title": "Test",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        issue = dict_to_issue(data)

        assert issue.id == "abc1"
        assert issue.namespace == "test"
        assert issue.full_id == "test-abc1"
        assert issue.title == "Test"
        assert issue.status == Status.OPEN

    def test_dict_to_issue_old_format_migration(self) -> None:
        """Test migrating old format (combined id) to new format (namespace + id)."""
        data = {
            "id": "dc-xyz9",  # Old format: namespace-id combined
            "title": "Test",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        issue = dict_to_issue(data)

        # Should split into namespace and id
        assert issue.namespace == "dc"
        assert issue.id == "xyz9"
        assert issue.full_id == "dc-xyz9"
        assert issue.title == "Test"

    def test_dict_to_issue_with_datetimes(self) -> None:
        """Test that ISO datetime strings are deserialized correctly."""
        now = datetime.now(timezone.utc)
        data = {
            "namespace": "issue",
            "id": "1",
            "title": "Test",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        issue = dict_to_issue(data)

        assert isinstance(issue.created_at, datetime)
        assert issue.created_at.isoformat() == now.isoformat()

    def test_dict_to_issue_with_comments(self) -> None:
        """Test deserializing issue with comments."""
        now = datetime.now(timezone.utc)
        data = {
            "id": "issue-1",
            "title": "Test",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "comments": [
                {
                    "id": "comment-1",
                    "issue_id": "issue-1",
                    "author": "user@example.com",
                    "text": "A comment",
                    "created_at": now.isoformat(),
                },
            ],
        }
        issue = dict_to_issue(data)

        assert len(issue.comments) == 1
        assert issue.comments[0].id == "comment-1"
        assert issue.comments[0].text == "A comment"

    def test_roundtrip_serialization(self) -> None:
        """Test that issue survives roundtrip serialization."""
        original = Issue(
            id="issue-1",
            title="Test Issue",
            description="A detailed description",
            status=Status.IN_PROGRESS,
            priority=1,
            issue_type=IssueType.BUG,
            owner="user@example.com",
            labels=["urgent", "bug"],
            acceptance="Should work on mobile",
            updated_by="agent@bot.com",
        )

        # Roundtrip
        data = issue_to_dict(original)
        restored = dict_to_issue(data)

        assert restored.id == original.id
        assert restored.title == original.title
        assert restored.description == original.description
        assert restored.status == original.status
        assert restored.priority == original.priority
        assert restored.issue_type == original.issue_type
        assert restored.owner == original.owner
        assert restored.labels == original.labels
        assert restored.acceptance == original.acceptance
        assert restored.updated_by == original.updated_by


class TestMetadata:
    """Test issue metadata field."""

    def test_issue_default_metadata_empty(self) -> None:
        """Test that metadata defaults to empty dict."""
        issue = Issue(id="issue-1", title="Test")
        assert issue.metadata == {}

    def test_issue_with_metadata(self) -> None:
        """Test creating issue with metadata."""
        issue = Issue(
            id="issue-1",
            title="Test",
            metadata={"manual": True, "custom_field": "value"},
        )
        assert issue.metadata["manual"] is True
        assert issue.metadata["custom_field"] == "value"

    def test_issue_to_dict_includes_metadata(self) -> None:
        """Test that metadata is serialized."""
        issue = Issue(
            id="issue-1",
            title="Test",
            metadata={"manual": True},
        )
        data = issue_to_dict(issue)
        assert data["metadata"] == {"manual": True}

    def test_issue_to_dict_empty_metadata(self) -> None:
        """Test that empty metadata is serialized as empty dict."""
        issue = Issue(id="issue-1", title="Test")
        data = issue_to_dict(issue)
        assert data["metadata"] == {}

    def test_dict_to_issue_with_metadata(self) -> None:
        """Test deserializing issue with metadata."""
        data = {
            "id": "issue-1",
            "title": "Test",
            "created_at": "2026-02-03T12:00:00+00:00",
            "updated_at": "2026-02-03T12:00:00+00:00",
            "metadata": {"manual": True, "priority_override": 0},
        }
        issue = dict_to_issue(data)
        assert issue.metadata["manual"] is True
        assert issue.metadata["priority_override"] == 0

    def test_dict_to_issue_missing_metadata(self) -> None:
        """Test deserializing issue without metadata field defaults to empty."""
        data = {
            "id": "issue-1",
            "title": "Test",
            "created_at": "2026-02-03T12:00:00+00:00",
            "updated_at": "2026-02-03T12:00:00+00:00",
        }
        issue = dict_to_issue(data)
        assert issue.metadata == {}

    def test_metadata_roundtrip(self) -> None:
        """Test metadata survives serialization roundtrip."""
        original = Issue(
            id="issue-1",
            title="Test",
            metadata={"manual": True, "tags": ["a", "b"], "count": 42},
        )
        data = issue_to_dict(original)
        restored = dict_to_issue(data)
        assert restored.metadata == original.metadata

    def test_issue_to_dict_includes_dcat_version(self) -> None:
        """Test that dcat_version is included in serialized output."""
        from dogcat._version import version

        issue = Issue(id="issue-1", title="Test")
        data = issue_to_dict(issue)
        assert "dcat_version" in data
        assert data["dcat_version"] == version

    def test_dict_to_issue_ignores_dcat_version(self) -> None:
        """Test that dcat_version in data is gracefully ignored on load."""
        data = {
            "dcat_version": "0.0.1",
            "namespace": "test",
            "id": "abc1",
            "title": "Test",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        issue = dict_to_issue(data)
        assert issue.id == "abc1"
        assert issue.title == "Test"

    def test_dict_to_issue_without_dcat_version(self) -> None:
        """Test that old records without dcat_version still load fine."""
        data = {
            "namespace": "test",
            "id": "abc1",
            "title": "Test",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        issue = dict_to_issue(data)
        assert issue.id == "abc1"


class TestDraftTypeMigration:
    """Test migration of legacy issue_type=draft to status=draft."""

    def test_draft_type_migrated_to_draft_status(self) -> None:
        """Old records with issue_type=draft become status=draft, type=task."""
        data = {
            "namespace": "dc",
            "id": "test1",
            "title": "Draft issue",
            "status": "open",
            "issue_type": "draft",
            "priority": 2,
            "created_at": "2025-01-01T00:00:00+00:00",
            "updated_at": "2025-01-01T00:00:00+00:00",
        }
        issue = dict_to_issue(data)
        assert issue.status == Status.DRAFT
        assert issue.issue_type == IssueType.TASK

    def test_closed_draft_preserves_closed_status(self) -> None:
        """Closed draft issues stay closed after migration."""
        data = {
            "namespace": "dc",
            "id": "test2",
            "title": "Closed draft",
            "status": "closed",
            "issue_type": "draft",
            "priority": 2,
            "created_at": "2025-01-01T00:00:00+00:00",
            "updated_at": "2025-01-01T00:00:00+00:00",
        }
        issue = dict_to_issue(data)
        assert issue.status == Status.CLOSED
        assert issue.issue_type == IssueType.TASK

    def test_tombstone_draft_preserves_tombstone_status(self) -> None:
        """Tombstone draft issues stay tombstone after migration."""
        data = {
            "namespace": "dc",
            "id": "test3",
            "title": "Deleted draft",
            "status": "tombstone",
            "issue_type": "draft",
            "priority": 2,
            "created_at": "2025-01-01T00:00:00+00:00",
            "updated_at": "2025-01-01T00:00:00+00:00",
        }
        issue = dict_to_issue(data)
        assert issue.status == Status.TOMBSTONE
        assert issue.issue_type == IssueType.TASK

    def test_draft_original_type_migrated(self) -> None:
        """Tombstones with original_type=draft get migrated to task."""
        data = {
            "namespace": "dc",
            "id": "test4",
            "title": "Deleted draft",
            "status": "tombstone",
            "issue_type": "task",
            "original_type": "draft",
            "priority": 2,
            "created_at": "2025-01-01T00:00:00+00:00",
            "updated_at": "2025-01-01T00:00:00+00:00",
        }
        issue = dict_to_issue(data)
        assert issue.original_type == IssueType.TASK

    def test_draft_status_emoji(self) -> None:
        """Draft status has pencil emoji."""
        issue = Issue(id="test", title="Test", status=Status.DRAFT)
        assert issue.get_status_emoji() == "\u270e"


class TestSubtaskTypeMigration:
    """Test migration of legacy issue_type=subtask to issue_type=task."""

    def test_subtask_type_migrated_to_task(self) -> None:
        """Old records with issue_type=subtask become type=task."""
        data = {
            "namespace": "dc",
            "id": "test1",
            "title": "Subtask issue",
            "status": "open",
            "issue_type": "subtask",
            "priority": 2,
            "created_at": "2025-01-01T00:00:00+00:00",
            "updated_at": "2025-01-01T00:00:00+00:00",
        }
        issue = dict_to_issue(data)
        assert issue.issue_type == IssueType.TASK
        assert issue.status == Status.OPEN

    def test_closed_subtask_preserves_closed_status(self) -> None:
        """Closed subtask issues stay closed after migration."""
        data = {
            "namespace": "dc",
            "id": "test2",
            "title": "Closed subtask",
            "status": "closed",
            "issue_type": "subtask",
            "priority": 2,
            "created_at": "2025-01-01T00:00:00+00:00",
            "updated_at": "2025-01-01T00:00:00+00:00",
        }
        issue = dict_to_issue(data)
        assert issue.status == Status.CLOSED
        assert issue.issue_type == IssueType.TASK

    def test_tombstone_subtask_preserves_tombstone_status(self) -> None:
        """Tombstone subtask issues stay tombstone after migration."""
        data = {
            "namespace": "dc",
            "id": "test3",
            "title": "Deleted subtask",
            "status": "tombstone",
            "issue_type": "subtask",
            "priority": 2,
            "created_at": "2025-01-01T00:00:00+00:00",
            "updated_at": "2025-01-01T00:00:00+00:00",
        }
        issue = dict_to_issue(data)
        assert issue.status == Status.TOMBSTONE
        assert issue.issue_type == IssueType.TASK

    def test_subtask_original_type_migrated(self) -> None:
        """Tombstones with original_type=subtask get migrated to task."""
        data = {
            "namespace": "dc",
            "id": "test4",
            "title": "Deleted subtask",
            "status": "tombstone",
            "issue_type": "task",
            "original_type": "subtask",
            "priority": 2,
            "created_at": "2025-01-01T00:00:00+00:00",
            "updated_at": "2025-01-01T00:00:00+00:00",
        }
        issue = dict_to_issue(data)
        assert issue.original_type == IssueType.TASK


class TestClassifyRecord:
    """Test JSONL record type classification."""

    def test_explicit_issue_record_type(self) -> None:
        """Test classify_record with explicit record_type='issue'."""
        data = {"record_type": "issue", "id": "abc1", "title": "Test"}
        assert classify_record(data) == "issue"

    def test_explicit_dependency_record_type(self) -> None:
        """Test classify_record with explicit record_type='dependency'."""
        data = {"record_type": "dependency", "issue_id": "a", "depends_on_id": "b"}
        assert classify_record(data) == "dependency"

    def test_explicit_link_record_type(self) -> None:
        """Test classify_record with explicit record_type='link'."""
        data = {"record_type": "link", "from_id": "a", "to_id": "b"}
        assert classify_record(data) == "link"

    def test_fallback_issue_without_record_type(self) -> None:
        """Test classify_record falls back to issue for old records."""
        data = {"id": "abc1", "title": "Test"}
        assert classify_record(data) == "issue"

    def test_fallback_dependency_without_record_type(self) -> None:
        """Test classify_record falls back to field-sniffing for dependencies."""
        data = {"issue_id": "a", "depends_on_id": "b", "type": "blocks"}
        assert classify_record(data) == "dependency"

    def test_fallback_link_without_record_type(self) -> None:
        """Test classify_record falls back to field-sniffing for links."""
        data = {"from_id": "a", "to_id": "b", "link_type": "relates_to"}
        assert classify_record(data) == "link"

    def test_explicit_type_overrides_field_sniffing(self) -> None:
        """Test that explicit record_type takes priority over field contents."""
        data = {"record_type": "issue", "from_id": "a", "to_id": "b"}
        assert classify_record(data) == "issue"

    def test_unknown_record_type_falls_back(self) -> None:
        """Test that unknown record_type values trigger fallback."""
        data = {"record_type": "unknown", "from_id": "a", "to_id": "b"}
        assert classify_record(data) == "link"

    def test_issue_to_dict_includes_record_type(self) -> None:
        """Test that issue_to_dict includes record_type='issue'."""
        issue = Issue(id="issue-1", title="Test")
        data = issue_to_dict(issue)
        assert data["record_type"] == "issue"
