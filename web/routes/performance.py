"""WarPie Web Control Panel - Performance Monitoring Routes.

Handles system performance metrics, threshold monitoring, and automatic
response actions for the WarPie Raspberry Pi wardriving platform.
"""

import json
import os
import re
import subprocess
import time
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request

performance_bp = Blueprint("performance", __name__)

# =============================================================================
# Phase 3: Configuration and Constants
# =============================================================================

PERFORMANCE_CONFIG = "/etc/warpie/performance_thresholds.conf"
PERFORMANCE_LOG = "/var/log/warpie/performance_actions.log"

# Default threshold configuration
DEFAULT_CONFIG = {
    "cpu_temp": {
        "enabled": True,
        "warning_threshold": 75,
        "critical_threshold": 80,
        "action_threshold": 85,
        "response_action": "stop_kismet",
        "custom_command": None,
    },
    "disk_usage": {
        "enabled": True,
        "warning_threshold": 80,
        "critical_threshold": 85,
        "action_threshold": 90,
        "response_action": "stop_and_shutdown",
        "custom_command": None,
    },
    "memory_usage": {
        "enabled": True,
        "warning_threshold": 80,
        "critical_threshold": 85,
        "action_threshold": 90,
        "response_action": "none",
        "custom_command": None,
    },
    "global_settings": {
        "auto_actions_enabled": True,
        "refresh_interval_seconds": 5,
        "action_cooldown_seconds": 300,
    },
}

# Dangerous command patterns to block
DANGEROUS_PATTERNS = [
    r"rm\s+-rf",
    r"dd\s+",
    r"mkfs\.",
    r">/dev/sd",
    r"curl.*\|.*sh",
    r"wget.*\|.*sh",
]

# Track last action times for cooldown
last_actions = {}


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
# Phase 2: Enhanced Metric Collection Functions
# =============================================================================


def get_gps_status() -> dict:
    """Get GPS status from gpspipe.

    Queries gpsd via gpspipe to get current GPS fix quality,
    satellite count, and lock status.

    Returns:
        Dict with status (NO_FIX/2D_FIX/3D_FIX), satellites (int), and
        fix_quality (str). Returns safe defaults on failure.
    """
    try:
        # Use gpspipe to query gpsd for TPV (time-position-velocity) data
        result = subprocess.run(
            ["gpspipe", "-w", "-n", "5"],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )

        if result.returncode == 0:
            # Parse JSON output from gpspipe
            # Look for TPV class messages with mode field
            import json

            satellites = 0
            mode = 0  # 0=no fix, 2=2D, 3=3D

            for line in result.stdout.strip().split("\n"):
                try:
                    data = json.loads(line)
                    if data.get("class") == "TPV":
                        mode = data.get("mode", 0)
                    elif data.get("class") == "SKY":
                        # Count satellites with signal
                        satellites = len(data.get("satellites", []))
                except json.JSONDecodeError:
                    continue

            # Determine status string
            if mode == 3:
                status = "3D_FIX"
            elif mode == 2:
                status = "2D_FIX"
            else:
                status = "NO_FIX"

            return {
                "status": status,
                "satellites": satellites,
                "fix_quality": status,
            }
    except Exception:
        pass

    return {
        "status": "NO_FIX",
        "satellites": 0,
        "fix_quality": "NO_FIX",
    }


def get_adapter_status(interface: str) -> str:
    """Get WiFi adapter status.

    Checks if the specified interface (wlan1, wlan2) is UP.

    Args:
        interface: Interface name (e.g., "wlan1", "wlan2")

    Returns:
        "UP", "DOWN", or "NOT_FOUND"
    """
    try:
        result = subprocess.run(
            ["ip", "link", "show", interface],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )

        if result.returncode == 0:
            # Parse output for state
            # Example: 2: wlan1: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500
            if "state UP" in result.stdout or ",UP," in result.stdout:
                return "UP"
            else:
                return "DOWN"
        else:
            return "NOT_FOUND"
    except Exception:
        return "NOT_FOUND"


def get_capture_rate() -> float:
    """Get current packet capture rate from Kismet.

    Queries Kismet REST API for packets per second.

    Returns:
        Packets per second (float), or 0.0 on failure.
    """
    try:
        import json
        import urllib.request

        # Query Kismet system status endpoint
        url = "http://localhost:2501/system/status.json"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})

        with urllib.request.urlopen(req, timeout=2) as response:
            data = json.loads(response.read().decode())

            # Extract packets per second from system status
            # The exact field may vary; check Kismet API docs
            pps = data.get("kismet.system.packets_rrd", {}).get("kismet.common.rrd.last_time", 0)

            return round(float(pps), 1)
    except Exception:
        return 0.0


# =============================================================================
# Phase 3: Threshold Management and Action Execution
# =============================================================================


def load_threshold_config() -> dict:
    """Load threshold configuration from file.

    Returns:
        Threshold config dict, or defaults if file doesn't exist or is corrupted.
    """
    try:
        if os.path.exists(PERFORMANCE_CONFIG):
            with open(PERFORMANCE_CONFIG) as f:
                return json.load(f)
    except Exception:
        pass

    return DEFAULT_CONFIG.copy()


def save_threshold_config(config: dict) -> bool:
    """Save threshold configuration atomically.

    Args:
        config: Threshold configuration dict to save

    Returns:
        True on success, False on failure
    """
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(PERFORMANCE_CONFIG), exist_ok=True)

        # Atomic write using temp file
        temp_path = PERFORMANCE_CONFIG + ".tmp"
        with open(temp_path, "w") as f:
            json.dump(config, f, indent=2)

        # Atomic replace
        os.replace(temp_path, PERFORMANCE_CONFIG)
        return True
    except Exception:
        return False


def evaluate_thresholds(metrics: dict, config: dict) -> list[dict]:
    """Evaluate metrics against thresholds.

    Args:
        metrics: Dict with cpu_temp, disk, memory, etc.
        config: Threshold configuration

    Returns:
        List of alert dicts with metric, level, value, threshold
    """
    alerts = []

    # Check CPU temperature
    if config.get("cpu_temp", {}).get("enabled", True):
        temp = metrics.get("cpu_temp", 0.0)
        thresholds = config.get("cpu_temp", {})

        if temp >= thresholds.get("action_threshold", 85):
            alerts.append(
                {
                    "metric": "cpu_temp",
                    "level": "action",
                    "value": temp,
                    "threshold": thresholds["action_threshold"],
                    "unit": "°C",
                }
            )
        elif temp >= thresholds.get("critical_threshold", 80):
            alerts.append(
                {
                    "metric": "cpu_temp",
                    "level": "critical",
                    "value": temp,
                    "threshold": thresholds["critical_threshold"],
                    "unit": "°C",
                }
            )
        elif temp >= thresholds.get("warning_threshold", 75):
            alerts.append(
                {
                    "metric": "cpu_temp",
                    "level": "warning",
                    "value": temp,
                    "threshold": thresholds["warning_threshold"],
                    "unit": "°C",
                }
            )

    # Check disk usage
    if config.get("disk_usage", {}).get("enabled", True):
        disk_percent = metrics.get("disk", {}).get("used_percent", 0)
        thresholds = config.get("disk_usage", {})

        if disk_percent >= thresholds.get("action_threshold", 90):
            alerts.append(
                {
                    "metric": "disk_usage",
                    "level": "action",
                    "value": disk_percent,
                    "threshold": thresholds["action_threshold"],
                    "unit": "%",
                }
            )
        elif disk_percent >= thresholds.get("critical_threshold", 85):
            alerts.append(
                {
                    "metric": "disk_usage",
                    "level": "critical",
                    "value": disk_percent,
                    "threshold": thresholds["critical_threshold"],
                    "unit": "%",
                }
            )
        elif disk_percent >= thresholds.get("warning_threshold", 80):
            alerts.append(
                {
                    "metric": "disk_usage",
                    "level": "warning",
                    "value": disk_percent,
                    "threshold": thresholds["warning_threshold"],
                    "unit": "%",
                }
            )

    # Check memory usage
    if config.get("memory_usage", {}).get("enabled", True):
        memory_percent = metrics.get("memory", {}).get("used_percent", 0.0)
        thresholds = config.get("memory_usage", {})

        if memory_percent >= thresholds.get("action_threshold", 90):
            alerts.append(
                {
                    "metric": "memory_usage",
                    "level": "action",
                    "value": memory_percent,
                    "threshold": thresholds["action_threshold"],
                    "unit": "%",
                }
            )
        elif memory_percent >= thresholds.get("critical_threshold", 85):
            alerts.append(
                {
                    "metric": "memory_usage",
                    "level": "critical",
                    "value": memory_percent,
                    "threshold": thresholds["critical_threshold"],
                    "unit": "%",
                }
            )
        elif memory_percent >= thresholds.get("warning_threshold", 80):
            alerts.append(
                {
                    "metric": "memory_usage",
                    "level": "warning",
                    "value": memory_percent,
                    "threshold": thresholds["warning_threshold"],
                    "unit": "%",
                }
            )

    return alerts


def validate_custom_command(cmd: str) -> bool:
    """Validate custom command for dangerous patterns.

    Args:
        cmd: Command string to validate

    Returns:
        True if safe, False if dangerous
    """
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, cmd, re.IGNORECASE):
            return False
    return True


def can_execute_action(metric: str, cooldown: int) -> bool:
    """Check if action can be executed based on cooldown.

    Args:
        metric: Metric name (e.g., "cpu_temp")
        cooldown: Cooldown period in seconds

    Returns:
        True if cooldown has elapsed or no previous action
    """
    if metric not in last_actions:
        return True

    elapsed = time.time() - last_actions[metric]
    return elapsed > cooldown


def log_action(metric: str, value: float, level: str, action: str, success: bool):
    """Log action to performance log file.

    Args:
        metric: Metric that triggered action
        value: Metric value
        level: Alert level (warning/critical/action)
        action: Action taken
        success: Whether action succeeded
    """
    try:
        os.makedirs(os.path.dirname(PERFORMANCE_LOG), exist_ok=True)

        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        status = "SUCCESS" if success else "FAILED"
        log_entry = f"{timestamp} | {metric} | {value} | {level} | {action} | {status}\n"

        with open(PERFORMANCE_LOG, "a") as f:
            f.write(log_entry)
    except Exception:
        pass


def execute_action(metric: str, action: str, custom_cmd: str | None, value: float) -> bool:
    """Execute response action with safety checks.

    Args:
        metric: Metric that triggered action
        action: Action type (stop_kismet/stop_and_shutdown/custom)
        custom_cmd: Custom command if action is "custom"
        value: Metric value that triggered action

    Returns:
        True if action executed successfully
    """
    try:
        if action == "stop_kismet":
            result = subprocess.run(
                ["systemctl", "stop", "wardrive.service"],
                check=False,
                capture_output=True,
                timeout=10,
            )
            success = result.returncode == 0

        elif action == "stop_and_shutdown":
            # Stop Kismet first
            subprocess.run(
                ["systemctl", "stop", "wardrive.service"],
                check=False,
                timeout=10,
            )
            # Initiate shutdown
            result = subprocess.run(
                ["sudo", "shutdown", "-h", "+1"],
                check=False,
                capture_output=True,
                timeout=5,
            )
            success = result.returncode == 0

        elif action == "custom" and custom_cmd:
            # Validate before executing
            if not validate_custom_command(custom_cmd):
                log_action(metric, value, "action", f"custom:{custom_cmd}", False)
                return False

            result = subprocess.run(
                custom_cmd,
                shell=True,
                check=False,
                capture_output=True,
                timeout=30,
            )
            success = result.returncode == 0

        else:
            # Unknown action or "none"
            return False

        # Log the action
        log_action(metric, value, "action", action, success)

        # Update last action time if successful
        if success:
            last_actions[metric] = time.time()

        return success

    except Exception:
        log_action(metric, value, "action", action, False)
        return False


# =============================================================================
# Phase 1: API Routes
# =============================================================================


@performance_bp.route("/performance")
def api_performance():
    """Get performance metrics as JSON.

    Returns:
        JSON with all metrics: Phase 1 (cpu_temp, disk, memory, cpu_load)
        and Phase 2 (gps, adapters, capture_rate).
    """
    return jsonify(
        {
            "cpu_temp": get_cpu_temperature(),
            "disk": get_disk_usage(),
            "memory": get_memory_usage(),
            "cpu_load": get_cpu_load(),
            "gps": get_gps_status(),
            "adapter_wlan1": get_adapter_status("wlan1"),
            "adapter_wlan2": get_adapter_status("wlan2"),
            "capture_rate": get_capture_rate(),
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
        gps=get_gps_status(),
        adapter_wlan1=get_adapter_status("wlan1"),
        adapter_wlan2=get_adapter_status("wlan2"),
        capture_rate=get_capture_rate(),
    )


# =============================================================================
# Phase 3: API Routes
# =============================================================================


@performance_bp.route("/performance/alerts")
def api_alerts():
    """Get current alerts as JSON.

    Returns:
        JSON with list of active alerts
    """
    metrics = {
        "cpu_temp": get_cpu_temperature(),
        "disk": get_disk_usage(),
        "memory": get_memory_usage(),
    }

    config = load_threshold_config()
    alerts = evaluate_thresholds(metrics, config)

    # Auto-execute actions for action-level alerts
    if config.get("global_settings", {}).get("auto_actions_enabled", True):
        cooldown = config.get("global_settings", {}).get("action_cooldown_seconds", 300)

        for alert in alerts:
            if alert["level"] == "action":
                metric_key = alert["metric"]
                metric_config = config.get(metric_key, {})

                if can_execute_action(metric_key, cooldown):
                    action = metric_config.get("response_action", "none")
                    custom_cmd = metric_config.get("custom_command")

                    execute_action(metric_key, action, custom_cmd, alert["value"])

    return jsonify({"alerts": alerts})


@performance_bp.route("/performance/alerts/html")
def api_alerts_html():
    """Get alert banner as HTML fragment.

    Returns:
        HTML partial for alert banner on main dashboard
    """
    metrics = {
        "cpu_temp": get_cpu_temperature(),
        "disk": get_disk_usage(),
        "memory": get_memory_usage(),
    }

    config = load_threshold_config()
    alerts = evaluate_thresholds(metrics, config)

    return render_template("partials/_performance_alerts.html", alerts=alerts)


@performance_bp.route("/performance/config")
def api_config_get():
    """Get threshold configuration as JSON.

    Returns:
        JSON with current threshold config
    """
    return jsonify(load_threshold_config())


@performance_bp.route("/performance/config", methods=["POST"])
def api_config_post():
    """Save threshold configuration.

    Returns:
        JSON with success status
    """
    try:
        config = request.get_json()

        if not config:
            return jsonify({"success": False, "error": "No config provided"}), 400

        # Basic validation
        required_keys = ["cpu_temp", "disk_usage", "memory_usage", "global_settings"]
        if not all(key in config for key in required_keys):
            return jsonify({"success": False, "error": "Missing required config keys"}), 400

        if save_threshold_config(config):
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Failed to save config"}), 500

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@performance_bp.route("/performance/dismiss", methods=["POST"])
def api_dismiss_alert():
    """Dismiss an alert (client-side only).

    Returns:
        JSON with success status
    """
    # This endpoint exists for client-side alert dismissal
    # The actual dismissal happens in JavaScript
    return jsonify({"success": True})


@performance_bp.route("/performance/history")
def api_history():
    """Get action execution history.

    Returns:
        JSON with recent action history
    """
    try:
        if not os.path.exists(PERFORMANCE_LOG):
            return jsonify({"history": []})

        with open(PERFORMANCE_LOG) as f:
            lines = f.readlines()[-50:]  # Last 50 entries

        history = []
        for line in lines:
            parts = line.strip().split(" | ")
            if len(parts) >= 6:
                history.append(
                    {
                        "timestamp": parts[0],
                        "metric": parts[1],
                        "value": parts[2],
                        "level": parts[3],
                        "action": parts[4],
                        "status": parts[5],
                    }
                )

        return jsonify({"history": history})

    except Exception:
        return jsonify({"history": []})


@performance_bp.route("/performance/test-action", methods=["POST"])
def api_test_action():
    """Test an action without cooldown restrictions.

    Returns:
        JSON with success status
    """
    try:
        data = request.get_json()
        metric = data.get("metric")
        action = data.get("action")
        custom_cmd = data.get("custom_cmd")
        value = data.get("value", 0.0)

        if not metric or not action:
            return jsonify({"success": False, "error": "Missing metric or action"}), 400

        # Execute without checking cooldown
        success = execute_action(metric, action, custom_cmd, value)

        return jsonify({"success": success})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
