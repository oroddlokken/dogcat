#!/usr/bin/env python
"""Benchmarking utility for dogcat storage operations.

Tests loading performance with varying numbers of issues:
500, 1000, 2000, 5000, 10000 issues.

Uses deterministic random generation for reproducible results.
"""

from __future__ import annotations

import random
import statistics
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import orjson

from dogcat.models import (
    Comment,
    Dependency,
    DependencyType,
    Issue,
    IssueType,
    Link,
    Status,
    issue_to_dict,
)
from dogcat.storage import JSONLStorage

# Number of issues to benchmark
ISSUE_COUNTS = [500, 1000, 2000, 5000, 10000, 25000]

# Number of times to run each benchmark for averaging
ITERATIONS = 3

# Random seed for deterministic generation
DEFAULT_SEED = 42

# Sample data for realistic issue generation
TITLE_VERBS = [
    "Implement",
    "Fix",
    "Add",
    "Update",
    "Refactor",
    "Remove",
    "Optimize",
    "Debug",
    "Test",
    "Document",
    "Review",
    "Migrate",
    "Integrate",
    "Configure",
    "Deploy",
]

TITLE_SUBJECTS = [
    "user authentication",
    "database connection pooling",
    "API rate limiting",
    "error handling",
    "logging system",
    "cache invalidation",
    "search functionality",
    "notification service",
    "payment processing",
    "file upload",
    "email templates",
    "dashboard widgets",
    "export feature",
    "import wizard",
    "settings page",
    "user profiles",
    "permission system",
    "audit logging",
    "backup mechanism",
    "report generation",
    "data validation",
    "session management",
    "webhook handlers",
    "batch processing",
    "queue workers",
]

TITLE_CONTEXTS = [
    "for mobile app",
    "in admin panel",
    "for API v2",
    "on production",
    "for enterprise tier",
    "in background jobs",
    "for scheduled tasks",
    "in user dashboard",
    "for analytics module",
    "in checkout flow",
]

OWNERS = [
    "alice@example.com",
    "bob@example.com",
    "carol@example.com",
    "david@example.com",
    "eve@example.com",
    "frank@example.com",
    "grace@example.com",
    "henry@example.com",
    None,  # Some issues have no owner
    None,
]

DESCRIPTION_TEMPLATES = [
    "We need to {verb} the {subject} to improve system reliability.",
    "Users have reported issues with {subject}. This task addresses those concerns.",
    "As part of the Q{quarter} roadmap, we're updating {subject}.",
    "Technical debt: {subject} needs attention before the next release.",
    "Feature request from customer: enhance {subject} capabilities.",
    "Security review identified improvements needed in {subject}.",
    "Performance profiling shows {subject} is a bottleneck.",
    "Following best practices, we should refactor {subject}.",
    None,  # Some issues have no description
]

NOTES_TEMPLATES = [
    "Discussed in standup on {date}. Team agreed on approach.",
    "Blocked by external dependency. Waiting for vendor response.",
    "Spike completed. Estimated effort: {points} story points.",
    "Related to ticket from last sprint. See linked issues.",
    "Customer escalation - high visibility item.",
    "Consider backwards compatibility during implementation.",
    "Needs code review from senior engineer.",
    "Documentation update required after completion.",
    None,
    None,  # Many issues have no notes
]

ACCEPTANCE_TEMPLATES = [
    "- [ ] Unit tests pass\n- [ ] Integration tests pass\n- [ ] Code reviewed",
    "- [ ] Feature works as specified\n- [ ] No regressions\n- [ ] Docs updated",
    "- [ ] Performance meets SLA\n- [ ] Monitoring in place\n- [ ] Rollback plan",
    "- [ ] Manual QA completed\n- [ ] Stakeholder sign-off\n- [ ] Release notes",
    None,
    None,
    None,  # Many issues have no acceptance criteria
]

DESIGN_TEMPLATES = [
    "## Approach\nUse existing {component} pattern.\n\n## Changes\n"
    "- Modify {file}\n- Add tests",
    "Follow RFC-{rfc_num} specification.\nSee design doc: https://docs.example.com/design/{doc_id}",
    "## Architecture\n```\nClient -> API -> Service -> DB\n```\n\nNo breaking changes.",
    "Spike findings: Option B is preferred. Lower complexity, better performance.",
    None,
    None,
    None,
    None,  # Most issues have no design doc
]

LABELS = [
    "backend",
    "frontend",
    "infrastructure",
    "security",
    "performance",
    "ux",
    "api",
    "database",
    "urgent",
    "tech-debt",
    "documentation",
    "testing",
]

COMMENT_TEMPLATES = [
    "I've started looking into this. Initial findings suggest we need to {action}.",
    "Blocked on {blocker}. Will resume once that's resolved.",
    "PR ready for review: https://github.com/example/repo/pull/{pr_num}",
    "Tested locally, works as expected. Moving to QA.",
    "Found a related issue while working on this. Created {related_id} to track it.",
    "@{mention} can you review the approach here?",
    "Updated the implementation based on feedback. PTAL.",
    "This is more complex than expected. Splitting into subtasks.",
    "Closing as duplicate of {dup_id}.",
    "Deployed to staging. Please verify.",
    "Reverted due to {reason}. Will reattempt after fixing.",
    "Added unit tests. Coverage now at {coverage}%.",
]

EXTERNAL_REF_TEMPLATES = [
    "https://github.com/example/repo/issues/{num}",
    "https://github.com/example/repo/pull/{num}",
    "JIRA-{num}",
    "https://linear.app/team/issue/TEAM-{num}",
    "https://trello.com/c/{card_id}",
    None,
    None,
    None,  # Many issues have no external ref
]

METADATA_KEYS = [
    "story_points",
    "sprint",
    "component",
    "affected_version",
    "fix_version",
    "environment",
    "browser",
    "os",
    "customer_id",
    "severity",
]

LINK_TYPES = [
    "relates_to",
    "duplicates",
    "is_duplicated_by",
    "blocks",
    "is_blocked_by",
    "clones",
    "is_cloned_by",
]


class DeterministicIssueGenerator:
    """Generates realistic test issues with deterministic randomness."""

    def __init__(self, seed: int = DEFAULT_SEED, prefix: str = "dc") -> None:
        """Initialize the generator.

        Args:
            seed: Random seed for reproducibility
            prefix: ID prefix for generated issues
        """
        self.rng = random.Random(seed)
        self.prefix = prefix
        self.issue_counter = 0
        self.comment_counter = 0
        self.generated_ids: list[str] = []

        # Base timestamp for deterministic dates
        self.base_time = datetime(2024, 1, 1, 9, 0, 0, tzinfo=timezone.utc)

    def _generate_id(self) -> str:
        """Generate a deterministic issue ID."""
        self.issue_counter += 1
        # Use counter-based ID for determinism
        hash_part = f"{self.issue_counter:04x}"
        return f"{self.prefix}-{hash_part}"

    def _generate_comment_id(self) -> str:
        """Generate a deterministic comment ID."""
        self.comment_counter += 1
        # Use a deterministic UUID-like format
        return f"comment-{self.comment_counter:08x}"

    def _random_datetime(self, days_offset: int, hours_variance: int = 8) -> datetime:
        """Generate a datetime with some variance."""
        base = self.base_time + timedelta(days=days_offset)
        hours = self.rng.randint(0, hours_variance)
        minutes = self.rng.randint(0, 59)
        return base + timedelta(hours=hours, minutes=minutes)

    def _generate_title(self) -> str:
        """Generate a realistic issue title."""
        verb = self.rng.choice(TITLE_VERBS)
        subject = self.rng.choice(TITLE_SUBJECTS)

        # Sometimes add context
        if self.rng.random() < 0.3:
            context = self.rng.choice(TITLE_CONTEXTS)
            return f"{verb} {subject} {context}"
        return f"{verb} {subject}"

    def _generate_description(self) -> str | None:
        """Generate a realistic description."""
        template = self.rng.choice(DESCRIPTION_TEMPLATES)
        if template is None:
            return None

        return template.format(
            verb=self.rng.choice(TITLE_VERBS).lower(),
            subject=self.rng.choice(TITLE_SUBJECTS),
            quarter=self.rng.randint(1, 4),
        )

    def _generate_notes(self) -> str | None:
        """Generate realistic notes."""
        template = self.rng.choice(NOTES_TEMPLATES)
        if template is None:
            return None

        return template.format(
            date=f"2024-{self.rng.randint(1, 12):02d}-{self.rng.randint(1, 28):02d}",
            points=self.rng.choice([1, 2, 3, 5, 8, 13]),
        )

    def _generate_acceptance(self) -> str | None:
        """Generate acceptance criteria."""
        return self.rng.choice(ACCEPTANCE_TEMPLATES)

    def _generate_design(self) -> str | None:
        """Generate design documentation."""
        template = self.rng.choice(DESIGN_TEMPLATES)
        if template is None:
            return None

        return template.format(
            component=self.rng.choice(["repository", "service", "controller", "util"]),
            file=self.rng.choice(["api.py", "models.py", "handlers.ts", "utils.go"]),
            rfc_num=self.rng.randint(100, 999),
            doc_id=f"{self.rng.randint(1000, 9999)}",
        )

    def _generate_external_ref(self) -> str | None:
        """Generate an external reference."""
        template = self.rng.choice(EXTERNAL_REF_TEMPLATES)
        if template is None:
            return None

        return template.format(
            num=self.rng.randint(100, 9999),
            card_id=f"{self.rng.randint(10000000, 99999999):x}",
        )

    def _generate_metadata(self) -> dict[str, str | int | None]:
        """Generate arbitrary metadata."""
        # Most issues have no metadata
        if self.rng.random() > 0.3:
            return {}

        metadata: dict[str, str | int | None] = {}
        num_keys = self.rng.randint(1, 4)
        keys = self.rng.sample(METADATA_KEYS, num_keys)

        for key in keys:
            if key == "story_points":
                metadata[key] = self.rng.choice([1, 2, 3, 5, 8, 13, 21])
            elif key == "sprint":
                metadata[key] = f"Sprint {self.rng.randint(1, 52)}"
            elif key == "component":
                metadata[key] = self.rng.choice(
                    ["auth", "api", "ui", "db", "infra", "core"],
                )
            elif key == "affected_version" or key == "fix_version":
                metadata[key] = f"{self.rng.randint(1, 5)}.{self.rng.randint(0, 20)}.0"
            elif key == "environment":
                metadata[key] = self.rng.choice(["dev", "staging", "prod"])
            elif key == "browser":
                metadata[key] = self.rng.choice(["Chrome", "Firefox", "Safari", "Edge"])
            elif key == "os":
                metadata[key] = self.rng.choice(
                    ["macOS", "Windows", "Linux", "iOS", "Android"],
                )
            elif key == "customer_id":
                metadata[key] = f"cust_{self.rng.randint(1000, 9999)}"
            elif key == "severity":
                metadata[key] = self.rng.choice(
                    ["critical", "major", "minor", "trivial"],
                )

        return metadata

    def _generate_labels(self) -> list[str]:
        """Generate a list of labels."""
        num_labels = self.rng.randint(0, 3)
        if num_labels == 0:
            return []
        return self.rng.sample(LABELS, num_labels)

    def _generate_comments(
        self,
        issue_id: str,
        created_at: datetime,
        count: int,
    ) -> list[Comment]:
        """Generate comments for an issue.

        Args:
            issue_id: The issue ID
            created_at: Issue creation time (comments come after)
            count: Number of comments to generate

        Returns:
            List of comments
        """
        comments: list[Comment] = []

        for i in range(count):
            template = self.rng.choice(COMMENT_TEMPLATES)
            text = template.format(
                action=self.rng.choice(
                    ["refactor the module", "add error handling", "update the schema"],
                ),
                blocker=self.rng.choice(
                    ["API changes", "infrastructure", "dependency upgrade"],
                ),
                pr_num=self.rng.randint(100, 9999),
                related_id=f"{self.prefix}-{self.rng.randint(1, 1000):04x}",
                mention=self.rng.choice(["alice", "bob", "carol", "david", "eve"]),
                dup_id=f"{self.prefix}-{self.rng.randint(1, 1000):04x}",
                reason=self.rng.choice(
                    ["test failures", "performance regression", "user reports"],
                ),
                coverage=self.rng.randint(70, 99),
            )

            comment_time = created_at + timedelta(
                hours=self.rng.randint(1, 72 * (i + 1)),
                minutes=self.rng.randint(0, 59),
            )

            comment = Comment(
                id=self._generate_comment_id(),
                issue_id=issue_id,
                author=self.rng.choice([o for o in OWNERS if o is not None]),
                text=text,
                created_at=comment_time,
            )
            comments.append(comment)

        return comments

    def generate_issue(self, index: int) -> Issue:
        """Generate a single realistic issue.

        Args:
            index: Issue index (affects timestamps)

        Returns:
            Generated Issue
        """
        issue_id = self._generate_id()
        self.generated_ids.append(issue_id)

        # Timestamps
        days_offset = index // 10  # ~10 issues per day
        created_at = self._random_datetime(days_offset)
        updated_at = created_at + timedelta(
            hours=self.rng.randint(0, 48),
            minutes=self.rng.randint(0, 59),
        )

        # Status with realistic distribution
        status_weights = [
            (Status.OPEN, 0.3),
            (Status.IN_PROGRESS, 0.2),
            (Status.IN_REVIEW, 0.1),
            (Status.BLOCKED, 0.05),
            (Status.DEFERRED, 0.05),
            (Status.CLOSED, 0.25),
            (Status.TOMBSTONE, 0.05),
        ]
        status = self.rng.choices(
            [s for s, _ in status_weights],
            weights=[w for _, w in status_weights],
        )[0]

        # Closed/deleted timestamps for appropriate statuses
        closed_at = None
        deleted_at = None
        delete_reason = None
        original_type = None

        # Issue type with realistic distribution
        type_weights = [
            (IssueType.TASK, 0.25),
            (IssueType.BUG, 0.2),
            (IssueType.FEATURE, 0.2),
            (IssueType.STORY, 0.1),
            (IssueType.CHORE, 0.1),
            (IssueType.EPIC, 0.05),
            (IssueType.SUBTASK, 0.05),
            (IssueType.QUESTION, 0.03),
            (IssueType.DRAFT, 0.02),
        ]
        issue_type = self.rng.choices(
            [t for t, _ in type_weights],
            weights=[w for _, w in type_weights],
        )[0]

        if status == Status.CLOSED:
            closed_at = updated_at + timedelta(hours=self.rng.randint(1, 24))
        elif status == Status.TOMBSTONE:
            deleted_at = updated_at + timedelta(hours=self.rng.randint(1, 24))
            delete_reason = self.rng.choice(
                [
                    "Duplicate of another issue",
                    "No longer relevant",
                    "Created in error",
                    "Superseded by new approach",
                ],
            )
            original_type = issue_type

        # Generate comments (0-5, weighted toward fewer)
        num_comments = self.rng.choices(
            [0, 1, 2, 3, 4, 5],
            weights=[0.3, 0.25, 0.2, 0.15, 0.07, 0.03],
        )[0]
        comments = self._generate_comments(issue_id, created_at, num_comments)

        return Issue(
            id=issue_id,
            title=self._generate_title(),
            description=self._generate_description(),
            status=status,
            priority=self.rng.choices(
                [0, 1, 2, 3, 4],
                weights=[0.05, 0.15, 0.5, 0.2, 0.1],
            )[0],
            issue_type=issue_type,
            owner=self.rng.choice(OWNERS),
            labels=self._generate_labels(),
            external_ref=self._generate_external_ref(),
            design=self._generate_design(),
            acceptance=self._generate_acceptance(),
            notes=self._generate_notes(),
            created_at=created_at,
            created_by=self.rng.choice(OWNERS),
            updated_at=updated_at,
            updated_by=self.rng.choice(OWNERS),
            closed_at=closed_at,
            closed_by=self.rng.choice(OWNERS) if closed_at else None,
            deleted_at=deleted_at,
            deleted_by=self.rng.choice(OWNERS) if deleted_at else None,
            delete_reason=delete_reason,
            original_type=original_type,
            comments=comments,
            metadata=self._generate_metadata(),
        )

    def generate_issues(self, count: int) -> list[Issue]:
        """Generate multiple issues.

        Args:
            count: Number of issues to generate

        Returns:
            List of generated issues
        """
        self.generated_ids = []
        self.comment_counter = 0
        return [self.generate_issue(i) for i in range(count)]

    def generate_parent_child_relations(
        self,
        issues: list[Issue],
        relation_ratio: float = 0.15,
    ) -> None:
        """Add parent-child relationships to issues.

        Modifies issues in place to set parent field.
        Epics become parents, subtasks and some tasks become children.

        Args:
            issues: List of issues to modify
            relation_ratio: Fraction of issues to make children
        """
        # Find potential parents (epics, features, stories)
        parent_types = {IssueType.EPIC, IssueType.FEATURE, IssueType.STORY}
        potential_parents = [i for i in issues if i.issue_type in parent_types]

        if not potential_parents:
            return

        # Find potential children (subtasks, tasks, bugs)
        child_types = {IssueType.SUBTASK, IssueType.TASK, IssueType.BUG}
        potential_children = [i for i in issues if i.issue_type in child_types]

        num_children = int(len(potential_children) * relation_ratio)
        children_to_assign = self.rng.sample(
            potential_children,
            min(num_children, len(potential_children)),
        )

        for child in children_to_assign:
            parent = self.rng.choice(potential_parents)
            # Don't make something its own parent
            if parent.id != child.id:
                child.parent = parent.id

    def generate_duplicate_relations(
        self,
        issues: list[Issue],
        duplicate_ratio: float = 0.03,
    ) -> None:
        """Mark some issues as duplicates of others.

        Args:
            issues: List of issues to modify
            duplicate_ratio: Fraction of issues to mark as duplicates
        """
        num_duplicates = int(len(issues) * duplicate_ratio)
        if num_duplicates == 0:
            return

        # Pick issues to be duplicates (prefer closed ones)
        closed_issues = [i for i in issues if i.status == Status.CLOSED]
        open_issues = [i for i in issues if i.status != Status.CLOSED]

        duplicates_to_mark = self.rng.sample(
            closed_issues,
            min(num_duplicates, len(closed_issues)),
        )

        for dup in duplicates_to_mark:
            # Pick a different issue as the original
            potential_originals = [i for i in open_issues if i.id != dup.id]
            if potential_originals:
                original = self.rng.choice(potential_originals)
                dup.duplicate_of = original.id

    def generate_dependencies(
        self,
        issues: list[Issue],
        dependency_ratio: float = 0.1,
    ) -> list[Dependency]:
        """Generate dependencies between issues.

        Args:
            issues: List of issues
            dependency_ratio: Fraction of issues to have dependencies

        Returns:
            List of dependencies
        """
        dependencies: list[Dependency] = []
        issue_ids = [i.id for i in issues]

        num_deps = int(len(issues) * dependency_ratio)

        for _ in range(num_deps):
            # Pick two different issues
            if len(issue_ids) < 2:
                break

            issue_id, depends_on_id = self.rng.sample(issue_ids, 2)

            # Avoid duplicate dependencies
            existing = {(d.issue_id, d.depends_on_id) for d in dependencies}
            if (issue_id, depends_on_id) in existing:
                continue

            dep = Dependency(
                issue_id=issue_id,
                depends_on_id=depends_on_id,
                dep_type=DependencyType.BLOCKS,
                created_at=self._random_datetime(self.rng.randint(0, 100)),
                created_by=self.rng.choice(OWNERS),
            )
            dependencies.append(dep)

        return dependencies

    def generate_links(
        self,
        issues: list[Issue],
        link_ratio: float = 0.08,
    ) -> list[Link]:
        """Generate links between issues.

        Args:
            issues: List of issues
            link_ratio: Fraction of issues to have links

        Returns:
            List of links
        """
        links: list[Link] = []
        issue_ids = [i.id for i in issues]

        num_links = int(len(issues) * link_ratio)

        for _ in range(num_links):
            if len(issue_ids) < 2:
                break

            from_id, to_id = self.rng.sample(issue_ids, 2)

            # Avoid duplicate links
            existing = {(ln.from_id, ln.to_id) for ln in links}
            if (from_id, to_id) in existing:
                continue

            link = Link(
                from_id=from_id,
                to_id=to_id,
                link_type=self.rng.choice(LINK_TYPES),
                created_at=self._random_datetime(self.rng.randint(0, 100)),
                created_by=self.rng.choice(OWNERS),
            )
            links.append(link)

        return links


def generate_test_data(
    count: int,
    seed: int = DEFAULT_SEED,
    prefix: str = "dc",
) -> tuple[list[Issue], list[Dependency], list[Link]]:
    """Generate test issues, dependencies, and links.

    Args:
        count: Number of issues to generate
        seed: Random seed for determinism
        prefix: ID prefix to use

    Returns:
        Tuple of (issues, dependencies, links)
    """
    generator = DeterministicIssueGenerator(seed=seed, prefix=prefix)
    issues = generator.generate_issues(count)
    generator.generate_parent_child_relations(issues)
    generator.generate_duplicate_relations(issues)
    dependencies = generator.generate_dependencies(issues)
    links = generator.generate_links(issues)
    return issues, dependencies, links


def write_test_jsonl(
    issues: list[Issue],
    dependencies: list[Dependency],
    links: list[Link],
    path: Path,
) -> None:
    """Write issues, dependencies, and links to a JSONL file.

    Args:
        issues: List of issues to write
        dependencies: List of dependencies to write
        links: List of links to write
        path: Path to write to
    """
    with path.open("wb") as f:
        # Write issues
        for issue in issues:
            data = issue_to_dict(issue)
            f.write(orjson.dumps(data))
            f.write(b"\n")

        # Write dependencies
        for dep in dependencies:
            dep_data = {
                "issue_id": dep.issue_id,
                "depends_on_id": dep.depends_on_id,
                "type": dep.dep_type.value,
                "created_at": dep.created_at.isoformat(),
                "created_by": dep.created_by,
            }
            f.write(orjson.dumps(dep_data))
            f.write(b"\n")

        # Write links
        for link in links:
            link_data = {
                "from_id": link.from_id,
                "to_id": link.to_id,
                "link_type": link.link_type,
                "created_at": link.created_at.isoformat(),
                "created_by": link.created_by,
            }
            f.write(orjson.dumps(link_data))
            f.write(b"\n")


def benchmark_load(
    storage_path: Path,
    iterations: int = ITERATIONS,
) -> dict[str, float]:
    """Benchmark loading issues from storage.

    Args:
        storage_path: Path to the JSONL file
        iterations: Number of times to run the benchmark

    Returns:
        Dictionary with timing statistics
    """
    times: list[float] = []

    for _ in range(iterations):
        # Create storage instance (triggers _load in __init__)
        start = time.perf_counter()
        storage = JSONLStorage(path=str(storage_path), create_dir=False)
        end = time.perf_counter()

        elapsed = (end - start) * 1000  # Convert to milliseconds
        times.append(elapsed)

        # Verify issues loaded
        _ = len(storage.list())

    return {
        "min_ms": min(times),
        "max_ms": max(times),
        "avg_ms": statistics.mean(times),
        "median_ms": statistics.median(times),
        "stdev_ms": statistics.stdev(times) if len(times) > 1 else 0.0,
    }


def format_results(count: int, stats: dict[str, float]) -> str:
    """Format benchmark results for display.

    Args:
        count: Number of issues tested
        stats: Timing statistics

    Returns:
        Formatted string
    """
    return (
        f"{count:>6} issues: "
        f"avg={stats['avg_ms']:>8.2f}ms  "
        f"median={stats['median_ms']:>8.2f}ms  "
        f"min={stats['min_ms']:>8.2f}ms  "
        f"max={stats['max_ms']:>8.2f}ms  "
        f"stdev={stats['stdev_ms']:>6.2f}ms"
    )


def run_benchmarks(
    counts: list[int] | None = None,
    iterations: int = ITERATIONS,
    seed: int = DEFAULT_SEED,
    verbose: bool = True,
) -> dict[int, dict[str, float]]:
    """Run benchmarks for different issue counts.

    Args:
        counts: List of issue counts to test (default: ISSUE_COUNTS)
        iterations: Number of iterations per benchmark
        seed: Random seed for deterministic generation
        verbose: Whether to print progress

    Returns:
        Dictionary mapping issue count to timing statistics
    """
    if counts is None:
        counts = ISSUE_COUNTS

    results: dict[int, dict[str, float]] = {}

    if verbose:
        print("=" * 80)
        print("Dogcat Storage Benchmark")
        print("=" * 80)
        print(f"Testing load performance with {iterations} iterations each")
        print(f"Random seed: {seed} (deterministic)")
        print()

    with tempfile.TemporaryDirectory() as tmpdir:
        dogcats_dir = Path(tmpdir) / ".dogcats"
        dogcats_dir.mkdir()
        storage_path = dogcats_dir / "issues.jsonl"

        for count in counts:
            if verbose:
                print(f"Generating {count} test issues...", end=" ", flush=True)

            # Generate test data
            issues, dependencies, links = generate_test_data(count, seed=seed)
            write_test_jsonl(issues, dependencies, links, storage_path)

            # Count relationships for reporting
            num_with_parent = sum(1 for i in issues if i.parent is not None)
            num_with_comments = sum(1 for i in issues if i.comments)
            total_comments = sum(len(i.comments) for i in issues)
            num_duplicates = sum(1 for i in issues if i.duplicate_of is not None)
            num_deps = len(dependencies)
            num_links = len(links)

            file_size = storage_path.stat().st_size
            if verbose:
                print(f"({file_size / 1024:.1f} KB)")
                print(
                    f"  {num_with_parent} parents, {num_deps} deps, {num_links} links, "
                    f"{num_duplicates} duplicates",
                )
                print(
                    f"  {num_with_comments} issues with comments "
                    f"({total_comments} total comments)",
                )
                print(
                    f"  Running {iterations} load iterations...",
                    end=" ",
                    flush=True,
                )

            # Run benchmark
            stats = benchmark_load(storage_path, iterations)
            results[count] = stats

            if verbose:
                print("done")
                print(f"  {format_results(count, stats)}")
                print()

    if verbose:
        print("=" * 80)
        print("Summary")
        print("=" * 80)
        for count, stats in sorted(results.items()):
            print(format_results(count, stats))

        # Calculate issues per second for each count
        print()
        print("Throughput (issues loaded per second):")
        for count, stats in sorted(results.items()):
            ips = (count / stats["avg_ms"]) * 1000
            print(f"  {count:>6} issues: {ips:>12,.0f} issues/sec")

    return results


def main() -> None:
    """Run the benchmark suite."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Benchmark dogcat storage loading performance",
    )
    parser.add_argument(
        "--counts",
        type=int,
        nargs="+",
        default=ISSUE_COUNTS,
        help=f"Issue counts to test (default: {ISSUE_COUNTS})",
    )
    parser.add_argument(
        "--iterations",
        "-n",
        type=int,
        default=ITERATIONS,
        help=f"Number of iterations per test (default: {ITERATIONS})",
    )
    parser.add_argument(
        "--seed",
        "-s",
        type=int,
        default=DEFAULT_SEED,
        help=f"Random seed for deterministic generation (default: {DEFAULT_SEED})",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Only show summary results",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )

    args = parser.parse_args()

    results = run_benchmarks(
        counts=args.counts,
        iterations=args.iterations,
        seed=args.seed,
        verbose=not args.quiet and not args.json,
    )

    if args.json:
        output = {
            "seed": args.seed,
            "iterations": args.iterations,
            "results": {str(k): v for k, v in results.items()},
        }
        print(orjson.dumps(output, option=orjson.OPT_INDENT_2).decode())


if __name__ == "__main__":
    main()
