"""WarPie Web Control Panel - Log Viewing Routes."""

import subprocess
from datetime import date
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request

logs_bp = Blueprint("logs", __name__)


def _get_wigle_logs(lines: int) -> list[str]:
    """Get WiGLE CSV log content."""
    today = date.today().strftime("%Y-%m-%d")
    log_base = Path("/home/pi/kismet/logs")

    # Find today's WiGLE CSV files
    files = list(log_base.glob(f"*/{today}/*.wiglecsv"))
    if not files:
        return [f"No WiGLE CSV found for today ({today})", "Waiting for Kismet..."]

    latest = max(files, key=lambda p: p.stat().st_mtime)
    result = subprocess.run(
        ["tail", "-n", str(lines), str(latest)],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    if result.returncode == 0:
        output = [f"=== {latest.name} ===", ""]
        output.extend(
            result.stdout.strip().split("\n") if result.stdout.strip() else ["(empty)"]
        )
        return output
    return ["Error reading WiGLE CSV"]


def _get_journal_logs(unit: str, lines: int, output_format: str = "short") -> list[str]:
    """Get journalctl logs for a unit."""
    result = subprocess.run(
        [
            "journalctl", "-u", unit,
            "-n", str(lines),
            "--no-pager", "-o", output_format,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip().split("\n")
    return ["No log entries found"]


def get_logs(source: str = "wardrive", lines: int = 100) -> list[str]:  # noqa: PLR0911
    """Get log content from various sources.

    Args:
        source: Log source (wigle, wardrive, kismet, gps, network).
        lines: Number of lines to retrieve.

    Returns:
        List of log lines.
    """
    try:
        if source == "wigle":
            return _get_wigle_logs(lines)
        if source == "wardrive":
            return _get_journal_logs("wardrive", lines)
        if source == "kismet":
            return _get_journal_logs("wardrive", lines, "cat")
        if source == "gps":
            return _get_journal_logs("gpsd-wardriver", lines)
        if source == "network":
            return _get_journal_logs("warpie-network", lines)
        return ["Unknown log source"]
    except Exception as e:
        return [f"Error: {e!s}"]


@logs_bp.route("/logs")
def api_logs():
    """Get log content as JSON."""
    source = request.args.get("source", "wardrive")
    lines = request.args.get("lines", 100, type=int)

    log_lines = get_logs(source, lines)

    return jsonify({
        "logs": log_lines,
        "lines": len(log_lines),
        "source": source,
    })


@logs_bp.route("/logs/html")
def api_logs_html():
    """Get log content as HTML fragment for HTMX."""
    source = request.args.get("source", "wardrive")
    lines = request.args.get("lines", 100, type=int)

    log_lines = get_logs(source, lines)

    return render_template(
        "partials/_log_content.html",
        logs=log_lines,
        source=source,
    )
