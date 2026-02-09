"""Tests for the feature_flags module and CLI command."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from dogcat.cli import app
from dogcat.feature_flags import FeatureFlag, _env_var_name, feature_enabled

runner = CliRunner()


class TestFeatureEnabled:
    """Tests for the feature_enabled() function."""

    def test_default_false_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Return False when env var is unset and no default given."""
        monkeypatch.delenv("DCAT_FEATURE_TUI", raising=False)
        assert feature_enabled(FeatureFlag.TUI) is False

    def test_default_true_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Return True when env var is unset and default=True."""
        monkeypatch.delenv("DCAT_FEATURE_TUI", raising=False)
        assert feature_enabled(FeatureFlag.TUI, default=True) is True

    @pytest.mark.parametrize("value", ["1", "true", "yes", "TRUE", "Yes", "  1  "])
    def test_truthy_values(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        """Recognize truthy env var values as enabled."""
        monkeypatch.setenv("DCAT_FEATURE_TUI", value)
        assert feature_enabled(FeatureFlag.TUI) is True

    @pytest.mark.parametrize("value", ["0", "false", "no", "anything", "enabled"])
    def test_non_truthy_values(
        self,
        monkeypatch: pytest.MonkeyPatch,
        value: str,
    ) -> None:
        """Treat non-truthy env var values as disabled."""
        monkeypatch.setenv("DCAT_FEATURE_TUI", value)
        assert feature_enabled(FeatureFlag.TUI) is False

    def test_empty_string_uses_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Fall back to default when env var is an empty string."""
        monkeypatch.setenv("DCAT_FEATURE_TUI", "")
        assert feature_enabled(FeatureFlag.TUI) is False
        assert feature_enabled(FeatureFlag.TUI, default=True) is True


class TestEnvVarName:
    """Tests for the _env_var_name() helper."""

    def test_env_var_name(self) -> None:
        """Build the correct DCAT_FEATURE_ prefixed env var name."""
        assert _env_var_name(FeatureFlag.TUI) == "DCAT_FEATURE_TUI"


class TestFeaturesCLI:
    """Tests for the 'dcat features' CLI command."""

    def test_lists_flags(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Show all flags with their env var name and disabled status."""
        monkeypatch.delenv("DCAT_FEATURE_TUI", raising=False)
        result = runner.invoke(app, ["features"])
        assert result.exit_code == 0
        assert "TUI" in result.output
        assert "DCAT_FEATURE_TUI" in result.output
        assert "disabled" in result.output

    def test_shows_enabled_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Show enabled status when the env var is set."""
        monkeypatch.setenv("DCAT_FEATURE_TUI", "1")
        result = runner.invoke(app, ["features"])
        assert result.exit_code == 0
        assert "enabled" in result.output
