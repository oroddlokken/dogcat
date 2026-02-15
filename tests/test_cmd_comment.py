"""Tests for Dogcat CLI commands."""

import json
from pathlib import Path

from typer.testing import CliRunner

from dogcat.cli import app

runner = CliRunner()


class TestCLIComments:
    """Test comment functionality."""

    def test_comment_add(self, tmp_path: Path) -> None:
        """Test adding a comment to an issue."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        create_result = runner.invoke(
            app,
            ["create", "Test issue", "--dogcats-dir", str(dogcats_dir)],
        )
        issue_id = create_result.stdout.split(": ")[0].split()[-1]

        result = runner.invoke(
            app,
            [
                "comment",
                issue_id,
                "add",
                "--text",
                "Test comment",
                "--by",
                "testuser",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Added comment" in result.stdout

    def test_comment_stores_full_issue_id(self, tmp_path: Path) -> None:
        """Test that comment stores full issue ID, not partial."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Create issue and get full ID
        create_result = runner.invoke(
            app,
            ["create", "Test issue", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        issue_data = json.loads(create_result.stdout)
        hash_only = issue_data["id"]  # e.g., "abc1"
        namespace = issue_data["namespace"]  # e.g., "dc"
        full_id = f"{namespace}-{hash_only}"

        # Add comment using partial (hash-only) ID
        result = runner.invoke(
            app,
            [
                "comment",
                hash_only,
                "add",
                "--text",
                "Test comment",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0

        # Get the issue and verify comment has full issue_id
        show_result = runner.invoke(
            app,
            ["show", full_id, "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        show_data = json.loads(show_result.stdout)
        assert len(show_data["comments"]) == 1
        # Comment's issue_id should be the full ID, not the partial
        assert show_data["comments"][0]["issue_id"] == full_id

    def test_comment_list(self, tmp_path: Path) -> None:
        """Test listing comments for an issue."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        create_result = runner.invoke(
            app,
            ["create", "Test issue", "--dogcats-dir", str(dogcats_dir)],
        )
        issue_id = create_result.stdout.split(": ")[0].split()[-1]

        # Add comments
        runner.invoke(
            app,
            [
                "comment",
                issue_id,
                "add",
                "--text",
                "First comment",
                "--by",
                "user1",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        runner.invoke(
            app,
            [
                "comment",
                issue_id,
                "add",
                "--text",
                "Second comment",
                "--by",
                "user2",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["comment", issue_id, "list", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "First comment" in result.stdout
        assert "Second comment" in result.stdout

    def test_show_displays_comments(self, tmp_path: Path) -> None:
        """Test that show command displays comments."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        create_result = runner.invoke(
            app,
            ["create", "Test issue", "--dogcats-dir", str(dogcats_dir)],
        )
        issue_id = create_result.stdout.split(": ")[0].split()[-1]

        # Add comment
        runner.invoke(
            app,
            [
                "comment",
                issue_id,
                "add",
                "--text",
                "Test comment",
                "--by",
                "testuser",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        result = runner.invoke(
            app,
            ["show", issue_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Comments:" in result.stdout
        assert "Test comment" in result.stdout

    def test_comment_delete(self, tmp_path: Path) -> None:
        """Test deleting a comment."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        create_result = runner.invoke(
            app,
            ["create", "Test issue", "--dogcats-dir", str(dogcats_dir)],
        )
        issue_id = create_result.stdout.split(": ")[0].split()[-1]

        # Add comment
        runner.invoke(
            app,
            [
                "comment",
                issue_id,
                "add",
                "--text",
                "Comment to delete",
                "--by",
                "testuser",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        # Get comment ID
        list_result = runner.invoke(
            app,
            ["comment", issue_id, "list", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        comments = json.loads(list_result.stdout)
        comment_id = comments[0]["id"]

        # Delete comment
        result = runner.invoke(
            app,
            [
                "comment",
                issue_id,
                "delete",
                "--comment-id",
                comment_id,
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Deleted comment" in result.stdout
