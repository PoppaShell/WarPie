"""WarPie Web Control Panel - Performance Monitoring Routes.

Handles system performance metrics, threshold monitoring, and automatic
response actions for the WarPie Raspberry Pi wardriving platform.
"""

import subprocess
from pathlib import Path

from flask import Blueprint, jsonify, render_template

performance_bp = Blueprint("performance", __name__)


# =============================================================================
# Phase 1: Core Metric Collection Functions
# =============================================================================


def get_cpu_temperature() -> float:
    """Get CPU temperature in Celsius.

    Reads from /sys/class/thermal/thermal_zone0/temp which reports
    temperature in millidegrees Celsius.

    Returns:
        CPU temperature in Celsius, or 0.0 on failure.
    """
    try:
        temp_path = Path("/sys/class/thermal/thermal_zone0/temp")
        temp_str = temp_path.read_text().strip()
        # Convert from millidegrees to degrees
        return float(temp_str) / 1000.0
    except Exception:
        return 0.0


def get_disk_usage() -> dict:
    """Get disk usage statistics for /var/log/kismet.

    Returns:
        Dict with total_gb, used_gb, avail_gb, and used_percent.
        Returns zeros on failure.
    """
    try:
        result = subprocess.run(
            ["df", "-BG", "/var/log/kismet"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            # Parse df output
            # Example: /dev/root       30G  14G  15G  48% /
            lines = result.stdout.strip().split("\n")
            if len(lines) >= 2:
                parts = lines[1].split()
                if len(parts) >= 5:
                    # Remove 'G' suffix and convert to int
                    total_gb = int(parts[1].rstrip("G"))
                    used_gb = int(parts[2].rstrip("G"))
                    avail_gb = int(parts[3].rstrip("G"))
                    used_percent = int(parts[4].rstrip("%"))

                    return {
                        "total_gb": total_gb,
                        "used_gb": used_gb,
                        "avail_gb": avail_gb,
                        "used_percent": used_percent,
                    }
    except Exception:
        pass

    return {
        "total_gb": 0,
        "used_gb": 0,
        "avail_gb": 0,
        "used_percent": 0,
    }


def get_memory_usage() -> dict:
    """Get memory usage statistics from /proc/meminfo.

    Returns:
        Dict with total_mb, available_mb, used_mb, and used_percent.
        Returns zeros on failure.
    """
    try:
        meminfo_path = Path("/proc/meminfo")
        meminfo = meminfo_path.read_text()

        # Parse meminfo for MemTotal and MemAvailable
        mem_total = 0
        mem_available = 0

        for line in meminfo.split("\n"):
            if line.startswith("MemTotal:"):
                mem_total = int(line.split()[1])  # kB
            elif line.startswith("MemAvailable:"):
                mem_available = int(line.split()[1])  # kB

        if mem_total > 0:
            # Convert kB to MB
            total_mb = mem_total / 1024
            available_mb = mem_available / 1024
            used_mb = total_mb - available_mb
            used_percent = (used_mb / total_mb) * 100

            return {
                "total_mb": round(total_mb, 1),
                "available_mb": round(available_mb, 1),
                "used_mb": round(used_mb, 1),
                "used_percent": round(used_percent, 1),
            }
    except Exception:
        pass

    return {
        "total_mb": 0.0,
        "available_mb": 0.0,
        "used_mb": 0.0,
        "used_percent": 0.0,
    }


def get_cpu_load() -> list[float]:
    """Get CPU load averages from /proc/loadavg.

    Returns:
        List of [1min, 5min, 15min] load averages.
        Returns [0.0, 0.0, 0.0] on failure.
    """
    try:
        loadavg_path = Path("/proc/loadavg")
        loadavg = loadavg_path.read_text().strip()

        # Format: 0.52 0.58 0.59 1/596 12345
        parts = loadavg.split()
        if len(parts) >= 3:
            return [
                round(float(parts[0]), 2),
                round(float(parts[1]), 2),
                round(float(parts[2]), 2),
            ]
    except Exception:
        pass

    return [0.0, 0.0, 0.0]


# =============================================================================
# Phase 1: API Routes
# =============================================================================


@performance_bp.route("/performance")
def api_performance():
    """Get performance metrics as JSON.

    Returns:
        JSON with all Phase 1 metrics: cpu_temp, disk_usage, memory_usage, cpu_load.
    """
    return jsonify(
        {
            "cpu_temp": get_cpu_temperature(),
            "disk": get_disk_usage(),
            "memory": get_memory_usage(),
            "cpu_load": get_cpu_load(),
        }
    )


@performance_bp.route("/performance/html")
def api_performance_html():
    """Get performance metrics as HTML fragment for HTMX.

    Returns:
        HTML partial with metrics display for flyout.
    """
    return render_template(
        "partials/_performance_metrics.html",
        cpu_temp=get_cpu_temperature(),
        disk=get_disk_usage(),
        memory=get_memory_usage(),
        cpu_load=get_cpu_load(),
    )
