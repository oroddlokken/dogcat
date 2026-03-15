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

    def test_contains_closing_workflow(self) -> None:
        """Test that the template includes closing workflow guidance."""
        result = runner.invoke(app, ["example-md"])
        assert "in_review" in result.output
        assert "Wait for explicit user approval before closing any issue" in result.output

    def test_contains_findings_guidance(self) -> None:
        """Test that the template includes the two-step findings pattern."""
        result = runner.invoke(app, ["example-md"])
        assert "Should I update issue" in result.output
