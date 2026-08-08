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
        assert (
            "Wait for explicit user approval before closing any issue" in result.output
        )

    def test_in_review_precedes_the_closure_gate(self) -> None:
        """The template sets `in_review` before asking to close.

        This repo's own AGENTS.md skips `in_review` because a pull request is
        its review surface, and that divergence has already caused the template
        to drift once. Pin the shipped default so a change to it is deliberate.
        """
        result = runner.invoke(app, ["example-md"])
        assert "dcat update --status in_review" in result.output
        assert result.output.index("in_review") < result.output.index("dcat close")

    def test_contains_findings_guidance(self) -> None:
        """Test that the template includes the two-step findings pattern."""
        result = runner.invoke(app, ["example-md"])
        assert "Should I update issue" in result.output


def test_template_bounds_multiple_in_progress() -> None:
    """The template must say when more than one `in_progress` is allowed.

    It told the agent to work "one at a time, not the whole backlog at
    once" and then, four lines later, that working on multiple related
    issues was fine — without ever naming the condition. Users paste this
    whole into their CLAUDE.md, so the gap ships to every project.
    (dogcat-1zi3)
    """
    result = runner.invoke(app, ["example-md"])
    assert result.exit_code == 0

    assert "only when a single change closes all of them" in result.stdout
    assert "okay to work on multiple related issues" not in result.stdout
    # The rule it qualifies must still be present, or the bound is orphaned.
    assert "one at a time, not the whole backlog at once" in result.stdout
