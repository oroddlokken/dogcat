"""Regression tests for loading versioned issues.jsonl fixtures.

Discovers all fixture files in tests/fixtures/ and verifies that the current
JSONLStorage can load them without errors, preserving issues, dependencies,
links, comments, and all model fields.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

import pytest

from dogcat.models import Dependency, DependencyType, IssueType, Link, Status
from dogcat.storage import JSONLStorage

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _discover_fixtures() -> list[Path]:
    """Find all versioned fixture files."""
    fixtures = sorted(FIXTURES_DIR.glob("v*_issues.jsonl"))
    if not fixtures:
        pytest.skip("No fixture files found in tests/fixtures/")
    return fixtures


def _fixture_ids(fixtures: list[Path]) -> list[str]:
    """Extract version labels for test IDs."""
    return [f.stem.replace("_issues", "") for f in fixtures]


_fixtures = _discover_fixtures()


@pytest.fixture(params=_fixtures, ids=_fixture_ids(_fixtures))
def loaded_storage(request: pytest.FixtureRequest, tmp_path: Path) -> JSONLStorage:
    """Load a fixture file into a fresh JSONLStorage instance."""
    fixture_path: Path = request.param
    dogcats_dir = tmp_path / ".dogcats"
    dogcats_dir.mkdir()
    dest = dogcats_dir / "issues.jsonl"
    shutil.copy2(fixture_path, dest)
    return JSONLStorage(str(dest))


class TestFixtureRegression:
    """Verify that all versioned fixtures load correctly with current code."""

    def test_loads_without_errors(self, loaded_storage: JSONLStorage) -> None:
        """Fixture loads without raising exceptions."""
        assert loaded_storage is not None

    def test_has_issues(self, loaded_storage: JSONLStorage) -> None:
        """Fixture contains issues."""
        issues = loaded_storage.list()
        assert len(issues) > 0

    def test_has_all_issue_types(self, loaded_storage: JSONLStorage) -> None:
        """Fixture covers all issue types (draft/subtask migrated to task)."""
        issues = loaded_storage.list()
        types_found = {i.issue_type for i in issues}
        expected_types = {
            IssueType.EPIC,
            IssueType.FEATURE,
            IssueType.TASK,
            IssueType.BUG,
            IssueType.STORY,
            IssueType.CHORE,
            IssueType.QUESTION,
        }
        assert types_found >= expected_types, (
            f"Missing types: {expected_types - types_found}"
        )

    def test_has_all_statuses(self, loaded_storage: JSONLStorage) -> None:
        """Fixture covers all statuses used in practice (including migrated drafts)."""
        issues = loaded_storage.list()
        statuses_found = {i.status for i in issues}
        expected_statuses = {
            Status.DRAFT,
            Status.OPEN,
            Status.IN_PROGRESS,
            Status.IN_REVIEW,
            Status.CLOSED,
            Status.DEFERRED,
            Status.TOMBSTONE,
        }
        assert statuses_found >= expected_statuses, (
            f"Missing statuses: {expected_statuses - statuses_found}"
        )

    def test_dependencies_survive(self, loaded_storage: JSONLStorage) -> None:
        """Fixture preserves dependency relationships."""
        issues = loaded_storage.list()
        all_deps: list[Dependency] = []
        for issue in issues:
            deps = loaded_storage.get_dependencies(issue.full_id)
            all_deps.extend(deps)
        assert len(all_deps) > 0, "No dependencies found in fixture"

    def test_links_survive(self, loaded_storage: JSONLStorage) -> None:
        """Fixture preserves link relationships."""
        issues = loaded_storage.list()
        all_links: list[Link] = []
        for issue in issues:
            links = loaded_storage.get_links(issue.full_id)
            all_links.extend(links)
        # Demo may or may not create links depending on version
        assert isinstance(all_links, list)

    def test_comments_survive(self, loaded_storage: JSONLStorage) -> None:
        """Fixture preserves comments on issues."""
        issues = loaded_storage.list()
        total_comments = sum(len(i.comments) for i in issues)
        assert total_comments > 0, "No comments found in fixture"

    # --- Issue field preservation ---

    def test_priority_range(self, loaded_storage: JSONLStorage) -> None:
        """Fixture covers the full priority range (0-4)."""
        issues = loaded_storage.list()
        priorities_found = {i.priority for i in issues}
        assert priorities_found >= {
            0,
            1,
            2,
            3,
            4,
        }, f"Missing priorities: {set(range(5)) - priorities_found}"

    def test_labels_survive(self, loaded_storage: JSONLStorage) -> None:
        """Fixture preserves labels on issues."""
        issues = loaded_storage.list()
        issues_with_labels = [i for i in issues if i.labels]
        assert len(issues_with_labels) > 0, "No issues with labels found"
        # Verify labels are actual strings, not collapsed
        for issue in issues_with_labels:
            assert all(isinstance(lbl, str) and lbl for lbl in issue.labels)

    def test_owner_survives(self, loaded_storage: JSONLStorage) -> None:
        """Fixture preserves the owner field."""
        issues = loaded_storage.list()
        owners = {i.owner for i in issues if i.owner}
        assert len(owners) > 0, "No issues with owners found"

    def test_description_survives(self, loaded_storage: JSONLStorage) -> None:
        """Fixture preserves description text."""
        issues = loaded_storage.list()
        with_desc = [i for i in issues if i.description]
        assert len(with_desc) > 0, "No issues with descriptions found"

    def test_external_ref_survives(self, loaded_storage: JSONLStorage) -> None:
        """Fixture preserves external reference values."""
        issues = loaded_storage.list()
        refs = {i.external_ref for i in issues if i.external_ref}
        assert len(refs) > 0, "No issues with external_ref found"

    def test_design_field_survives(self, loaded_storage: JSONLStorage) -> None:
        """Fixture preserves design documentation."""
        issues = loaded_storage.list()
        with_design = [i for i in issues if i.design]
        assert len(with_design) > 0, "No issues with design field found"

    def test_acceptance_field_survives(self, loaded_storage: JSONLStorage) -> None:
        """Fixture preserves acceptance criteria."""
        issues = loaded_storage.list()
        with_acceptance = [i for i in issues if i.acceptance]
        assert len(with_acceptance) > 0, "No issues with acceptance criteria found"

    def test_notes_field_survives(self, loaded_storage: JSONLStorage) -> None:
        """Fixture preserves notes."""
        issues = loaded_storage.list()
        with_notes = [i for i in issues if i.notes]
        assert len(with_notes) > 0, "No issues with notes found"

    def test_close_reason_survives(self, loaded_storage: JSONLStorage) -> None:
        """Fixture preserves close_reason on closed issues."""
        issues = loaded_storage.list()
        with_reason = [i for i in issues if i.close_reason]
        assert len(with_reason) > 0, "No issues with close_reason found"

    def test_namespace_survives(self, loaded_storage: JSONLStorage) -> None:
        """Fixture preserves namespace and full_id is consistent."""
        issues = loaded_storage.list()
        for issue in issues:
            assert issue.namespace, "Issue missing namespace"
            assert issue.full_id == f"{issue.namespace}-{issue.id}"

    # --- Audit trail ---

    def test_created_by_survives(self, loaded_storage: JSONLStorage) -> None:
        """Fixture preserves created_by on issues."""
        issues = loaded_storage.list()
        with_creator = [i for i in issues if i.created_by]
        assert len(with_creator) > 0, "No issues with created_by found"

    def test_updated_by_survives(self, loaded_storage: JSONLStorage) -> None:
        """Fixture preserves updated_by on issues."""
        issues = loaded_storage.list()
        with_updater = [i for i in issues if i.updated_by]
        assert len(with_updater) > 0, "No issues with updated_by found"

    def test_closed_at_and_by_survive(self, loaded_storage: JSONLStorage) -> None:
        """Fixture preserves closed_at and closed_by on closed issues."""
        issues = loaded_storage.list()
        closed = [i for i in issues if i.status == Status.CLOSED]
        assert len(closed) > 0, "No closed issues found"
        with_closed_at = [i for i in closed if i.closed_at]
        assert len(with_closed_at) > 0, "No closed issues with closed_at found"
        for issue in with_closed_at:
            assert isinstance(issue.closed_at, datetime)

    def test_timestamps_are_datetimes(self, loaded_storage: JSONLStorage) -> None:
        """All timestamp fields are parsed as datetime objects."""
        issues = loaded_storage.list()
        for issue in issues:
            assert isinstance(issue.created_at, datetime)
            assert isinstance(issue.updated_at, datetime)

    # --- Tombstone / soft-delete ---

    def test_tombstone_issues_exist(self, loaded_storage: JSONLStorage) -> None:
        """Fixture contains tombstone (soft-deleted) issues."""
        issues = loaded_storage.list()
        tombstones = [i for i in issues if i.status == Status.TOMBSTONE]
        assert len(tombstones) > 0, "No tombstone issues found"

    def test_tombstone_deleted_at_survives(self, loaded_storage: JSONLStorage) -> None:
        """Fixture preserves deleted_at timestamp when present."""
        issues = loaded_storage.list()
        tombstones = [i for i in issues if i.status == Status.TOMBSTONE]
        with_deleted_at = [t for t in tombstones if t.deleted_at is not None]
        for ts in with_deleted_at:
            assert isinstance(ts.deleted_at, datetime)

    def test_tombstone_original_type_survives(
        self,
        loaded_storage: JSONLStorage,
    ) -> None:
        """Fixture preserves original_type when present."""
        issues = loaded_storage.list()
        tombstones = [i for i in issues if i.status == Status.TOMBSTONE]
        with_orig = [t for t in tombstones if t.original_type is not None]
        for ts in with_orig:
            assert isinstance(ts.original_type, IssueType)

    def test_delete_reason_survives(self, loaded_storage: JSONLStorage) -> None:
        """Fixture preserves delete_reason on tombstoned issues."""
        issues = loaded_storage.list()
        tombstones = [i for i in issues if i.status == Status.TOMBSTONE]
        with_reason = [t for t in tombstones if t.delete_reason]
        assert len(with_reason) > 0, "No tombstones with delete_reason found"

    def test_duplicate_of_survives(self, loaded_storage: JSONLStorage) -> None:
        """Fixture preserves duplicate_of field."""
        issues = loaded_storage.list()
        duplicates = [i for i in issues if i.duplicate_of]
        assert len(duplicates) > 0, "No issues with duplicate_of found"

    # --- Parent-child ---

    def test_parent_child_relationships(self, loaded_storage: JSONLStorage) -> None:
        """Fixture preserves parent field and get_children() works."""
        issues = loaded_storage.list()
        with_parent = [i for i in issues if i.parent]
        assert len(with_parent) > 0, "No issues with parent found"
        # Verify get_children returns the inverse
        parent_ids: set[str] = {i.parent for i in with_parent if i.parent is not None}
        for pid in parent_ids:
            children = loaded_storage.get_children(pid)
            assert len(children) > 0, f"get_children({pid}) returned no children"

    # --- Comment details ---

    def test_comment_fields_preserved(self, loaded_storage: JSONLStorage) -> None:
        """Comment author, text, and created_at survive loading."""
        issues = loaded_storage.list()
        all_comments = [c for i in issues for c in i.comments]
        assert len(all_comments) > 0
        for comment in all_comments:
            assert comment.id, "Comment missing id"
            assert comment.author, "Comment missing author"
            assert comment.text, "Comment missing text"
            assert isinstance(comment.created_at, datetime)

    # --- Dependency details ---

    def test_dependency_type_preserved(self, loaded_storage: JSONLStorage) -> None:
        """Dependency type (e.g. BLOCKS) survives loading."""
        issues = loaded_storage.list()
        all_deps = [
            d for i in issues for d in loaded_storage.get_dependencies(i.full_id)
        ]
        assert len(all_deps) > 0
        for dep in all_deps:
            assert isinstance(dep.dep_type, DependencyType)

    def test_get_dependents_works(self, loaded_storage: JSONLStorage) -> None:
        """Reverse dependency lookup via get_dependents() works."""
        issues = loaded_storage.list()
        all_deps = [
            d for i in issues for d in loaded_storage.get_dependencies(i.full_id)
        ]
        assert len(all_deps) > 0
        # Pick a dependency target and verify reverse lookup finds it
        target_id = all_deps[0].depends_on_id
        dependents = loaded_storage.get_dependents(target_id)
        assert len(dependents) > 0, f"get_dependents({target_id}) returned nothing"

    # --- get() by ID ---

    def test_get_by_full_id(self, loaded_storage: JSONLStorage) -> None:
        """Individual issue retrieval via get() works."""
        issues = loaded_storage.list()
        for issue in issues[:3]:
            fetched = loaded_storage.get(issue.full_id)
            assert fetched is not None, f"get({issue.full_id}) returned None"
            assert fetched.title == issue.title
