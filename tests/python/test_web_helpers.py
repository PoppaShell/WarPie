"""Unit tests for Flask route helper functions.

Tests internal helper functions that handle system operations:
- Kismet status detection
- System uptime
- Mode switching
- System control (reboot/shutdown)
- Log retrieval
- Target list I/O
- Filter script integration
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

# =============================================================================
# Main Routes Helper Tests
# =============================================================================


class TestGetKismetStatus:
    """Tests for get_kismet_status() helper function."""

    @patch("subprocess.run")
    def test_kismet_not_running(self, mock_run):
        """Returns False and 'Stopped' when Kismet is not running."""
        from web.routes.main import get_kismet_status

        mock_run.return_value = MagicMock(returncode=1, stdout="")

        running, mode = get_kismet_status()
        assert running is False
        assert mode == "Stopped"

    @patch("subprocess.run")
    def test_kismet_running_normal_mode(self, mock_run):
        """Returns True and 'Normal' when running in normal mode."""
        from web.routes.main import get_kismet_status

        mock_run.return_value = MagicMock(returncode=0, stdout="12345 kismet")

        running, mode = get_kismet_status()
        assert running is True
        assert mode == "Normal"

    @patch("subprocess.run")
    def test_kismet_running_wardrive_mode(self, mock_run):
        """Returns True and 'Wardrive' when running in wardrive mode."""
        from web.routes.main import get_kismet_status

        mock_run.return_value = MagicMock(returncode=0, stdout="12345 kismet --wardrive")

        running, mode = get_kismet_status()
        assert running is True
        assert mode == "Wardrive"

    @patch("subprocess.run")
    def test_kismet_running_targeted_mode(self, mock_run):
        """Returns True and 'Targeted' when running in targeted mode."""
        from web.routes.main import get_kismet_status

        mock_run.return_value = MagicMock(returncode=0, stdout="12345 kismet targeted")

        running, mode = get_kismet_status()
        assert running is True
        assert mode == "Targeted"

    @patch("subprocess.run")
    def test_kismet_status_handles_exception(self, mock_run):
        """Returns False and 'Unknown' on exception."""
        from web.routes.main import get_kismet_status

        mock_run.side_effect = Exception("Connection refused")

        running, mode = get_kismet_status()
        assert running is False
        assert mode == "Unknown"


class TestGetUptime:
    """Tests for get_uptime() helper function."""

    @patch.object(Path, "read_text")
    def test_uptime_calculation(self, mock_read):
        """Correctly calculates hours and minutes from /proc/uptime."""
        from web.routes.main import get_uptime

        # 10000 seconds = 2h 46m
        mock_read.return_value = "10000.50 500.25"

        result = get_uptime()
        assert result == "2h 46m"

    @patch.object(Path, "read_text")
    def test_uptime_handles_exception(self, mock_read):
        """Returns N/A on exception."""
        from web.routes.main import get_uptime

        mock_read.side_effect = FileNotFoundError()

        result = get_uptime()
        assert result == "N/A"


class TestSwitchMode:
    """Tests for switch_mode() helper function."""

    @patch("subprocess.run")
    def test_switch_mode_stop(self, mock_run):
        """Stop mode returns True without starting Kismet."""
        from web.routes.main import switch_mode

        result = switch_mode("stop")
        assert result is True

    @patch("subprocess.run")
    def test_switch_mode_invalid_mode(self, mock_run):
        """Invalid mode returns False."""
        from web.routes.main import switch_mode

        result = switch_mode("invalid_mode")
        assert result is False

    @patch("subprocess.run")
    @patch.object(Path, "mkdir")
    @patch.object(Path, "write_text")
    def test_switch_mode_normal(self, mock_write, mock_mkdir, mock_run):
        """Normal mode switch creates correct environment file."""
        from web.routes.main import switch_mode

        result = switch_mode("normal")
        assert result is True

    @patch("subprocess.run")
    @patch.object(Path, "mkdir")
    @patch.object(Path, "write_text")
    def test_switch_mode_targeted_with_lists(self, mock_write, mock_mkdir, mock_run):
        """Targeted mode includes target lists in environment."""
        from web.routes.main import switch_mode

        result = switch_mode("targeted", ["list1", "list2"])
        assert result is True


class TestRebootShutdown:
    """Tests for reboot_system() and shutdown_system() helpers."""

    @patch("subprocess.run")
    @patch("subprocess.Popen")
    def test_reboot_system_success(self, mock_popen, mock_run):
        """Successful reboot returns True."""
        from web.routes.main import reboot_system

        result = reboot_system()
        assert result is True
        mock_popen.assert_called()

    @patch("subprocess.run")
    @patch("subprocess.Popen")
    def test_reboot_system_failure(self, mock_popen, mock_run):
        """Failed reboot returns False."""
        from web.routes.main import reboot_system

        mock_popen.side_effect = Exception("Permission denied")

        result = reboot_system()
        assert result is False

    @patch("subprocess.run")
    @patch("subprocess.Popen")
    def test_shutdown_system_success(self, mock_popen, mock_run):
        """Successful shutdown returns True."""
        from web.routes.main import shutdown_system

        result = shutdown_system()
        assert result is True

    @patch("subprocess.run")
    @patch("subprocess.Popen")
    def test_shutdown_system_failure(self, mock_popen, mock_run):
        """Failed shutdown returns False."""
        from web.routes.main import shutdown_system

        mock_popen.side_effect = Exception("Permission denied")

        result = shutdown_system()
        assert result is False


# =============================================================================
# Log Routes Helper Tests
# =============================================================================


class TestGetLogs:
    """Tests for get_logs() helper function."""

    @patch("web.routes.logs._get_journal_logs")
    def test_get_logs_wardrive(self, mock_journal):
        """Wardrive source calls journal logs."""
        from web.routes.logs import get_logs

        mock_journal.return_value = ["Log line 1", "Log line 2"]

        result = get_logs("wardrive", 100)
        assert result == ["Log line 1", "Log line 2"]

    @patch("web.routes.logs._get_journal_logs")
    def test_get_logs_kismet(self, mock_journal):
        """Kismet source calls journal logs with cat format."""
        from web.routes.logs import get_logs

        mock_journal.return_value = ["Kismet log"]

        get_logs("kismet", 50)
        mock_journal.assert_called_with("wardrive", 50, "cat")

    @patch("web.routes.logs._get_wigle_logs")
    def test_get_logs_wigle(self, mock_wigle):
        """Wigle source calls wigle log function."""
        from web.routes.logs import get_logs

        mock_wigle.return_value = ["WiGLE data"]

        get_logs("wigle", 100)
        mock_wigle.assert_called_with(100)

    @patch("web.routes.logs._get_journal_logs")
    def test_get_logs_gps(self, mock_journal):
        """GPS source calls journal logs for gpsd-wardriver."""
        from web.routes.logs import get_logs

        mock_journal.return_value = ["GPS log"]

        get_logs("gps", 50)
        mock_journal.assert_called_with("gpsd-wardriver", 50)

    @patch("web.routes.logs._get_journal_logs")
    def test_get_logs_network(self, mock_journal):
        """Network source calls journal logs for warpie-network."""
        from web.routes.logs import get_logs

        mock_journal.return_value = ["Network log"]

        get_logs("network", 50)
        mock_journal.assert_called_with("warpie-network", 50)

    def test_get_logs_unknown_source(self):
        """Unknown source returns error message."""
        from web.routes.logs import get_logs

        result = get_logs("unknown", 100)
        assert result == ["Unknown log source"]

    @patch("web.routes.logs._get_journal_logs")
    def test_get_logs_handles_exception(self, mock_journal):
        """Exception returns error message."""
        from web.routes.logs import get_logs

        mock_journal.side_effect = Exception("Error")

        result = get_logs("wardrive", 100)
        assert result == ["An error occurred while retrieving logs"]


class TestGetWigleLogs:
    """Tests for _get_wigle_logs() helper function."""

    @patch("web.routes.logs.Path.glob")
    def test_wigle_no_files(self, mock_glob):
        """Returns message when no WiGLE files found."""
        from web.routes.logs import _get_wigle_logs

        mock_glob.return_value = []

        result = _get_wigle_logs(100)
        assert "No WiGLE CSV found" in result[0]

    @patch("subprocess.run")
    @patch("web.routes.logs.Path.glob")
    def test_wigle_reads_file(self, mock_glob, mock_run):
        """Returns file content from WiGLE CSV."""
        from web.routes.logs import _get_wigle_logs

        # Create a mock file path
        mock_path = MagicMock()
        mock_path.name = "test.wiglecsv"
        mock_path.stat.return_value = MagicMock(st_mtime=12345)
        mock_glob.return_value = [mock_path]

        mock_run.return_value = MagicMock(
            returncode=0, stdout="WiGLE,Header\ndata,line"
        )

        result = _get_wigle_logs(100)
        assert "=== test.wiglecsv ===" in result[0]

    @patch("subprocess.run")
    @patch("web.routes.logs.Path.glob")
    def test_wigle_empty_file(self, mock_glob, mock_run):
        """Returns (empty) for empty files."""
        from web.routes.logs import _get_wigle_logs

        mock_path = MagicMock()
        mock_path.name = "empty.wiglecsv"
        mock_path.stat.return_value = MagicMock(st_mtime=12345)
        mock_glob.return_value = [mock_path]

        mock_run.return_value = MagicMock(returncode=0, stdout="")

        result = _get_wigle_logs(100)
        assert "(empty)" in result

    @patch("subprocess.run")
    @patch("web.routes.logs.Path.glob")
    def test_wigle_read_error(self, mock_glob, mock_run):
        """Returns error message on read failure."""
        from web.routes.logs import _get_wigle_logs

        mock_path = MagicMock()
        mock_path.stat.return_value = MagicMock(st_mtime=12345)
        mock_glob.return_value = [mock_path]

        mock_run.return_value = MagicMock(returncode=1)

        result = _get_wigle_logs(100)
        assert result == ["Error reading WiGLE CSV"]


class TestGetJournalLogs:
    """Tests for _get_journal_logs() helper function."""

    @patch("subprocess.run")
    def test_journal_logs_success(self, mock_run):
        """Returns parsed journal lines on success."""
        from web.routes.logs import _get_journal_logs

        mock_run.return_value = MagicMock(
            returncode=0, stdout="Line 1\nLine 2\nLine 3\n"
        )

        result = _get_journal_logs("wardrive", 100)
        assert len(result) == 3
        assert result[0] == "Line 1"

    @patch("subprocess.run")
    def test_journal_logs_empty(self, mock_run):
        """Returns no entries message for empty logs."""
        from web.routes.logs import _get_journal_logs

        mock_run.return_value = MagicMock(returncode=0, stdout="")

        result = _get_journal_logs("wardrive", 100)
        assert result == ["No log entries found"]

    @patch("subprocess.run")
    def test_journal_logs_failure(self, mock_run):
        """Returns no entries message on failure."""
        from web.routes.logs import _get_journal_logs

        mock_run.return_value = MagicMock(returncode=1, stdout="")

        result = _get_journal_logs("wardrive", 100)
        assert result == ["No log entries found"]


# =============================================================================
# Target Routes Helper Tests
# =============================================================================


class TestTargetListIO:
    """Tests for target list load/save helper functions."""

    @patch.object(Path, "exists")
    def test_load_target_lists_no_file(self, mock_exists):
        """Returns builtin lists when no config file exists."""
        from web.routes.targets import load_target_lists

        mock_exists.return_value = False

        result = load_target_lists()
        assert "targeted-devices-example" in result

    @patch.object(Path, "read_text")
    @patch.object(Path, "exists")
    def test_load_target_lists_with_user_data(self, mock_exists, mock_read):
        """Merges user lists with builtin lists."""
        from web.routes.targets import load_target_lists

        mock_exists.return_value = True
        mock_read.return_value = json.dumps(
            {
                "lists": {
                    "user-list": {
                        "id": "user-list",
                        "name": "User List",
                        "ouis": [],
                    }
                }
            }
        )

        result = load_target_lists()
        assert "user-list" in result
        assert "targeted-devices-example" in result

    @patch.object(Path, "read_text")
    @patch.object(Path, "exists")
    def test_load_target_lists_hidden_lists(self, mock_exists, mock_read):
        """Hidden builtin lists are not returned."""
        from web.routes.targets import load_target_lists

        mock_exists.return_value = True
        mock_read.return_value = json.dumps(
            {"hidden_lists": ["targeted-devices-example"], "lists": {}}
        )

        result = load_target_lists()
        assert "targeted-devices-example" not in result

    @patch.object(Path, "read_text")
    @patch.object(Path, "exists")
    def test_load_target_lists_invalid_json(self, mock_exists, mock_read):
        """Returns builtin lists on JSON decode error."""
        from web.routes.targets import load_target_lists

        mock_exists.return_value = True
        mock_read.return_value = "invalid json"

        result = load_target_lists()
        assert "targeted-devices-example" in result

    @patch.object(Path, "write_text")
    @patch.object(Path, "mkdir")
    def test_save_target_lists_success(self, mock_mkdir, mock_write):
        """Returns True on successful save."""
        from web.routes.targets import save_target_lists

        result = save_target_lists(
            {"user-list": {"id": "user-list", "name": "User List", "ouis": []}}
        )
        assert result is True

    @patch.object(Path, "write_text")
    @patch.object(Path, "mkdir")
    def test_save_target_lists_failure(self, mock_mkdir, mock_write):
        """Returns False on write error."""
        from web.routes.targets import save_target_lists

        mock_write.side_effect = PermissionError("Cannot write")

        result = save_target_lists({})
        assert result is False

    @patch.object(Path, "read_text")
    @patch.object(Path, "exists")
    def test_get_hidden_lists(self, mock_exists, mock_read):
        """Returns list of hidden builtin list IDs."""
        from web.routes.targets import get_hidden_lists

        mock_exists.return_value = True
        mock_read.return_value = json.dumps(
            {"hidden_lists": ["list1", "list2"], "lists": {}}
        )

        result = get_hidden_lists()
        assert result == ["list1", "list2"]

    @patch.object(Path, "exists")
    def test_get_hidden_lists_no_file(self, mock_exists):
        """Returns empty list when no config file."""
        from web.routes.targets import get_hidden_lists

        mock_exists.return_value = False

        result = get_hidden_lists()
        assert result == []


# =============================================================================
# Filter Routes Helper Tests
# =============================================================================


class TestCallFilterScript:
    """Tests for call_filter_script() helper function."""

    @patch("subprocess.run")
    @patch.object(Path, "exists")
    def test_call_filter_script_success(self, mock_exists, mock_run):
        """Returns parsed JSON on success."""
        from web.routes.filters import call_filter_script

        mock_exists.return_value = True
        mock_run.return_value = MagicMock(
            stdout='{"success": true}', stderr="", returncode=0
        )

        result = call_filter_script("--list")
        assert result["success"] is True

    @patch.object(Path, "exists")
    def test_call_filter_script_no_script(self, mock_exists):
        """Returns error when no script found."""
        from web.routes.filters import call_filter_script

        mock_exists.return_value = False

        result = call_filter_script("--list")
        assert result["success"] is False
        assert "found" in result["error"]

    @patch("subprocess.run")
    @patch.object(Path, "exists")
    def test_call_filter_script_invalid_json(self, mock_exists, mock_run):
        """Returns error on invalid JSON response."""
        from web.routes.filters import call_filter_script

        mock_exists.return_value = True
        mock_run.return_value = MagicMock(stdout="not json", stderr="", returncode=0)

        result = call_filter_script("--list")
        assert result["success"] is False
        assert "Invalid JSON" in result["error"]

    @patch("subprocess.run")
    @patch.object(Path, "exists")
    def test_call_filter_script_timeout(self, mock_exists, mock_run):
        """Returns error on timeout."""
        from web.routes.filters import call_filter_script

        mock_exists.return_value = True
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=30)

        result = call_filter_script("--list")
        assert result["success"] is False
        assert "timeout" in result["error"].lower()

    @patch("subprocess.run")
    @patch.object(Path, "exists")
    def test_call_filter_script_stderr(self, mock_exists, mock_run):
        """Returns error from stderr when no stdout."""
        from web.routes.filters import call_filter_script

        mock_exists.return_value = True
        mock_run.return_value = MagicMock(
            stdout="", stderr="Error message", returncode=1
        )

        result = call_filter_script("--list")
        assert result["success"] is False
        assert "Error message" in result["error"]

    @patch("subprocess.run")
    @patch.object(Path, "exists")
    def test_call_filter_script_no_output(self, mock_exists, mock_run):
        """Returns error when no output at all."""
        from web.routes.filters import call_filter_script

        mock_exists.return_value = True
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)

        result = call_filter_script("--list")
        assert result["success"] is False
        assert "No output" in result["error"]


class TestCallProcessorScript:
    """Tests for call_processor_script() helper function."""

    @patch("subprocess.run")
    @patch.object(Path, "exists")
    def test_call_processor_script_success(self, mock_exists, mock_run):
        """Returns parsed JSON on success."""
        from web.routes.filters import call_processor_script

        mock_exists.return_value = True
        mock_run.return_value = MagicMock(
            stdout='{"success": true}', stderr="", returncode=0
        )

        result = call_processor_script("--preview", "/path")
        assert result["success"] is True

    @patch.object(Path, "exists")
    def test_call_processor_script_not_installed(self, mock_exists):
        """Returns error when processor not installed."""
        from web.routes.filters import call_processor_script

        mock_exists.return_value = False

        result = call_processor_script("--preview", "/path")
        assert result["success"] is False
        assert "not installed" in result["error"]

    @patch("subprocess.run")
    @patch.object(Path, "exists")
    def test_call_processor_script_timeout(self, mock_exists, mock_run):
        """Returns error on timeout."""
        from web.routes.filters import call_processor_script

        mock_exists.return_value = True
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=60)

        result = call_processor_script("--preview", "/path")
        assert result["success"] is False
        assert "timeout" in result["error"].lower()
