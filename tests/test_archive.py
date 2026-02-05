"""Tests for the archive command."""

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
        ["init", "--dogcats-dir", str(dogcats_dir), "--no-gitattributes"],
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
            ["archive", "--confirm", "--dogcats-dir", str(dogcats_dir)],
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
            ["archive", "--confirm", "--dogcats-dir", str(dogcats_dir)],
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
            ["archive", "--confirm", "--dogcats-dir", str(dogcats_dir)],
        )

        archive_dir = dogcats_dir / "archive"
        archive_files = list(archive_dir.glob("closed-*.jsonl"))
        assert len(archive_files) == 1

        # Read and verify content
        with archive_files[0].open("rb") as f:
            lines = f.readlines()
            assert len(lines) == 1
            data = orjson.loads(lines[0])
            assert data["title"] == "Test issue"
            assert data["status"] == "closed"


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
                "--confirm",
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
            ["archive", "--confirm", "--dogcats-dir", str(dogcats_dir)],
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
            ["archive", "--confirm", "--dogcats-dir", str(dogcats_dir)],
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
            ["archive", "--confirm", "--dogcats-dir", str(dogcats_dir)],
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
            ["archive", "--confirm", "--dogcats-dir", str(dogcats_dir)],
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
