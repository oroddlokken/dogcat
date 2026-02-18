"""Tests for Dogcat CLI commands."""

import json
from pathlib import Path

from cli_test_helpers import (
    _create_issue,
    _create_multi_ns_issues,
    _init_with_namespace,
    _set_ns_config,
)
from typer.testing import CliRunner

from dogcat.cli import app

runner = CliRunner()


class TestNamespacesCommand:
    """Test dcat namespaces command."""

    def test_single_namespace_shows_primary(self, tmp_path: Path) -> None:
        """Single namespace → shows (primary) with count."""
        dogcats_dir = tmp_path / ".dogcats"
        _init_with_namespace(dogcats_dir, "proj-a")
        _create_issue(dogcats_dir, "Issue 1")

        result = runner.invoke(app, ["namespaces", "--dogcats-dir", str(dogcats_dir)])
        assert result.exit_code == 0
        assert "proj-a (1 issues) (primary)" in result.stdout

    def test_multiple_namespaces(self, tmp_path: Path) -> None:
        """Multiple namespaces → lists all with counts."""
        dogcats_dir = tmp_path / ".dogcats"
        _create_multi_ns_issues(dogcats_dir)

        result = runner.invoke(app, ["namespaces", "--dogcats-dir", str(dogcats_dir)])
        assert result.exit_code == 0
        assert "proj-a (2 issues) (primary)" in result.stdout
        assert "proj-b (1 issues)" in result.stdout

    def test_empty_issues(self, tmp_path: Path) -> None:
        """Empty issues → "No namespaces found"."""
        dogcats_dir = tmp_path / ".dogcats"
        _init_with_namespace(dogcats_dir, "proj-a")

        result = runner.invoke(app, ["namespaces", "--dogcats-dir", str(dogcats_dir)])
        assert result.exit_code == 0
        assert "No namespaces found" in result.stdout

    def test_json_output(self, tmp_path: Path) -> None:
        """--json → valid JSON with namespace, count, visibility."""
        dogcats_dir = tmp_path / ".dogcats"
        _create_multi_ns_issues(dogcats_dir)

        result = runner.invoke(
            app,
            ["namespaces", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert len(data) == 2
        ns_map = {item["namespace"]: item for item in data}
        assert ns_map["proj-a"]["count"] == 2
        assert ns_map["proj-a"]["visibility"] == "primary"
        assert ns_map["proj-b"]["count"] == 1
        assert ns_map["proj-b"]["visibility"] == "visible"

    def test_tombstones_excluded(self, tmp_path: Path) -> None:
        """Tombstones excluded from counts."""
        dogcats_dir = tmp_path / ".dogcats"
        _init_with_namespace(dogcats_dir, "proj-a")
        _create_issue(dogcats_dir, "To delete")
        _create_issue(dogcats_dir, "To keep")

        # Get the issue ID of the first issue to delete it
        list_result = runner.invoke(
            app,
            ["list", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        issues = json.loads(list_result.stdout)
        first_id = issues[0]["id"]
        first_ns = issues[0]["namespace"]

        full_id = f"{first_ns}-{first_id}"
        runner.invoke(
            app,
            ["delete", full_id, "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(app, ["namespaces", "--dogcats-dir", str(dogcats_dir)])
        assert "proj-a (1 issues)" in result.stdout

    def test_with_visible_namespaces_annotation(self, tmp_path: Path) -> None:
        """With visible_namespaces config → annotations correct."""
        dogcats_dir = tmp_path / ".dogcats"
        _create_multi_ns_issues(dogcats_dir)
        _set_ns_config(dogcats_dir, "visible_namespaces", ["proj-a"])

        result = runner.invoke(app, ["namespaces", "--dogcats-dir", str(dogcats_dir)])
        assert "proj-a (2 issues) (primary)" in result.stdout
        assert "proj-b (1 issues) (hidden)" in result.stdout

    def test_with_hidden_namespaces_annotation(self, tmp_path: Path) -> None:
        """With hidden_namespaces config → annotations correct."""
        dogcats_dir = tmp_path / ".dogcats"
        _create_multi_ns_issues(dogcats_dir)
        _set_ns_config(dogcats_dir, "hidden_namespaces", ["proj-b"])

        result = runner.invoke(app, ["namespaces", "--dogcats-dir", str(dogcats_dir)])
        assert "proj-a (2 issues) (primary)" in result.stdout
        assert "proj-b (1 issues) (hidden)" in result.stdout

    def test_includes_inbox_proposals(self, tmp_path: Path) -> None:
        """Inbox proposals contribute to namespace counts."""
        from dogcat.inbox import InboxStorage
        from dogcat.models import Proposal

        dogcats_dir = tmp_path / ".dogcats"
        _init_with_namespace(dogcats_dir, "proj-a")
        _create_issue(dogcats_dir, "Issue A1")

        # Add an inbox proposal in a new namespace
        inbox = InboxStorage(dogcats_dir=str(dogcats_dir))
        inbox.create(Proposal(id="p1", title="Inbox P1", namespace="proj-new"))

        result = runner.invoke(app, ["namespaces", "--dogcats-dir", str(dogcats_dir)])
        assert result.exit_code == 0
        assert "proj-a (1 issues) (primary)" in result.stdout
        assert "proj-new (1 inbox)" in result.stdout

    def test_inbox_json_includes_proposals(self, tmp_path: Path) -> None:
        """--json output includes inbox proposal namespaces."""
        from dogcat.inbox import InboxStorage
        from dogcat.models import Proposal

        dogcats_dir = tmp_path / ".dogcats"
        _init_with_namespace(dogcats_dir, "proj-a")
        _create_issue(dogcats_dir, "Issue A1")

        inbox = InboxStorage(dogcats_dir=str(dogcats_dir))
        inbox.create(Proposal(id="p1", title="Inbox P1", namespace="proj-new"))

        result = runner.invoke(
            app,
            ["namespaces", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        ns_map = {item["namespace"]: item for item in data}
        assert "proj-new" in ns_map
        assert ns_map["proj-new"]["count"] == 1
        assert ns_map["proj-new"]["inbox"] == 1
        assert ns_map["proj-new"]["issues"] == 0

    def test_inbox_same_namespace_adds_to_count(self, tmp_path: Path) -> None:
        """Inbox proposals in an existing namespace add to the count."""
        from dogcat.inbox import InboxStorage
        from dogcat.models import Proposal

        dogcats_dir = tmp_path / ".dogcats"
        _init_with_namespace(dogcats_dir, "proj-a")
        _create_issue(dogcats_dir, "Issue A1")

        inbox = InboxStorage(dogcats_dir=str(dogcats_dir))
        inbox.create(Proposal(id="p1", title="Inbox P1", namespace="proj-a"))

        result = runner.invoke(app, ["namespaces", "--dogcats-dir", str(dogcats_dir)])
        assert result.exit_code == 0
        assert "proj-a (1 issues, 1 inbox) (primary)" in result.stdout


class TestSearchNamespaceFilter:
    """Test namespace filtering in search command."""

    def test_search_respects_hidden_config(self, tmp_path: Path) -> None:
        """Search respects config visibility."""
        dogcats_dir = tmp_path / ".dogcats"
        _create_multi_ns_issues(dogcats_dir)
        _set_ns_config(dogcats_dir, "hidden_namespaces", ["proj-b"])

        result = runner.invoke(
            app,
            ["search", "Issue", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        issues = json.loads(result.stdout)
        assert all(i["namespace"] != "proj-b" for i in issues)

    def test_search_respects_visible_config(self, tmp_path: Path) -> None:
        """Hidden namespace issues not returned in search."""
        dogcats_dir = tmp_path / ".dogcats"
        _create_multi_ns_issues(dogcats_dir)
        _set_ns_config(dogcats_dir, "visible_namespaces", ["proj-a"])

        result = runner.invoke(
            app,
            ["search", "Issue", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        issues = json.loads(result.stdout)
        assert len(issues) == 2
        assert all(i["namespace"] == "proj-a" for i in issues)


class TestRecentlyNamespaceFilter:
    """Test namespace filtering in recently-added and recently-closed."""

    def test_recently_added_respects_config(self, tmp_path: Path) -> None:
        """recently-added respects config visibility."""
        dogcats_dir = tmp_path / ".dogcats"
        _create_multi_ns_issues(dogcats_dir)
        _set_ns_config(dogcats_dir, "hidden_namespaces", ["proj-b"])

        result = runner.invoke(
            app,
            ["recently-added", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        issues = json.loads(result.stdout)
        assert all(i["namespace"] != "proj-b" for i in issues)

    def test_recently_closed_respects_config(self, tmp_path: Path) -> None:
        """recently-closed respects config visibility."""
        dogcats_dir = tmp_path / ".dogcats"
        _create_multi_ns_issues(dogcats_dir)

        # Close all issues
        list_result = runner.invoke(
            app,
            ["list", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        issues = json.loads(list_result.stdout)
        for issue in issues:
            full_id = f"{issue['namespace']}-{issue['id']}"
            runner.invoke(
                app,
                ["close", full_id, "--dogcats-dir", str(dogcats_dir)],
            )

        # Hide proj-b
        _set_ns_config(dogcats_dir, "hidden_namespaces", ["proj-b"])

        result = runner.invoke(
            app,
            ["recently-closed", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        events = json.loads(result.stdout)
        for event in events:
            assert not event["issue_id"].startswith("proj-b-")
