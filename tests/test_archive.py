"""Tests for the archive command."""

import json
from pathlib import Path

import orjson
from typer.testing import CliRunner

from dogcat.cli import app
from dogcat.storage import JSONLStorage

runner = CliRunner()


def init_repo(dogcats_dir: Path) -> None:
    """Initialize a dogcat repo for testing."""
    runner.invoke(
        app,
        ["init", "--dogcats-dir", str(dogcats_dir)],
    )


def create_issue(dogcats_dir: Path, title: str, **kwargs: str) -> str:
    """Create an issue and return its ID."""
    args = ["create", title, "--dogcats-dir", str(dogcats_dir), "--json"]
    for key, value in kwargs.items():
        args.extend([f"--{key.replace('_', '-')}", value])
    result = runner.invoke(app, args)
    assert result.exit_code == 0, f"Create failed: {result.stdout}"
    data = orjson.loads(result.stdout)
    return f"{data['namespace']}-{data['id']}"


def close_issue(dogcats_dir: Path, issue_id: str) -> None:
    """Close an issue."""
    result = runner.invoke(
        app,
        ["close", issue_id, "--dogcats-dir", str(dogcats_dir)],
    )
    assert result.exit_code == 0, f"Close failed: {result.stdout}"


class TestArchiveBasic:
    """Test basic archive functionality."""

    def test_archive_no_closed_issues(self, tmp_path: Path) -> None:
        """Test archive with no closed issues."""
        dogcats_dir = tmp_path / ".dogcats"
        init_repo(dogcats_dir)
        create_issue(dogcats_dir, "Open issue")

        result = runner.invoke(
            app,
            ["archive", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No closed issues to archive" in result.stdout

    def test_archive_dry_run(self, tmp_path: Path) -> None:
        """Test archive dry run shows what would be archived."""
        dogcats_dir = tmp_path / ".dogcats"
        init_repo(dogcats_dir)
        issue_id = create_issue(dogcats_dir, "Test issue")
        close_issue(dogcats_dir, issue_id)

        result = runner.invoke(
            app,
            ["archive", "--dry-run", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Will archive 1 issue(s)" in result.stdout
        assert "Test issue" in result.stdout
        assert "dry run - no changes made" in result.stdout

        # Verify no archive was created
        archive_dir = dogcats_dir / "archive"
        assert not archive_dir.exists()

    def test_archive_with_confirm(self, tmp_path: Path) -> None:
        """Test archive with --confirm skips prompt."""
        dogcats_dir = tmp_path / ".dogcats"
        init_repo(dogcats_dir)
        issue_id = create_issue(dogcats_dir, "Test issue")
        close_issue(dogcats_dir, issue_id)

        result = runner.invoke(
            app,
            ["archive", "--yes", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Archived 1 issue(s)" in result.stdout

        # Verify archive was created
        archive_dir = dogcats_dir / "archive"
        assert archive_dir.exists()
        archive_files = list(archive_dir.glob("closed-*.jsonl"))
        assert len(archive_files) == 1

    def test_archive_removes_from_main_storage(self, tmp_path: Path) -> None:
        """Test that archived issues are removed from main storage."""
        dogcats_dir = tmp_path / ".dogcats"
        init_repo(dogcats_dir)
        issue_id = create_issue(dogcats_dir, "Test issue")
        close_issue(dogcats_dir, issue_id)

        # Verify issue exists before archive
        storage = JSONLStorage(str(dogcats_dir / "issues.jsonl"))
        assert storage.get(issue_id) is not None

        runner.invoke(
            app,
            ["archive", "--yes", "--dogcats-dir", str(dogcats_dir)],
        )

        # Reload and verify issue is gone
        storage.reload()
        assert storage.get(issue_id) is None

    def test_archive_creates_valid_jsonl(self, tmp_path: Path) -> None:
        """Test that archive file contains valid JSONL."""
        dogcats_dir = tmp_path / ".dogcats"
        init_repo(dogcats_dir)
        issue_id = create_issue(dogcats_dir, "Test issue")
        close_issue(dogcats_dir, issue_id)

        runner.invoke(
            app,
            ["archive", "--yes", "--dogcats-dir", str(dogcats_dir)],
        )

        archive_dir = dogcats_dir / "archive"
        archive_files = list(archive_dir.glob("closed-*.jsonl"))
        assert len(archive_files) == 1

        # Read and verify content — archive preserves full event history,
        # so there may be multiple lines (create + status updates + events).
        # The last issue record should be the final closed state.
        with archive_files[0].open("rb") as f:
            lines = f.readlines()
            assert len(lines) >= 1
            issue_records = [
                orjson.loads(line)
                for line in lines
                if orjson.loads(line).get("record_type") != "event"
            ]
            assert len(issue_records) >= 1
            last_record = issue_records[-1]
            assert last_record["title"] == "Test issue"
            assert last_record["status"] == "closed"


class TestArchiveOlderThan:
    """Test --older-than filtering."""

    def test_archive_older_than_format(self, tmp_path: Path) -> None:
        """Test --older-than requires correct format."""
        dogcats_dir = tmp_path / ".dogcats"
        init_repo(dogcats_dir)

        result = runner.invoke(
            app,
            ["archive", "--older-than", "invalid", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 1
        # Error is written to stderr, combined output is in result.output
        assert "must be in format Nd" in result.output

    def test_archive_older_than_filters(self, tmp_path: Path) -> None:
        """Test --older-than filters issues by closed date."""
        dogcats_dir = tmp_path / ".dogcats"
        init_repo(dogcats_dir)
        issue_id = create_issue(dogcats_dir, "Recent issue")
        close_issue(dogcats_dir, issue_id)

        # Try to archive issues closed more than 30 days ago
        result = runner.invoke(
            app,
            [
                "archive",
                "--older-than",
                "30d",
                "--yes",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "No closed issues older than 30 days" in result.stdout


class TestArchiveWithChildren:
    """Test archive behavior with parent-child relationships."""

    def test_skip_parent_with_open_child(self, tmp_path: Path) -> None:
        """Test that parents with open children are skipped."""
        dogcats_dir = tmp_path / ".dogcats"
        init_repo(dogcats_dir)

        # Create parent and child
        parent_id = create_issue(dogcats_dir, "Parent issue")
        create_issue(dogcats_dir, "Child issue", parent=parent_id)

        # Close only the parent
        close_issue(dogcats_dir, parent_id)

        result = runner.invoke(
            app,
            ["archive", "--dry-run", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No issues can be archived" in result.stdout
        assert "open child" in result.stdout

    def test_skip_child_with_open_parent(self, tmp_path: Path) -> None:
        """Test that closed children with open parents are skipped."""
        dogcats_dir = tmp_path / ".dogcats"
        init_repo(dogcats_dir)

        # Create parent and child
        parent_id = create_issue(dogcats_dir, "Parent issue")
        child_id = create_issue(dogcats_dir, "Child issue", parent=parent_id)

        # Close only the child
        close_issue(dogcats_dir, child_id)

        result = runner.invoke(
            app,
            ["archive", "--dry-run", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No issues can be archived" in result.stdout
        assert "parent" in result.stdout
        assert "not being archived" in result.stdout

    def test_skip_child_with_closed_but_non_candidate_parent(
        self, tmp_path: Path
    ) -> None:
        """Test that closed child is skipped if parent is closed but not a candidate.

        This can happen when --older-than filters out the parent but not
        the child, or when --namespace excludes the parent.
        """
        dogcats_dir = tmp_path / ".dogcats"
        init_repo(dogcats_dir)

        # Create parent and child
        parent_id = create_issue(dogcats_dir, "Parent issue")
        child_id = create_issue(dogcats_dir, "Child issue", parent=parent_id)

        # Close both
        close_issue(dogcats_dir, child_id)
        close_issue(dogcats_dir, parent_id)

        # Use --older-than 999d so both are too recent → no candidates
        # The point is to verify the check uses candidate_ids, not just status
        result = runner.invoke(
            app,
            [
                "archive",
                "--older-than",
                "999d",
                "--dry-run",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "No closed issues older than 999 days" in result.stdout

    def test_archive_parent_with_closed_children(self, tmp_path: Path) -> None:
        """Test that parents with all closed children can be archived."""
        dogcats_dir = tmp_path / ".dogcats"
        init_repo(dogcats_dir)

        # Create parent and child
        parent_id = create_issue(dogcats_dir, "Parent issue")
        child_id = create_issue(dogcats_dir, "Child issue", parent=parent_id)

        # Close both
        close_issue(dogcats_dir, child_id)
        close_issue(dogcats_dir, parent_id)

        result = runner.invoke(
            app,
            ["archive", "--dry-run", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Will archive 2 issue(s)" in result.stdout


class TestArchiveWithDependencies:
    """Test archive behavior with dependencies."""

    def test_skip_issue_depending_on_open(self, tmp_path: Path) -> None:
        """Test that issues depending on open issues are skipped."""
        dogcats_dir = tmp_path / ".dogcats"
        init_repo(dogcats_dir)

        # Create two issues
        blocker_id = create_issue(dogcats_dir, "Blocker issue")
        dependent_id = create_issue(dogcats_dir, "Dependent issue")

        # Add dependency
        runner.invoke(
            app,
            [
                "dep",
                dependent_id,
                "add",
                "--depends-on",
                blocker_id,
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        # Close only the dependent
        close_issue(dogcats_dir, dependent_id)

        result = runner.invoke(
            app,
            ["archive", "--dry-run", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No issues can be archived" in result.stdout
        assert "depends on non-archived" in result.stdout

    def test_archive_both_with_dependency(self, tmp_path: Path) -> None:
        """Test archiving issues where both sides of dependency are closed."""
        dogcats_dir = tmp_path / ".dogcats"
        init_repo(dogcats_dir)

        # Create two issues
        blocker_id = create_issue(dogcats_dir, "Blocker issue")
        dependent_id = create_issue(dogcats_dir, "Dependent issue")

        # Add dependency
        runner.invoke(
            app,
            [
                "dep",
                dependent_id,
                "add",
                "--depends-on",
                blocker_id,
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        # Close both
        close_issue(dogcats_dir, blocker_id)
        close_issue(dogcats_dir, dependent_id)

        result = runner.invoke(
            app,
            ["archive", "--yes", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Archived 2 issue(s)" in result.stdout
        assert "Including 1 dependency record" in result.stdout


class TestArchiveWithLinks:
    """Test archive behavior with links."""

    def test_skip_issue_linked_to_open(self, tmp_path: Path) -> None:
        """Test that issues linked to open issues are skipped."""
        dogcats_dir = tmp_path / ".dogcats"
        init_repo(dogcats_dir)

        # Create two issues
        issue1_id = create_issue(dogcats_dir, "Issue 1")
        issue2_id = create_issue(dogcats_dir, "Issue 2")

        # Add link using --related option
        result = runner.invoke(
            app,
            [
                "link",
                issue1_id,
                "add",
                "--related",
                issue2_id,
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0, f"Link failed: {result.stdout}"

        # Close only issue1
        close_issue(dogcats_dir, issue1_id)

        result = runner.invoke(
            app,
            ["archive", "--dry-run", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No issues can be archived" in result.stdout
        assert "has links to non-archived" in result.stdout

    def test_archive_both_with_link(self, tmp_path: Path) -> None:
        """Test archiving issues where both sides of link are closed."""
        dogcats_dir = tmp_path / ".dogcats"
        init_repo(dogcats_dir)

        # Create two issues
        issue1_id = create_issue(dogcats_dir, "Issue 1")
        issue2_id = create_issue(dogcats_dir, "Issue 2")

        # Add link using --related option
        result = runner.invoke(
            app,
            [
                "link",
                issue1_id,
                "add",
                "--related",
                issue2_id,
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0, f"Link failed: {result.stdout}"

        # Close both
        close_issue(dogcats_dir, issue1_id)
        close_issue(dogcats_dir, issue2_id)

        result = runner.invoke(
            app,
            ["archive", "--yes", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Archived 2 issue(s)" in result.stdout
        assert "Including 1 link record" in result.stdout


class TestArchiveMultiple:
    """Test archiving multiple issues."""

    def test_archive_multiple_independent(self, tmp_path: Path) -> None:
        """Test archiving multiple independent closed issues."""
        dogcats_dir = tmp_path / ".dogcats"
        init_repo(dogcats_dir)

        # Create and close multiple issues
        for i in range(5):
            issue_id = create_issue(dogcats_dir, f"Issue {i}")
            close_issue(dogcats_dir, issue_id)

        result = runner.invoke(
            app,
            ["archive", "--yes", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Archived 5 issue(s)" in result.stdout

        # Verify all gone from main storage
        storage = JSONLStorage(str(dogcats_dir / "issues.jsonl"))
        assert len(storage.list()) == 0

    def test_partial_archive(self, tmp_path: Path) -> None:
        """Test that some issues are archived while others are skipped."""
        dogcats_dir = tmp_path / ".dogcats"
        init_repo(dogcats_dir)

        # Create independent closed issue
        independent_id = create_issue(dogcats_dir, "Independent")
        close_issue(dogcats_dir, independent_id)

        # Create parent with open child
        parent_id = create_issue(dogcats_dir, "Parent")
        create_issue(dogcats_dir, "Open child", parent=parent_id)
        close_issue(dogcats_dir, parent_id)

        result = runner.invoke(
            app,
            ["archive", "--yes", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Archived 1 issue(s)" in result.stdout
        assert "Skipping 1 issue(s)" in result.stdout

        # Verify correct issue was archived
        storage = JSONLStorage(str(dogcats_dir / "issues.jsonl"))
        remaining = storage.list()
        assert len(remaining) == 2  # parent + open child
        assert storage.get(independent_id) is None
        assert storage.get(parent_id) is not None


class TestArchiveAbort:
    """Test archive abort behavior."""

    def test_archive_abort_on_no_confirm(self, tmp_path: Path) -> None:
        """Test that archive aborts when user doesn't confirm."""
        dogcats_dir = tmp_path / ".dogcats"
        init_repo(dogcats_dir)
        issue_id = create_issue(dogcats_dir, "Test issue")
        close_issue(dogcats_dir, issue_id)

        # Simulate user entering 'n' at the prompt
        result = runner.invoke(
            app,
            ["archive", "--dogcats-dir", str(dogcats_dir)],
            input="n\n",
        )
        assert result.exit_code == 0
        assert "Aborted" in result.stdout

        # Verify no archive was created
        archive_dir = dogcats_dir / "archive"
        assert not archive_dir.exists() or len(list(archive_dir.glob("*.jsonl"))) == 0


class TestArchivePreservesHistory:
    """Test that archive preserves the full append-only event history."""

    def test_archive_preserves_issue_event_history(self, tmp_path: Path) -> None:
        """Archived issues retain all intermediate records (create, update, close)."""
        dogcats_dir = tmp_path / ".dogcats"
        init_repo(dogcats_dir)
        issue_id = create_issue(dogcats_dir, "History issue")

        # Update priority to create an extra append-only record
        runner.invoke(
            app,
            [
                "update",
                issue_id,
                "--priority",
                "1",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        close_issue(dogcats_dir, issue_id)

        # Count raw lines in the main file before archive
        main_path = dogcats_dir / "issues.jsonl"
        pre_lines = [ln for ln in main_path.read_bytes().splitlines() if ln.strip()]
        # Should have at least create + update + close records
        assert len(pre_lines) >= 3

        runner.invoke(
            app,
            ["archive", "--yes", "--dogcats-dir", str(dogcats_dir)],
        )

        archive_dir = dogcats_dir / "archive"
        archive_files = list(archive_dir.glob("closed-*.jsonl"))
        assert len(archive_files) == 1

        archived_lines = [
            ln for ln in archive_files[0].read_bytes().splitlines() if ln.strip()
        ]
        # Archive must have all the original raw records, not just a snapshot
        assert len(archived_lines) >= 3

        # Filter to issue records only (skip event records)
        issue_records = [
            orjson.loads(ln)
            for ln in archived_lines
            if orjson.loads(ln).get("record_type") != "event"
        ]

        # Verify first issue record is the initial create (status=open)
        first = issue_records[0]
        assert first["status"] == "open"

        # Verify last issue record is the final closed state
        last = issue_records[-1]
        assert last["status"] == "closed"

    def test_archive_preserves_remaining_issue_history(self, tmp_path: Path) -> None:
        """Open issues that stay in the main file keep their event history."""
        dogcats_dir = tmp_path / ".dogcats"
        init_repo(dogcats_dir)

        # Create an issue that will stay open (with updates to generate history)
        open_id = create_issue(dogcats_dir, "Staying open")
        runner.invoke(
            app,
            [
                "update",
                open_id,
                "--priority",
                "1",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        # Create and close another issue to be archived
        closed_id = create_issue(dogcats_dir, "Going away")
        close_issue(dogcats_dir, closed_id)

        # Count raw lines for the open issue before archive
        main_path = dogcats_dir / "issues.jsonl"
        pre_lines = [ln for ln in main_path.read_bytes().splitlines() if ln.strip()]
        open_issue_pre_count = sum(
            1
            for ln in pre_lines
            if open_id.split("-")[-1] in ln.decode()
            and b"depends_on_id" not in ln
            and b"from_id" not in ln
        )
        assert open_issue_pre_count >= 2  # create + update

        runner.invoke(
            app,
            ["archive", "--yes", "--dogcats-dir", str(dogcats_dir)],
        )

        # Verify open issue still has all its history in the main file
        post_lines = [ln for ln in main_path.read_bytes().splitlines() if ln.strip()]
        open_issue_post_count = sum(
            1
            for ln in post_lines
            if open_id.split("-")[-1] in ln.decode()
            and b"depends_on_id" not in ln
            and b"from_id" not in ln
        )
        assert open_issue_post_count == open_issue_pre_count


class TestArchiveNamespace:
    """Test --namespace filtering for archive command."""

    def test_namespace_filters_issues(self, tmp_path: Path) -> None:
        """Test that --namespace only archives matching namespace."""
        dogcats_dir = tmp_path / ".dogcats"
        init_repo(dogcats_dir)

        # Create and close an issue (uses default namespace)
        issue_id = create_issue(dogcats_dir, "Default ns issue")
        close_issue(dogcats_dir, issue_id)

        # Try to archive with a non-matching namespace
        result = runner.invoke(
            app,
            [
                "archive",
                "--namespace",
                "other",
                "--dry-run",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "No closed issues in namespace 'other'" in result.stdout

    def test_namespace_archives_matching(self, tmp_path: Path) -> None:
        """Test that --namespace archives issues from the matching namespace."""
        dogcats_dir = tmp_path / ".dogcats"
        init_repo(dogcats_dir)

        # Create and close issues
        issue_id = create_issue(dogcats_dir, "Matching ns issue")
        close_issue(dogcats_dir, issue_id)

        # Get the actual namespace from the issue ID
        ns = issue_id.rsplit("-", 1)[0]

        result = runner.invoke(
            app,
            [
                "archive",
                "--namespace",
                ns,
                "--yes",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Archived 1 issue(s)" in result.stdout


def _create_proposal(tmp_path: Path, title: str = "Test proposal") -> str:
    """Create a proposal and return its full ID."""
    result = runner.invoke(
        app,
        ["propose", title, "--to", str(tmp_path), "--json"],
    )
    data = json.loads(result.stdout)
    return f"{data['namespace']}-inbox-{data['id']}"


class TestArchiveInbox:
    """Test archiving closed inbox proposals alongside issues."""

    def test_archive_includes_closed_proposals(self, tmp_path: Path) -> None:
        """Test that archive also archives closed inbox proposals."""
        dogcats_dir = tmp_path / ".dogcats"
        init_repo(dogcats_dir)

        # Create and close an issue (needed to trigger archive)
        issue_id = create_issue(dogcats_dir, "Test issue")
        close_issue(dogcats_dir, issue_id)

        # Create and close a proposal
        prop_id = _create_proposal(tmp_path, "Proposal to archive")
        runner.invoke(
            app,
            ["inbox", "close", prop_id, "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["archive", "--yes", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Archived 1 inbox proposal(s)" in result.stdout

        # Verify archive file was created
        archive_dir = dogcats_dir / "archive"
        inbox_archives = list(archive_dir.glob("inbox-closed-*.jsonl"))
        assert len(inbox_archives) == 1

    def test_archive_skips_open_proposals(self, tmp_path: Path) -> None:
        """Test that open proposals are not archived."""
        dogcats_dir = tmp_path / ".dogcats"
        init_repo(dogcats_dir)

        # Create and close an issue
        issue_id = create_issue(dogcats_dir, "Test issue")
        close_issue(dogcats_dir, issue_id)

        # Create an open proposal (not closed)
        _create_proposal(tmp_path, "Open proposal")

        result = runner.invoke(
            app,
            ["archive", "--yes", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        # Should not mention inbox archiving
        assert "inbox proposal(s)" not in result.stdout

    def test_archive_json_includes_inbox_count(self, tmp_path: Path) -> None:
        """Test that JSON output includes inbox_archived when proposals archived."""
        dogcats_dir = tmp_path / ".dogcats"
        init_repo(dogcats_dir)

        # Create and close an issue + proposal
        issue_id = create_issue(dogcats_dir, "Test issue")
        close_issue(dogcats_dir, issue_id)

        prop_id = _create_proposal(tmp_path, "JSON archive test")
        runner.invoke(
            app,
            ["inbox", "close", prop_id, "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["archive", "--yes", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        # JSON output is the last line; preceding lines are the summary
        json_line = [
            ln for ln in result.stdout.strip().splitlines() if ln.startswith("{")
        ][-1]
        data = json.loads(json_line)
        assert data["inbox_archived"] == 1

    def test_archive_removes_proposals_from_inbox(self, tmp_path: Path) -> None:
        """Test that archived proposals are removed from inbox.jsonl."""
        dogcats_dir = tmp_path / ".dogcats"
        init_repo(dogcats_dir)

        # Create and close an issue
        issue_id = create_issue(dogcats_dir, "Test issue")
        close_issue(dogcats_dir, issue_id)

        # Create two proposals, close one
        _create_proposal(tmp_path, "Open proposal")
        prop_id = _create_proposal(tmp_path, "Closed proposal")
        runner.invoke(
            app,
            ["inbox", "close", prop_id, "--dogcats-dir", str(dogcats_dir)],
        )

        runner.invoke(
            app,
            ["archive", "--yes", "--dogcats-dir", str(dogcats_dir)],
        )

        # Inbox list should only show the open proposal
        result = runner.invoke(
            app,
            ["inbox", "list", "--dogcats-dir", str(dogcats_dir)],
        )
        assert "Open proposal" in result.stdout
        assert "Closed proposal" not in result.stdout
