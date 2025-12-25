"""Basic tests for WarPie web control panel.

These are smoke tests to ensure the Flask application can be imported
and basic configuration is correct. More comprehensive tests will be added later.
"""

from pathlib import Path


class TestWebAppStructure:
    """Test that the Flask web application structure exists."""

    def test_web_package_exists(self):
        """Verify the web package exists."""
        web_path = Path(__file__).parent.parent.parent / "web"
        assert web_path.exists(), "web/ package should exist"
        assert (web_path / "__init__.py").exists(), "web/__init__.py should exist"

    def test_control_entry_point_exists(self):
        """Verify the control panel entry point exists."""
        control_path = Path(__file__).parent.parent.parent / "bin" / "warpie-control"
        assert control_path.exists(), "warpie-control should exist in bin/"

    def test_routes_exist(self):
        """Verify route modules exist."""
        routes_path = Path(__file__).parent.parent.parent / "web" / "routes"
        assert routes_path.exists(), "web/routes/ should exist"
        assert (routes_path / "main.py").exists(), "main.py route should exist"
        assert (routes_path / "filters.py").exists(), "filters.py route should exist"


class TestModeConfiguration:
    """Test Kismet mode configuration constants."""

    def test_modes_defined(self):
        """Verify capture modes are defined in config."""
        config_path = Path(__file__).parent.parent.parent / "web" / "config.py"
        content = config_path.read_text()

        assert "MODES = {" in content, "MODES dictionary should be defined"
        assert '"normal"' in content, "Normal mode should be defined"
        assert '"wardrive"' in content, "Wardrive mode should be defined"


class TestTemplatesExist:
    """Test that template files exist."""

    def test_main_template_exists(self):
        """Verify the main template exists."""
        template_path = Path(__file__).parent.parent.parent / "web" / "templates" / "index.html"
        assert template_path.exists(), "index.html template should exist"

    def test_static_files_exist(self):
        """Verify static files exist."""
        static_path = Path(__file__).parent.parent.parent / "web" / "static"
        assert (static_path / "style.css").exists(), "style.css should exist"
        assert (static_path / "warpie.js").exists(), "warpie.js should exist"
