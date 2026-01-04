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

        mock_run.side_effect = subprocess.TimeoutExpired("df", 5)  # noqa: F821

        result = get_disk_usage()
        assert result["total_gb"] == 0


class TestMemoryUsage:
    """Tests for get_memory_usage()."""

    @patch.object(Path, "read_text")
    def test_memory_success(self, mock_read):
        """Returns memory usage statistics."""
        from web.routes.performance import get_memory_usage

        # Simulate /proc/meminfo (values in kB)
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
        mock_read.return_value = (
            "MemTotal:        4000000 kB\n" "MemAvailable:     400000 kB\n"
        )

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
    def test_api_performance_returns_json(
        self, mock_load, mock_memory, mock_disk, mock_temp, client
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

        response = client.get("/api/performance")
        assert response.status_code == 200

        import json

        data = json.loads(response.data)
        assert data["cpu_temp"] == 65.5
        assert data["disk"]["used_percent"] == 50
        assert data["memory"]["used_percent"] == 50.0
        assert data["cpu_load"] == [1.2, 1.5, 1.8]

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
