"""Tests for the TUI command registration."""

from __future__ import annotations

from typer.testing import CliRunner

runner = CliRunner()


class TestTuiCommand:
    """Verify the 'dcat tui' command is always registered."""

    def test_tui_command_registered(self) -> None:
        """Command should be available without any feature flag."""
        import importlib

        import dogcat.cli as cli_mod

        importlib.reload(cli_mod)

        result = runner.invoke(cli_mod.app, ["tui", "--help"])
        assert result.exit_code == 0
        assert "Launch the interactive TUI dashboard" in result.output
