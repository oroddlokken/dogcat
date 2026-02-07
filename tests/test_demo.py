"""Tests for demo issue generation."""

import tempfile
from pathlib import Path

from dogcat.demo import generate_demo_issues
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
            assert (
                issue.namespace != "demo"
            ), f"Issue {issue.full_id} still uses hardcoded 'demo' namespace"
            assert (
                issue.namespace != "dc"
            ), f"Issue {issue.full_id} uses default 'dc' namespace"


def test_demo_uses_configured_prefix() -> None:
    """Demo issues should respect an explicitly configured prefix."""
    with tempfile.TemporaryDirectory() as tmpdir:
        dogcats_dir = str(Path(tmpdir) / ".dogcats")
        Path(dogcats_dir).mkdir()

        # Write a config with explicit prefix
        config_path = Path(dogcats_dir) / "config.toml"
        config_path.write_text('issue_prefix = "testns"\n')

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
