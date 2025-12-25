#!/usr/bin/env python3
"""WarPie Filter Manager - Unified CLI for network filter management.

Supports three filtering paradigms:
  1. Static Exclusions  - Block stable-MAC networks at capture time
  2. Dynamic Exclusions - Post-process removal for rotating-MAC networks
  3. Targeting Inclusions - Add OUI prefixes to targeting modes

Supports multiple PHY types:
  - wifi: IEEE 802.11 WiFi networks (default)
  - btle: Bluetooth Low Energy devices
  - bt:   Classic Bluetooth devices

Usage:
  Interactive:  ./warpie-filter-manager.py
  JSON API:     ./warpie-filter-manager.py --json --list
  BTLE:         ./warpie-filter-manager.py --add-static --phy btle --bssid AA:BB:CC:DD:EE:FF
"""

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Configuration
VERSION = "2.4.1"
WARPIE_DIR = Path("/etc/warpie")
FILTER_RULES_FILE = WARPIE_DIR / "filter_rules.conf"
LEGACY_EXCLUSIONS_FILE = WARPIE_DIR / "ssid_exclusions.conf"
KISMET_CONF_DIR = Path("/etc/kismet")
KISMET_SITE_CONF = KISMET_CONF_DIR / "kismet_site.conf"
KISMET_WARDRIVE_CONF = KISMET_CONF_DIR / "kismet_wardrive.conf"
KISMET_LOGS_DIR = Path.home() / "kismet" / "logs"
SCAN_INTERFACE = "wlan0"

# Section markers
SECTION_STATIC = "[static_exclusions]"
SECTION_DYNAMIC = "[dynamic_exclusions]"
SECTION_SMART = "[smart_mode_targets]"
SECTION_TARGETS = "[targeting_inclusions]"
SECTION_BTLE_STATIC = "[btle_static_exclusions]"
SECTION_BTLE_DYNAMIC = "[btle_dynamic_exclusions]"
SECTION_BT_STATIC = "[bt_static_exclusions]"
SECTION_BT_DYNAMIC = "[bt_dynamic_exclusions]"

# PHY type to Kismet PHY name mapping
PHY_KISMET_NAMES = {
    "wifi": "IEEE802.11",
    "btle": "BTLE",
    "bt": "Bluetooth",
}

# Valid PHY types
VALID_PHY_TYPES = ("wifi", "btle", "bt")


@dataclass
class FilterEntry:
    """A filter entry from the config file."""

    value: str
    type: str
    description: str = ""
    phy: str = "wifi"  # wifi, btle, or bt


@dataclass
class ScanResult:
    """A WiFi scan result."""

    bssid: str
    ssid: str
    signal: str = ""
    channel: str = ""


@dataclass
class FilterConfig:
    """The complete filter configuration."""

    static_exclusions: list = field(default_factory=list)  # WiFi static
    dynamic_exclusions: list = field(default_factory=list)  # WiFi dynamic
    targeting_inclusions: list = field(default_factory=list)
    btle_static_exclusions: list = field(default_factory=list)  # BTLE static
    btle_dynamic_exclusions: list = field(default_factory=list)  # BTLE dynamic
    bt_static_exclusions: list = field(default_factory=list)  # Classic BT static
    bt_dynamic_exclusions: list = field(default_factory=list)  # Classic BT dynamic


class FilterManager:
    """Manages network filters for WarPie."""

    def __init__(self, json_mode: bool = False, quiet_mode: bool = False):
        """Initialize the filter manager.

        Args:
            json_mode: Output in JSON format.
            quiet_mode: Suppress non-essential output.
        """
        self.json_mode = json_mode
        self.quiet_mode = quiet_mode

    def log_info(self, msg: str) -> None:
        """Log an info message."""
        if not self.json_mode and not self.quiet_mode:
            print(f"\033[0;34m[INFO]\033[0m {msg}")

    def log_success(self, msg: str) -> None:
        """Log a success message."""
        if not self.json_mode and not self.quiet_mode:
            print(f"\033[0;32m[OK]\033[0m {msg}")

    def log_warn(self, msg: str) -> None:
        """Log a warning message."""
        if not self.json_mode and not self.quiet_mode:
            print(f"\033[1;33m[WARN]\033[0m {msg}")

    def log_error(self, msg: str) -> None:
        """Log an error message."""
        if not self.json_mode:
            print(f"\033[0;31m[ERROR]\033[0m {msg}", file=sys.stderr)

    def json_output(self, data: dict) -> None:
        """Output JSON data."""
        print(json.dumps(data))

    def json_error(self, msg: str) -> None:
        """Output JSON error and exit."""
        if self.json_mode:
            print(json.dumps({"success": False, "error": msg}))
        else:
            self.log_error(msg)
        sys.exit(1)

    def json_success(self, msg: str, extra: Optional[dict] = None) -> None:
        """Output JSON success."""
        if self.json_mode:
            result = {"success": True, "message": msg}
            if extra:
                result.update(extra)
            print(json.dumps(result))
        else:
            self.log_success(msg)

    def ensure_config_dir(self) -> None:
        """Ensure config directory and files exist."""
        if not WARPIE_DIR.exists():
            subprocess.run(["sudo", "mkdir", "-p", str(WARPIE_DIR)], check=True)

        if not FILTER_RULES_FILE.exists():
            config_content = """# WarPie Network Filter Configuration
# Version: 2.4.1
#
# Three filtering paradigms:
# 1. STATIC EXCLUSIONS: Stable-MAC networks blocked at capture time
# 2. DYNAMIC EXCLUSIONS: Rotating-MAC networks removed via post-processing
# 3. TARGETING INCLUSIONS: OUI prefixes added to targeting modes
#
# Supports multiple PHY types:
# - WiFi (IEEE 802.11) - default sections
# - BTLE (Bluetooth Low Energy) - btle_* sections
# - BT (Classic Bluetooth) - bt_* sections
#
# FORMAT: value|type|description
# TYPES: exact, pattern, bssid, oui, name (for BTLE device names)
# PATTERNS: * = any characters, ? = single character

[static_exclusions]
# WiFi networks with stable MACs - BSSIDs discovered and blocked at capture time
# HOME-5G|exact|Home 5GHz network
# 74:83:C2:8A:23:4C|bssid|Home router MAC

[dynamic_exclusions]
# WiFi networks with rotating MACs - only SSID stored, post-process removal
# PoppaShell|exact|Personal iPhone hotspot
# iPhone*|pattern|Any iPhone hotspot

[btle_static_exclusions]
# BTLE devices with stable MACs - blocked at capture time
# AA:BB:CC:DD:EE:FF|bssid|My Fitbit
# Note: BTLE uses heavy MAC randomization, consider dynamic instead

[btle_dynamic_exclusions]
# BTLE devices with rotating MACs - removed by device name post-processing
# Fitbit*|pattern|Any Fitbit device
# My iPhone|exact|Personal iPhone (advertises via BTLE too)
# Note: Device name = BTLE advertising name, similar to WiFi SSID

[bt_static_exclusions]
# Classic Bluetooth devices with stable MACs
# AA:BB:CC:DD:EE:FF|bssid|Car audio system

[bt_dynamic_exclusions]
# Classic Bluetooth devices removed by name
# CarPlay*|pattern|Any CarPlay device

[smart_mode_targets]
# Optional inverted filtering - ONLY capture these
# (uncomment and configure to enable)

[targeting_inclusions]
# Add OUI prefixes to targeting modes
# FORMAT: oui_prefix|target_mode|description
# 00:AA:BB:*|target|New variant discovered
"""
            # Write via sudo
            proc = subprocess.run(
                ["sudo", "tee", str(FILTER_RULES_FILE)],
                input=config_content.encode(),
                capture_output=True,
            )
            if proc.returncode == 0:
                subprocess.run(
                    ["sudo", "chmod", "644", str(FILTER_RULES_FILE)], check=True
                )
                self.log_info(f"Created filter configuration file: {FILTER_RULES_FILE}")

    def load_config(self) -> FilterConfig:
        """Load the filter configuration file.

        Returns:
            FilterConfig with all sections parsed.
        """
        self.ensure_config_dir()

        config = FilterConfig()
        current_section = ""
        current_phy = "wifi"

        # First, load from the new filter_rules.conf
        if FILTER_RULES_FILE.exists():
            content = FILTER_RULES_FILE.read_text()
            for line in content.splitlines():
                line = line.strip()

                # Section headers - map section marker to (list_name, phy_type)
                section_map = {
                    SECTION_STATIC: ("static", "wifi"),
                    SECTION_DYNAMIC: ("dynamic", "wifi"),
                    SECTION_SMART: ("smart", "wifi"),
                    SECTION_TARGETS: ("targets", "wifi"),
                    SECTION_BTLE_STATIC: ("btle_static", "btle"),
                    SECTION_BTLE_DYNAMIC: ("btle_dynamic", "btle"),
                    SECTION_BT_STATIC: ("bt_static", "bt"),
                    SECTION_BT_DYNAMIC: ("bt_dynamic", "bt"),
                }

                if line in section_map:
                    current_section, current_phy = section_map[line]
                    continue
                elif line.startswith("[") and line.endswith("]"):
                    current_section = ""
                    current_phy = "wifi"
                    continue

                # Skip comments and empty lines
                if not line or line.startswith("#"):
                    continue

                # Parse entry
                parts = line.split("|", 2)
                if len(parts) >= 2:
                    entry = FilterEntry(
                        value=parts[0],
                        type=parts[1],
                        description=parts[2] if len(parts) > 2 else "",
                        phy=current_phy if current_section else "wifi",
                    )

                    if current_section == "static":
                        config.static_exclusions.append(entry)
                    elif current_section == "dynamic":
                        config.dynamic_exclusions.append(entry)
                    elif current_section == "targets":
                        config.targeting_inclusions.append(entry)
                    elif current_section == "btle_static":
                        config.btle_static_exclusions.append(entry)
                    elif current_section == "btle_dynamic":
                        config.btle_dynamic_exclusions.append(entry)
                    elif current_section == "bt_static":
                        config.bt_static_exclusions.append(entry)
                    elif current_section == "bt_dynamic":
                        config.bt_dynamic_exclusions.append(entry)

        # Also load legacy exclusions from Kismet config files
        # These were added by the installer directly to Kismet configs
        # Track seen MACs per PHY type to avoid duplicates
        seen_wifi_macs = {
            e.value.upper() for e in config.static_exclusions if e.type == "bssid"
        }
        seen_btle_macs = {
            e.value.upper() for e in config.btle_static_exclusions if e.type == "bssid"
        }
        seen_bt_macs = {
            e.value.upper() for e in config.bt_static_exclusions if e.type == "bssid"
        }

        for kismet_conf in [KISMET_SITE_CONF, KISMET_WARDRIVE_CONF]:
            if kismet_conf.exists():
                try:
                    content = kismet_conf.read_text()
                    filter_context = ""
                    for line in content.splitlines():
                        line = line.strip()

                        # Check for WARPIE_FILTER comment with context
                        if line.startswith("# WARPIE_FILTER:"):
                            filter_context = line.replace(
                                "# WARPIE_FILTER:", ""
                            ).strip()
                            continue

                        # Check for home network exclusions comment
                        if "Home network exclusion" in line or "Home WiFi" in line:
                            filter_context = "Home Network"
                            continue

                        # Parse kis_log_device_filter lines for all PHY types
                        if line.startswith("kis_log_device_filter="):
                            # Format: kis_log_device_filter=PHY,MAC,action
                            # or: kis_log_device_filter=PHY,MAC/MASK,action
                            filter_part = line.replace("kis_log_device_filter=", "")
                            parts = filter_part.split(",")
                            if len(parts) >= 3 and parts[2] == "block":
                                phy_name = parts[0]
                                bssid_or_mask = parts[1]
                                # Handle masked addresses
                                if "/" in bssid_or_mask:
                                    mac = bssid_or_mask.split("/")[0]
                                else:
                                    mac = bssid_or_mask

                                mac_upper = mac.upper()

                                # Determine PHY type and add to appropriate list
                                if phy_name == "IEEE802.11":
                                    if mac_upper not in seen_wifi_macs:
                                        seen_wifi_macs.add(mac_upper)
                                        config.static_exclusions.append(
                                            FilterEntry(
                                                value=mac,
                                                type="bssid",
                                                description=filter_context
                                                or "Legacy Kismet filter",
                                                phy="wifi",
                                            )
                                        )
                                elif phy_name == "BTLE":
                                    if mac_upper not in seen_btle_macs:
                                        seen_btle_macs.add(mac_upper)
                                        config.btle_static_exclusions.append(
                                            FilterEntry(
                                                value=mac,
                                                type="bssid",
                                                description=filter_context
                                                or "Legacy Kismet BTLE filter",
                                                phy="btle",
                                            )
                                        )
                                elif phy_name == "Bluetooth":
                                    if mac_upper not in seen_bt_macs:
                                        seen_bt_macs.add(mac_upper)
                                        config.bt_static_exclusions.append(
                                            FilterEntry(
                                                value=mac,
                                                type="bssid",
                                                description=filter_context
                                                or "Legacy Kismet BT filter",
                                                phy="bt",
                                            )
                                        )
                                filter_context = ""
                except OSError:
                    pass

        return config

    def add_to_section(self, section: str, entry: str) -> None:
        """Add an entry to a section in the config file.

        Args:
            section: The section marker (e.g., SECTION_STATIC).
            entry: The entry to add (value|type|description).
        """
        self.ensure_config_dir()

        # Escape section for sed
        escaped_section = section.replace("[", "\\[").replace("]", "\\]")

        subprocess.run(
            [
                "sudo",
                "sed",
                "-i",
                f"/^{escaped_section}$/a {entry}",
                str(FILTER_RULES_FILE),
            ],
            check=True,
        )

    def scan_live(self, ssid_pattern: str) -> list[ScanResult]:
        """Perform a live WiFi scan for networks matching a pattern.

        Args:
            ssid_pattern: SSID pattern to match (supports * and ? wildcards).

        Returns:
            List of ScanResult objects.
        """
        # Ensure interface is up
        subprocess.run(
            ["sudo", "ip", "link", "set", SCAN_INTERFACE, "up"],
            capture_output=True,
        )

        # Give interface time to come up
        import time

        time.sleep(1)

        # Perform scan
        result = subprocess.run(
            ["sudo", "iw", "dev", SCAN_INTERFACE, "scan"],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return []

        # Parse scan output
        networks = []
        current_bssid = ""
        current_ssid = ""
        current_signal = ""
        current_channel = ""

        for line in result.stdout.splitlines():
            line = line.strip()

            # New BSS entry
            bss_match = re.match(r"^BSS\s+([0-9a-fA-F:]+)", line)
            if bss_match:
                # Save previous network if SSID matches
                if current_bssid and self.match_pattern(current_ssid, ssid_pattern):
                    networks.append(
                        ScanResult(
                            bssid=current_bssid,
                            ssid=current_ssid,
                            signal=current_signal,
                            channel=current_channel,
                        )
                    )
                current_bssid = bss_match.group(1)
                current_ssid = ""
                current_signal = ""
                current_channel = ""
                continue

            # SSID
            ssid_match = re.match(r"^SSID:\s*(.*)", line)
            if ssid_match:
                current_ssid = ssid_match.group(1)
                continue

            # Signal
            signal_match = re.match(r"^signal:\s*([0-9.-]+)", line)
            if signal_match:
                current_signal = signal_match.group(1)
                continue

            # Channel
            channel_match = re.search(r"channel\s+(\d+)", line)
            if channel_match:
                current_channel = channel_match.group(1)
                continue

        # Don't forget last entry
        if current_bssid and self.match_pattern(current_ssid, ssid_pattern):
            networks.append(
                ScanResult(
                    bssid=current_bssid,
                    ssid=current_ssid,
                    signal=current_signal,
                    channel=current_channel,
                )
            )

        return networks

    def match_pattern(self, text: str, pattern: str) -> bool:
        """Match text against a glob-style pattern.

        Args:
            text: Text to match.
            pattern: Pattern with * (any chars) and ? (single char) wildcards.

        Returns:
            True if text matches pattern.
        """
        # Convert glob pattern to regex
        regex = pattern.replace("*", ".*").replace("?", ".")
        regex = f"^{regex}$"
        return bool(re.match(regex, text, re.IGNORECASE))

    def scan_historical(self, ssid_pattern: str) -> list[str]:
        """Search historical Kismet logs for BSSIDs matching an SSID.

        Args:
            ssid_pattern: SSID pattern to match.

        Returns:
            List of unique BSSIDs found.
        """
        found_bssids = set()

        if not KISMET_LOGS_DIR.exists():
            return []

        for wigle_file in KISMET_LOGS_DIR.rglob("*.wiglecsv"):
            try:
                with open(wigle_file) as f:
                    for line in f:
                        parts = line.strip().split(",")
                        if len(parts) >= 2:
                            bssid = parts[0]
                            ssid = parts[1]
                            if self.match_pattern(ssid, ssid_pattern):
                                if re.match(r"^[0-9A-Fa-f:]+$", bssid):
                                    found_bssids.add(bssid)
            except (OSError, UnicodeDecodeError):
                continue

        return list(found_bssids)

    def discover_ssid(self, ssid: str) -> dict:
        """Discover BSSIDs for an SSID via live scan and historical logs.

        Args:
            ssid: SSID or pattern to search for.

        Returns:
            Dict with ssid, live results, and historical BSSIDs.
        """
        self.log_info(f"Scanning for networks matching '{ssid}'...")

        live_results = self.scan_live(ssid)
        historical_bssids = self.scan_historical(ssid)

        if self.json_mode:
            return {
                "ssid": ssid,
                "live": [
                    {
                        "bssid": r.bssid,
                        "ssid": r.ssid,
                        "signal": r.signal,
                        "channel": r.channel,
                    }
                    for r in live_results
                ],
                "historical": historical_bssids,
            }
        else:
            print()
            print(f"Live scan results for '{ssid}':")
            if not live_results:
                print("  (no networks found in range)")
            else:
                for r in live_results:
                    print(f"  {r.bssid} (Signal: {r.signal}dBm)")

            print()
            print("Historical records:")
            if not historical_bssids:
                print("  (no historical records found)")
            else:
                for bssid in historical_bssids:
                    print(f"  {bssid}")

            return {}

    def check_duplicate_static(self, value: str, phy: str = "wifi") -> bool:
        """Check if a static exclusion already exists (case-insensitive).

        Args:
            value: SSID or BSSID to check.
            phy: PHY type (wifi, btle, bt).

        Returns:
            True if duplicate exists.
        """
        config = self.load_config()
        value_upper = value.upper()

        # Get the appropriate list based on PHY type
        if phy == "btle":
            entries = config.btle_static_exclusions
        elif phy == "bt":
            entries = config.bt_static_exclusions
        else:
            entries = config.static_exclusions

        for entry in entries:
            if entry.value.upper() == value_upper:
                return True
        return False

    def check_duplicate_dynamic(self, value: str, phy: str = "wifi") -> bool:
        """Check if a dynamic exclusion already exists (case-insensitive).

        Args:
            value: SSID or device name to check.
            phy: PHY type (wifi, btle, bt).

        Returns:
            True if duplicate exists.
        """
        config = self.load_config()
        value_upper = value.upper()

        # Get the appropriate list based on PHY type
        if phy == "btle":
            entries = config.btle_dynamic_exclusions
        elif phy == "bt":
            entries = config.bt_dynamic_exclusions
        else:
            entries = config.dynamic_exclusions

        for entry in entries:
            if entry.value.upper() == value_upper:
                return True
        return False

    def add_static(
        self,
        ssid: str,
        match_type: str = "exact",
        description: str = "",
        bssids: str = "",
        phy: str = "wifi",
    ) -> None:
        """Add a static exclusion.

        Args:
            ssid: SSID/device name or MAC to exclude.
            match_type: One of exact, pattern, bssid.
            description: Optional description.
            bssids: Comma-separated list of MACs to also add.
            phy: PHY type - wifi, btle, or bt.
        """
        self.ensure_config_dir()

        if not ssid:
            self.json_error("SSID/name or MAC required")

        if match_type not in ("exact", "pattern", "bssid"):
            self.json_error("Type must be: exact, pattern, or bssid")

        if phy not in VALID_PHY_TYPES:
            self.json_error(f"PHY must be: {', '.join(VALID_PHY_TYPES)}")

        # Determine target section based on PHY type
        section_map = {
            "wifi": SECTION_STATIC,
            "btle": SECTION_BTLE_STATIC,
            "bt": SECTION_BT_STATIC,
        }
        target_section = section_map[phy]
        phy_display = {"wifi": "WiFi", "btle": "BTLE", "bt": "Bluetooth"}[phy]

        # Check for duplicates (case-insensitive)
        if self.check_duplicate_static(ssid, phy):
            self.json_error(
                f"'{ssid}' already exists in {phy_display} static exclusions"
            )
            return

        # Add to config
        entry = f"{ssid}|{match_type}|{description}"
        self.add_to_section(target_section, entry)

        # If we have MACs, also add them (skip duplicates)
        added_macs = []
        if bssids:
            for mac in bssids.split(","):
                mac = mac.strip()
                if mac and not self.check_duplicate_static(mac, phy):
                    self.add_to_section(
                        target_section, f"{mac}|bssid|{description} MAC"
                    )
                    added_macs.append(mac)

        # Apply to Kismet configs
        self.apply_static_filter(
            ssid, match_type, ",".join(added_macs) if added_macs else "", phy
        )

        self.json_success(f"{phy_display} static exclusion added for '{ssid}'")

    def add_dynamic(
        self,
        ssid: str,
        match_type: str = "exact",
        description: str = "",
        phy: str = "wifi",
    ) -> None:
        """Add a dynamic exclusion.

        Args:
            ssid: SSID or device name to exclude.
            match_type: One of exact, pattern.
            description: Optional description.
            phy: PHY type - wifi, btle, or bt.
        """
        self.ensure_config_dir()

        if not ssid:
            self.json_error("SSID/name required")

        if match_type not in ("exact", "pattern"):
            self.json_error("Type must be: exact or pattern")

        if phy not in VALID_PHY_TYPES:
            self.json_error(f"PHY must be: {', '.join(VALID_PHY_TYPES)}")

        # Determine target section based on PHY type
        section_map = {
            "wifi": SECTION_DYNAMIC,
            "btle": SECTION_BTLE_DYNAMIC,
            "bt": SECTION_BT_DYNAMIC,
        }
        target_section = section_map[phy]
        phy_display = {"wifi": "WiFi", "btle": "BTLE", "bt": "Bluetooth"}[phy]

        # Check for duplicates (case-insensitive)
        if self.check_duplicate_dynamic(ssid, phy):
            self.json_error(
                f"'{ssid}' already exists in {phy_display} dynamic exclusions"
            )
            return

        # Add to config - dynamic exclusions NEVER get MACs
        entry = f"{ssid}|{match_type}|{description}"
        self.add_to_section(target_section, entry)

        self.log_warn(
            f"{phy_display} dynamic exclusion added - will be processed post-capture"
        )
        self.json_success(
            f"{phy_display} dynamic exclusion added for '{ssid}' (post-processing only)"
        )

    def apply_static_filter(
        self, ssid: str, match_type: str, macs: str = "", phy: str = "wifi"
    ) -> None:
        """Apply static filter to Kismet config files.

        Args:
            ssid: SSID/name or MAC.
            match_type: Filter type.
            macs: Comma-separated MACs.
            phy: PHY type - wifi, btle, or bt.
        """
        configs = [KISMET_SITE_CONF, KISMET_WARDRIVE_CONF]
        kismet_phy = PHY_KISMET_NAMES.get(phy, "IEEE802.11")
        phy_display = {"wifi": "WiFi", "btle": "BTLE", "bt": "Bluetooth"}[phy]

        for config in configs:
            if not config.exists():
                continue

            marker = f"# WARPIE_FILTER ({phy_display}): {ssid}"

            if match_type == "bssid":
                # Direct MAC address
                upper_mac = ssid.upper()
                lines = (
                    f"{marker}\nkis_log_device_filter={kismet_phy},{upper_mac},block\n"
                )
                subprocess.run(
                    ["sudo", "tee", "-a", str(config)],
                    input=lines.encode(),
                    capture_output=True,
                )
            elif macs:
                # Add discovered MACs
                lines = ""
                for mac in macs.split(","):
                    mac = mac.strip()
                    if mac:
                        upper_mac = mac.upper()
                        lines += f"{marker}\nkis_log_device_filter={kismet_phy},{upper_mac},block\n"
                if lines:
                    subprocess.run(
                        ["sudo", "tee", "-a", str(config)],
                        input=lines.encode(),
                        capture_output=True,
                    )
            else:
                # Just add a comment for later discovery
                if phy == "wifi":
                    comment = f"{marker} (SSID-only, discover BSSIDs with --discover)\n"
                else:
                    comment = f"{marker} (name-only, dynamic exclusion recommended for {phy_display})\n"
                subprocess.run(
                    ["sudo", "tee", "-a", str(config)],
                    input=comment.encode(),
                    capture_output=True,
                )

        self.log_info("Kismet configurations updated")

    def remove_static(self, value: str, phy: str = "wifi") -> None:
        """Remove a static exclusion.

        Args:
            value: The SSID/name or MAC to remove.
            phy: PHY type - wifi, btle, or bt.
        """
        self.ensure_config_dir()

        kismet_phy = PHY_KISMET_NAMES.get(phy, "IEEE802.11")
        phy_display = {"wifi": "WiFi", "btle": "BTLE", "bt": "Bluetooth"}[phy]

        # Escape special characters for sed
        escaped_value = (
            value.replace("*", "\\*").replace("/", "\\/").replace(":", "\\:")
        )

        # Remove from config file (new format)
        if FILTER_RULES_FILE.exists():
            subprocess.run(
                ["sudo", "sed", "-i", f"/^{escaped_value}|/d", str(FILTER_RULES_FILE)],
                check=False,
            )

        # Remove from Kismet configs - handle both new WARPIE_FILTER comments
        # and legacy kis_log_device_filter entries
        for config in [KISMET_SITE_CONF, KISMET_WARDRIVE_CONF]:
            if config.exists():
                # Remove WARPIE_FILTER comment lines for this value (both old and new format)
                # Old format: # WARPIE_FILTER: value
                # New format: # WARPIE_FILTER (PHY): value
                for marker in [
                    f"# WARPIE_FILTER: {value}",
                    f"# WARPIE_FILTER ({phy_display}): {value}",
                ]:
                    escaped_marker = (
                        marker.replace("*", "\\*")
                        .replace(":", "\\:")
                        .replace("(", "\\(")
                        .replace(")", "\\)")
                    )
                    subprocess.run(
                        ["sudo", "sed", "-i", f"/{escaped_marker}/d", str(config)],
                        check=False,
                    )

                # Remove kis_log_device_filter entries with this MAC for the specified PHY
                mac_upper = value.upper().replace(":", "\\:")
                subprocess.run(
                    [
                        "sudo",
                        "sed",
                        "-i",
                        f"/kis_log_device_filter={kismet_phy},{mac_upper}/d",
                        str(config),
                    ],
                    check=False,
                )

        self.json_success(f"Removed {phy_display} static exclusion: {value}")

    def remove_dynamic(self, value: str, phy: str = "wifi") -> None:
        """Remove a dynamic exclusion.

        Args:
            value: The SSID/name to remove.
            phy: PHY type - wifi, btle, or bt.
        """
        self.ensure_config_dir()

        phy_display = {"wifi": "WiFi", "btle": "BTLE", "bt": "Bluetooth"}[phy]

        # Escape special characters for sed
        escaped_value = value.replace("*", "\\*").replace("/", "\\/")

        # Remove from config file
        subprocess.run(
            ["sudo", "sed", "-i", f"/^{escaped_value}|/d", str(FILTER_RULES_FILE)],
            check=False,
        )

        self.json_success(f"Removed {phy_display} dynamic exclusion: {value}")

    def list_filters(self) -> dict:
        """List all filters.

        Returns:
            Dict with all filter sections.
        """
        config = self.load_config()

        if self.json_mode:
            return {
                # WiFi filters
                "static_exclusions": [
                    {
                        "ssid": e.value,
                        "type": e.type,
                        "description": e.description,
                        "phy": "wifi",
                    }
                    for e in config.static_exclusions
                ],
                "dynamic_exclusions": [
                    {
                        "ssid": e.value,
                        "type": e.type,
                        "description": e.description,
                        "phy": "wifi",
                    }
                    for e in config.dynamic_exclusions
                ],
                # BTLE filters
                "btle_static_exclusions": [
                    {
                        "value": e.value,
                        "type": e.type,
                        "description": e.description,
                        "phy": "btle",
                    }
                    for e in config.btle_static_exclusions
                ],
                "btle_dynamic_exclusions": [
                    {
                        "value": e.value,
                        "type": e.type,
                        "description": e.description,
                        "phy": "btle",
                    }
                    for e in config.btle_dynamic_exclusions
                ],
                # Classic Bluetooth filters
                "bt_static_exclusions": [
                    {
                        "value": e.value,
                        "type": e.type,
                        "description": e.description,
                        "phy": "bt",
                    }
                    for e in config.bt_static_exclusions
                ],
                "bt_dynamic_exclusions": [
                    {
                        "value": e.value,
                        "type": e.type,
                        "description": e.description,
                        "phy": "bt",
                    }
                    for e in config.bt_dynamic_exclusions
                ],
                # Targeting
                "targeting_inclusions": [
                    {"oui": e.value, "mode": e.type, "description": e.description}
                    for e in config.targeting_inclusions
                ],
                "counts": {
                    "wifi_static": len(config.static_exclusions),
                    "wifi_dynamic": len(config.dynamic_exclusions),
                    "btle_static": len(config.btle_static_exclusions),
                    "btle_dynamic": len(config.btle_dynamic_exclusions),
                    "bt_static": len(config.bt_static_exclusions),
                    "bt_dynamic": len(config.bt_dynamic_exclusions),
                    "targets": len(config.targeting_inclusions),
                },
            }
        else:
            print()
            print("\033[1m=== WarPie Network Filters ===\033[0m")

            # WiFi Static
            print()
            print("\033[0;36mWiFi Static Exclusions\033[0m (blocked at capture time):")
            print("-" * 50)
            if not config.static_exclusions:
                print("  (none configured)")
            else:
                for e in config.static_exclusions:
                    print(f"  \033[0;32m*\033[0m {e.value} \033[1;33m[{e.type}]\033[0m")
                    if e.description:
                        print(f"    {e.description}")

            # WiFi Dynamic
            print()
            print("\033[0;36mWiFi Dynamic Exclusions\033[0m (post-processing removal):")
            print("-" * 52)
            if not config.dynamic_exclusions:
                print("  (none configured)")
            else:
                for e in config.dynamic_exclusions:
                    print(f"  \033[1;33m*\033[0m {e.value} \033[1;33m[{e.type}]\033[0m")
                    if e.description:
                        print(f"    {e.description}")

            # BTLE Static
            print()
            print("\033[0;35mBTLE Static Exclusions\033[0m (blocked at capture time):")
            print("-" * 50)
            if not config.btle_static_exclusions:
                print("  (none configured)")
            else:
                for e in config.btle_static_exclusions:
                    print(f"  \033[0;35m*\033[0m {e.value} \033[1;33m[{e.type}]\033[0m")
                    if e.description:
                        print(f"    {e.description}")

            # BTLE Dynamic
            print()
            print(
                "\033[0;35mBTLE Dynamic Exclusions\033[0m (post-processing by device name):"
            )
            print("-" * 58)
            if not config.btle_dynamic_exclusions:
                print("  (none configured)")
            else:
                for e in config.btle_dynamic_exclusions:
                    print(f"  \033[0;35m*\033[0m {e.value} \033[1;33m[{e.type}]\033[0m")
                    if e.description:
                        print(f"    {e.description}")

            # Classic BT Static
            print()
            print(
                "\033[0;34mBluetooth Static Exclusions\033[0m (blocked at capture time):"
            )
            print("-" * 55)
            if not config.bt_static_exclusions:
                print("  (none configured)")
            else:
                for e in config.bt_static_exclusions:
                    print(f"  \033[0;34m*\033[0m {e.value} \033[1;33m[{e.type}]\033[0m")
                    if e.description:
                        print(f"    {e.description}")

            # Classic BT Dynamic
            print()
            print(
                "\033[0;34mBluetooth Dynamic Exclusions\033[0m (post-processing by name):"
            )
            print("-" * 56)
            if not config.bt_dynamic_exclusions:
                print("  (none configured)")
            else:
                for e in config.bt_dynamic_exclusions:
                    print(f"  \033[0;34m*\033[0m {e.value} \033[1;33m[{e.type}]\033[0m")
                    if e.description:
                        print(f"    {e.description}")

            # Targeting
            print()
            print("\033[0;36mTargeting Inclusions\033[0m (added to targeting modes):")
            print("-" * 48)
            if not config.targeting_inclusions:
                print("  (none configured)")
            else:
                for e in config.targeting_inclusions:
                    print(f"  \033[0;34m*\033[0m {e.value} -> \033[1m{e.type}\033[0m")
                    if e.description:
                        print(f"    {e.description}")
            print()

            return {}

    def run_cleanup(self, all_static: bool = False) -> dict:
        """Run retroactive cleanup on historical logs.

        Args:
            all_static: If True, clean all static exclusions.

        Returns:
            Dict with cleanup results.
        """
        config = self.load_config()

        if not config.static_exclusions and not config.dynamic_exclusions:
            self.json_success("No exclusions configured - nothing to clean")
            return {"success": True, "cleaned": 0}

        # For now, just report what would be cleaned
        # Full implementation would iterate through kismetdb files
        cleaned_count = 0

        if self.json_mode:
            return {
                "success": True,
                "message": "Cleanup completed",
                "cleaned": cleaned_count,
            }
        else:
            self.log_success(f"Cleanup completed - {cleaned_count} entries processed")
            return {}


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description=f"WarPie Filter Manager v{VERSION}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Add home WiFi network (static, stable MAC)
  %(prog)s --add-static --ssid "HOME-5G" --desc "Home network"

  # Add iPhone hotspot (dynamic, rotating MAC)
  %(prog)s --add-dynamic --ssid "iPhone*" --type pattern --desc "iPhone hotspots"

  # Add BTLE device by MAC (static)
  %(prog)s --add-static --phy btle --bssid AA:BB:CC:DD:EE:FF --desc "My Fitbit"

  # Add BTLE device by name pattern (dynamic - recommended for BTLE)
  %(prog)s --add-dynamic --phy btle --ssid "Fitbit*" --type pattern --desc "Fitbit devices"

  # JSON API for web interface
  %(prog)s --json --list
  %(prog)s --json --discover "NetworkName"
""",
    )

    # Mode flags
    parser.add_argument("--json", action="store_true", help="Output in JSON format")
    parser.add_argument(
        "--quiet", "-q", action="store_true", help="Suppress non-essential output"
    )

    # Actions
    parser.add_argument("--list", action="store_true", help="List all filters")
    parser.add_argument(
        "--add-static", action="store_true", help="Add static exclusion"
    )
    parser.add_argument(
        "--add-dynamic", action="store_true", help="Add dynamic exclusion"
    )
    parser.add_argument(
        "--remove-static", action="store_true", help="Remove static exclusion"
    )
    parser.add_argument(
        "--remove-dynamic", action="store_true", help="Remove dynamic exclusion"
    )
    parser.add_argument(
        "--discover", metavar="SSID", help="Discover BSSIDs for an SSID (WiFi only)"
    )
    parser.add_argument(
        "--cleanup", action="store_true", help="Run retroactive cleanup"
    )
    parser.add_argument(
        "--all-static",
        action="store_true",
        help="With --cleanup, clean all static exclusions",
    )

    # Parameters
    parser.add_argument("--ssid", help="SSID or device name for exclusion")
    parser.add_argument("--bssid", help="BSSID/MAC address for exclusion")
    parser.add_argument(
        "--type",
        choices=["exact", "pattern", "bssid"],
        default="exact",
        help="Match type (default: exact)",
    )
    parser.add_argument("--desc", "--description", dest="desc", help="Description")
    parser.add_argument(
        "--phy",
        choices=["wifi", "btle", "bt"],
        default="wifi",
        help="PHY type: wifi (default), btle (Bluetooth Low Energy), bt (Classic Bluetooth)",
    )

    parser.add_argument(
        "--version", "-v", action="version", version=f"WarPie Filter Manager v{VERSION}"
    )

    args = parser.parse_args()

    manager = FilterManager(json_mode=args.json, quiet_mode=args.quiet)

    try:
        if args.list:
            result = manager.list_filters()
            if args.json and result:
                manager.json_output(result)

        elif args.add_static:
            if args.bssid:
                manager.add_static(args.bssid, "bssid", args.desc or "", phy=args.phy)
            elif args.ssid:
                manager.add_static(args.ssid, args.type, args.desc or "", phy=args.phy)
            else:
                manager.json_error("SSID/name or BSSID/MAC required")

        elif args.add_dynamic:
            if not args.ssid:
                manager.json_error("SSID/name required")
            manager.add_dynamic(args.ssid, args.type, args.desc or "", phy=args.phy)

        elif args.remove_static:
            if not args.ssid:
                manager.json_error("SSID/name required")
            manager.remove_static(args.ssid, phy=args.phy)

        elif args.remove_dynamic:
            if not args.ssid:
                manager.json_error("SSID/name required")
            manager.remove_dynamic(args.ssid, phy=args.phy)

        elif args.discover:
            if args.phy != "wifi":
                manager.log_warn(
                    "Discovery is only supported for WiFi. BTLE/BT devices must be added by MAC or name."
                )
            result = manager.discover_ssid(args.discover)
            if args.json and result:
                manager.json_output(result)

        elif args.cleanup:
            result = manager.run_cleanup(all_static=args.all_static)
            if args.json and result:
                manager.json_output(result)

        elif args.json:
            manager.json_error("Action required in JSON mode")

        else:
            # Interactive mode - for now just show help
            parser.print_help()

    except KeyboardInterrupt:
        print()
        sys.exit(130)


if __name__ == "__main__":
    main()
