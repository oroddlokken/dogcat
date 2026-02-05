"""Tests for the benchmarking utility."""

import tempfile
from pathlib import Path

from benchmark import (
    DeterministicIssueGenerator,
    generate_test_data,
    run_benchmarks,
    write_test_jsonl,
)
from dogcat.models import IssueType, Status


class TestDeterministicIssueGenerator:
    """Tests for the DeterministicIssueGenerator class."""

    def test_deterministic_ids(self) -> None:
        """Same seed produces same IDs."""
        gen1 = DeterministicIssueGenerator(seed=123)
        gen2 = DeterministicIssueGenerator(seed=123)

        issues1 = gen1.generate_issues(10)
        issues2 = gen2.generate_issues(10)

        assert [i.id for i in issues1] == [i.id for i in issues2]

    def test_deterministic_titles(self) -> None:
        """Same seed produces same titles."""
        gen1 = DeterministicIssueGenerator(seed=456)
        gen2 = DeterministicIssueGenerator(seed=456)

        issues1 = gen1.generate_issues(10)
        issues2 = gen2.generate_issues(10)

        assert [i.title for i in issues1] == [i.title for i in issues2]

    def test_different_seeds_produce_different_data(self) -> None:
        """Different seeds produce different data."""
        gen1 = DeterministicIssueGenerator(seed=1)
        gen2 = DeterministicIssueGenerator(seed=2)

        issues1 = gen1.generate_issues(10)
        issues2 = gen2.generate_issues(10)

        # Titles should differ (with high probability)
        assert [i.title for i in issues1] != [i.title for i in issues2]

    def test_issues_have_varied_attributes(self) -> None:
        """Generated issues have varied statuses, priorities, and types."""
        gen = DeterministicIssueGenerator(seed=42)
        issues = gen.generate_issues(100)

        statuses = {issue.status for issue in issues}
        priorities = {issue.priority for issue in issues}
        types = {issue.issue_type for issue in issues}
        owners = {issue.owner for issue in issues}

        # Should have variety
        assert len(statuses) >= 3
        assert len(priorities) >= 3
        assert len(types) >= 5
        assert len(owners) >= 3

    def test_issues_have_descriptions_and_notes(self) -> None:
        """Some issues have descriptions and notes."""
        gen = DeterministicIssueGenerator(seed=42)
        issues = gen.generate_issues(50)

        with_description = sum(1 for i in issues if i.description is not None)
        with_notes = sum(1 for i in issues if i.notes is not None)
        with_acceptance = sum(1 for i in issues if i.acceptance is not None)

        # Most should have descriptions (only 1/9 are None)
        assert with_description > 30
        # Some should have notes
        assert with_notes > 10
        # Some should have acceptance criteria
        assert with_acceptance > 10

    def test_closed_issues_have_closed_at(self) -> None:
        """Closed issues have closed_at timestamp."""
        gen = DeterministicIssueGenerator(seed=42)
        issues = gen.generate_issues(100)

        closed = [i for i in issues if i.status == Status.CLOSED]
        assert len(closed) > 0
        assert all(i.closed_at is not None for i in closed)

    def test_tombstone_issues_have_deleted_at(self) -> None:
        """Tombstoned issues have deleted_at and delete_reason."""
        gen = DeterministicIssueGenerator(seed=42)
        issues = gen.generate_issues(100)

        tombstones = [i for i in issues if i.status == Status.TOMBSTONE]
        # May be 0 due to randomness, so only check if we have some
        for t in tombstones:
            assert t.deleted_at is not None
            assert t.delete_reason is not None


class TestParentChildRelations:
    """Tests for parent-child relationship generation."""

    def test_generates_parent_child_relations(self) -> None:
        """Generator creates parent-child relationships."""
        gen = DeterministicIssueGenerator(seed=42)
        issues = gen.generate_issues(100)
        gen.generate_parent_child_relations(issues)

        with_parent = [i for i in issues if i.parent is not None]
        assert len(with_parent) > 0

    def test_parents_are_valid_issue_ids(self) -> None:
        """Parent IDs reference existing issues."""
        gen = DeterministicIssueGenerator(seed=42)
        issues = gen.generate_issues(100)
        gen.generate_parent_child_relations(issues)

        issue_ids = {i.id for i in issues}
        for issue in issues:
            if issue.parent is not None:
                assert issue.parent in issue_ids

    def test_parents_are_appropriate_types(self) -> None:
        """Parents are epics, features, or stories."""
        gen = DeterministicIssueGenerator(seed=42)
        issues = gen.generate_issues(100)
        gen.generate_parent_child_relations(issues)

        issue_map = {i.id: i for i in issues}
        parent_types = {IssueType.EPIC, IssueType.FEATURE, IssueType.STORY}

        for issue in issues:
            if issue.parent is not None:
                parent = issue_map[issue.parent]
                assert parent.issue_type in parent_types


class TestComments:
    """Tests for comment generation."""

    def test_some_issues_have_comments(self) -> None:
        """Some issues have comments."""
        gen = DeterministicIssueGenerator(seed=42)
        issues = gen.generate_issues(100)

        with_comments = [i for i in issues if i.comments]
        assert len(with_comments) > 0

    def test_comments_have_required_fields(self) -> None:
        """Comments have id, author, text, and created_at."""
        gen = DeterministicIssueGenerator(seed=42)
        issues = gen.generate_issues(100)

        for issue in issues:
            for comment in issue.comments:
                assert comment.id is not None
                assert comment.author is not None
                assert comment.text is not None
                assert comment.created_at is not None
                assert comment.issue_id == issue.id


class TestExternalRefAndDesign:
    """Tests for external_ref, design, and metadata generation."""

    def test_some_issues_have_external_ref(self) -> None:
        """Some issues have external references."""
        gen = DeterministicIssueGenerator(seed=42)
        issues = gen.generate_issues(100)

        with_ref = sum(1 for i in issues if i.external_ref is not None)
        assert with_ref > 0

    def test_some_issues_have_design(self) -> None:
        """Some issues have design docs."""
        gen = DeterministicIssueGenerator(seed=42)
        issues = gen.generate_issues(100)

        with_design = sum(1 for i in issues if i.design is not None)
        assert with_design > 0

    def test_some_issues_have_metadata(self) -> None:
        """Some issues have metadata."""
        gen = DeterministicIssueGenerator(seed=42)
        issues = gen.generate_issues(100)

        with_metadata = sum(1 for i in issues if i.metadata)
        assert with_metadata > 0


class TestDuplicates:
    """Tests for duplicate marking."""

    def test_some_issues_marked_as_duplicates(self) -> None:
        """Some issues are marked as duplicates."""
        gen = DeterministicIssueGenerator(seed=42)
        issues = gen.generate_issues(100)
        gen.generate_duplicate_relations(issues)

        duplicates = [i for i in issues if i.duplicate_of is not None]
        assert len(duplicates) > 0

    def test_duplicates_reference_valid_issues(self) -> None:
        """Duplicate_of references existing issues."""
        gen = DeterministicIssueGenerator(seed=42)
        issues = gen.generate_issues(100)
        gen.generate_duplicate_relations(issues)

        issue_ids = {i.id for i in issues}
        for issue in issues:
            if issue.duplicate_of is not None:
                assert issue.duplicate_of in issue_ids


class TestLinks:
    """Tests for link generation."""

    def test_generates_links(self) -> None:
        """Generator creates links."""
        gen = DeterministicIssueGenerator(seed=42)
        issues = gen.generate_issues(100)
        links = gen.generate_links(issues)

        assert len(links) > 0

    def test_links_reference_valid_issues(self) -> None:
        """Link IDs reference existing issues."""
        gen = DeterministicIssueGenerator(seed=42)
        issues = gen.generate_issues(100)
        links = gen.generate_links(issues)

        issue_ids = {i.id for i in issues}
        for link in links:
            assert link.from_id in issue_ids
            assert link.to_id in issue_ids

    def test_links_have_varied_types(self) -> None:
        """Links have various link types."""
        gen = DeterministicIssueGenerator(seed=42)
        issues = gen.generate_issues(200)
        links = gen.generate_links(issues)

        link_types = {link.link_type for link in links}
        assert len(link_types) >= 2


class TestDependencies:
    """Tests for dependency generation."""

    def test_generates_dependencies(self) -> None:
        """Generator creates dependencies."""
        gen = DeterministicIssueGenerator(seed=42)
        issues = gen.generate_issues(100)
        deps = gen.generate_dependencies(issues)

        assert len(deps) > 0

    def test_dependencies_reference_valid_issues(self) -> None:
        """Dependency IDs reference existing issues."""
        gen = DeterministicIssueGenerator(seed=42)
        issues = gen.generate_issues(100)
        deps = gen.generate_dependencies(issues)

        issue_ids = {i.id for i in issues}
        for dep in deps:
            assert dep.issue_id in issue_ids
            assert dep.depends_on_id in issue_ids

    def test_no_self_dependencies(self) -> None:
        """No issue depends on itself."""
        gen = DeterministicIssueGenerator(seed=42)
        issues = gen.generate_issues(100)
        deps = gen.generate_dependencies(issues)

        for dep in deps:
            assert dep.issue_id != dep.depends_on_id


class TestGenerateTestData:
    """Tests for the generate_test_data function."""

    def test_returns_issues_dependencies_and_links(self) -> None:
        """Returns tuple of issues, dependencies, and links."""
        issues, deps, links = generate_test_data(50, seed=42)

        assert len(issues) == 50
        assert len(deps) > 0
        assert len(links) > 0

    def test_deterministic(self) -> None:
        """Same seed produces same results."""
        issues1, deps1, links1 = generate_test_data(50, seed=42)
        issues2, deps2, links2 = generate_test_data(50, seed=42)

        assert [i.id for i in issues1] == [i.id for i in issues2]
        assert len(deps1) == len(deps2)
        assert len(links1) == len(links2)


class TestWriteTestJsonl:
    """Tests for write_test_jsonl function."""

    def test_writes_file(self) -> None:
        """Writes a valid JSONL file."""
        issues, deps, links = generate_test_data(10, seed=42)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.jsonl"
            write_test_jsonl(issues, deps, links, path)

            assert path.exists()
            lines = path.read_text().strip().split("\n")
            # Issues + dependencies + links
            assert len(lines) == len(issues) + len(deps) + len(links)


class TestRunBenchmarks:
    """Tests for run_benchmarks function."""

    def test_returns_results(self) -> None:
        """Returns results for each count."""
        results = run_benchmarks(counts=[10, 20], iterations=1, verbose=False)

        assert len(results) == 2
        assert 10 in results
        assert 20 in results

    def test_results_have_timing_stats(self) -> None:
        """Results include timing statistics."""
        results = run_benchmarks(counts=[10], iterations=2, verbose=False)

        stats = results[10]
        assert "avg_ms" in stats
        assert "min_ms" in stats
        assert "max_ms" in stats
        assert "median_ms" in stats
        assert "stdev_ms" in stats
        assert stats["avg_ms"] > 0
