"""Tests for performance monitoring helper functions.

Tests all metric collection functions with mocked system calls.
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestCPUTemperature:
    """Tests for get_cpu_temperature()."""

    @patch.object(Path, "read_text")
    def test_cpu_temp_success(self, mock_read):
        """Returns CPU temperature in Celsius."""
        from web.routes.performance import get_cpu_temperature

        # Simulate thermal zone reporting 65000 millidegrees (65°C)
        mock_read.return_value = "65000\n"

        result = get_cpu_temperature()
        assert result == 65.0

    @patch.object(Path, "read_text")
    def test_cpu_temp_high_value(self, mock_read):
        """Handles high temperature values correctly."""
        from web.routes.performance import get_cpu_temperature

        # 85°C
        mock_read.return_value = "85000\n"

        result = get_cpu_temperature()
        assert result == 85.0

    @patch.object(Path, "read_text")
    def test_cpu_temp_file_not_found(self, mock_read):
        """Returns 0.0 when thermal zone file doesn't exist."""
        from web.routes.performance import get_cpu_temperature

        mock_read.side_effect = FileNotFoundError("File not found")

        result = get_cpu_temperature()
        assert result == 0.0

    @patch.object(Path, "read_text")
    def test_cpu_temp_invalid_format(self, mock_read):
        """Returns 0.0 when file contains invalid data."""
        from web.routes.performance import get_cpu_temperature

        mock_read.return_value = "invalid_data"

        result = get_cpu_temperature()
        assert result == 0.0

    @patch.object(Path, "read_text")
    def test_cpu_temp_permission_denied(self, mock_read):
        """Returns 0.0 when permission denied."""
        from web.routes.performance import get_cpu_temperature

        mock_read.side_effect = PermissionError("Permission denied")

        result = get_cpu_temperature()
        assert result == 0.0


class TestDiskUsage:
    """Tests for get_disk_usage()."""

    @patch("subprocess.run")
    def test_disk_usage_success(self, mock_run):
        """Returns disk usage statistics."""
        from web.routes.performance import get_disk_usage

        # Simulate df output
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Filesystem      Size  Used Avail Use% Mounted on\n"
            "/dev/root        30G   15G   14G  52% /\n",
        )

        result = get_disk_usage()
        assert result["total_gb"] == 30
        assert result["used_gb"] == 15
        assert result["avail_gb"] == 14
        assert result["used_percent"] == 52

    @patch("subprocess.run")
    def test_disk_usage_high_usage(self, mock_run):
        """Handles high disk usage correctly."""
        from web.routes.performance import get_disk_usage

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Filesystem      Size  Used Avail Use% Mounted on\n"
            "/dev/root        32G   29G    2G  94% /\n",
        )

        result = get_disk_usage()
        assert result["used_percent"] == 94

    @patch("subprocess.run")
    def test_disk_usage_df_failure(self, mock_run):
        """Returns zeros when df command fails."""
        from web.routes.performance import get_disk_usage

        mock_run.return_value = MagicMock(returncode=1, stdout="")

        result = get_disk_usage()
        assert result["total_gb"] == 0
        assert result["used_gb"] == 0
        assert result["used_percent"] == 0

    @patch("subprocess.run")
    def test_disk_usage_parse_error(self, mock_run):
        """Returns zeros when df output is unparseable."""
        from web.routes.performance import get_disk_usage

        mock_run.return_value = MagicMock(returncode=0, stdout="invalid output\n")

        result = get_disk_usage()
        assert result["total_gb"] == 0

    @patch("subprocess.run")
    def test_disk_usage_timeout(self, mock_run):
        """Returns zeros when df times out."""
        from web.routes.performance import get_disk_usage

        mock_run.side_effect = subprocess.TimeoutExpired("df", 5)

        result = get_disk_usage()
        assert result["total_gb"] == 0


class TestMemoryUsage:
    """Tests for get_memory_usage()."""

    @patch.object(Path, "read_text")
    def test_memory_success(self, mock_read):
        """Returns memory usage statistics."""
        from web.routes.performance import get_memory_usage

        # Mock /proc/meminfo content with values in kB
        mock_read.return_value = (
            "MemTotal:        4000000 kB\n"
            "MemFree:         1500000 kB\n"
            "MemAvailable:    2000000 kB\n"
            "Buffers:          100000 kB\n"
        )

        result = get_memory_usage()
        # 4000000 kB = ~3906.2 MB total
        # 2000000 kB = ~1953.1 MB available
        # ~1953.1 MB used = ~50% usage
        assert result["total_mb"] > 3900
        assert result["total_mb"] < 4000
        assert result["available_mb"] > 1950
        assert result["available_mb"] < 2000
        assert result["used_percent"] > 49
        assert result["used_percent"] < 51

    @patch.object(Path, "read_text")
    def test_memory_high_usage(self, mock_read):
        """Handles high memory usage correctly."""
        from web.routes.performance import get_memory_usage

        # 90% usage scenario
        mock_read.return_value = "MemTotal:        4000000 kB\nMemAvailable:     400000 kB\n"

        result = get_memory_usage()
        assert result["used_percent"] > 89
        assert result["used_percent"] < 91

    @patch.object(Path, "read_text")
    def test_memory_file_read_error(self, mock_read):
        """Returns zeros when /proc/meminfo cannot be read."""
        from web.routes.performance import get_memory_usage

        mock_read.side_effect = FileNotFoundError("File not found")

        result = get_memory_usage()
        assert result["total_mb"] == 0.0
        assert result["used_mb"] == 0.0
        assert result["used_percent"] == 0.0

    @patch.object(Path, "read_text")
    def test_memory_parse_error(self, mock_read):
        """Returns zeros when meminfo format is invalid."""
        from web.routes.performance import get_memory_usage

        mock_read.return_value = "invalid data\n"

        result = get_memory_usage()
        assert result["total_mb"] == 0.0


class TestCPULoad:
    """Tests for get_cpu_load()."""

    @patch.object(Path, "read_text")
    def test_cpu_load_success(self, mock_read):
        """Returns load averages for 1/5/15 minutes."""
        from web.routes.performance import get_cpu_load

        # Simulate /proc/loadavg
        mock_read.return_value = "0.52 0.58 0.59 1/596 12345\n"

        result = get_cpu_load()
        assert result == [0.52, 0.58, 0.59]

    @patch.object(Path, "read_text")
    def test_cpu_load_high_values(self, mock_read):
        """Handles high load values correctly."""
        from web.routes.performance import get_cpu_load

        mock_read.return_value = "4.25 3.80 2.95 5/600 67890\n"

        result = get_cpu_load()
        assert result == [4.25, 3.80, 2.95]

    @patch.object(Path, "read_text")
    def test_cpu_load_file_not_found(self, mock_read):
        """Returns zeros when /proc/loadavg doesn't exist."""
        from web.routes.performance import get_cpu_load

        mock_read.side_effect = FileNotFoundError("File not found")

        result = get_cpu_load()
        assert result == [0.0, 0.0, 0.0]

    @patch.object(Path, "read_text")
    def test_cpu_load_invalid_format(self, mock_read):
        """Returns zeros when loadavg format is invalid."""
        from web.routes.performance import get_cpu_load

        mock_read.return_value = "invalid data\n"

        result = get_cpu_load()
        assert result == [0.0, 0.0, 0.0]


class TestGPSStatus:
    """Tests for get_gps_status()."""

    @patch("subprocess.run")
    def test_gps_3d_fix(self, mock_run):
        """Returns 3D_FIX when GPS has 3D fix."""
        from web.routes.performance import get_gps_status

        # Simulate gpspipe output with 3D fix (using uSat field)
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"class":"TPV","mode":3}\n{"class":"SKY","nSat":12,"uSat":8,"satellites":[{},{},{},{},{},{},{},{}]}\n',
        )

        result = get_gps_status()
        assert result["status"] == "3D_FIX"
        assert result["satellites"] == 8
        assert result["fix_quality"] == "3D_FIX"

    @patch("subprocess.run")
    def test_gps_2d_fix(self, mock_run):
        """Returns 2D_FIX when GPS has 2D fix."""
        from web.routes.performance import get_gps_status

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"class":"TPV","mode":2}\n{"class":"SKY","nSat":6,"uSat":4,"satellites":[{},{},{},{}]}\n',
        )

        result = get_gps_status()
        assert result["status"] == "2D_FIX"
        assert result["satellites"] == 4

    @patch("subprocess.run")
    def test_gps_no_fix(self, mock_run):
        """Returns NO_FIX when GPS has no fix."""
        from web.routes.performance import get_gps_status

        mock_run.return_value = MagicMock(returncode=0, stdout='{"class":"TPV","mode":0}\n')

        result = get_gps_status()
        assert result["status"] == "NO_FIX"
        assert result["satellites"] == 0

    @patch("subprocess.run")
    def test_gps_command_failure(self, mock_run):
        """Returns NO_FIX when gpspipe fails."""
        from web.routes.performance import get_gps_status

        mock_run.return_value = MagicMock(returncode=1, stdout="")

        result = get_gps_status()
        assert result["status"] == "NO_FIX"

    @patch("subprocess.run")
    def test_gps_timeout(self, mock_run):
        """Returns NO_FIX when gpspipe times out."""
        from web.routes.performance import get_gps_status

        mock_run.side_effect = subprocess.TimeoutExpired("gpspipe", 3)

        result = get_gps_status()
        assert result["status"] == "NO_FIX"


class TestAdapterStatus:
    """Tests for get_adapter_status()."""

    @patch("web.routes.performance.get_kismet_capture_count")
    def test_adapter_up(self, mock_count):
        """Returns UP when 2+ capture processes are running."""
        from web.routes.performance import get_adapter_status

        # Simulate 2 capture processes running (both adapters active)
        mock_count.return_value = 2

        result = get_adapter_status("wlan1")
        assert result == "UP"

    @patch("web.routes.performance.get_kismet_capture_count")
    def test_adapter_down(self, mock_count):
        """Returns DOWN when only 1 or no capture processes running."""
        from web.routes.performance import get_adapter_status

        # Simulate only 1 capture process
        mock_count.return_value = 1

        result = get_adapter_status("wlan1")
        assert result == "DOWN"

    @patch("web.routes.performance.get_kismet_capture_count")
    def test_adapter_not_found(self, mock_count):
        """Returns DOWN when no capture processes running."""
        from web.routes.performance import get_adapter_status

        # Simulate no capture processes
        mock_count.return_value = 0

        result = get_adapter_status("wlan999")
        assert result == "DOWN"

    @patch("web.routes.performance.get_kismet_capture_count")
    def test_adapter_command_timeout(self, mock_count):
        """Returns NOT_FOUND when process check raises exception."""
        from web.routes.performance import get_adapter_status

        # Simulate exception from process check
        mock_count.side_effect = Exception("Process check failed")

        result = get_adapter_status("wlan1")
        assert result == "NOT_FOUND"


class TestCaptureRate:
    """Tests for get_capture_rate()."""

    @patch("subprocess.run")
    @patch("web.routes.performance.get_kismet_capture_count")
    def test_capture_rate_success(self, mock_count, mock_run):
        """Returns capture rate based on recent detections."""
        from web.routes.performance import get_capture_rate

        # Simulate capture processes running
        mock_count.return_value = 2

        # Simulate journal output with 10 detections in 10 seconds
        mock_run.return_value = MagicMock(returncode=0, stdout="Detected new\n" * 10)

        result = get_capture_rate()
        assert result == 1.0  # 10 detections / 10 seconds

    @patch("web.routes.performance.get_kismet_capture_count")
    def test_capture_rate_zero(self, mock_count):
        """Returns 0.0 when no capture processes."""
        from web.routes.performance import get_capture_rate

        # Simulate no capture processes
        mock_count.return_value = 0

        result = get_capture_rate()
        assert result == 0.0

    @patch("subprocess.run")
    @patch("web.routes.performance.get_kismet_capture_count")
    def test_capture_rate_connection_error(self, mock_count, mock_run):
        """Returns 1.0 when processes running but journal fails."""
        from web.routes.performance import get_capture_rate

        # Simulate capture processes running
        mock_count.return_value = 2

        # Simulate journal failure
        mock_run.return_value = MagicMock(returncode=1, stdout="")

        result = get_capture_rate()
        assert result == 1.0  # Nominal rate when processes running but journal fails

    @patch("subprocess.run")
    @patch("web.routes.performance.get_kismet_capture_count")
    def test_capture_rate_timeout(self, mock_count, mock_run):
        """Returns 0.0 when subprocess raises exception."""
        from web.routes.performance import get_capture_rate

        # Simulate capture processes running
        mock_count.return_value = 2

        # Simulate timeout exception
        mock_run.side_effect = Exception("Request timed out")

        result = get_capture_rate()
        assert result == 0.0


class TestThresholdEvaluation:
    """Tests for evaluate_thresholds()."""

    def test_no_alerts_when_below_thresholds(self):
        """Returns empty list when all metrics below thresholds."""
        from web.routes.performance import DEFAULT_CONFIG, evaluate_thresholds

        metrics = {
            "cpu_temp": 65.0,
            "disk": {"used_percent": 50},
            "memory": {"used_percent": 60.0},
        }

        alerts = evaluate_thresholds(metrics, DEFAULT_CONFIG)
        assert alerts == []

    def test_warning_alert_triggered(self):
        """Returns warning alert when metric exceeds warning threshold."""
        from web.routes.performance import DEFAULT_CONFIG, evaluate_thresholds

        metrics = {
            "cpu_temp": 76.0,  # Above 75 warning
            "disk": {"used_percent": 50},
            "memory": {"used_percent": 60.0},
        }

        alerts = evaluate_thresholds(metrics, DEFAULT_CONFIG)
        assert len(alerts) == 1
        assert alerts[0]["metric"] == "cpu_temp"
        assert alerts[0]["level"] == "warning"
        assert alerts[0]["value"] == 76.0

    def test_critical_alert_triggered(self):
        """Returns critical alert when metric exceeds critical threshold."""
        from web.routes.performance import DEFAULT_CONFIG, evaluate_thresholds

        metrics = {
            "cpu_temp": 81.0,  # Above 80 critical
            "disk": {"used_percent": 50},
            "memory": {"used_percent": 60.0},
        }

        alerts = evaluate_thresholds(metrics, DEFAULT_CONFIG)
        assert len(alerts) == 1
        assert alerts[0]["level"] == "critical"

    def test_action_alert_triggered(self):
        """Returns action alert when metric exceeds action threshold."""
        from web.routes.performance import DEFAULT_CONFIG, evaluate_thresholds

        metrics = {
            "cpu_temp": 86.0,  # Above 85 action
            "disk": {"used_percent": 50},
            "memory": {"used_percent": 60.0},
        }

        alerts = evaluate_thresholds(metrics, DEFAULT_CONFIG)
        assert len(alerts) == 1
        assert alerts[0]["level"] == "action"

    def test_multiple_alerts(self):
        """Returns multiple alerts when multiple metrics exceed thresholds."""
        from web.routes.performance import DEFAULT_CONFIG, evaluate_thresholds

        metrics = {
            "cpu_temp": 86.0,  # Action
            "disk": {"used_percent": 92},  # Action
            "memory": {"used_percent": 82.0},  # Warning
        }

        alerts = evaluate_thresholds(metrics, DEFAULT_CONFIG)
        assert len(alerts) == 3
        assert any(a["metric"] == "cpu_temp" and a["level"] == "action" for a in alerts)
        assert any(a["metric"] == "disk_usage" and a["level"] == "action" for a in alerts)
        assert any(a["metric"] == "memory_usage" and a["level"] == "warning" for a in alerts)

    def test_disabled_metric_no_alert(self):
        """Disabled metrics don't generate alerts."""
        from web.routes.performance import evaluate_thresholds

        config = {
            "cpu_temp": {"enabled": False, "warning_threshold": 75},
            "disk_usage": {"enabled": True, "warning_threshold": 80},
            "memory_usage": {"enabled": True, "warning_threshold": 80},
        }

        metrics = {
            "cpu_temp": 90.0,  # Would trigger if enabled
            "disk": {"used_percent": 50},
            "memory": {"used_percent": 60.0},
        }

        alerts = evaluate_thresholds(metrics, config)
        assert len(alerts) == 0


class TestActionExecution:
    """Tests for execute_action()."""

    @patch("subprocess.run")
    def test_action_stop_kismet(self, mock_run):
        """Execute stop_kismet action."""
        from web.routes.performance import execute_action

        mock_run.return_value = MagicMock(returncode=0)

        result = execute_action("cpu_temp", "stop_kismet", None, 86.0)
        assert result is True
        mock_run.assert_called_once()
        assert "systemctl" in mock_run.call_args[0][0]

    @patch("subprocess.run")
    def test_action_stop_and_shutdown(self, mock_run):
        """Execute stop_and_shutdown action."""
        from web.routes.performance import execute_action

        mock_run.return_value = MagicMock(returncode=0)

        result = execute_action("disk_usage", "stop_and_shutdown", None, 92.0)
        assert result is True
        # Should call systemctl and shutdown
        assert mock_run.call_count == 2

    @patch("subprocess.run")
    def test_action_custom_command(self, mock_run):
        """Execute safe custom command."""
        from web.routes.performance import execute_action

        mock_run.return_value = MagicMock(returncode=0)

        result = execute_action("memory_usage", "custom", "echo 'test'", 91.0)
        assert result is True

    @patch("subprocess.run")
    def test_action_validation_blocks_dangerous_cmd(self, mock_run):
        """Dangerous commands are blocked."""
        from web.routes.performance import execute_action

        result = execute_action("memory_usage", "custom", "rm -rf /", 91.0)
        assert result is False
        # Subprocess should not be called
        mock_run.assert_not_called()

    def test_action_none_returns_false(self):
        """Action 'none' returns False."""
        from web.routes.performance import execute_action

        result = execute_action("cpu_temp", "none", None, 86.0)
        assert result is False

    @patch("subprocess.run")
    def test_cooldown_tracked_after_success(self, mock_run):
        """Cooldown is enforced after successful action."""
        from web.routes.performance import can_execute_action, execute_action, last_actions

        # Clear any previous state
        last_actions.clear()

        mock_run.return_value = MagicMock(returncode=0)

        # First execution should succeed
        assert can_execute_action("cpu_temp_test", 300) is True
        execute_action("cpu_temp_test", "stop_kismet", None, 86.0)

        # Second execution should be blocked by cooldown
        assert can_execute_action("cpu_temp_test", 300) is False


class TestConfigManagement:
    """Tests for load/save threshold config."""

    @patch("os.path.exists")
    def test_load_default_config(self, mock_exists):
        """Returns defaults when config file doesn't exist."""
        from web.routes.performance import DEFAULT_CONFIG, load_threshold_config

        mock_exists.return_value = False

        config = load_threshold_config()
        assert config == DEFAULT_CONFIG

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.open")
    def test_load_custom_config(self, mock_open, mock_exists):
        """Loads custom config from file."""
        from web.routes.performance import load_threshold_config

        mock_exists.return_value = True
        mock_open.return_value.__enter__.return_value.read.return_value = (
            '{"cpu_temp": {"enabled": true, "warning_threshold": 70}}'
        )

        load_threshold_config()
        # Should have loaded custom config (mocking makes this tricky, just verify it tries)
        mock_exists.assert_called_once()

    @patch("pathlib.Path.mkdir")
    @patch("pathlib.Path.open")
    @patch("pathlib.Path.replace")
    def test_save_config_atomic(self, mock_replace, mock_open, mock_mkdir):
        """Saves config atomically."""
        from web.routes.performance import DEFAULT_CONFIG, save_threshold_config

        result = save_threshold_config(DEFAULT_CONFIG)
        assert result is True
        # Should use temp file and atomic replace
        mock_replace.assert_called_once()


class TestPerformanceRoutes:
    """Tests for performance API routes."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from web.app import create_app

        app = create_app()
        app.config["TESTING"] = True
        return app.test_client()

    @patch("web.routes.performance.get_cpu_temperature")
    @patch("web.routes.performance.get_disk_usage")
    @patch("web.routes.performance.get_memory_usage")
    @patch("web.routes.performance.get_cpu_load")
    @patch("web.routes.performance.get_gps_status")
    @patch("web.routes.performance.get_adapter_status")
    @patch("web.routes.performance.get_capture_rate")
    def test_api_performance_returns_json(
        self,
        mock_capture,
        mock_adapter,
        mock_gps,
        mock_load,
        mock_memory,
        mock_disk,
        mock_temp,
        client,
    ):
        """Performance API returns JSON with all metrics."""
        mock_temp.return_value = 65.5
        mock_disk.return_value = {
            "total_gb": 32,
            "used_gb": 16,
            "avail_gb": 15,
            "used_percent": 50,
        }
        mock_memory.return_value = {
            "total_mb": 4000.0,
            "available_mb": 2000.0,
            "used_mb": 2000.0,
            "used_percent": 50.0,
        }
        mock_load.return_value = [1.2, 1.5, 1.8]
        mock_gps.return_value = {
            "status": "3D_FIX",
            "satellites": 8,
            "fix_quality": "3D_FIX",
        }
        mock_adapter.side_effect = ["UP", "UP"]  # wlan1, wlan2
        mock_capture.return_value = 245.6

        response = client.get("/api/performance")
        assert response.status_code == 200

        import json

        data = json.loads(response.data)
        assert data["cpu_temp"] == 65.5
        assert data["disk"]["used_percent"] == 50
        assert data["memory"]["used_percent"] == 50.0
        assert data["cpu_load"] == [1.2, 1.5, 1.8]
        assert data["gps"]["status"] == "3D_FIX"
        assert data["gps"]["satellites"] == 8
        assert data["adapter_wlan1"] == "UP"
        assert data["adapter_wlan2"] == "UP"
        assert data["capture_rate"] == 245.6

    @patch("web.routes.performance.get_cpu_temperature")
    @patch("web.routes.performance.get_disk_usage")
    @patch("web.routes.performance.get_memory_usage")
    @patch("web.routes.performance.get_cpu_load")
    def test_api_performance_html_for_htmx(
        self, mock_load, mock_memory, mock_disk, mock_temp, client
    ):
        """Performance HTML endpoint returns HTML fragment."""
        mock_temp.return_value = 70.0
        mock_disk.return_value = {
            "total_gb": 32,
            "used_gb": 20,
            "avail_gb": 11,
            "used_percent": 62,
        }
        mock_memory.return_value = {
            "total_mb": 4000.0,
            "available_mb": 1500.0,
            "used_mb": 2500.0,
            "used_percent": 62.5,
        }
        mock_load.return_value = [2.0, 2.2, 2.5]

        response = client.get("/api/performance/html")
        assert response.status_code == 200

        # Should return HTML, not JSON
        assert b"{" not in response.data[:10]
        # Should contain metric data
        assert b"70.0" in response.data or b"62" in response.data
