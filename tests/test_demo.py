"""Tests for demo issue generation."""

import tempfile
from pathlib import Path

from dogcat.demo import generate_demo_inbox, generate_demo_issues
from dogcat.inbox import InboxStorage
from dogcat.models import IssueType, ProposalStatus, Status
from dogcat.storage import JSONLStorage


def test_demo_uses_project_prefix_from_directory() -> None:
    """Demo issues should use the project namespace derived from the folder name."""
    with tempfile.TemporaryDirectory(suffix="-myproject") as tmpdir:
        dogcats_dir = str(Path(tmpdir) / ".dogcats")
        storage = JSONLStorage(f"{dogcats_dir}/issues.jsonl", create_dir=True)

        created_ids = generate_demo_issues(storage, dogcats_dir)

        assert len(created_ids) > 0
        # Verify stored issues use a namespace derived from the directory name,
        # not the old hardcoded "demo" or the default "dc"
        issues = storage.list()
        for issue in issues:
            assert issue.namespace != "demo", (
                f"Issue {issue.full_id} still uses hardcoded 'demo' namespace"
            )
            assert issue.namespace != "dc", (
                f"Issue {issue.full_id} uses default 'dc' namespace"
            )


def test_demo_uses_configured_prefix() -> None:
    """Demo issues should respect an explicitly configured prefix."""
    with tempfile.TemporaryDirectory() as tmpdir:
        dogcats_dir = str(Path(tmpdir) / ".dogcats")
        Path(dogcats_dir).mkdir()

        # Write a config with explicit prefix
        config_path = Path(dogcats_dir) / "config.toml"
        config_path.write_text('namespace = "testns"\n')

        storage = JSONLStorage(f"{dogcats_dir}/issues.jsonl", create_dir=True)
        generate_demo_issues(storage, dogcats_dir)

        issues = storage.list()
        assert len(issues) > 0
        for issue in issues:
            assert issue.namespace == "testns", (
                f"Issue {issue.full_id} has namespace '{issue.namespace}' "
                f"instead of configured 'testns'"
            )
            assert issue.full_id.startswith(
                "testns-",
            ), f"Issue full_id {issue.full_id} does not start with 'testns-'"


def test_demo_has_deferred_epic_with_subtasks() -> None:
    """Demo creates a deferred epic with subtasks."""
    with tempfile.TemporaryDirectory() as tmpdir:
        dogcats_dir = str(Path(tmpdir) / ".dogcats")
        storage = JSONLStorage(f"{dogcats_dir}/issues.jsonl", create_dir=True)

        generate_demo_issues(storage, dogcats_dir)

        issues = storage.list()

        # Find deferred epics
        deferred_epics = [
            i
            for i in issues
            if i.issue_type == IssueType.EPIC and i.status == Status.DEFERRED
        ]
        assert len(deferred_epics) >= 1, "Expected at least one deferred epic"

        # Check that the deferred epic has children
        deferred_epic = deferred_epics[0]
        children = storage.get_children(deferred_epic.full_id)
        assert len(children) > 0, (
            f"Deferred epic {deferred_epic.full_id} should have children"
        )


def test_demo_inbox_creates_proposals() -> None:
    """Demo inbox creates proposals in all three statuses."""
    with tempfile.TemporaryDirectory() as tmpdir:
        dogcats_dir = str(Path(tmpdir) / ".dogcats")
        # Need to init storage first so directory exists
        JSONLStorage(f"{dogcats_dir}/issues.jsonl", create_dir=True)

        count = generate_demo_inbox(dogcats_dir)
        assert count == 6

        inbox = InboxStorage(dogcats_dir=dogcats_dir)
        proposals = inbox.list(include_tombstones=True)
        assert len(proposals) == 6

        statuses = {p.status for p in proposals}
        assert ProposalStatus.OPEN in statuses
        assert ProposalStatus.CLOSED in statuses
        assert ProposalStatus.TOMBSTONE in statuses


def test_demo_inbox_has_source_repos() -> None:
    """Demo inbox proposals have realistic source_repo values."""
    with tempfile.TemporaryDirectory() as tmpdir:
        dogcats_dir = str(Path(tmpdir) / ".dogcats")
        JSONLStorage(f"{dogcats_dir}/issues.jsonl", create_dir=True)

        generate_demo_inbox(dogcats_dir)

        inbox = InboxStorage(dogcats_dir=dogcats_dir)
        proposals = inbox.list(include_tombstones=True)

        with_source = [p for p in proposals if p.source_repo]
        assert len(with_source) >= 4
