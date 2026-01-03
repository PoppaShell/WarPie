"""Configuration for WarPie Web Control Panel."""

from pathlib import Path

# Server settings
PORT = 1337
HOST = "0.0.0.0"
THREADS = 2

# Paths
FILTER_MANAGER_SCRIPT = "/usr/local/bin/warpie-filter-manager.py"
EXCLUDE_SCRIPT = "/usr/local/bin/warpie-exclude-ssid.sh"
FILTER_PROCESSOR_SCRIPT = "/usr/local/bin/warpie-filter-processor.py"
TARGET_LISTS_CONFIG = "/etc/warpie/target_lists.conf"
FILTER_RULES_CONFIG = "/etc/warpie/filter_rules.conf"
KISMET_CONF_DIR = "/etc/kismet"
KISMET_SITE_CONF = f"{KISMET_CONF_DIR}/kismet_site.conf"
KISMET_WARDRIVE_CONF = f"{KISMET_CONF_DIR}/kismet_wardrive.conf"
KISMET_LOG_DIR = str(Path.home() / "kismet" / "logs")

# Capture modes
MODES = {
    "normal": {
        "name": "Normal Mode",
        "desc": "Full capture, exclusions applied",
    },
    "wardrive": {
        "name": "Wardrive Mode",
        "desc": "AP-only, fast scan, exclusions applied",
    },
    "wardrive_bt": {
        "name": "Wardrive+BT",
        "desc": "WiFi + BT/BTLE (use converter for WiGLE)",
    },
    "targeted": {
        "name": "Targeted Devices",
        "desc": "Capture only from selected Target Lists",
    },
}

# Common networks for quick-add exclusions
QUICK_EXCLUDE_NETWORKS = [
    {"ssid": "xfinitywifi", "desc": "Xfinity Hotspots"},
    {"ssid": "attwifi", "desc": "AT&T Hotspots"},
    {"ssid": "Starbucks WiFi", "desc": "Starbucks"},
    {"ssid": "Google Starbucks", "desc": "Google Starbucks"},
    {"ssid": "McDonalds Free WiFi", "desc": "McDonald's"},
    {"ssid": "HPGuest", "desc": "HP Guest Networks"},
]
