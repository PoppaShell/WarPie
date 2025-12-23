"""WarPie Web Control Panel - Main Routes.

Handles dashboard, status, mode switching, and system controls.
"""

import subprocess
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request

from web.config import MODES

main_bp = Blueprint("main", __name__)


def get_kismet_status() -> tuple[bool, str]:
    """Check if Kismet is running and get current mode.

    Returns:
        Tuple of (is_running, mode_name).
    """
    try:
        result = subprocess.run(
            ["pgrep", "-a", "kismet"],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            cmdline = result.stdout
            if "wardrive" in cmdline.lower():
                return True, "Wardrive"
            elif "targeted" in cmdline.lower():
                return True, "Targeted"
            else:
                return True, "Normal"
        return False, "Stopped"
    except Exception:
        return False, "Unknown"


def get_uptime() -> str:
    """Get system uptime formatted as hours and minutes.

    Returns:
        Uptime string like "2h 47m".
    """
    try:
        secs = float(Path("/proc/uptime").read_text().split()[0])
        hours = int(secs // 3600)
        minutes = int((secs % 3600) // 60)
        return f"{hours}h {minutes}m"
    except Exception:
        return "N/A"


def switch_mode(mode: str, target_lists: list[str] | None = None) -> bool:
    """Switch Kismet capture mode.

    Args:
        mode: Mode to switch to (normal, wardrive, targeted, stop).
        target_lists: List of target list IDs for targeted mode.

    Returns:
        True if switch was successful.
    """
    # Stop any running Kismet instance
    subprocess.run(
        ["sudo", "systemctl", "stop", "wardrive"],
        check=False,
        capture_output=True,
    )
    subprocess.run(
        ["sudo", "pkill", "-9", "kismet"],
        check=False,
        capture_output=True,
    )
    subprocess.run(["sleep", "2"], check=False)

    if mode == "stop":
        return True

    if mode not in MODES:
        return False

    # Set mode environment for systemd
    env_dir = Path("/etc/systemd/system/wardrive.service.d")
    env_dir.mkdir(parents=True, exist_ok=True)

    env_content = f"[Service]\nEnvironment=KISMET_MODE={mode}\n"
    if mode == "targeted" and target_lists:
        env_content += f"Environment=TARGET_LISTS={','.join(target_lists)}\n"

    (env_dir / "mode.conf").write_text(env_content)

    subprocess.run(
        ["sudo", "systemctl", "daemon-reload"],
        check=False,
        capture_output=True,
    )
    subprocess.run(
        ["sudo", "systemctl", "start", "wardrive"],
        check=False,
        capture_output=True,
    )
    return True


def reboot_system() -> bool:
    """Initiate graceful system reboot.

    Returns:
        True if reboot command was issued.
    """
    try:
        # Stop services gracefully first
        subprocess.run(
            ["sudo", "systemctl", "stop", "wardrive"],
            check=False,
            capture_output=True,
        )
        # Initiate reboot
        subprocess.Popen(
            ["sudo", "shutdown", "-r", "now"],
            start_new_session=True,
        )
        return True
    except Exception:
        return False


def shutdown_system() -> bool:
    """Initiate graceful system shutdown.

    Returns:
        True if shutdown command was issued.
    """
    try:
        # Stop wardrive service gracefully first
        subprocess.run(
            ["sudo", "systemctl", "stop", "wardrive"],
            check=False,
            capture_output=True,
        )
        # Initiate shutdown - systemd will stop warpie-control as part of shutdown
        subprocess.Popen(
            ["sudo", "shutdown", "-h", "now"],
            start_new_session=True,
        )
        return True
    except Exception:
        return False


@main_bp.route("/")
def index():
    """Render the main dashboard."""
    running, current_mode = get_kismet_status()

    return render_template(
        "index.html",
        status="Running" if running else "Stopped",
        status_class="status-running" if running else "status-stopped",
        current_mode=current_mode,
        uptime=get_uptime(),
        modes=MODES,
        active_mode=current_mode.lower() if running else "",
    )


@main_bp.route("/api/status")
def api_status():
    """Get current system status as JSON."""
    running, mode = get_kismet_status()
    return jsonify({
        "running": running,
        "mode": mode,
        "uptime": get_uptime(),
    })


@main_bp.route("/api/status/html")
def api_status_html():
    """Get status panel as HTML fragment for HTMX."""
    running, current_mode = get_kismet_status()

    return render_template(
        "partials/_status.html",
        status="Running" if running else "Stopped",
        status_class="status-running" if running else "status-stopped",
        current_mode=current_mode,
        uptime=get_uptime(),
    )


@main_bp.route("/api/mode", methods=["POST"])
def api_mode():
    """Switch capture mode.

    Returns HTML partial for HTMX to swap into #status-panel.
    """
    # Handle both JSON and form-encoded data (HTMX sends form-encoded by default)
    if request.is_json:
        data = request.get_json() or {}
        mode = data.get("mode", "")
        target_lists = data.get("target_lists", [])
    else:
        mode = request.form.get("mode", "")
        target_lists = request.form.getlist("target_lists")

    if not mode:
        return jsonify({"success": False, "error": "Mode required"}), 400

    if mode not in ["normal", "wardrive", "targeted", "stop"]:
        return jsonify({"success": False, "error": "Invalid mode"}), 400

    success = switch_mode(mode, target_lists)

    if success:
        # Return updated status HTML for HTMX
        running, current_mode = get_kismet_status()
        return render_template(
            "partials/_status.html",
            status="Running" if running else "Stopped",
            status_class="status-running" if running else "status-stopped",
            current_mode=current_mode,
            uptime=get_uptime(),
        )
    else:
        return jsonify({"success": False, "error": "Failed to switch mode"}), 500


@main_bp.route("/api/reboot", methods=["POST"])
def api_reboot():
    """Initiate graceful system reboot."""
    success = reboot_system()

    if success:
        # Return a simple message - the page will disconnect when Pi reboots
        return "<div class='status-row'><span class='status-value'>Rebooting...</span></div>"
    else:
        return jsonify({"success": False, "error": "Failed to initiate reboot"}), 500


@main_bp.route("/api/shutdown", methods=["POST"])
def api_shutdown():
    """Initiate graceful system shutdown."""
    success = shutdown_system()

    if success:
        # Return a simple message - the page will disconnect when Pi shuts down
        return "<div class='status-row'><span class='status-value'>Shutting down...</span></div>"
    else:
        return jsonify({"success": False, "error": "Failed to initiate shutdown"}), 500
