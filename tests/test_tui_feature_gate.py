"""Tests for the TUI command feature gate."""

from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

if TYPE_CHECKING:
    import pytest

runner = CliRunner()


class TestTuiFeatureGate:
    """Verify the 'dcat tui' command is gated behind DCAT_FEATURE_TUI."""

    def test_tui_not_registered_when_flag_disabled(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Command should not exist when the feature flag is off."""
        monkeypatch.delenv("DCAT_FEATURE_TUI", raising=False)
        # Re-import to trigger register() with the flag disabled.
        import importlib

        import dogcat.cli as cli_mod

        importlib.reload(cli_mod)

        result = runner.invoke(cli_mod.app, ["tui", "--help"])
        assert result.exit_code != 0

    def test_tui_registered_when_flag_enabled(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Command should be available when the feature flag is on."""
        monkeypatch.setenv("DCAT_FEATURE_TUI", "1")
        import importlib

        import dogcat.cli as cli_mod

        importlib.reload(cli_mod)

        result = runner.invoke(cli_mod.app, ["tui", "--help"])
        assert result.exit_code == 0
        assert "Launch the interactive TUI dashboard" in result.output
