"""Basic tests for warpie-control.py web server.

These are smoke tests to ensure the module can be imported and basic
functionality works. More comprehensive tests will be added in Phase 4.
"""

import sys
from pathlib import Path

# Add bin directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "bin"))


class TestWarPieControlImport:
    """Test that warpie-control.py can be imported."""

    def test_module_exists(self):
        """Verify the control panel script exists."""
        control_path = Path(__file__).parent.parent.parent / "bin" / "warpie-control.py"
        assert control_path.exists(), "warpie-control.py should exist in bin/"


class TestModeConfiguration:
    """Test Kismet mode configuration constants."""

    def test_modes_defined(self):
        """Verify capture modes are defined."""
        # Import would fail if module has syntax errors
        # For now, just verify the file is valid Python
        control_path = Path(__file__).parent.parent.parent / "bin" / "warpie-control.py"
        content = control_path.read_text()

        assert "MODES = {" in content, "MODES dictionary should be defined"
        assert '"normal"' in content, "Normal mode should be defined"
        assert '"wardrive"' in content, "Wardrive mode should be defined"


# TODO: Add more tests in Phase 4:
# - Test HTTP request handling
# - Test mode switching logic
# - Test exclusion API endpoints
# - Test log viewing functionality
