"""Pytest configuration and shared fixtures."""

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest


@pytest.fixture
def temp_dogcats_dir() -> Generator[Path]:
    """Create a temporary .dogcats directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        dogcats_path = Path(tmpdir) / ".dogcats"
        dogcats_path.mkdir()
        yield dogcats_path


@pytest.fixture
def temp_workspace() -> Generator[Path]:
    """Create a temporary workspace directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)
