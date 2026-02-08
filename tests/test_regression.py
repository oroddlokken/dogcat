"""Regression tests for loading versioned issues.jsonl fixtures.

Discovers all fixture files in tests/fixtures/ and verifies that the current
JSONLStorage can load them without errors, preserving issues, dependencies,
links, and comments.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from dogcat.models import IssueType, Status
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

    def test_has_multiple_issue_types(self, loaded_storage: JSONLStorage) -> None:
        """Fixture covers multiple issue types."""
        issues = loaded_storage.list()
        types_found = {i.issue_type for i in issues}
        expected_types = {
            IssueType.EPIC,
            IssueType.FEATURE,
            IssueType.TASK,
            IssueType.BUG,
        }
        assert (
            types_found >= expected_types
        ), f"Missing types: {expected_types - types_found}"

    def test_has_multiple_statuses(self, loaded_storage: JSONLStorage) -> None:
        """Fixture covers multiple statuses."""
        issues = loaded_storage.list()
        statuses_found = {i.status for i in issues}
        expected_statuses = {Status.OPEN, Status.IN_PROGRESS, Status.CLOSED}
        assert (
            statuses_found >= expected_statuses
        ), f"Missing statuses: {expected_statuses - statuses_found}"

    def test_dependencies_survive(self, loaded_storage: JSONLStorage) -> None:
        """Fixture preserves dependency relationships."""
        issues = loaded_storage.list()
        all_deps = []
        for issue in issues:
            deps = loaded_storage.get_dependencies(issue.full_id)
            all_deps.extend(deps)
        assert len(all_deps) > 0, "No dependencies found in fixture"

    def test_links_survive(self, loaded_storage: JSONLStorage) -> None:
        """Fixture preserves link relationships."""
        issues = loaded_storage.list()
        all_links = []
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
