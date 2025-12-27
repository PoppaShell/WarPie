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


@pytest.fixture
def flask_app():
    """Create a test Flask application instance."""
    from web.app import create_app

    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def flask_client(flask_app):
    """Create a test client for making HTTP requests."""
    return flask_app.test_client()
