"""Pytest configuration and shared fixtures for WarPie tests."""

import pytest


@pytest.fixture
def mock_subprocess(mocker):
    """Mock subprocess.run for testing CLI calls."""
    return mocker.patch("subprocess.run")


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create a temporary config directory structure."""
    config_dir = tmp_path / "etc" / "warpie"
    config_dir.mkdir(parents=True)
    return config_dir
