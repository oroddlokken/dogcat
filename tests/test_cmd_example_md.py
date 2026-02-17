"""Tests for example-md command."""

from __future__ import annotations

from typer.testing import CliRunner

from dogcat.cli import app

runner = CliRunner()


class TestExampleMd:
    """Test example-md command."""

    def test_outputs_claude_md_template(self) -> None:
        """Test that example-md outputs CLAUDE.md template."""
        result = runner.invoke(app, ["example-md"])
        assert result.exit_code == 0
        assert "# Agent Instructions" in result.output
        assert "dcat prime --opinionated" in result.output
        assert "dcat list --agent-only" in result.output

    def test_contains_status_workflow(self) -> None:
        """Test that the template includes status workflow guidance."""
        result = runner.invoke(app, ["example-md"])
        assert "in_progress" in result.output
        assert "in_review" in result.output

    def test_contains_issue_creation_guidance(self) -> None:
        """Test that the template includes issue creation guidance."""
        result = runner.invoke(app, ["example-md"])
        assert "ALWAYS ask if we should create an issue" in result.output
