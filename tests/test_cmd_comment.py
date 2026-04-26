"""Tests for Dogcat CLI commands."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from dogcat.cli import app

if TYPE_CHECKING:
    from pathlib import Path

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


def _add_comment(dogcats_dir: Path, issue_id: str, text: str) -> None:
    """Add a comment to an issue and assert success."""
    result = runner.invoke(
        app,
        [
            "comment",
            issue_id,
            "add",
            "--text",
            text,
            "--by",
            "tester",
            "--dogcats-dir",
            str(dogcats_dir),
        ],
    )
    assert result.exit_code == 0, result.stdout


def _comment_count(dogcats_dir: Path, issue_id: str) -> int:
    """Return the number of comments via the JSON list output."""
    result = runner.invoke(
        app,
        [
            "comment",
            issue_id,
            "list",
            "--json",
            "--dogcats-dir",
            str(dogcats_dir),
        ],
    )
    assert result.exit_code == 0, result.stdout
    return len(json.loads(result.stdout))


class TestCommentLifecycleFlow:
    """Comments must survive close/reopen/archive/rename-namespace.

    A regression that wiped comments on a status transition or a
    namespace rename would only show up across this whole flow — each
    step in isolation already had coverage. (dogcat-2mv7)
    """

    def test_comments_survive_full_lifecycle(self, tmp_path: Path) -> None:
        """Three comments added across status transitions all survive."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])
        create_result = runner.invoke(
            app,
            ["create", "Lifecycle issue", "--dogcats-dir", str(dogcats_dir)],
        )
        issue_id = create_result.stdout.split(": ")[0].split()[-1]

        _add_comment(dogcats_dir, issue_id, "first")

        # Transition: open → in_progress
        runner.invoke(
            app,
            [
                "update",
                issue_id,
                "--status",
                "in_progress",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        _add_comment(dogcats_dir, issue_id, "second")

        # Transition: in_progress → closed
        runner.invoke(
            app,
            ["close", issue_id, "--dogcats-dir", str(dogcats_dir)],
        )
        # Comments must still be listed after close.
        assert _comment_count(dogcats_dir, issue_id) == 2

        # Transition: closed → open
        runner.invoke(
            app,
            ["reopen", issue_id, "--dogcats-dir", str(dogcats_dir)],
        )
        _add_comment(dogcats_dir, issue_id, "third")
        assert _comment_count(dogcats_dir, issue_id) == 3

    def test_comments_survive_archive(self, tmp_path: Path) -> None:
        """Archived issues retain every comment in the archive file.

        Reading the archive file directly (rather than the live
        ``issues.jsonl``) is the whole point: a regression that dropped
        comments during the split-rewrite step would only show up here.
        """
        from dogcat.storage import JSONLStorage

        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])
        create_result = runner.invoke(
            app,
            ["create", "To be archived", "--dogcats-dir", str(dogcats_dir)],
        )
        issue_id = create_result.stdout.split(": ")[0].split()[-1]

        _add_comment(dogcats_dir, issue_id, "alpha")
        _add_comment(dogcats_dir, issue_id, "beta")
        _add_comment(dogcats_dir, issue_id, "gamma")

        runner.invoke(app, ["close", issue_id, "--dogcats-dir", str(dogcats_dir)])

        archive_result = runner.invoke(
            app,
            ["archive", "--yes", "--dogcats-dir", str(dogcats_dir)],
        )
        assert archive_result.exit_code == 0, archive_result.stdout

        # Locate the archive file and load it through JSONLStorage.
        archive_dir = dogcats_dir / "archive"
        archive_files = list(archive_dir.glob("closed-*.jsonl"))
        assert len(archive_files) == 1, archive_files
        archived = JSONLStorage(str(archive_files[0]))
        issue = archived.get(issue_id)
        assert issue is not None, "archived issue not loadable"
        comment_texts = [c.text for c in issue.comments]
        assert comment_texts == ["alpha", "beta", "gamma"]

    def test_comments_survive_rename_namespace(self, tmp_path: Path) -> None:
        """rename-namespace preserves every comment on every issue."""
        from dogcat.config import save_config

        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])
        save_config(str(dogcats_dir), {"namespace": "old"})

        create_result = runner.invoke(
            app,
            ["create", "Rename issue", "--dogcats-dir", str(dogcats_dir)],
        )
        issue_id = create_result.stdout.split(": ")[0].split()[-1]

        _add_comment(dogcats_dir, issue_id, "before-rename-1")
        _add_comment(dogcats_dir, issue_id, "before-rename-2")

        result = runner.invoke(
            app,
            [
                "rename-namespace",
                "old",
                "new",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0, result.stdout

        # Issue's full_id now uses the new namespace.
        new_id = issue_id.replace("old-", "new-", 1)
        count = _comment_count(dogcats_dir, new_id)
        assert count == 2, f"expected 2 comments after rename, got {count}"
