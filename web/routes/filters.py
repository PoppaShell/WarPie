"""WarPie Web Control Panel - Network Filter (Exclusions) Routes."""

import json
import subprocess
from pathlib import Path

from flask import Blueprint, jsonify, request

from web.config import EXCLUDE_SCRIPT, FILTER_MANAGER_SCRIPT, FILTER_PROCESSOR_SCRIPT

filters_bp = Blueprint("filters", __name__)


def call_filter_script(*args) -> dict:
    """Call the filter manager script with arguments and return JSON result.

    Args:
        *args: Arguments to pass to the script.

    Returns:
        Parsed JSON response from the script.
    """
    # Use new filter manager if available, otherwise fall back to old script
    script = FILTER_MANAGER_SCRIPT if Path(FILTER_MANAGER_SCRIPT).exists() else EXCLUDE_SCRIPT

    try:
        cmd = ["sudo", script, "--json", *args]
        result = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=30)
        if result.stdout.strip():
            return json.loads(result.stdout)
        return {"success": False, "error": "No output from script"}
    except json.JSONDecodeError:
        return {"success": False, "error": "Invalid JSON response"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Script timeout"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def call_processor_script(*args) -> dict:
    """Call the filter processor script with arguments and return JSON result.

    Args:
        *args: Arguments to pass to the script.

    Returns:
        Parsed JSON response from the script.
    """
    if not Path(FILTER_PROCESSOR_SCRIPT).exists():
        return {"success": False, "error": "Filter processor not installed"}

    try:
        cmd = ["python3", FILTER_PROCESSOR_SCRIPT, "--json", *args]
        result = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=60)
        if result.stdout.strip():
            return json.loads(result.stdout)
        return {"success": False, "error": "No output from processor"}
    except json.JSONDecodeError:
        return {"success": False, "error": "Invalid JSON response"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Script timeout"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@filters_bp.route("/filters")
def api_list_filters():
    """List all exclusions (static and dynamic)."""
    return jsonify(call_filter_script("--list"))


@filters_bp.route("/filters/recent")
def api_list_recent():
    """List recently added filters."""
    # Get last 10 filters added
    result = call_filter_script("--list")
    if result.get("success", True):
        # Combine and sort by timestamp, take last 10
        static = result.get("static_exclusions", [])
        dynamic = result.get("dynamic_exclusions", [])
        all_filters = static + dynamic
        # Sort by added_at if available, take last 10
        recent = sorted(
            all_filters,
            key=lambda x: x.get("added_at", ""),
            reverse=True,
        )[:10]
        return jsonify({"success": True, "recent": recent})
    return jsonify(result)


@filters_bp.route("/filters", methods=["POST"])
def api_add_filter():
    """Add a new exclusion (static or dynamic)."""
    data = request.get_json() or {}
    ssid = data.get("ssid", "")
    filter_type = data.get("filter_type", "static")
    match_type = data.get("match_type", "exact")
    bssids = data.get("bssids", "")
    desc = data.get("description", "")

    if not ssid:
        return jsonify({"success": False, "error": "SSID required"}), 400

    if filter_type == "dynamic":
        args = ["--add-dynamic", "--ssid", ssid, "--type", match_type]
        if desc:
            args.extend(["--desc", desc])
        return jsonify(call_filter_script(*args))
    else:
        args = ["--add-static", "--ssid", ssid, "--type", match_type]
        if desc:
            args.extend(["--desc", desc])
        result = call_filter_script(*args)

        # If BSSIDs provided, also add them
        if bssids and result.get("success"):
            for bssid in bssids.split(","):
                bssid_clean = bssid.strip()
                if bssid_clean:
                    call_filter_script("--add-static", "--bssid", bssid_clean)

        return jsonify(result)


@filters_bp.route("/filters/<filter_type>/<path:value>", methods=["DELETE"])
def api_remove_filter(filter_type: str, value: str):
    """Remove an exclusion.

    Args:
        filter_type: Either 'static' or 'dynamic'.
        value: The SSID or BSSID to remove.
    """
    if filter_type not in ["static", "dynamic"]:
        return jsonify({"success": False, "error": "Invalid filter type"}), 400

    result = call_filter_script(f"--remove-{filter_type}", "--ssid", value)
    return jsonify(result)


@filters_bp.route("/filters/cleanup", methods=["POST"])
def api_cleanup():
    """Run retroactive cleanup on historical logs."""
    result = call_filter_script("--cleanup", "--all-static")
    return jsonify(result)


@filters_bp.route("/filters/pre-upload/preview")
def api_pre_upload_preview():
    """Preview what would be removed during pre-upload sanitization."""
    path = request.args.get("path", "")
    if not path:
        return jsonify({"success": False, "error": "Path required"}), 400

    return jsonify(call_processor_script("--preview", path))


@filters_bp.route("/filters/pre-upload/execute", methods=["POST"])
def api_pre_upload_execute():
    """Execute pre-upload sanitization."""
    data = request.get_json() or {}
    path = data.get("path", "")

    if not path:
        return jsonify({"success": False, "error": "Path required"}), 400

    result = call_processor_script("--process", path)
    return jsonify(result)


@filters_bp.route("/filters/backups")
def api_list_backups():
    """List available backups from sanitization."""
    return jsonify(call_processor_script("--list-backups"))


@filters_bp.route("/filters/processor/status")
def api_processor_status():
    """Check if filter processor daemon is running."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "warpie-filter-processor.py"],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            pids = result.stdout.strip().split("\n")
            pid = int(pids[0]) if pids and pids[0] else None
            return jsonify({"running": True, "pid": pid})
        return jsonify({"running": False, "pid": None})
    except Exception as e:
        return jsonify({"running": False, "pid": None, "error": str(e)})


@filters_bp.route("/scan-ssid")
def api_scan_ssid():
    """Scan for networks matching an SSID."""
    ssid = request.args.get("ssid", "")
    if not ssid:
        return jsonify({"success": False, "error": "SSID required"}), 400

    return jsonify(call_filter_script("--discover", ssid))
