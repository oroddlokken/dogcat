"""Tests for the feature_flags module and CLI command."""

from __future__ import annotations

from typer.testing import CliRunner

from dogcat.cli import app
from dogcat.feature_flags import FeatureFlag

runner = CliRunner()


class TestFeatureFlagEnum:
    """Tests for the FeatureFlag enum."""

    def test_enum_is_empty(self) -> None:
        """No feature flags are defined currently."""
        assert list(FeatureFlag) == []


class TestFeaturesCLI:
    """Tests for the 'dcat features' CLI command."""

    def test_no_flags_defined(self) -> None:
        """Show 'no feature flags' message when enum is empty."""
        result = runner.invoke(app, ["features"])
        assert result.exit_code == 0
        assert "No feature flags defined" in result.output
