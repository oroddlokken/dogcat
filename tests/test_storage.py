"""Tests for JSONL storage module."""

import json
from pathlib import Path

import orjson
import pytest

from dogcat.models import DependencyType, Issue, IssueType, Status
from dogcat.storage import JSONLStorage


@pytest.fixture
def storage(temp_dogcats_dir: Path) -> JSONLStorage:
    """Create a storage instance with temporary directory."""
    storage_path = temp_dogcats_dir / "issues.jsonl"
    return JSONLStorage(str(storage_path), create_dir=True)


def _mp_create_issues(
    storage_path: str, start: int, count: int, errors: "list[str]"
) -> None:
    """Concurrent-write worker (module-level so multiprocessing can pickle it)."""
    try:
        local_storage = JSONLStorage(storage_path)
        for i in range(start, start + count):
            local_storage.create(Issue(id=f"issue-{i}", title=f"Issue {i}"))
    except Exception as e:  # noqa: BLE001 - propagate any failure to the parent
        errors.append(repr(e))


class TestStorageInitialization:
    """Test storage initialization."""

    def test_storage_fails_without_directory(self, temp_workspace: Path) -> None:
        """Test that storage fails if directory doesn't exist and create_dir=False."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        with pytest.raises(ValueError, match="does not exist"):
            JSONLStorage(str(storage_path))

    def test_storage_creates_directory_with_flag(self, temp_workspace: Path) -> None:
        """Test that storage creates directory when create_dir=True."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        JSONLStorage(str(storage_path), create_dir=True)

        assert storage_path.parent.exists()
        assert storage_path.parent.is_dir()

    def test_storage_creates_issues_file(self, temp_workspace: Path) -> None:
        """Test that storage creates issues.jsonl file."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        # Create an issue to trigger save
        issue = Issue(id="test-1", title="Test")
        storage.create(issue)

        assert storage_path.exists()

    def test_storage_loads_existing_issues(self, temp_workspace: Path) -> None:
        """Test that storage loads existing issues from file."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"

        # Create storage and add issue
        storage1 = JSONLStorage(str(storage_path), create_dir=True)
        issue1 = Issue(id="test-1", title="Test Issue")
        storage1.create(issue1)

        # Create new storage instance pointing to same file (dir exists now)
        storage2 = JSONLStorage(str(storage_path))

        # Should load the existing issue
        assert storage2.get("test-1") is not None


class TestCRUDOperations:
    """Test CRUD operations."""

    def test_create_issue(self, storage: JSONLStorage) -> None:
        """Test creating an issue.

        Inspecting the returned object only proves ``create`` constructs
        a record — to prove the record actually persisted, reload the
        store from disk and look it up. (dogcat-4tud)
        """
        issue = Issue(id="issue-1", title="Test Issue")
        created = storage.create(issue)

        assert created.id == "issue-1"
        assert created.title == "Test Issue"

        reloaded = JSONLStorage(str(storage.path)).get("dc-issue-1")
        assert reloaded is not None
        assert reloaded.id == "issue-1"
        assert reloaded.title == "Test Issue"

    def test_create_duplicate_id_raises(self, storage: JSONLStorage) -> None:
        """Test that creating issue with duplicate ID raises."""
        issue1 = Issue(id="issue-1", title="Test 1")
        storage.create(issue1)

        issue2 = Issue(id="issue-1", title="Test 2")
        with pytest.raises(ValueError, match="already exists"):
            storage.create(issue2)

    def test_create_empty_title_raises(self, storage: JSONLStorage) -> None:
        """Test that creating issue without title raises."""
        issue = Issue(id="issue-1", title="")
        with pytest.raises(ValueError, match="must have a non-empty title"):
            storage.create(issue)

    def test_get_issue(self, storage: JSONLStorage) -> None:
        """Test getting an issue by ID."""
        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)

        retrieved = storage.get("issue-1")
        assert retrieved is not None
        assert retrieved.id == "issue-1"
        assert retrieved.title == "Test"

    def test_get_nonexistent_issue(self, storage: JSONLStorage) -> None:
        """Test that getting nonexistent issue returns None."""
        result = storage.get("nonexistent")
        assert result is None

    def test_list_all_issues(self, storage: JSONLStorage) -> None:
        """Test listing all issues."""
        for i in range(3):
            issue = Issue(id=f"issue-{i}", title=f"Test {i}")
            storage.create(issue)

        issues = storage.list()
        assert len(issues) == 3

    def test_list_filter_by_status(self, storage: JSONLStorage) -> None:
        """Test filtering issues by status."""
        issue1 = Issue(id="issue-1", title="Open", status=Status.OPEN)
        issue2 = Issue(id="issue-2", title="Closed", status=Status.CLOSED)
        storage.create(issue1)
        storage.create(issue2)

        open_issues = storage.list({"status": "open"})
        assert len(open_issues) == 1
        assert open_issues[0].id == "issue-1"

    def test_list_filter_by_priority(self, storage: JSONLStorage) -> None:
        """Test filtering issues by priority."""
        issue1 = Issue(id="issue-1", title="High", priority=0)
        issue2 = Issue(id="issue-2", title="Medium", priority=2)
        storage.create(issue1)
        storage.create(issue2)

        high_priority = storage.list({"priority": 0})
        assert len(high_priority) == 1
        assert high_priority[0].id == "issue-1"

    def test_list_filter_by_type(self, storage: JSONLStorage) -> None:
        """Test filtering issues by type."""
        issue1 = Issue(id="issue-1", title="Bug", issue_type=IssueType.BUG)
        issue2 = Issue(id="issue-2", title="Feature", issue_type=IssueType.FEATURE)
        storage.create(issue1)
        storage.create(issue2)

        bugs = storage.list({"type": "bug"})
        assert len(bugs) == 1
        assert bugs[0].id == "issue-1"

    def test_list_filter_by_label(self, storage: JSONLStorage) -> None:
        """Test filtering issues by label."""
        issue1 = Issue(id="issue-1", title="Test", labels=["urgent", "bug"])
        issue2 = Issue(id="issue-2", title="Test", labels=["feature"])
        storage.create(issue1)
        storage.create(issue2)

        urgent = storage.list({"label": "urgent"})
        assert len(urgent) == 1
        assert urgent[0].id == "issue-1"

    def test_list_filter_by_owner(self, storage: JSONLStorage) -> None:
        """Test filtering issues by owner."""
        issue1 = Issue(id="issue-1", title="Test", owner="user1@example.com")
        issue2 = Issue(id="issue-2", title="Test", owner="user2@example.com")
        storage.create(issue1)
        storage.create(issue2)

        user1_issues = storage.list({"owner": "user1@example.com"})
        assert len(user1_issues) == 1
        assert user1_issues[0].id == "issue-1"

    def test_update_issue(self, storage: JSONLStorage) -> None:
        """Test updating an issue."""
        issue = Issue(id="issue-1", title="Original")
        storage.create(issue)

        updated = storage.update("issue-1", {"title": "Updated"})
        assert updated.title == "Updated"

        retrieved = storage.get("issue-1")
        assert retrieved is not None
        assert retrieved.title == "Updated"

    def test_update_nonexistent_issue_raises(self, storage: JSONLStorage) -> None:
        """Test that updating nonexistent issue raises."""
        with pytest.raises(ValueError, match="not found"):
            storage.update("nonexistent", {"title": "New"})

    def test_update_timestamp_changes(self, storage: JSONLStorage) -> None:
        """Test that update changes updated_at timestamp."""
        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)
        original_issue = storage.get("issue-1")
        assert original_issue is not None
        original_time = original_issue.updated_at

        storage.update("issue-1", {"title": "Updated"})

        updated_issue = storage.get("issue-1")
        assert updated_issue is not None
        new_time = updated_issue.updated_at
        assert new_time > original_time

    def test_update_status_away_from_closed_clears_closed_fields(
        self, storage: JSONLStorage
    ) -> None:
        """Test that updating status away from closed clears closed_at/reason/by."""
        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)
        storage.close("issue-1", reason="Done", closed_by="alice")

        updated = storage.update("issue-1", {"status": "in_review"})
        assert updated.status == Status.IN_REVIEW
        assert updated.closed_at is None
        assert updated.closed_reason is None
        assert updated.closed_by is None

    def test_update_status_to_closed_sets_closed_at(
        self, storage: JSONLStorage
    ) -> None:
        """Test that updating status to closed sets closed_at."""
        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)

        updated = storage.update("issue-1", {"status": "closed"})
        assert updated.status == Status.CLOSED
        assert updated.closed_at is not None

    def test_update_status_away_from_closed_persists(
        self, temp_workspace: Path
    ) -> None:
        """Test that cleared closed fields survive reload."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)
        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)
        storage.close("issue-1", reason="Done", closed_by="alice")
        storage.update("issue-1", {"status": "in_review"})

        reloaded = JSONLStorage(str(storage_path))
        got = reloaded.get("issue-1")
        assert got is not None
        assert got.status == Status.IN_REVIEW
        assert got.closed_at is None
        assert got.closed_reason is None
        assert got.closed_by is None

    def test_close_issue(self, storage: JSONLStorage) -> None:
        """Test closing an issue."""
        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)

        closed = storage.close("issue-1", reason="Fixed")
        assert closed.status == Status.CLOSED
        assert closed.closed_at is not None

    def test_close_nonexistent_issue_raises(self, storage: JSONLStorage) -> None:
        """Test that closing nonexistent issue raises."""
        with pytest.raises(ValueError, match="not found"):
            storage.close("nonexistent")

    def test_delete_issue_creates_tombstone(self, storage: JSONLStorage) -> None:
        """Test that deleting an issue creates a tombstone."""
        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)

        deleted = storage.delete("issue-1", reason="Duplicate")
        assert deleted.status == Status.TOMBSTONE
        assert deleted.deleted_at is not None
        assert deleted.deleted_reason == "Duplicate"

    def test_delete_nonexistent_issue_raises(self, storage: JSONLStorage) -> None:
        """Test that deleting nonexistent issue raises."""
        with pytest.raises(ValueError, match="not found"):
            storage.delete("nonexistent")


class TestDependencies:
    """Test dependency management."""

    def test_add_dependency(self, storage: JSONLStorage) -> None:
        """Test adding a dependency."""
        issue1 = Issue(id="1", namespace="test", title="Test 1")
        issue2 = Issue(id="2", namespace="test", title="Test 2")
        storage.create(issue1)
        storage.create(issue2)

        dep = storage.add_dependency("test-1", "test-2", "blocks")
        assert dep.issue_id == "test-1"
        assert dep.depends_on_id == "test-2"
        assert dep.dep_type == DependencyType.BLOCKS

    def test_add_dependency_nonexistent_issue_raises(
        self,
        storage: JSONLStorage,
    ) -> None:
        """Test that adding dependency to nonexistent issue raises."""
        issue1 = Issue(id="1", namespace="test", title="Test 1")
        storage.create(issue1)

        with pytest.raises(ValueError, match="not found"):
            storage.add_dependency("test-1", "nonexistent", "blocks")

    def test_get_dependencies(self, storage: JSONLStorage) -> None:
        """Test getting dependencies of an issue."""
        issue1 = Issue(id="1", namespace="test", title="Test 1")
        issue2 = Issue(id="2", namespace="test", title="Test 2")
        issue3 = Issue(id="3", namespace="test", title="Test 3")
        storage.create(issue1)
        storage.create(issue2)
        storage.create(issue3)

        storage.add_dependency("test-1", "test-2", "blocks")
        storage.add_dependency("test-1", "test-3", "blocks")

        deps = storage.get_dependencies("test-1")
        assert len(deps) == 2
        assert all(d.issue_id == "test-1" for d in deps)

    def test_get_dependents(self, storage: JSONLStorage) -> None:
        """Test getting issues that depend on this one."""
        issue1 = Issue(id="1", namespace="test", title="Test 1")
        issue2 = Issue(id="2", namespace="test", title="Test 2")
        issue3 = Issue(id="3", namespace="test", title="Test 3")
        storage.create(issue1)
        storage.create(issue2)
        storage.create(issue3)

        storage.add_dependency("test-2", "test-1", "blocks")
        storage.add_dependency("test-3", "test-1", "blocks")

        dependents = storage.get_dependents("test-1")
        assert len(dependents) == 2
        assert all(d.depends_on_id == "test-1" for d in dependents)

    def test_remove_dependency(self, storage: JSONLStorage) -> None:
        """Test removing a dependency."""
        issue1 = Issue(id="1", namespace="test", title="Test 1")
        issue2 = Issue(id="2", namespace="test", title="Test 2")
        storage.create(issue1)
        storage.create(issue2)

        storage.add_dependency("test-1", "test-2", "blocks")
        assert len(storage.get_dependencies("test-1")) == 1

        storage.remove_dependency("test-1", "test-2")
        assert len(storage.get_dependencies("test-1")) == 0

    def test_duplicate_dependency_not_added(self, storage: JSONLStorage) -> None:
        """Test that duplicate dependencies are not added."""
        issue1 = Issue(id="1", namespace="test", title="Test 1")
        issue2 = Issue(id="2", namespace="test", title="Test 2")
        storage.create(issue1)
        storage.create(issue2)

        storage.add_dependency("test-1", "test-2", "blocks")
        storage.add_dependency("test-1", "test-2", "blocks")

        deps = storage.get_dependencies("test-1")
        assert len(deps) == 1


class TestAtomicWrites:
    """Test atomic write operations."""

    def test_save_creates_valid_jsonl(self, temp_workspace: Path) -> None:
        """Test that save creates valid JSONL file."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)

        # Read the file and verify each line is valid JSON with expected structure
        records: list[dict[str, object]] = []
        with storage_path.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))

        assert len(records) >= 1
        assert any(r.get("id") == "issue-1" for r in records)
        assert any(r.get("title") == "Test" for r in records)

    def test_persistence_across_instances(self, temp_workspace: Path) -> None:
        """Test that data persists across storage instances."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"

        storage1 = JSONLStorage(str(storage_path), create_dir=True)
        issue = Issue(id="issue-1", title="Test")
        storage1.create(issue)

        # Create new instance (dir exists now)
        storage2 = JSONLStorage(str(storage_path))
        retrieved = storage2.get("issue-1")

        assert retrieved is not None
        assert retrieved.title == "Test"


class TestErrorHandling:
    """Test error handling."""

    def test_corrupted_jsonl_middle_line_skipped(self, temp_workspace: Path) -> None:
        """A corrupt non-last line is logged, skipped, and tracked for repair."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage_path.parent.mkdir(parents=True, exist_ok=True)

        # Valid first line, corrupt second, valid third
        import orjson

        from dogcat.models import issue_to_dict

        valid_a = orjson.dumps(issue_to_dict(Issue(id="aaa", title="A"))).decode()
        valid_b = orjson.dumps(issue_to_dict(Issue(id="bbb", title="B"))).decode()
        storage_path.write_text(f"{valid_a}\ninvalid json line\n{valid_b}\n")

        s = JSONLStorage(str(storage_path))
        ids = sorted(i.id for i in s.list())
        assert ids == ["aaa", "bbb"]
        assert len(s._bad_lines) == 1
        assert s._bad_lines[0][0] == 2  # 1-indexed line number
        assert s._needs_compaction is True

    def test_corrupted_last_line_tolerated(self, temp_workspace: Path) -> None:
        """Test that a corrupted last line is tolerated (crash recovery)."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage_path.parent.mkdir(parents=True, exist_ok=True)

        import orjson

        from dogcat.models import issue_to_dict

        valid = orjson.dumps(issue_to_dict(Issue(id="ok", title="OK"))).decode()
        storage_path.write_text(f"{valid}\ntruncated garbage")

        # Should NOT raise — malformed last line is skipped
        s = JSONLStorage(str(storage_path))
        issues = s.list()
        assert len(issues) == 1
        assert issues[0].title == "OK"

    def test_corrupted_only_line_tolerated(self, temp_workspace: Path) -> None:
        """Test that a single corrupt line (only line) is tolerated."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage_path.parent.mkdir(parents=True, exist_ok=True)

        storage_path.write_text("invalid json line\n")

        # Single corrupt line is the last line — tolerated
        s = JSONLStorage(str(storage_path))
        assert len(s.list()) == 0

    def test_empty_jsonl_file_ok(self, temp_workspace: Path) -> None:
        """Test that empty JSONL file is handled gracefully."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        # Should not raise
        issues = storage.list()
        assert len(issues) == 0

    @pytest.mark.parametrize(
        "non_dict_payload", ["null", "42", "[]", '"string"', "true"]
    )
    def test_non_dict_jsonl_middle_line_skipped(
        self, temp_workspace: Path, non_dict_payload: str
    ) -> None:
        """A non-dict JSONL line in the middle is skipped, not raised."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage_path.parent.mkdir(parents=True, exist_ok=True)

        import orjson

        from dogcat.models import issue_to_dict

        valid_a = orjson.dumps(issue_to_dict(Issue(id="aaa", title="A"))).decode()
        valid_b = orjson.dumps(issue_to_dict(Issue(id="bbb", title="B"))).decode()
        storage_path.write_text(f"{valid_a}\n{non_dict_payload}\n{valid_b}\n")

        s = JSONLStorage(str(storage_path))
        ids = sorted(i.id for i in s.list())
        assert ids == ["aaa", "bbb"]
        assert len(s._bad_lines) == 1
        assert s._needs_compaction is True

    @pytest.mark.parametrize(
        "non_dict_payload", ["null", "42", "[]", '"string"', "true"]
    )
    def test_non_dict_jsonl_last_line_tolerated(
        self, temp_workspace: Path, non_dict_payload: str
    ) -> None:
        """A non-dict last JSONL line is tolerated (crash-recovery branch)."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage_path.parent.mkdir(parents=True, exist_ok=True)

        import orjson

        from dogcat.models import issue_to_dict

        valid = orjson.dumps(issue_to_dict(Issue(id="ok", title="OK"))).decode()
        storage_path.write_text(f"{valid}\n{non_dict_payload}\n")

        s = JSONLStorage(str(storage_path))
        issues = s.list()
        assert len(issues) == 1
        assert issues[0].title == "OK"

    @pytest.mark.parametrize(
        "non_dict_payload", ["null", "42", "[]", '"string"', "true"]
    )
    def test_non_dict_jsonl_only_line_tolerated(
        self, temp_workspace: Path, non_dict_payload: str
    ) -> None:
        """A single non-dict line (only line) is tolerated as last-line."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        storage_path.write_text(f"{non_dict_payload}\n")

        s = JSONLStorage(str(storage_path))
        assert len(s.list()) == 0


class TestCompactionTolerantOfBadLines:
    """_save_locked must tolerate the same lines _load skipped.

    Regression for dogcat-5tix: _load tolerated a corrupt last line and
    set _needs_compaction=True, but the next mutation triggered _save →
    _save_locked, which re-parsed the file and crashed on the same line
    because the event-preservation block only caught (JSONDecodeError,
    ValueError) — not AttributeError/TypeError on a non-dict.
    """

    def test_compaction_succeeds_with_non_dict_last_line(
        self, temp_workspace: Path
    ) -> None:
        """A non-dict last line is skipped during compaction, not raised."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage_path.parent.mkdir(parents=True, exist_ok=True)

        import orjson

        from dogcat.models import issue_to_dict

        valid = orjson.dumps(issue_to_dict(Issue(id="ok", title="OK"))).decode()
        # Write a valid record then a non-dict last line; _load will
        # tolerate it and mark _needs_compaction.
        storage_path.write_text(f"{valid}\n42\n")

        s = JSONLStorage(str(storage_path))
        assert s._needs_compaction is True
        # Trigger a mutation that goes through _save_locked. update()
        # itself does an append, so call prune_tombstones which forces
        # the rewrite path.
        s.create(Issue(id="x", title="X"))
        s.delete("dc-x")
        s.prune_tombstones()
        # The compacted file must not crash.
        assert "\n42\n" not in storage_path.read_text()


class TestUpdateTypeGuards:
    """update() must reject wrong-typed values for each known field.

    Regression for dogcat-3o3b: setattr-with-anything would silently
    persist e.g. ``priority=True``, ``labels='bug'``, ``status=42``.
    """

    def test_priority_must_be_int(self, storage: JSONLStorage) -> None:
        """Priority refuses bool / str / float."""
        storage.create(Issue(id="x", title="X"))
        for bad in [True, "high", 1.5, None]:
            with pytest.raises(TypeError, match="priority"):
                storage.update("dc-x", {"priority": bad})

    def test_status_must_be_str_or_enum(self, storage: JSONLStorage) -> None:
        """Status refuses int / None / list."""
        storage.create(Issue(id="x", title="X"))
        with pytest.raises(TypeError, match="status"):
            storage.update("dc-x", {"status": 42})
        with pytest.raises(TypeError, match="status"):
            storage.update("dc-x", {"status": None})

    def test_labels_must_be_list_of_strings(self, storage: JSONLStorage) -> None:
        """Labels refuses a bare string (which would iterate as chars)."""
        storage.create(Issue(id="x", title="X"))
        with pytest.raises(TypeError, match="labels"):
            storage.update("dc-x", {"labels": "bug"})
        with pytest.raises(TypeError, match="labels"):
            storage.update("dc-x", {"labels": [1, 2, 3]})

    def test_metadata_must_be_dict(self, storage: JSONLStorage) -> None:
        """Metadata refuses a string."""
        storage.create(Issue(id="x", title="X"))
        with pytest.raises(TypeError, match="metadata"):
            storage.update("dc-x", {"metadata": "hello"})

    def test_string_fields_refuse_non_string(self, storage: JSONLStorage) -> None:
        """Description / owner / parent refuse non-string non-None values."""
        storage.create(Issue(id="x", title="X"))
        with pytest.raises(TypeError, match="description"):
            storage.update("dc-x", {"description": 123})
        with pytest.raises(TypeError, match="owner"):
            storage.update("dc-x", {"owner": 42})

    def test_create_rejects_bool_priority(self, storage: JSONLStorage) -> None:
        """create() rejects bool priority — bool is an int subclass.

        Without this guard ``priority=True`` would slip through
        ``validate_priority`` and persist on disk. (dogcat-65fm)
        """
        with pytest.raises(ValueError, match="Priority must be"):
            storage.create(Issue(id="x", title="X", priority=True))  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="Priority must be"):
            storage.create(Issue(id="y", title="Y", priority=False))  # type: ignore[arg-type]


class TestBatchContextManager:
    """Direct coverage for ``storage.batch()`` write coalescing. (dogcat-29nz)."""

    def test_batch_writes_all_records_in_one_append(
        self,
        temp_dogcats_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """N creates inside batch produce one disk write, not N.

        Without batching, each ``create`` acquires the lock and fsyncs
        separately — N creates would be N round trips. The batch
        contract amortizes this. We count actual disk writes via
        ``append_jsonl_payload`` rather than ``_append`` because
        ``_append`` returns early when batching, so call counts on
        ``_append`` don't reflect real I/O. (dogcat-29nz)
        """
        from dogcat import _jsonl_io as io_mod

        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        write_count = {"n": 0}
        original_write = io_mod.append_jsonl_payload

        def counting_write(target: Path, payload: bytes) -> None:
            write_count["n"] += 1
            return original_write(target, payload)

        # Patch the symbol on the storage module — that's the binding the
        # storage code resolves at call time.
        monkeypatch.setattr("dogcat.storage.append_jsonl_payload", counting_write)

        with storage.batch():
            for i in range(5):
                storage.create(Issue(id=f"b{i}", title=f"Batch {i}"))

        assert write_count["n"] == 1, (
            f"expected exactly one disk write inside batch, got {write_count['n']}"
        )

        # All 5 issues persisted.
        reloaded = JSONLStorage(str(storage_path))
        assert len([i for i in reloaded.list() if i.id.startswith("b")]) == 5

    def test_batch_nested_is_noop(
        self,
        temp_dogcats_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A nested ``with storage.batch():`` does not double-buffer.

        The inner enter/exit must not flush the outer batch — only the
        outermost exit performs the locked write. (dogcat-29nz)
        """
        from dogcat import _jsonl_io as io_mod

        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        write_count = {"n": 0}
        original_write = io_mod.append_jsonl_payload

        def counting_write(target: Path, payload: bytes) -> None:
            write_count["n"] += 1
            return original_write(target, payload)

        monkeypatch.setattr("dogcat.storage.append_jsonl_payload", counting_write)

        with storage.batch():
            storage.create(Issue(id="outer1", title="O1"))
            with storage.batch():
                storage.create(Issue(id="inner", title="I"))
            # Inner exit must not have flushed.
            assert write_count["n"] == 0, (
                f"inner batch flushed prematurely: {write_count['n']} writes"
            )
            storage.create(Issue(id="outer2", title="O2"))
        # Single flush at the outer exit.
        assert write_count["n"] == 1

    def test_batch_flushes_pending_on_exception(
        self,
        temp_dogcats_dir: Path,
    ) -> None:
        """When the ``with`` block raises, buffered records are still flushed.

        Documents the current best-effort save contract: the in-memory
        state already mutated, and flushing keeps disk consistent with
        memory rather than silently dropping completed writes. Callers
        wanting rollback must reset in-memory state themselves.
        """
        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        class _BoomError(RuntimeError):
            pass

        def _raise_inside_batch() -> None:
            with storage.batch():
                storage.create(Issue(id="pre-boom", title="Should persist"))
                raise _BoomError

        with pytest.raises(_BoomError):
            _raise_inside_batch()

        # The pre-exception write was flushed despite the raise.
        reloaded = JSONLStorage(str(storage_path))
        assert reloaded.get("dc-pre-boom") is not None


class TestStatusFinalityGuards:
    """Tombstone status is final — close/update/delete must not resurrect it.

    Regression for dogcat-4g76: previously close() set status=closed on a
    tombstoned issue (leaving deleted_at populated alongside closed_at),
    update() permitted TOMBSTONE→OPEN with stale deleted_*, and a double
    delete() overwrote the original deleted_at/deleted_reason.
    """

    def test_close_refuses_tombstoned_issue(self, storage: JSONLStorage) -> None:
        """close() on a tombstoned issue raises rather than resurrecting it."""
        from dogcat.models import Status

        storage.create(Issue(id="x", title="X"))
        storage.delete("dc-x", reason="gone")
        with pytest.raises(ValueError, match="tombstoned"):
            storage.close("dc-x")
        # State unchanged
        issue = storage.get("dc-x")
        assert issue is not None
        assert issue.status == Status.TOMBSTONE
        assert issue.deleted_reason == "gone"
        assert issue.closed_at is None

    def test_update_refuses_status_change_from_tombstone(
        self, storage: JSONLStorage
    ) -> None:
        """update(--status open) on a tombstone raises."""
        storage.create(Issue(id="x", title="X"))
        storage.delete("dc-x")
        with pytest.raises(ValueError, match="tombstoned"):
            storage.update("dc-x", {"status": "open"})

    def test_update_refuses_status_change_via_enum(self, storage: JSONLStorage) -> None:
        """Update accepts both string and enum forms — guard works for both."""
        from dogcat.models import Status

        storage.create(Issue(id="x", title="X"))
        storage.delete("dc-x")
        with pytest.raises(ValueError, match="tombstoned"):
            storage.update("dc-x", {"status": Status.OPEN})

    def test_delete_is_idempotent(self, storage: JSONLStorage) -> None:
        """A second delete on a tombstoned issue does not overwrite forensics."""
        storage.create(Issue(id="x", title="X"))
        first = storage.delete("dc-x", reason="first reason", deleted_by="alice")
        first_at = first.deleted_at

        # Second delete with different reason / by should not modify state.
        second = storage.delete("dc-x", reason="second reason", deleted_by="bob")
        assert second.deleted_at == first_at
        assert second.deleted_reason == "first reason"
        assert second.deleted_by == "alice"


class TestInputCapEnforcement:
    """validate_issue caps + namespace rule are enforced at the storage boundary."""

    def test_oversized_title_rejected_on_create(self, storage: JSONLStorage) -> None:
        """A title above MAX_TITLE_LEN is rejected on create()."""
        from dogcat.constants import MAX_TITLE_LEN

        oversized = "x" * (MAX_TITLE_LEN + 1)
        with pytest.raises(ValueError, match="title exceeds"):
            storage.create(Issue(id="big", title=oversized))

    def test_oversized_description_rejected_on_create(
        self, storage: JSONLStorage
    ) -> None:
        """A description above MAX_DESC_LEN is rejected on create()."""
        from dogcat.constants import MAX_DESC_LEN

        oversized = "x" * (MAX_DESC_LEN + 1)
        with pytest.raises(ValueError, match="description exceeds"):
            storage.create(Issue(id="big", title="OK", description=oversized))

    def test_title_at_exact_limit_accepted(self, storage: JSONLStorage) -> None:
        """A title at exactly MAX_TITLE_LEN must be accepted.

        Pins the boundary so a typo loosening the bound from ``>`` to
        ``>=`` is caught at the storage layer (the web layer already
        has parity coverage). (dogcat-3d29)
        """
        from dogcat.constants import MAX_TITLE_LEN

        title = "x" * MAX_TITLE_LEN
        issue = storage.create(Issue(id="exact", title=title))
        assert len(issue.title) == MAX_TITLE_LEN

    def test_description_at_exact_limit_accepted(self, storage: JSONLStorage) -> None:
        """A description at exactly MAX_DESC_LEN must be accepted. (dogcat-3d29)."""
        from dogcat.constants import MAX_DESC_LEN

        body = "x" * MAX_DESC_LEN
        issue = storage.create(Issue(id="exact-d", title="OK", description=body))
        assert issue.description is not None
        assert len(issue.description) == MAX_DESC_LEN

    def test_invalid_namespace_rejected_on_create(self, storage: JSONLStorage) -> None:
        """A namespace with spaces / control bytes is rejected on create()."""
        with pytest.raises(ValueError, match="namespace"):
            storage.create(Issue(id="x", title="OK", namespace="bad ns"))

    def test_control_chars_stripped_from_title_on_create(
        self, storage: JSONLStorage
    ) -> None:
        """Control bytes (e.g. terminal escapes) are stripped from the title."""
        issue = storage.create(
            Issue(id="x", title="\x1b[31mevil\x1b[0m"),
        )
        assert "\x1b" not in issue.title
        assert "evil" in issue.title

    def test_control_chars_stripped_from_description_on_create(
        self, storage: JSONLStorage
    ) -> None:
        """Control bytes in the description are stripped during create()."""
        issue = storage.create(
            Issue(
                id="d",
                title="OK",
                description="hi\x1b[2J\x1b[Hthere",
            ),
        )
        assert "\x1b" not in (issue.description or "")
        # ESC chars stripped but printable bracket sequences remain harmless.
        assert "hi" in (issue.description or "")
        assert "there" in (issue.description or "")

    def test_empty_title_after_strip_rejected(self, storage: JSONLStorage) -> None:
        """A title containing only control bytes is rejected (post-strip empty)."""
        with pytest.raises(ValueError, match="empty after stripping"):
            storage.create(Issue(id="x", title="\x1b\x00\x07"))

    def test_c1_controls_stripped_from_title(self, storage: JSONLStorage) -> None:
        r"""C1 control bytes (U+0080..U+009F) are also stripped, not just C0.

        ``_control_char_pattern`` covers ``\\x7f-\\x9f`` — pin that with
        a test so a regex change that drops the upper range silently
        re-opens a prompt-injection vector via ``\\x9b`` (CSI in C1).
        (dogcat-2rpd)
        """
        # \x9b is CSI in the C1 control set; surrounded by safe text.
        issue = storage.create(
            Issue(id="c1", title="ok\x9b[2Jstill ok"),
        )
        assert "\x9b" not in issue.title
        assert "ok" in issue.title
        assert "still ok" in issue.title

    def test_invisible_format_chars_pass_through(self, storage: JSONLStorage) -> None:
        """RTL override (U+202E) and zero-width chars (U+200B) are not stripped.

        Documents the current contract: ``strip_control_bytes`` only
        targets C0/C1 controls + DEL. Format characters render through
        because the render-side ``sanitize_for_terminal`` is the layer
        that handles display safety; storage records the raw text.
        Pinning this prevents an over-eager strip that would mangle
        legitimate uses of bidi marks. (dogcat-2rpd)
        """
        storage.create(Issue(id="zw", title="hello​world‮marker"))
        # Both characters survive the storage round-trip.
        reloaded = JSONLStorage(str(storage.path)).get("dc-zw")
        assert reloaded is not None
        assert "​" in reloaded.title
        assert "‮" in reloaded.title

    def test_multibyte_utf8_title_round_trips(self, storage: JSONLStorage) -> None:
        """CJK characters and emoji round-trip through write + reload.

        Most existing storage tests use ASCII titles; without a
        multi-byte test, a regression in the JSON encoding (e.g.
        ``ensure_ascii=True``) or in the byte-size cap would slip
        through. (dogcat-2rpd)
        """
        title = "Issue 中文 — 日本語 — 한국어 — 🐱🐶"
        storage.create(Issue(id="utf", title=title))
        reloaded = JSONLStorage(str(storage.path)).get("dc-utf")
        assert reloaded is not None
        assert reloaded.title == title

    def test_realistic_namespaces_round_trip(self, storage: JSONLStorage) -> None:
        """Hyphen, mixed-case, digit, and single-char namespaces round-trip.

        Most tests use ``namespace='test'``; pin the format whitelist
        with realistic alternatives so a regression to the namespace
        validator surfaces here. (dogcat-2rpd)
        """
        cases = ["my-cool-project", "Team42", "client_alpha", "a"]
        for i, ns in enumerate(cases):
            storage.create(Issue(id=f"n{i:03d}", title=f"From {ns}", namespace=ns))
        reloaded = JSONLStorage(str(storage.path))
        for i, ns in enumerate(cases):
            issue = reloaded.get(f"{ns}-n{i:03d}")
            assert issue is not None, f"namespace={ns!r} not round-tripped"
            assert issue.namespace == ns

    def test_oversized_title_rejected_on_update(self, storage: JSONLStorage) -> None:
        """A too-long title fed via update() is rejected too."""
        from dogcat.constants import MAX_TITLE_LEN

        storage.create(Issue(id="ok", title="OK"))
        with pytest.raises(ValueError, match="title exceeds"):
            storage.update("ok", {"title": "x" * (MAX_TITLE_LEN + 1)})

    def test_invalid_namespace_rejected_on_change_namespace(
        self, storage: JSONLStorage
    ) -> None:
        """change_namespace() rejects an invalid target namespace."""
        storage.create(Issue(id="ok", title="OK"))
        with pytest.raises(ValueError, match="invalid"):
            storage.change_namespace("ok", "bad ns")


class TestAtomicRewritePreservesMode:
    """Compaction must not silently demote 0644 → 0600.

    Regression for dogcat-1cfd: tempfile.NamedTemporaryFile defaults to
    0600, and Path.replace inherits the tmp's mode — so a shared
    issues.jsonl became unreadable to other users after the first
    compaction.
    """

    def test_compaction_preserves_0644(self, temp_workspace: Path) -> None:
        """A 0644 issues.jsonl stays 0644 after a rewrite via _save."""
        import stat

        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage_path.parent.mkdir(parents=True, exist_ok=True)

        s = JSONLStorage(str(storage_path), create_dir=True)
        s.create(Issue(id="ok", title="OK"))
        # Set explicit 0644 on the post-create file.
        storage_path.chmod(0o644)

        s._save()
        post_mode = stat.S_IMODE(storage_path.stat().st_mode)
        assert post_mode == 0o644

    def test_compaction_preserves_0664(self, temp_workspace: Path) -> None:
        """A 0664 (group-writable) file stays 0664 after a rewrite."""
        import stat

        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage_path.parent.mkdir(parents=True, exist_ok=True)

        s = JSONLStorage(str(storage_path), create_dir=True)
        s.create(Issue(id="ok", title="OK"))
        storage_path.chmod(0o664)

        s._save()
        post_mode = stat.S_IMODE(storage_path.stat().st_mode)
        assert post_mode == 0o664


class TestIsDefaultBranchLocale:
    """``_is_default_branch`` must work under non-English locales.

    Regression for dogcat-4tl1: ``result.stderr.lower()`` substring
    checked for ``"not a git repository"``, but git emits localized
    strings under non-English LC_ALL, so the check failed and
    auto-compaction was silently disabled.
    """

    def test_subprocess_invoked_with_c_locale(self, temp_workspace: Path) -> None:
        """The ``git rev-parse`` call passes LC_ALL=C / LANG=C in env."""
        from unittest.mock import patch

        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        s = JSONLStorage(str(storage_path))

        captured: dict[str, dict[str, str]] = {}

        def mock_run(*_args: object, **kwargs: object) -> object:
            env = kwargs.get("env")
            if isinstance(env, dict):
                captured["env"] = env  # type: ignore[assignment]
            from subprocess import CompletedProcess

            # Pretend we're outside a git repo via the (localized) French
            # error string. With LC_ALL=C this would be the English form;
            # the test verifies that the call SETS the C locale, not what
            # git returns.
            return CompletedProcess(
                args=[],
                returncode=128,
                stdout="",
                stderr="ce n'est pas un dépôt git",
            )

        with patch("subprocess.run", side_effect=mock_run):
            s._is_default_branch()

        assert captured["env"]["LC_ALL"] == "C"
        assert captured["env"]["LANG"] == "C"


class TestLargeDataset:
    """Test with large datasets."""

    def test_many_issues(self, storage: JSONLStorage) -> None:
        """Test creating and retrieving many issues."""
        count = 100
        for i in range(count):
            issue = Issue(id=f"issue-{i}", title=f"Issue {i}")
            storage.create(issue)

        # Verify all were stored
        issues = storage.list()
        assert len(issues) == count

        # Verify retrieval works
        issue_50 = storage.get("issue-50")
        assert issue_50 is not None
        assert issue_50.title == "Issue 50"

    def test_many_dependencies(self, storage: JSONLStorage) -> None:
        """Test creating many dependencies."""
        # Create issues
        for i in range(10):
            issue = Issue(id=f"issue-{i}", title=f"Issue {i}")
            storage.create(issue)

        # Create dependencies
        dep_count = 0
        for i in range(1, 10):
            storage.add_dependency("issue-0", f"issue-{i}", "blocks")
            dep_count += 1

        # Verify
        deps = storage.get_dependencies("issue-0")
        assert len(deps) == dep_count


class TestParentChildRelationships:
    """Test parent-child issue relationships."""

    def test_get_children(self, storage: JSONLStorage) -> None:
        """Test getting child issues of a parent."""
        parent = Issue(id="p1", namespace="test", title="Parent Issue")
        child1 = Issue(
            id="c1",
            namespace="test",
            title="Child Issue 1",
            parent="test-p1",
        )
        child2 = Issue(
            id="c2",
            namespace="test",
            title="Child Issue 2",
            parent="test-p1",
        )
        orphan = Issue(id="o1", namespace="test", title="Orphan Issue")

        storage.create(parent)
        storage.create(child1)
        storage.create(child2)
        storage.create(orphan)

        children = storage.get_children("test-p1")
        assert len(children) == 2
        assert all(c.parent == "test-p1" for c in children)
        child_ids = {c.full_id for c in children}
        assert child_ids == {"test-c1", "test-c2"}

    def test_get_children_no_children(self, storage: JSONLStorage) -> None:
        """Test get_children returns empty list when no children exist."""
        parent = Issue(id="p1", namespace="test", title="Parent Issue")
        storage.create(parent)

        children = storage.get_children("test-p1")
        assert len(children) == 0

    def test_get_children_with_partial_id(self, storage: JSONLStorage) -> None:
        """Test get_children works with partial ID resolution."""
        parent = Issue(id="parent", namespace="dc", title="Parent Issue")
        child = Issue(
            id="child",
            namespace="dc",
            title="Child Issue",
            parent="dc-parent",
        )

        storage.create(parent)
        storage.create(child)

        # Use partial ID (just the hash part)
        children = storage.get_children("parent")
        assert len(children) == 1
        assert children[0].full_id == "dc-child"


class TestChildrenByParentIndex:
    """Test the _children_by_parent index is maintained correctly."""

    def test_index_populated_on_create(self, storage: JSONLStorage) -> None:
        """Test index is updated when creating issues with a parent."""
        parent = Issue(id="p1", namespace="test", title="Parent")
        child = Issue(id="c1", namespace="test", title="Child", parent="test-p1")
        storage.create(parent)
        storage.create(child)

        assert {c.full_id for c in storage.get_children("test-p1")} == {"test-c1"}

    def test_index_updated_on_reparent(self, storage: JSONLStorage) -> None:
        """Test index is updated when an issue's parent changes."""
        p1 = Issue(id="p1", namespace="test", title="Parent 1")
        p2 = Issue(id="p2", namespace="test", title="Parent 2")
        child = Issue(id="c1", namespace="test", title="Child", parent="test-p1")
        storage.create(p1)
        storage.create(p2)
        storage.create(child)

        storage.update("test-c1", {"parent": "test-p2"})

        assert storage.get_children("test-p1") == []
        assert {c.full_id for c in storage.get_children("test-p2")} == {"test-c1"}

    def test_index_updated_on_parent_removed(self, storage: JSONLStorage) -> None:
        """Test index is updated when parent is set to None."""
        parent = Issue(id="p1", namespace="test", title="Parent")
        child = Issue(id="c1", namespace="test", title="Child", parent="test-p1")
        storage.create(parent)
        storage.create(child)

        storage.update("test-c1", {"parent": None})

        assert storage.get_children("test-p1") == []

    def test_index_survives_reload(self, storage: JSONLStorage) -> None:
        """Test index is rebuilt correctly after reload."""
        parent = Issue(id="p1", namespace="test", title="Parent")
        child = Issue(id="c1", namespace="test", title="Child", parent="test-p1")
        storage.create(parent)
        storage.create(child)

        storage.reload()

        children = storage.get_children("test-p1")
        assert len(children) == 1
        assert children[0].full_id == "test-c1"

    def test_index_empty_for_no_children(self, storage: JSONLStorage) -> None:
        """Test index has no entry for issues without children."""
        issue = Issue(id="p1", namespace="test", title="No children")
        storage.create(issue)

        assert storage.get_children("test-p1") == []


class TestUpdateFieldAllowlist:
    """Test that update() only modifies allowed fields."""

    def test_update_allowed_field(self, storage: JSONLStorage) -> None:
        """Test that allowed fields can be updated."""
        issue = Issue(id="issue-1", title="Original")
        storage.create(issue)

        updated = storage.update("issue-1", {"title": "Updated"})
        assert updated.title == "Updated"

    def test_update_ignores_id(self, storage: JSONLStorage) -> None:
        """Test that update() cannot overwrite the id field."""
        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)

        storage.update("issue-1", {"id": "hacked"})
        retrieved = storage.get("issue-1")
        assert retrieved is not None
        assert retrieved.id == "issue-1"

    def test_update_ignores_namespace(self, storage: JSONLStorage) -> None:
        """Test that update() cannot overwrite the namespace field."""
        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)

        storage.update("issue-1", {"namespace": "evil"})
        retrieved = storage.get("issue-1")
        assert retrieved is not None
        assert retrieved.namespace == "dc"

    def test_update_ignores_created_at(self, storage: JSONLStorage) -> None:
        """Test that update() cannot overwrite created_at."""
        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)
        original_created_at = issue.created_at

        from datetime import datetime

        storage.update("issue-1", {"created_at": datetime(2000, 1, 1).astimezone()})
        retrieved = storage.get("issue-1")
        assert retrieved is not None
        assert retrieved.created_at == original_created_at

    def test_update_allows_comments(self, storage: JSONLStorage) -> None:
        """Test that update() can set comments via UPDATABLE_FIELDS."""
        from dogcat.models import Comment

        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)

        comment = Comment(id="c1", issue_id="issue-1", author="alice", text="hello")
        storage.update("issue-1", {"comments": [comment]})
        retrieved = storage.get("issue-1")
        assert retrieved is not None
        assert len(retrieved.comments) == 1
        assert retrieved.comments[0].text == "hello"


class TestCloseReasonField:
    """Test that close reason uses a dedicated field instead of notes."""

    def test_close_sets_close_reason(self, storage: JSONLStorage) -> None:
        """Test that closing with a reason sets the close_reason field."""
        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)

        closed = storage.close("issue-1", reason="Fixed the bug")
        assert closed.closed_reason == "Fixed the bug"

    def test_close_does_not_embed_reason_in_notes(self, storage: JSONLStorage) -> None:
        """Test that closing does not embed the reason in notes."""
        issue = Issue(id="issue-1", title="Test", notes="Some notes")
        storage.create(issue)

        closed = storage.close("issue-1", reason="Fixed")
        assert closed.notes == "Some notes"
        assert "Closed:" not in (closed.notes or "")

    def test_close_without_reason(self, storage: JSONLStorage) -> None:
        """Test closing without a reason leaves close_reason as None."""
        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)

        closed = storage.close("issue-1")
        assert closed.closed_reason is None

    def test_close_reason_persists(self, temp_workspace: Path) -> None:
        """Test that close_reason survives save/load cycle."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)
        storage.close("issue-1", reason="Done")

        # Reload from disk
        storage2 = JSONLStorage(str(storage_path))
        loaded = storage2.get("issue-1")
        assert loaded is not None
        assert loaded.closed_reason == "Done"

    def test_legacy_close_reason_migrated_from_notes(
        self,
    ) -> None:
        """Test that old issues with close reason in notes are migrated."""
        from dogcat.models import _migrate_close_reason, _migrate_notes

        notes = "User notes\n\nClosed: Legacy reason"
        assert _migrate_close_reason(notes, None) == "Legacy reason"
        assert _migrate_notes(notes, None) == "User notes"

    def test_migration_preserves_existing_close_reason(self) -> None:
        """Test that migration does not overwrite existing close_reason."""
        from dogcat.models import _migrate_close_reason, _migrate_notes

        notes = "Notes with\n\nClosed: something"
        assert _migrate_close_reason(notes, "Real reason") == "Real reason"
        assert _migrate_notes(notes, "Real reason") == notes


class TestCloseDeleteUpdatedAt:
    """Test that close() and delete() set updated_at."""

    def test_close_sets_updated_at(self, storage: JSONLStorage) -> None:
        """Test that close() updates the updated_at timestamp."""
        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)
        original_time = issue.updated_at

        closed = storage.close("issue-1", reason="Done")
        assert closed.updated_at > original_time
        assert closed.closed_at is not None
        assert closed.updated_at >= closed.closed_at

    def test_delete_sets_updated_at(self, storage: JSONLStorage) -> None:
        """Test that delete() updates the updated_at timestamp."""
        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)
        original_time = issue.updated_at

        deleted = storage.delete("issue-1", reason="Dup")
        assert deleted.updated_at > original_time
        assert deleted.deleted_at is not None
        assert deleted.updated_at >= deleted.deleted_at


class TestCloseDeleteOperator:
    """Test that close() and delete() accept operator parameters."""

    def test_close_sets_closed_by(self, storage: JSONLStorage) -> None:
        """Test that close() sets closed_by when provided."""
        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)

        closed = storage.close("issue-1", reason="Done", closed_by="alice")
        assert closed.closed_by == "alice"

    def test_close_without_closed_by(self, storage: JSONLStorage) -> None:
        """Test that close() leaves closed_by as None when not provided."""
        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)

        closed = storage.close("issue-1", reason="Done")
        assert closed.closed_by is None

    def test_delete_sets_deleted_by(self, storage: JSONLStorage) -> None:
        """Test that delete() sets deleted_by when provided."""
        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)

        deleted = storage.delete("issue-1", reason="Dup", deleted_by="bob")
        assert deleted.deleted_by == "bob"

    def test_delete_without_deleted_by(self, storage: JSONLStorage) -> None:
        """Test that delete() leaves deleted_by as None when not provided."""
        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)

        deleted = storage.delete("issue-1", reason="Dup")
        assert deleted.deleted_by is None

    def test_close_with_closed_by_persists(self, temp_workspace: Path) -> None:
        """Test that closed_by survives save/load cycle."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)
        storage.close("issue-1", reason="Done", closed_by="alice")

        storage2 = JSONLStorage(str(storage_path))
        loaded = storage2.get("issue-1")
        assert loaded is not None
        assert loaded.closed_by == "alice"

    def test_close_writes_single_event(self, temp_workspace: Path) -> None:
        """Test that close with closed_by writes one issue record + one event record."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)

        lines_before = storage_path.read_text().strip().count("\n") + 1
        storage.close("issue-1", reason="Done", closed_by="alice")
        lines_after = storage_path.read_text().strip().count("\n") + 1

        # Each close appends 2 lines: issue record + event record
        assert lines_after - lines_before == 2

    def test_delete_includes_deleted_by_in_tombstone_record(
        self,
        temp_workspace: Path,
    ) -> None:
        """Test that delete with deleted_by includes it in the tombstone record."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)
        storage.delete("issue-1", reason="Dup", deleted_by="bob")

        # Delete is append-only: the last issue record should be the tombstone
        import orjson

        lines = storage_path.read_text().strip().split("\n")
        issue_records = [
            orjson.loads(line)
            for line in lines
            if orjson.loads(line).get("id") == "issue-1"
        ]
        assert len(issue_records) >= 1
        # Last-write-wins: the final record is the tombstone
        tombstone = issue_records[-1]
        assert tombstone["deleted_by"] == "bob"
        assert tombstone["status"] == "tombstone"


class TestStatusTransitionEdgeCases:
    """Edge cases for status transitions through storage.update()."""

    def test_closed_open_closed_roundtrip_resets_close_fields(
        self, storage: JSONLStorage
    ) -> None:
        """CLOSED -> OPEN -> CLOSED: close fields clear, then closed_at resets."""
        issue = Issue(id="rt-1", title="Round trip")
        storage.create(issue)

        # First close populates all three fields.
        storage.close("rt-1", reason="initial", closed_by="alice")
        first = storage.get("rt-1")
        assert first is not None
        first_closed_at = first.closed_at
        assert first_closed_at is not None
        assert first.closed_reason == "initial"
        assert first.closed_by == "alice"

        # Reopen via update — all close fields must clear.
        reopened = storage.update("rt-1", {"status": "open"})
        assert reopened.status == Status.OPEN
        assert reopened.closed_at is None
        assert reopened.closed_reason is None
        assert reopened.closed_by is None

        # Re-close via update — closed_at gets set fresh; reason/by remain None
        # because update() doesn't accept them and prior values were cleared.
        reclosed = storage.update("rt-1", {"status": "closed"})
        assert reclosed.status == Status.CLOSED
        assert reclosed.closed_at is not None
        assert reclosed.closed_at >= first_closed_at
        assert reclosed.closed_reason is None
        assert reclosed.closed_by is None

    def test_update_to_closed_without_closed_by(self, storage: JSONLStorage) -> None:
        """Closing via update (no closed_by argument) leaves closed_by None."""
        issue = Issue(id="nbc-1", title="No closed_by")
        storage.create(issue)

        updated = storage.update("nbc-1", {"status": "closed"})
        assert updated.status == Status.CLOSED
        assert updated.closed_at is not None
        assert updated.closed_by is None
        assert updated.closed_reason is None

    def test_closed_blocked_closed_restores_closed_at(
        self, storage: JSONLStorage
    ) -> None:
        """CLOSED -> BLOCKED -> CLOSED: closed_at clears, then resets on re-close."""
        issue = Issue(id="cbc-1", title="Close blocked close")
        storage.create(issue)

        storage.close("cbc-1", reason="initial", closed_by="bob")
        before = storage.get("cbc-1")
        assert before is not None
        assert before.closed_at is not None
        before_closed_at = before.closed_at

        # Move to BLOCKED — closed fields must clear.
        blocked = storage.update("cbc-1", {"status": "blocked"})
        assert blocked.status == Status.BLOCKED
        assert blocked.closed_at is None
        assert blocked.closed_reason is None
        assert blocked.closed_by is None

        # Re-close — closed_at is set anew (not the original).
        reclosed = storage.update("cbc-1", {"status": "closed"})
        assert reclosed.status == Status.CLOSED
        assert reclosed.closed_at is not None
        assert reclosed.closed_at >= before_closed_at

    def test_bulk_status_updates_consistency(self, storage: JSONLStorage) -> None:
        """Closing many issues in a loop yields consistent state for each."""
        ids = [f"bulk-{i}" for i in range(10)]
        for iid in ids:
            storage.create(Issue(id=iid, title=f"Bulk {iid}"))

        for iid in ids:
            storage.update(iid, {"status": "closed"})

        for iid in ids:
            got = storage.get(iid)
            assert got is not None
            assert got.status == Status.CLOSED
            assert got.closed_at is not None
            assert got.closed_reason is None
            assert got.closed_by is None


class TestAppendOnlyStorage:
    """Test that mutations append instead of rewriting the entire file."""

    def test_create_appends_single_line(self, temp_workspace: Path) -> None:
        """Test that creating an issue appends lines rather than rewriting."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        storage.create(Issue(id="issue-1", title="First"))
        lines_after_first = _count_lines(storage_path)

        storage.create(Issue(id="issue-2", title="Second"))
        lines_after_second = _count_lines(storage_path)

        # Each create appends 2 lines: issue record + event record
        assert lines_after_second == lines_after_first + 2

    def test_update_appends_single_line(self, temp_workspace: Path) -> None:
        """Test that updating an issue appends lines."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        storage.create(Issue(id="issue-1", title="Original"))
        lines_before = _count_lines(storage_path)

        storage.update("issue-1", {"title": "Updated"})
        lines_after = _count_lines(storage_path)

        # Each update appends 2 lines: issue record + event record
        assert lines_after == lines_before + 2

    def test_update_persists_through_reload(self, temp_workspace: Path) -> None:
        """Test that appended updates are correctly loaded by a new instance."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        storage.create(Issue(id="issue-1", title="Original"))
        storage.update("issue-1", {"title": "Updated"})

        # Reload from disk
        storage2 = JSONLStorage(str(storage_path))
        loaded = storage2.get("issue-1")
        assert loaded is not None
        assert loaded.title == "Updated"

    def test_add_dependency_appends(self, temp_workspace: Path) -> None:
        """Test that adding a dependency appends one line."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        lines_before = _count_lines(storage_path)

        storage.add_dependency("t-a", "t-b", "blocks")
        lines_after = _count_lines(storage_path)

        assert lines_after == lines_before + 1

    def test_remove_dependency_appends_removal(self, temp_workspace: Path) -> None:
        """Test that removing a dep appends a removal record and reloads correctly."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        storage.add_dependency("t-a", "t-b", "blocks")
        assert len(storage.get_dependencies("t-a")) == 1

        storage.remove_dependency("t-a", "t-b")
        assert len(storage.get_dependencies("t-a")) == 0

        # Reload and verify removal is persisted
        storage2 = JSONLStorage(str(storage_path))
        assert len(storage2.get_dependencies("t-a")) == 0

    def test_add_link_appends(self, temp_workspace: Path) -> None:
        """Test that adding a link appends one line."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        lines_before = _count_lines(storage_path)

        storage.add_link("t-a", "t-b")
        lines_after = _count_lines(storage_path)

        assert lines_after == lines_before + 1

    def test_remove_link_appends_removal(self, temp_workspace: Path) -> None:
        """Test that removing a link appends a removal record and reloads correctly."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        storage.add_link("t-a", "t-b")
        assert len(storage.get_links("t-a")) == 1

        storage.remove_link("t-a", "t-b")
        assert len(storage.get_links("t-a")) == 0

        # Reload and verify removal is persisted
        storage2 = JSONLStorage(str(storage_path))
        assert len(storage2.get_links("t-a")) == 0

    def test_compaction_reduces_file_size(self, temp_workspace: Path) -> None:
        """Test that compaction eliminates superseded records."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        # Create an issue and update it several times
        storage.create(Issue(id="issue-1", title="v0"))
        for i in range(1, 6):
            storage.update("issue-1", {"title": f"v{i}"})

        # Each op appends 2 lines (issue + event): 1 create + 5 updates = 12
        assert _count_lines(storage_path) == 12

        # Force compaction
        storage._save()

        # After compaction: 1 issue line + 6 preserved event records = 7 lines
        assert _count_lines(storage_path) == 7

        # Data still correct after compaction
        storage2 = JSONLStorage(str(storage_path))
        loaded = storage2.get("issue-1")
        assert loaded is not None
        assert loaded.title == "v5"


class TestUpdatableFieldsAllowlist:
    """Test that storage.update() enforces UPDATABLE_FIELDS allowlist."""

    def test_disallowed_field_is_ignored(self, storage: JSONLStorage) -> None:
        """Fields not in UPDATABLE_FIELDS are silently skipped."""
        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)

        original_id = issue.id
        storage.update("issue-1", {"id": "hacked", "title": "Updated"})

        retrieved = storage.get("issue-1")
        assert retrieved is not None
        assert retrieved.id == original_id
        assert retrieved.title == "Updated"

    def test_comments_in_updatable_fields(self, storage: JSONLStorage) -> None:
        """Comments field is in UPDATABLE_FIELDS and can be updated."""
        from dogcat.models import Comment

        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)

        comment = Comment(id="c1", issue_id="issue-1", author="alice", text="hello")
        storage.update("issue-1", {"comments": [comment]})

        retrieved = storage.get("issue-1")
        assert retrieved is not None
        assert len(retrieved.comments) == 1
        assert retrieved.comments[0].text == "hello"

    def test_updated_by_in_updatable_fields(self, storage: JSONLStorage) -> None:
        """updated_by field is in UPDATABLE_FIELDS and gets persisted."""
        issue = Issue(id="issue-1", title="Test")
        storage.create(issue)

        storage.update("issue-1", {"status": "in_progress", "updated_by": "alice"})

        retrieved = storage.get("issue-1")
        assert retrieved is not None
        assert retrieved.updated_by == "alice"
        assert retrieved.status == Status.IN_PROGRESS


class TestRemoveArchived:
    """Test remove_archived() method."""

    def test_remove_archived_removes_issues(self, storage: JSONLStorage) -> None:
        """Test that archived issue IDs are removed from _issues."""
        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        storage.create(Issue(id="c", namespace="t", title="C"))

        storage.remove_archived({"t-a", "t-c"}, remaining_lines=1)

        assert storage.get("t-a") is None
        assert storage.get("t-b") is not None
        assert storage.get("t-c") is None

    def test_remove_archived_filters_dependencies_both_archived(
        self,
        storage: JSONLStorage,
    ) -> None:
        """Test that deps are removed when both sides are archived."""
        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        storage.create(Issue(id="c", namespace="t", title="C"))
        storage.add_dependency("t-a", "t-b", "blocks")
        storage.add_dependency("t-b", "t-c", "blocks")

        # Archive both a and b; dep t-a -> t-b should be filtered
        # (both issue_id AND depends_on_id are in archived_ids)
        storage.remove_archived({"t-a", "t-b"}, remaining_lines=1)

        # Only t-b -> t-c dep remains (t-b is archived but t-c is not)
        remaining_deps = storage.all_dependencies
        assert len(remaining_deps) == 1
        assert remaining_deps[0].issue_id == "t-b"
        assert remaining_deps[0].depends_on_id == "t-c"

    def test_remove_archived_keeps_deps_with_one_non_archived(
        self,
        storage: JSONLStorage,
    ) -> None:
        """Test that deps are kept when only one side is archived."""
        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        storage.add_dependency("t-a", "t-b", "blocks")

        # Archive only a; dep should remain because t-b is not archived
        storage.remove_archived({"t-a"}, remaining_lines=1)

        remaining_deps = storage.all_dependencies
        assert len(remaining_deps) == 1

    def test_remove_archived_filters_links_both_archived(
        self,
        storage: JSONLStorage,
    ) -> None:
        """Test that links are removed when both sides are archived."""
        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        storage.create(Issue(id="c", namespace="t", title="C"))
        storage.add_link("t-a", "t-b")
        storage.add_link("t-b", "t-c")

        # Archive both a and b; link t-a -> t-b should be filtered
        storage.remove_archived({"t-a", "t-b"}, remaining_lines=1)

        remaining_links = storage.all_links
        assert len(remaining_links) == 1
        assert remaining_links[0].from_id == "t-b"
        assert remaining_links[0].to_id == "t-c"

    def test_remove_archived_keeps_links_with_one_non_archived(
        self,
        storage: JSONLStorage,
    ) -> None:
        """Test that links are kept when only one side is archived."""
        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        storage.add_link("t-a", "t-b")

        # Archive only a; link should remain because t-b is not archived
        storage.remove_archived({"t-a"}, remaining_lines=1)

        remaining_links = storage.all_links
        assert len(remaining_links) == 1

    def test_remove_archived_rebuilds_indexes(self, storage: JSONLStorage) -> None:
        """Test that indexes are rebuilt after removing archived issues."""
        storage.create(
            Issue(id="parent", namespace="t", title="Parent"),
        )
        storage.create(
            Issue(id="child", namespace="t", title="Child", parent="t-parent"),
        )

        # Archive child
        storage.remove_archived({"t-child"}, remaining_lines=1)

        # Children index should be rebuilt without the archived child
        children = storage.get_children("t-parent")
        assert len(children) == 0

    def test_remove_archived_keeps_only_unarchived(self, storage: JSONLStorage) -> None:
        """remove_archived removes the named ids from the in-memory view.

        Previously this test asserted on the private ``_base_lines`` /
        ``_appended_lines`` counters. The behaviour observable to
        callers is that archived issues no longer appear via ``list``
        or ``get``; that is what we assert here. (dogcat-308p)
        """
        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))

        storage.remove_archived({"t-a"}, remaining_lines=42)

        assert storage.get("t-a") is None
        assert storage.get("t-b") is not None
        assert {i.full_id for i in storage.list()} == {"t-b"}

    def test_remove_archived_no_ids(self, storage: JSONLStorage) -> None:
        """Test remove_archived with empty set does not remove anything."""
        storage.create(Issue(id="a", namespace="t", title="A"))

        storage.remove_archived(set(), remaining_lines=1)

        assert storage.get("t-a") is not None


class TestAllDependenciesAndLinksProperties:
    """Test all_dependencies and all_links properties."""

    def test_all_dependencies_returns_copy(self, storage: JSONLStorage) -> None:
        """Test that all_dependencies returns a copy of the internal list."""
        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        storage.add_dependency("t-a", "t-b", "blocks")

        deps = storage.all_dependencies
        assert len(deps) == 1
        assert deps[0].issue_id == "t-a"
        assert deps[0].depends_on_id == "t-b"

        # Modifying the returned list should not affect internal state
        deps.clear()
        assert len(storage.all_dependencies) == 1

    def test_all_dependencies_empty(self, storage: JSONLStorage) -> None:
        """Test all_dependencies returns empty list when no deps exist."""
        storage.create(Issue(id="a", namespace="t", title="A"))

        assert storage.all_dependencies == []

    def test_all_links_returns_copy(self, storage: JSONLStorage) -> None:
        """Test that all_links returns a copy of the internal list."""
        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        storage.add_link("t-a", "t-b")

        links = storage.all_links
        assert len(links) == 1
        assert links[0].from_id == "t-a"
        assert links[0].to_id == "t-b"

        # Modifying the returned list should not affect internal state
        links.clear()
        assert len(storage.all_links) == 1

    def test_all_links_empty(self, storage: JSONLStorage) -> None:
        """Test all_links returns empty list when no links exist."""
        storage.create(Issue(id="a", namespace="t", title="A"))

        assert storage.all_links == []


class TestCheckIdUniqueness:
    """Test check_id_uniqueness() method.

    Real check now scans the JSONL log for hash collisions: two distinct
    issues sharing a full_id but with different created_at values would
    collapse into one under last-write-wins replay.
    """

    def test_check_id_uniqueness_returns_true(self, storage: JSONLStorage) -> None:
        """An empty database has no collisions."""
        assert storage.check_id_uniqueness() is True

    def test_check_id_uniqueness_with_issues(self, storage: JSONLStorage) -> None:
        """Distinct issues with distinct ids do not collide."""
        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))

        assert storage.check_id_uniqueness() is True

    def test_check_id_uniqueness_empty_storage(self, storage: JSONLStorage) -> None:
        """An empty file has no collisions."""
        assert storage.check_id_uniqueness() is True

    def test_check_id_uniqueness_repeated_updates_are_fine(
        self, storage: JSONLStorage
    ) -> None:
        """Many updates to one issue (same created_at) are not a collision."""
        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.update("t-a", {"title": "A2"})
        storage.update("t-a", {"title": "A3"})
        assert storage.check_id_uniqueness() is True

    def test_check_id_uniqueness_detects_hash_collision(self, tmp_path: Path) -> None:
        """Two issue records sharing a full_id but with different created_at fail."""
        from dogcat.storage import JSONLStorage

        path = tmp_path / "issues.jsonl"
        # Write two creation records with the same id+namespace but different
        # created_at — exactly the shape a hand-edit or merge collision would
        # produce.
        path.write_text(
            '{"record_type": "issue", "id": "abcd", "namespace": "t", '
            '"title": "first", "status": "open", "priority": 2, '
            '"created_at": "2026-04-25T12:00:00+00:00", '
            '"updated_at": "2026-04-25T12:00:00+00:00"}\n'
            '{"record_type": "issue", "id": "abcd", "namespace": "t", '
            '"title": "collision", "status": "open", "priority": 2, '
            '"created_at": "2026-04-25T13:00:00+00:00", '
            '"updated_at": "2026-04-25T13:00:00+00:00"}\n'
        )
        s = JSONLStorage(str(path))
        assert s.check_id_uniqueness() is False


class TestFindDanglingDependencies:
    """Test find_dangling_dependencies() method."""

    def test_no_dangling_deps(self, storage: JSONLStorage) -> None:
        """Test that no dangling deps found when all issues exist."""
        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        storage.add_dependency("t-a", "t-b", "blocks")

        dangling = storage.find_dangling_dependencies()
        assert dangling == []

    def test_dangling_dep_issue_id_missing(self, tmp_path: Path) -> None:
        """A dependency whose issue_id no longer has an issue record is dangling.

        Drives the malformed state from real input: a JSONL file that
        contains a dependency record but no matching issue record. This
        is exactly what merge collisions or hand-edits can produce, and
        is what the dangling-dep check has to detect on disk reload.
        (dogcat-308p)
        """
        path = tmp_path / "issues.jsonl"
        path.write_text(
            '{"record_type": "issue", "id": "b", "namespace": "t", '
            '"title": "B", "status": "open", "priority": 2, '
            '"issue_type": "task", '
            '"created_at": "2026-04-25T12:00:00+00:00", '
            '"updated_at": "2026-04-25T12:00:00+00:00"}\n'
            '{"record_type": "dependency", "issue_id": "t-a", '
            '"depends_on_id": "t-b", "type": "blocks", '
            '"created_at": "2026-04-25T12:00:00+00:00"}\n'
        )
        s = JSONLStorage(str(path))

        dangling = s.find_dangling_dependencies()
        assert len(dangling) == 1
        assert dangling[0].issue_id == "t-a"

    def test_dangling_dep_depends_on_id_missing(self, tmp_path: Path) -> None:
        """A dependency whose depends_on_id has no issue record is dangling.

        Mirrors :meth:`test_dangling_dep_issue_id_missing` for the
        opposite endpoint. Loading a file that names ``t-b`` only as a
        target, never as an issue, is the on-disk shape of an
        out-of-order delete. (dogcat-308p)
        """
        path = tmp_path / "issues.jsonl"
        path.write_text(
            '{"record_type": "issue", "id": "a", "namespace": "t", '
            '"title": "A", "status": "open", "priority": 2, '
            '"issue_type": "task", '
            '"created_at": "2026-04-25T12:00:00+00:00", '
            '"updated_at": "2026-04-25T12:00:00+00:00"}\n'
            '{"record_type": "dependency", "issue_id": "t-a", '
            '"depends_on_id": "t-b", "type": "blocks", '
            '"created_at": "2026-04-25T12:00:00+00:00"}\n'
        )
        s = JSONLStorage(str(path))

        dangling = s.find_dangling_dependencies()
        assert len(dangling) == 1
        assert dangling[0].depends_on_id == "t-b"

    def test_no_dangling_when_no_deps(self, storage: JSONLStorage) -> None:
        """Test that empty list returned when there are no dependencies."""
        storage.create(Issue(id="a", namespace="t", title="A"))

        dangling = storage.find_dangling_dependencies()
        assert dangling == []


class TestRemoveDependencies:
    """Test remove_dependencies() method."""

    def test_remove_specific_dependencies(self, storage: JSONLStorage) -> None:
        """Test removing specific dependency records."""
        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        storage.create(Issue(id="c", namespace="t", title="C"))
        dep1 = storage.add_dependency("t-a", "t-b", "blocks")
        storage.add_dependency("t-a", "t-c", "blocks")

        storage.remove_dependencies([dep1])

        remaining = storage.all_dependencies
        assert len(remaining) == 1
        assert remaining[0].depends_on_id == "t-c"

    def test_remove_dependencies_rebuilds_indexes(self, storage: JSONLStorage) -> None:
        """Test that indexes are rebuilt after removing dependencies."""
        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        dep = storage.add_dependency("t-a", "t-b", "blocks")

        storage.remove_dependencies([dep])

        # Index-based lookup should reflect the removal
        assert len(storage.get_dependencies("t-a")) == 0
        assert len(storage.get_dependents("t-b")) == 0

    def test_remove_dependencies_persists(self, temp_workspace: Path) -> None:
        """Test that remove_dependencies rewrites storage file."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        dep = storage.add_dependency("t-a", "t-b", "blocks")

        storage.remove_dependencies([dep])

        # Reload from disk
        storage2 = JSONLStorage(str(storage_path))
        assert len(storage2.all_dependencies) == 0

    def test_remove_empty_list(self, storage: JSONLStorage) -> None:
        """Test removing empty list of dependencies is a no-op."""
        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        storage.add_dependency("t-a", "t-b", "blocks")

        storage.remove_dependencies([])

        assert len(storage.all_dependencies) == 1


class TestDeleteCascadingCleanup:
    """delete() must remove dependencies and links touching the issue."""

    def test_delete_removes_incoming_and_outgoing_deps(
        self, storage: JSONLStorage
    ) -> None:
        """All deps where the deleted issue is either side are removed."""
        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        storage.create(Issue(id="c", namespace="t", title="C"))
        storage.add_dependency("t-b", "t-a", "blocks")  # b depends on a (incoming)
        storage.add_dependency("t-a", "t-c", "blocks")  # a depends on c (outgoing)

        storage.delete("t-a")

        # Both deps touching t-a should be gone in-memory
        assert storage.all_dependencies == []

    def test_delete_removes_both_link_directions(self, storage: JSONLStorage) -> None:
        """Links where the deleted issue appears as either endpoint are removed."""
        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        storage.create(Issue(id="c", namespace="t", title="C"))
        storage.add_link("t-a", "t-b")  # a -> b (outgoing)
        storage.add_link("t-c", "t-a")  # c -> a (incoming)

        storage.delete("t-a")

        assert storage.all_links == []

    def test_delete_cleanup_persists_through_reload(self, temp_workspace: Path) -> None:
        """After delete + reload, removed deps and links are gone from disk."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)
        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        storage.create(Issue(id="c", namespace="t", title="C"))
        storage.add_dependency("t-b", "t-a", "blocks")
        storage.add_dependency("t-a", "t-c", "blocks")
        storage.add_link("t-a", "t-b")
        storage.add_link("t-c", "t-a")

        storage.delete("t-a", reason="Duplicate")

        # Fresh reload from disk replays the append-only log
        reloaded = JSONLStorage(str(storage_path))
        assert reloaded.all_dependencies == []
        assert reloaded.all_links == []
        # Untouched issues survive
        assert reloaded.get("t-b") is not None
        assert reloaded.get("t-c") is not None
        # Tombstone is preserved
        tombstone = reloaded.get("t-a")
        assert tombstone is not None
        assert tombstone.is_tombstone()

    def test_delete_leaves_unrelated_deps_and_links_intact(
        self, storage: JSONLStorage
    ) -> None:
        """Deleting one issue doesn't touch deps/links between other issues."""
        storage.create(Issue(id="a", namespace="t", title="A"))
        storage.create(Issue(id="b", namespace="t", title="B"))
        storage.create(Issue(id="c", namespace="t", title="C"))
        storage.create(Issue(id="d", namespace="t", title="D"))
        storage.add_dependency("t-c", "t-d", "blocks")
        storage.add_link("t-c", "t-d")
        storage.add_dependency("t-a", "t-b", "blocks")  # touches deleted

        storage.delete("t-a")

        # The c<->d relations remain untouched
        assert len(storage.all_dependencies) == 1
        assert storage.all_dependencies[0].issue_id == "t-c"
        assert len(storage.all_links) == 1
        assert storage.all_links[0].from_id == "t-c"


class TestFileLock:
    """Test _file_lock() for concurrent write safety."""

    def test_file_lock_creates_lock_file(self, temp_workspace: Path) -> None:
        """Test that file lock creates a lock file."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        with storage._file_lock():
            assert storage._lock_path.exists()

    def test_file_lock_is_reentrant_safe(self, temp_workspace: Path) -> None:
        """Test that sequential lock acquisitions work correctly."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        # Acquire and release lock twice in sequence
        with storage._file_lock():
            acquired_first = True
        with storage._file_lock():
            acquired_second = True

        assert acquired_first
        assert acquired_second

        # Verify storage still works after sequential lock cycles
        storage.create(Issue(id="lock-1", title="After locks"))
        assert storage.get("lock-1") is not None

    def test_concurrent_writes_dont_corrupt(self, temp_workspace: Path) -> None:
        """Concurrent writes from two processes preserve every record.

        Uses multiprocessing because ``fcntl.flock`` is per-process — two
        threads in the same process share an open file description and would
        not actually contend for the lock, leaving the lock path untested.
        Asserts no errors and exact issue count so a regression that drops
        writes (e.g. lost wakeup, truncate-vs-rename ordering) shows up
        instead of silently passing. (dogcat-5l9g)
        """
        import multiprocessing

        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        JSONLStorage(str(storage_path), create_dir=True)

        ctx = multiprocessing.get_context("fork")
        manager = ctx.Manager()
        errors = manager.list()  # type: ignore[var-annotated]

        p1 = ctx.Process(
            target=_mp_create_issues, args=(str(storage_path), 0, 10, errors)
        )
        p2 = ctx.Process(
            target=_mp_create_issues, args=(str(storage_path), 100, 10, errors)
        )
        p1.start()
        p2.start()
        p1.join(timeout=30)
        p2.join(timeout=30)

        assert not p1.is_alive(), "child 1 hung"
        assert not p2.is_alive(), "child 2 hung"
        assert p1.exitcode == 0, f"child 1 exit={p1.exitcode}"
        assert p2.exitcode == 0, f"child 2 exit={p2.exitcode}"
        assert list(errors) == [], f"workers reported errors: {list(errors)}"

        # Exact count: 10 from each process, no dropped writes.
        final_storage = JSONLStorage(str(storage_path))
        all_issues = final_storage.list()
        assert len(all_issues) == 20

        # Each line in the file is still valid JSONL.
        with storage_path.open() as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    json.loads(stripped)

    def test_file_lock_open_failure_raises_runtimeerror(
        self, temp_workspace: Path
    ) -> None:
        """OSError opening the lock file is wrapped in a clear RuntimeError."""
        storage_path = temp_workspace / ".dogcats" / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)
        # Point lock at a path inside a missing directory so open('w') fails.
        storage._lock_path = temp_workspace / "missing-dir" / "subdir" / ".issues.lock"

        with (
            pytest.raises(RuntimeError, match="Failed to open lock file"),
            storage._file_lock(),
        ):
            pass


def _count_lines(path: Path) -> int:
    """Count non-empty lines in a file."""
    with path.open() as f:
        return sum(1 for line in f if line.strip())


class TestChangeNamespace:
    """Test change_namespace() method."""

    def test_basic_namespace_change(self, storage: JSONLStorage) -> None:
        """Test changing an issue's namespace."""
        issue = Issue(id="abc1", title="Test", namespace="dc")
        storage.create(issue)

        updated = storage.change_namespace("dc-abc1", "newns")
        assert updated.namespace == "newns"
        assert updated.full_id == "newns-abc1"
        assert storage.get("newns-abc1") is not None
        assert storage.get("dc-abc1") is None

    def test_noop_when_same_namespace(self, storage: JSONLStorage) -> None:
        """Test that no-op when namespace doesn't change."""
        issue = Issue(id="abc1", title="Test", namespace="dc")
        storage.create(issue)

        updated = storage.change_namespace("dc-abc1", "dc")
        assert updated.full_id == "dc-abc1"

    def test_error_on_id_conflict(self, storage: JSONLStorage) -> None:
        """Test that error is raised if new ID already exists."""
        issue1 = Issue(id="abc1", title="Issue 1", namespace="dc")
        issue2 = Issue(id="abc1", title="Issue 2", namespace="other")
        storage.create(issue1)
        storage.create(issue2)

        with pytest.raises(ValueError, match="already exists"):
            storage.change_namespace("dc-abc1", "other")

    def test_error_on_nonexistent_issue(self, storage: JSONLStorage) -> None:
        """Test that error is raised for nonexistent issue."""
        with pytest.raises(ValueError, match="not found"):
            storage.change_namespace("dc-nope", "newns")

    def test_cascades_to_parent_references(self, storage: JSONLStorage) -> None:
        """Test that parent references in children are updated."""
        parent = Issue(id="par1", title="Parent", namespace="dc")
        storage.create(parent)
        child = Issue(id="ch1", title="Child", namespace="dc", parent="dc-par1")
        storage.create(child)

        storage.change_namespace("dc-par1", "newns")

        # Child's parent reference should point to new ID
        updated_child = storage.get("dc-ch1")
        assert updated_child is not None
        assert updated_child.parent == "newns-par1"

        # Parent-child index should work
        children = storage.get_children("newns-par1")
        assert len(children) == 1
        assert children[0].full_id == "dc-ch1"

    def test_cascades_to_duplicate_of(self, storage: JSONLStorage) -> None:
        """Test that duplicate_of references are updated."""
        original = Issue(id="orig1", title="Original", namespace="dc")
        storage.create(original)
        dup = Issue(
            id="dup1", title="Duplicate", namespace="dc", duplicate_of="dc-orig1"
        )
        storage.create(dup)

        storage.change_namespace("dc-orig1", "newns")

        updated_dup = storage.get("dc-dup1")
        assert updated_dup is not None
        assert updated_dup.duplicate_of == "newns-orig1"

    def test_cascades_to_dependencies(self, storage: JSONLStorage) -> None:
        """Test that dependency records are updated."""
        issue1 = Issue(id="is1", title="Issue 1", namespace="dc")
        issue2 = Issue(id="is2", title="Issue 2", namespace="dc")
        storage.create(issue1)
        storage.create(issue2)
        storage.add_dependency("dc-is1", "dc-is2", "blocks")

        storage.change_namespace("dc-is2", "newns")

        # Dependency should now reference the new ID
        deps = storage.get_dependencies("dc-is1")
        assert len(deps) == 1
        assert deps[0].depends_on_id == "newns-is2"

        # Reverse lookup should also work
        dependents = storage.get_dependents("newns-is2")
        assert len(dependents) == 1
        assert dependents[0].issue_id == "dc-is1"

    def test_cascades_to_links(self, storage: JSONLStorage) -> None:
        """Test that link records are updated."""
        issue1 = Issue(id="is1", title="Issue 1", namespace="dc")
        issue2 = Issue(id="is2", title="Issue 2", namespace="dc")
        storage.create(issue1)
        storage.create(issue2)
        storage.add_link("dc-is1", "dc-is2", "relates_to")

        storage.change_namespace("dc-is1", "newns")

        # Link should now reference the new ID
        links = storage.get_links("newns-is1")
        assert len(links) == 1
        assert links[0].from_id == "newns-is1"
        assert links[0].to_id == "dc-is2"

        # Incoming link lookup should work too
        incoming = storage.get_incoming_links("dc-is2")
        assert len(incoming) == 1
        assert incoming[0].from_id == "newns-is1"

    def test_persists_after_reload(self, storage: JSONLStorage) -> None:
        """Test that namespace change persists after reload."""
        parent = Issue(id="par1", title="Parent", namespace="dc")
        storage.create(parent)
        child = Issue(id="ch1", title="Child", namespace="dc", parent="dc-par1")
        storage.create(child)
        storage.add_dependency("dc-ch1", "dc-par1", "blocks")

        storage.change_namespace("dc-par1", "newns")

        # Reload from disk
        storage.reload()

        assert storage.get("newns-par1") is not None
        assert storage.get("dc-par1") is None

        updated_child = storage.get("dc-ch1")
        assert updated_child is not None
        assert updated_child.parent == "newns-par1"

        deps = storage.get_dependencies("dc-ch1")
        assert len(deps) == 1
        assert deps[0].depends_on_id == "newns-par1"

    def test_namespace_change_updates_event_ids(self, storage: JSONLStorage) -> None:
        """Test that events have issue_id rewritten after namespace change."""
        issue = Issue(id="ev1", title="Evented", namespace="dc")
        storage.create(issue)
        storage.update("dc-ev1", {"title": "Updated title"})

        storage.change_namespace("dc-ev1", "newns")

        # Read raw JSONL and collect event issue_ids
        raw_lines = storage.path.read_bytes().splitlines()
        event_issue_ids: set[str] = set()
        for line in raw_lines:
            data = orjson.loads(line)
            if data.get("record_type") == "event":
                event_issue_ids.add(data["issue_id"])

        # Old namespace should not appear in any events
        assert "dc-ev1" not in event_issue_ids

        # Events should reference the new namespace
        assert "newns-ev1" in event_issue_ids


class TestGetNamespaces:
    """Test the get_namespaces() utility function."""

    def test_counts_issues_by_namespace(self, temp_dogcats_dir: Path) -> None:
        """Counts issues grouped by namespace."""
        from dogcat.storage import NamespaceCounts, get_namespaces

        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)
        storage.create(Issue(id="a1", title="A1", namespace="ns-a"))
        storage.create(Issue(id="a2", title="A2", namespace="ns-a"))
        storage.create(Issue(id="b1", title="B1", namespace="ns-b"))

        result = get_namespaces(storage, include_inbox=False)
        assert result == {
            "ns-a": NamespaceCounts(issues=2),
            "ns-b": NamespaceCounts(issues=1),
        }

    def test_excludes_tombstones(self, temp_dogcats_dir: Path) -> None:
        """Tombstoned issues are excluded from counts."""
        from dogcat.storage import NamespaceCounts, get_namespaces

        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)
        storage.create(Issue(id="a1", title="A1", namespace="ns-a"))
        storage.create(Issue(id="a2", title="A2", namespace="ns-a"))
        storage.delete("ns-a-a1")

        result = get_namespaces(storage, include_inbox=False)
        assert result == {"ns-a": NamespaceCounts(issues=1)}

    def test_includes_inbox_proposals(self, temp_dogcats_dir: Path) -> None:
        """Inbox proposals are included when include_inbox=True."""
        from dogcat.inbox import InboxStorage
        from dogcat.models import Proposal
        from dogcat.storage import NamespaceCounts, get_namespaces

        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)
        storage.create(Issue(id="a1", title="A1", namespace="ns-a"))

        inbox = InboxStorage(dogcats_dir=str(temp_dogcats_dir))
        inbox.create(Proposal(id="p1", title="P1", namespace="ns-new"))

        result = get_namespaces(storage, dogcats_dir=str(temp_dogcats_dir))
        assert result["ns-a"] == NamespaceCounts(issues=1)
        assert result["ns-new"] == NamespaceCounts(inbox=1)

    def test_inbox_counts_separate_from_issues(self, temp_dogcats_dir: Path) -> None:
        """Inbox proposals in same namespace tracked separately."""
        from dogcat.inbox import InboxStorage
        from dogcat.models import Proposal
        from dogcat.storage import NamespaceCounts, get_namespaces

        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)
        storage.create(Issue(id="a1", title="A1", namespace="ns-a"))

        inbox = InboxStorage(dogcats_dir=str(temp_dogcats_dir))
        inbox.create(Proposal(id="p1", title="P1", namespace="ns-a"))

        result = get_namespaces(storage, dogcats_dir=str(temp_dogcats_dir))
        assert result == {"ns-a": NamespaceCounts(issues=1, inbox=1)}
        assert result["ns-a"].total == 2

    def test_no_inbox_file_is_safe(self, temp_dogcats_dir: Path) -> None:
        """Missing inbox.jsonl does not cause errors."""
        from dogcat.storage import NamespaceCounts, get_namespaces

        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)
        storage.create(Issue(id="a1", title="A1", namespace="ns-a"))

        result = get_namespaces(storage)
        assert result == {"ns-a": NamespaceCounts(issues=1)}

    def test_empty_storage(self, temp_dogcats_dir: Path) -> None:
        """Empty storage returns empty dict."""
        from dogcat.storage import get_namespaces

        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        result = get_namespaces(storage, include_inbox=False)
        assert result == {}

    def test_pinned_namespaces_always_included(self, temp_dogcats_dir: Path) -> None:
        """Pinned namespaces appear even with no issues or proposals."""
        from dogcat.config import save_config
        from dogcat.storage import NamespaceCounts, get_namespaces

        save_config(str(temp_dogcats_dir), {"pinned_namespaces": ["pinned-ns"]})
        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)

        result = get_namespaces(
            storage, dogcats_dir=str(temp_dogcats_dir), include_inbox=False
        )
        assert result == {"pinned-ns": NamespaceCounts()}

    def test_pinned_namespace_with_existing_issues(
        self, temp_dogcats_dir: Path
    ) -> None:
        """Pinned namespace that also has issues shows correct counts."""
        from dogcat.config import save_config
        from dogcat.storage import NamespaceCounts, get_namespaces

        save_config(str(temp_dogcats_dir), {"pinned_namespaces": ["ns-a"]})
        storage_path = temp_dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path), create_dir=True)
        storage.create(Issue(id="a1", title="A1", namespace="ns-a"))

        result = get_namespaces(
            storage, dogcats_dir=str(temp_dogcats_dir), include_inbox=False
        )
        assert result == {"ns-a": NamespaceCounts(issues=1)}


class TestCreateIssueFactory:
    """Test ``JSONLStorage.create_issue`` factory.

    Regression for dogcat-6a1g: the namespace-lookup → IDGenerator → build
    Issue → create() pattern was duplicated at four call sites; the factory
    centralizes it.
    """

    def test_create_issue_generates_id(self, storage: JSONLStorage) -> None:
        """The factory mints an id from the IDGenerator under the given namespace."""
        issue = storage.create_issue(title="Hello", namespace="abc")
        assert issue.namespace == "abc"
        assert issue.id  # generated, non-empty
        assert issue.title == "Hello"

    def test_create_issue_persists(self, storage: JSONLStorage) -> None:
        """Returned issue is stored and resolvable by full_id."""
        issue = storage.create_issue(title="Persist me", namespace="t")
        loaded = storage.get(issue.full_id)
        assert loaded is not None
        assert loaded.title == "Persist me"

    def test_create_issue_passes_through_optional_fields(
        self, storage: JSONLStorage
    ) -> None:
        """All forwarded kwargs land on the constructed Issue."""
        from dogcat.models import IssueType, Status

        issue = storage.create_issue(
            title="Full",
            namespace="t",
            description="desc",
            status=Status.IN_PROGRESS,
            priority=1,
            issue_type=IssueType.BUG,
            owner="alice",
            labels=["a", "b"],
            external_ref="JIRA-1",
            design="design",
            acceptance="ok",
            notes="notes",
            created_by="bob",
            metadata={"manual": True},
        )
        assert issue.description == "desc"
        assert issue.status is Status.IN_PROGRESS
        assert issue.priority == 1
        assert issue.issue_type is IssueType.BUG
        assert issue.owner == "alice"
        assert issue.labels == ["a", "b"]
        assert issue.external_ref == "JIRA-1"
        assert issue.design == "design"
        assert issue.acceptance == "ok"
        assert issue.notes == "notes"
        assert issue.created_by == "bob"
        assert issue.metadata == {"manual": True}

    def test_create_issue_unique_ids(self, storage: JSONLStorage) -> None:
        """Two calls with the same title under the same namespace get distinct ids."""
        a = storage.create_issue(title="Same title", namespace="t")
        b = storage.create_issue(title="Same title", namespace="t")
        assert a.full_id != b.full_id


class TestIsDefaultBranch:
    """Test ``_is_default_branch`` git error handling.

    Regression for dogcat-5l16: any non-zero git returncode used to fall
    through to "safe to compact", silently disabling the feature-branch
    protection on permission errors / lock contention. Now only
    FileNotFoundError and "not a git repository" return True.
    """

    def test_main_branch_returns_true(
        self, storage: JSONLStorage, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """On main branch, eligible for compaction."""
        import subprocess

        def fake_run(
            *_args: object, **_kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(
                args=[], returncode=0, stdout="main\n", stderr=""
            )

        monkeypatch.setattr(subprocess, "run", fake_run)
        assert storage._is_default_branch() is True

    def test_feature_branch_returns_false(
        self, storage: JSONLStorage, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """On a feature branch, NOT eligible for compaction.

        Mocks dispatch on the git subcommand: ``rev-parse --abbrev-ref HEAD``
        returns the branch name; ``config init.defaultBranch`` returns rc=1
        (key unset) so the union with the user's configured default doesn't
        accidentally include the feature branch.
        """
        import subprocess

        def fake_run(
            argv: list[str], **_kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            if "config" in argv:
                return subprocess.CompletedProcess(
                    args=argv, returncode=1, stdout="", stderr=""
                )
            return subprocess.CompletedProcess(
                args=argv, returncode=0, stdout="feature/x\n", stderr=""
            )

        monkeypatch.setattr(subprocess, "run", fake_run)
        assert storage._is_default_branch() is False

    def test_init_default_branch_config_overrides(
        self, storage: JSONLStorage, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``init.defaultBranch=develop`` makes ``develop`` count as default."""
        import subprocess

        def fake_run(
            argv: list[str], **_kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            if "config" in argv:
                return subprocess.CompletedProcess(
                    args=argv, returncode=0, stdout="develop\n", stderr=""
                )
            return subprocess.CompletedProcess(
                args=argv, returncode=0, stdout="develop\n", stderr=""
            )

        monkeypatch.setattr(subprocess, "run", fake_run)
        assert storage._is_default_branch() is True

    def test_not_a_git_repo_returns_true(
        self, storage: JSONLStorage, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``not a git repository`` stderr is treated as 'no repo, safe'."""
        import subprocess

        def fake_run(
            *_args: object, **_kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(
                args=[],
                returncode=128,
                stdout="",
                stderr="fatal: not a git repository (or any parent up to ...)\n",
            )

        monkeypatch.setattr(subprocess, "run", fake_run)
        assert storage._is_default_branch() is True

    def test_git_not_installed_returns_true(
        self, storage: JSONLStorage, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If git is missing entirely, treat as no-repo and allow compaction."""
        import subprocess

        def fake_run(
            *_args: object, **_kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            msg = "git not on PATH"
            raise FileNotFoundError(msg)

        monkeypatch.setattr(subprocess, "run", fake_run)
        assert storage._is_default_branch() is True

    def test_permission_error_returns_false(
        self,
        storage: JSONLStorage,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Permission denied (non-zero rc, non-'no repo' stderr) blocks compaction."""
        import subprocess

        def fake_run(
            *_args: object, **_kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(
                args=[],
                returncode=128,
                stdout="",
                stderr="fatal: unable to read .git/HEAD: Permission denied\n",
            )

        monkeypatch.setattr(subprocess, "run", fake_run)
        with caplog.at_level("WARNING"):
            assert storage._is_default_branch() is False
        joined = " ".join(rec.getMessage() for rec in caplog.records)
        assert "git rev-parse failed" in joined
        assert "Permission denied" in joined
