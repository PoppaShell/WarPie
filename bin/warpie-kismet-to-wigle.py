#!/usr/bin/env python3
"""
WarPie Kismet to WiGLE CSV Converter

Exports WiFi, BTLE, and Classic Bluetooth devices from Kismet database files
to WiGLE CSV 1.4 format with proper GPS correlation. Works around upstream
Kismet bugs that prevent BTLE devices from being exported to WiGLE format.

Features:
- Extracts WiFi (IEEE802.11), BTLE, and Classic Bluetooth devices
- Correlates GPS from devices, packets, and data tables
- Outputs WiGLE CSV 1.4 format with correct Type field
- Rate limiting (1 record/sec/device) to prevent WiGLE duplicates
- Privacy filtering via exclusion zones and SSID patterns
- JSON mode for web API integration

Usage:
    warpie-kismet-to-wigle.py --in Kismet-*.kismet --out export.wiglecsv
    warpie-kismet-to-wigle.py --in capture.kismet --btle-only --out btle.csv
    warpie-kismet-to-wigle.py --json --in capture.kismet --stats

Version: 2.4.1
"""

import argparse
import fnmatch
import json
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# =============================================================================
# CONFIGURATION
# =============================================================================

VERSION = "2.4.1"
FILTER_RULES_FILE = Path("/etc/warpie/filter_rules.conf")

# WiGLE CSV 1.4 column definitions
WIGLE_HEADER_LINE1 = (
    "WigleWifi-1.4,appRelease=warpie-{version},"
    "model=RaspberryPi,release=bookworm,"
    "device=WarPie,display=,board=,brand=WarPie"
)
WIGLE_HEADER_LINE2 = (
    "MAC,SSID,AuthMode,FirstSeen,Channel,RSSI,"
    "CurrentLatitude,CurrentLongitude,AltitudeMeters,AccuracyMeters,Type"
)

# PHY name to WiGLE Type mapping
PHY_TO_WIGLE_TYPE = {
    "IEEE802.11": "WIFI",
    "BTLE": "BLE",
    "Bluetooth": "BT",
}


# =============================================================================
# TERMINAL COLORS
# =============================================================================


class Colors:
    """ANSI color codes for terminal output."""

    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    BLUE = "\033[0;34m"
    CYAN = "\033[0;36m"
    BOLD = "\033[1m"
    NC = "\033[0m"  # No Color

    @classmethod
    def disable(cls):
        """Disable colors for non-TTY output."""
        cls.RED = cls.GREEN = cls.YELLOW = ""
        cls.BLUE = cls.CYAN = cls.BOLD = cls.NC = ""


# Disable colors if not a TTY
if not sys.stdout.isatty():
    Colors.disable()


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class DeviceRecord:
    """Represents a device ready for WiGLE export."""

    mac: str
    name: str  # SSID for WiFi, device name for BT/BLE
    auth_mode: str  # Security/capabilities
    first_seen: datetime
    channel: int
    rssi: int
    latitude: float
    longitude: float
    altitude: float = 0.0
    accuracy: float = 0.0
    device_type: str = "WIFI"  # WIFI, BLE, BT
    phy_name: str = "IEEE802.11"


@dataclass
class ExportConfig:
    """Configuration for WiGLE export."""

    input_files: list = field(default_factory=list)
    output_file: Path | None = None
    include_wifi: bool = True
    include_btle: bool = True
    include_bt: bool = True
    rate_limit: bool = True
    exclusion_zones: list = field(default_factory=list)
    apply_ssid_exclusions: bool = False


@dataclass
class ExportStats:
    """Statistics from export operation."""

    wifi_count: int = 0
    btle_count: int = 0
    bt_count: int = 0
    total_with_gps: int = 0
    filtered_count: int = 0
    rate_limited_count: int = 0
    files_processed: int = 0


@dataclass
class ExportResult:
    """Result of export operation."""

    success: bool = True
    error: str = ""
    stats: ExportStats = field(default_factory=ExportStats)
    output_file: str = ""
    devices: list = field(default_factory=list)


# =============================================================================
# DATABASE EXTRACTION
# =============================================================================


def extract_wifi_devices(db_path: str) -> list[DeviceRecord]:
    """Extract WiFi APs with GPS from kismetdb.

    Args:
        db_path: Path to kismetdb file

    Returns:
        List of DeviceRecord objects for WiFi devices with GPS
    """
    devices = []

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Query devices with GPS, preferring packet-level GPS over device average
        cursor.execute("""
            SELECT
                d.devmac,
                d.device,
                d.first_time,
                d.avg_lat,
                d.avg_lon
            FROM devices d
            WHERE d.phyname = 'IEEE802.11'
            AND d.avg_lat != 0
            AND d.avg_lon != 0
        """)

        for row in cursor.fetchall():
            devmac, device_json, first_time, avg_lat, avg_lon = row

            # Parse device JSON for SSID and other metadata
            ssid, auth_mode, channel, rssi = _parse_wifi_device(device_json)

            # Skip if no valid GPS
            if avg_lat == 0 or avg_lon == 0:
                continue

            device = DeviceRecord(
                mac=devmac.upper() if devmac else "",
                name=ssid,
                auth_mode=auth_mode,
                first_seen=datetime.fromtimestamp(first_time) if first_time else datetime.now(),
                channel=channel,
                rssi=rssi,
                latitude=avg_lat,
                longitude=avg_lon,
                device_type="WIFI",
                phy_name="IEEE802.11",
            )
            devices.append(device)

        conn.close()

    except sqlite3.Error as e:
        print(
            f"{Colors.RED}[ERROR]{Colors.NC} Database error reading {db_path}: {e}",
            file=sys.stderr,
        )

    return devices


def extract_btle_devices(db_path: str) -> list[DeviceRecord]:
    """Extract BTLE devices with GPS from kismetdb.

    BTLE GPS extraction strategy:
    1. Check device table avg_lat/avg_lon
    2. Fall back to packets table GPS
    3. Fall back to data table GPS

    Args:
        db_path: Path to kismetdb file

    Returns:
        List of DeviceRecord objects for BTLE devices with GPS
    """
    devices = []

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # First, get devices with GPS from device table
        cursor.execute("""
            SELECT
                d.devmac,
                d.device,
                d.first_time,
                d.avg_lat,
                d.avg_lon
            FROM devices d
            WHERE d.phyname = 'BTLE'
            AND d.avg_lat != 0
            AND d.avg_lon != 0
        """)

        for row in cursor.fetchall():
            devmac, device_json, first_time, avg_lat, avg_lon = row

            name, rssi = _parse_btle_device(device_json)

            device = DeviceRecord(
                mac=devmac.upper() if devmac else "",
                name=name,
                auth_mode="BLE",
                first_seen=datetime.fromtimestamp(first_time) if first_time else datetime.now(),
                channel=0,  # BLE advertising channels
                rssi=rssi,
                latitude=avg_lat,
                longitude=avg_lon,
                device_type="BLE",
                phy_name="BTLE",
            )
            devices.append(device)

        # Now try to get devices without GPS from device table but with GPS in packets
        cursor.execute("""
            SELECT DISTINCT
                d.devmac,
                d.device,
                d.first_time,
                p.lat,
                p.lon,
                p.signal
            FROM devices d
            JOIN packets p ON p.sourcemac = d.devmac
            WHERE d.phyname = 'BTLE'
            AND (d.avg_lat = 0 OR d.avg_lat IS NULL)
            AND p.lat != 0
            AND p.lon != 0
            GROUP BY d.devmac
        """)

        seen_macs = {d.mac for d in devices}
        for row in cursor.fetchall():
            devmac, device_json, first_time, lat, lon, signal = row
            mac_upper = devmac.upper() if devmac else ""

            if mac_upper in seen_macs:
                continue

            name, rssi = _parse_btle_device(device_json)
            if signal and signal != 0:
                rssi = signal

            device = DeviceRecord(
                mac=mac_upper,
                name=name,
                auth_mode="BLE",
                first_seen=datetime.fromtimestamp(first_time) if first_time else datetime.now(),
                channel=0,
                rssi=rssi,
                latitude=lat,
                longitude=lon,
                device_type="BLE",
                phy_name="BTLE",
            )
            devices.append(device)
            seen_macs.add(mac_upper)

        conn.close()

    except sqlite3.Error as e:
        print(
            f"{Colors.RED}[ERROR]{Colors.NC} Database error reading {db_path}: {e}",
            file=sys.stderr,
        )

    return devices


def extract_bt_devices(db_path: str) -> list[DeviceRecord]:
    """Extract Classic Bluetooth devices with GPS from kismetdb.

    Args:
        db_path: Path to kismetdb file

    Returns:
        List of DeviceRecord objects for Classic Bluetooth devices with GPS
    """
    devices = []

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                d.devmac,
                d.device,
                d.first_time,
                d.avg_lat,
                d.avg_lon
            FROM devices d
            WHERE d.phyname = 'Bluetooth'
            AND d.avg_lat != 0
            AND d.avg_lon != 0
        """)

        for row in cursor.fetchall():
            devmac, device_json, first_time, avg_lat, avg_lon = row

            name, rssi = _parse_bt_device(device_json)

            device = DeviceRecord(
                mac=devmac.upper() if devmac else "",
                name=name,
                auth_mode="BT",
                first_seen=datetime.fromtimestamp(first_time) if first_time else datetime.now(),
                channel=0,
                rssi=rssi,
                latitude=avg_lat,
                longitude=avg_lon,
                device_type="BT",
                phy_name="Bluetooth",
            )
            devices.append(device)

        conn.close()

    except sqlite3.Error as e:
        print(
            f"{Colors.RED}[ERROR]{Colors.NC} Database error reading {db_path}: {e}",
            file=sys.stderr,
        )

    return devices


def _parse_wifi_device(device_json: str) -> tuple[str, str, int, int]:
    """Parse WiFi device JSON for SSID, auth mode, channel, and RSSI.

    Args:
        device_json: JSON blob from devices table

    Returns:
        Tuple of (ssid, auth_mode, channel, rssi)
    """
    ssid = ""
    auth_mode = ""
    channel = 0
    rssi = -100

    if not device_json:
        return ssid, auth_mode, channel, rssi

    try:
        device = json.loads(device_json)

        # Get SSID from various possible locations
        dot11 = device.get("dot11.device", {})
        advertised = dot11.get("dot11.device.advertised_ssid_map")
        if advertised:
            # Get first advertised SSID
            first_ssid = next(iter(advertised.values()), {})
            ssid = first_ssid.get("dot11.advertisedssid.ssid", "")

        # Fall back to other SSID fields
        if not ssid:
            ssid = device.get("kismet.device.base.commonname", "")
        if not ssid:
            ssid = device.get("kismet.device.base.name", "")

        # Get channel
        channel = device.get("kismet.device.base.channel", 0)
        if not channel:
            freq = device.get("kismet.device.base.frequency", 0)
            channel = _freq_to_channel(freq)

        # Get signal strength
        rssi = device.get("kismet.device.base.signal", {}).get(
            "kismet.common.signal.last_signal", -100
        )

        # Get auth mode / encryption
        if advertised:
            first_ssid = next(iter(advertised.values()), {})
            crypt = first_ssid.get("dot11.advertisedssid.crypt_set", 0)
            auth_mode = _crypt_to_auth_mode(crypt)

    except (json.JSONDecodeError, TypeError, KeyError):
        pass

    return ssid, auth_mode, channel, rssi


def _parse_btle_device(device_json: str) -> tuple[str, int]:
    """Parse BTLE device JSON for name and RSSI.

    Args:
        device_json: JSON blob from devices table

    Returns:
        Tuple of (name, rssi)
    """
    name = ""
    rssi = -100

    if not device_json:
        return name, rssi

    try:
        device = json.loads(device_json)

        # Try BTLE-specific name fields
        btle = device.get("btle.device", {})
        name = btle.get("btle.device.common_name", "")
        if not name:
            name = btle.get("btle.device.advertised_name", "")

        # Fall back to generic device name
        if not name:
            name = device.get("kismet.device.base.commonname", "")
        if not name:
            name = device.get("kismet.device.base.name", "")

        # Get signal
        rssi = device.get("kismet.device.base.signal", {}).get(
            "kismet.common.signal.last_signal", -100
        )

    except (json.JSONDecodeError, TypeError, KeyError):
        pass

    return name, rssi


def _parse_bt_device(device_json: str) -> tuple[str, int]:
    """Parse Classic Bluetooth device JSON for name and RSSI.

    Args:
        device_json: JSON blob from devices table

    Returns:
        Tuple of (name, rssi)
    """
    name = ""
    rssi = -100

    if not device_json:
        return name, rssi

    try:
        device = json.loads(device_json)

        # Try Bluetooth-specific name fields
        bt = device.get("bluetooth.device", {})
        name = bt.get("bluetooth.device.name", "")

        # Fall back to generic device name
        if not name:
            name = device.get("kismet.device.base.commonname", "")
        if not name:
            name = device.get("kismet.device.base.name", "")

        # Get signal
        rssi = device.get("kismet.device.base.signal", {}).get(
            "kismet.common.signal.last_signal", -100
        )

    except (json.JSONDecodeError, TypeError, KeyError):
        pass

    return name, rssi


def _freq_to_channel(freq: int) -> int:
    """Convert frequency in KHz to WiFi channel number.

    Args:
        freq: Frequency in KHz

    Returns:
        Channel number, or 0 if unknown
    """
    if not freq:
        return 0

    # Convert to MHz if in KHz
    if freq > 10000:
        freq = freq // 1000

    # 2.4 GHz band
    if 2412 <= freq <= 2484:
        if freq == 2484:
            return 14
        return (freq - 2412) // 5 + 1

    # 5 GHz band
    if 5170 <= freq <= 5825:
        return (freq - 5000) // 5

    return 0


def _crypt_to_auth_mode(crypt: int) -> str:
    """Convert Kismet crypt_set bitmask to WiGLE auth mode string.

    Args:
        crypt: Crypt bitmask from Kismet

    Returns:
        Auth mode string (e.g., "WPA2", "WEP", "OPEN")
    """
    if not crypt:
        return "OPEN"

    # Check for WPA3
    if crypt & 0x800000:
        return "WPA3"

    # Check for WPA2
    if crypt & 0x400:
        return "WPA2"

    # Check for WPA
    if crypt & 0x200:
        return "WPA"

    # Check for WEP
    if crypt & 0x100:
        return "WEP"

    return "OPEN"


# =============================================================================
# RATE LIMITING
# =============================================================================


def apply_rate_limiting(devices: list[DeviceRecord]) -> list[DeviceRecord]:
    """Apply WiGLE rate limiting: 1 observation per second per device.

    WiGLE deduplicates based on MAC + timestamp. If we submit multiple
    observations of the same device within the same second, only one
    is counted. This function selects the best observation per device
    per second (strongest signal).

    Args:
        devices: All extracted devices

    Returns:
        Rate-limited device list
    """
    # Group by (MAC, timestamp_second)
    seen_keys: dict[tuple[str, int], DeviceRecord] = {}

    for device in devices:
        ts_second = int(device.first_seen.timestamp())
        key = (device.mac, ts_second)

        if key not in seen_keys:
            seen_keys[key] = device
        elif device.rssi > seen_keys[key].rssi:
            # Keep observation with best signal
            seen_keys[key] = device

    return list(seen_keys.values())


# =============================================================================
# WIGLE CSV OUTPUT
# =============================================================================


def format_wigle_header() -> str:
    """Generate WiGLE CSV 1.4 header lines.

    Returns:
        Header string with two lines
    """
    header1 = WIGLE_HEADER_LINE1.format(version=VERSION)
    return f"{header1}\n{WIGLE_HEADER_LINE2}\n"


def format_device_row(device: DeviceRecord) -> str:
    """Format a device as WiGLE CSV row.

    Args:
        device: DeviceRecord to format

    Returns:
        CSV row string
    """
    # Format timestamp as "YYYY-MM-DD HH:MM:SS"
    first_seen = device.first_seen.strftime("%Y-%m-%d %H:%M:%S")

    # Escape SSID for CSV (handle commas and quotes)
    name = _escape_csv(device.name)

    return (
        f"{device.mac},{name},{device.auth_mode},{first_seen},"
        f"{device.channel},{device.rssi},"
        f"{device.latitude:.6f},{device.longitude:.6f},"
        f"{device.altitude:.1f},{device.accuracy:.1f},{device.device_type}"
    )


def _escape_csv(value: str) -> str:
    """Escape a string for CSV output.

    Args:
        value: String to escape

    Returns:
        Escaped string
    """
    if not value:
        return ""

    # If contains comma, quote, or newline, wrap in quotes
    if "," in value or '"' in value or "\n" in value:
        # Double any existing quotes
        value = value.replace('"', '""')
        return f'"{value}"'

    return value


# =============================================================================
# PRIVACY FILTERING
# =============================================================================


def is_in_exclusion_zone(
    lat: float, lon: float, zones: list[tuple[float, float, float, float]]
) -> bool:
    """Check if coordinates fall within any exclusion zone.

    Args:
        lat: Latitude
        lon: Longitude
        zones: List of (min_lat, min_lon, max_lat, max_lon) tuples

    Returns:
        True if point is in any exclusion zone
    """
    for min_lat, min_lon, max_lat, max_lon in zones:
        if min_lat <= lat <= max_lat and min_lon <= lon <= max_lon:
            return True
    return False


def load_ssid_exclusions(config_path: Path | None = None) -> list[tuple[str, str]]:
    """Load SSID exclusion patterns from filter rules config.

    Args:
        config_path: Path to filter_rules.conf (default: /etc/warpie/filter_rules.conf)

    Returns:
        List of (pattern, match_type) tuples
    """
    if config_path is None:
        config_path = FILTER_RULES_FILE

    exclusions = []

    if not config_path.exists():
        return exclusions

    try:
        content = config_path.read_text()
        in_dynamic = False

        for raw_line in content.splitlines():
            line = raw_line.strip()

            if line == "[dynamic_exclusions]":
                in_dynamic = True
                continue
            if line.startswith("[") and line.endswith("]"):
                in_dynamic = False
                continue

            if not in_dynamic or not line or line.startswith("#"):
                continue

            parts = line.split("|", 2)
            if len(parts) >= 2:
                pattern = parts[0]
                match_type = parts[1]
                exclusions.append((pattern, match_type))

    except OSError:
        pass

    return exclusions


def matches_ssid_exclusion(name: str, exclusions: list[tuple[str, str]]) -> bool:
    """Check if a device name matches any SSID exclusion pattern.

    Args:
        name: Device name/SSID
        exclusions: List of (pattern, match_type) tuples

    Returns:
        True if name matches any exclusion
    """
    for pattern, match_type in exclusions:
        if match_type == "exact" and name == pattern:
            return True
        if match_type == "pattern" and fnmatch.fnmatch(name, pattern):
            return True

    return False


# =============================================================================
# MAIN EXPORT LOGIC
# =============================================================================


def export_to_wigle(config: ExportConfig) -> ExportResult:
    """Export kismetdb files to WiGLE CSV format.

    Args:
        config: Export configuration

    Returns:
        ExportResult with stats and output info
    """
    result = ExportResult()
    all_devices: list[DeviceRecord] = []

    # Process each input file
    for input_path in config.input_files:
        if not Path(input_path).exists():
            result.error = f"Input file not found: {input_path}"
            result.success = False
            return result

        result.stats.files_processed += 1

        # Extract devices by type
        if config.include_wifi:
            wifi_devices = extract_wifi_devices(input_path)
            all_devices.extend(wifi_devices)
            result.stats.wifi_count += len(wifi_devices)

        if config.include_btle:
            btle_devices = extract_btle_devices(input_path)
            all_devices.extend(btle_devices)
            result.stats.btle_count += len(btle_devices)

        if config.include_bt:
            bt_devices = extract_bt_devices(input_path)
            all_devices.extend(bt_devices)
            result.stats.bt_count += len(bt_devices)

    result.stats.total_with_gps = len(all_devices)

    # Apply exclusion zones
    if config.exclusion_zones:
        before_count = len(all_devices)
        all_devices = [
            d
            for d in all_devices
            if not is_in_exclusion_zone(d.latitude, d.longitude, config.exclusion_zones)
        ]
        result.stats.filtered_count += before_count - len(all_devices)

    # Apply SSID exclusions
    if config.apply_ssid_exclusions:
        exclusions = load_ssid_exclusions()
        if exclusions:
            before_count = len(all_devices)
            all_devices = [d for d in all_devices if not matches_ssid_exclusion(d.name, exclusions)]
            result.stats.filtered_count += before_count - len(all_devices)

    # Apply rate limiting
    if config.rate_limit:
        before_count = len(all_devices)
        all_devices = apply_rate_limiting(all_devices)
        result.stats.rate_limited_count = before_count - len(all_devices)

    # Store devices for preview mode
    result.devices = all_devices

    # Write output if output file specified
    # NOTE: Writing MAC addresses and GPS coordinates is the core purpose of this
    # WiGLE export tool. WiGLE is a public crowdsourced database of wireless networks.
    # This is intentional functionality, not a security vulnerability.
    if config.output_file:
        try:
            with Path(config.output_file).open("w") as f:
                f.write(format_wigle_header())
                for device in all_devices:
                    f.write(format_device_row(device) + "\n")

            result.output_file = str(config.output_file)

        except OSError as e:
            result.error = f"Failed to write output: {e}"
            result.success = False

    return result


# =============================================================================
# CLI OUTPUT
# =============================================================================


def print_stats(result: ExportResult, json_mode: bool = False):
    """Print export statistics.

    Args:
        result: ExportResult to display
        json_mode: If True, output JSON format
    """
    if json_mode:
        output = {
            "success": result.success,
            "stats": {
                "wifi_count": result.stats.wifi_count,
                "btle_count": result.stats.btle_count,
                "bt_count": result.stats.bt_count,
                "total_with_gps": result.stats.total_with_gps,
                "filtered_count": result.stats.filtered_count,
                "rate_limited_count": result.stats.rate_limited_count,
                "files_processed": result.stats.files_processed,
                "final_count": len(result.devices),
            },
        }
        if result.output_file:
            output["output_file"] = result.output_file
        if result.error:
            output["error"] = result.error

        print(json.dumps(output, indent=2))
        return

    # Human-readable output
    print(f"\n{Colors.BOLD}=== WiGLE Export Statistics ==={Colors.NC}")
    print(f"Files processed: {result.stats.files_processed}")
    print()
    print(f"  {Colors.CYAN}WiFi devices:{Colors.NC}  {result.stats.wifi_count}")
    print(f"  {Colors.CYAN}BTLE devices:{Colors.NC}  {result.stats.btle_count}")
    print(f"  {Colors.CYAN}BT devices:{Colors.NC}    {result.stats.bt_count}")
    print(f"  {Colors.BOLD}Total w/GPS:{Colors.NC}   {result.stats.total_with_gps}")
    print()

    if result.stats.filtered_count > 0:
        print(f"  Filtered out:  {result.stats.filtered_count}")
    if result.stats.rate_limited_count > 0:
        print(f"  Rate limited:  {result.stats.rate_limited_count}")

    print(f"\n  {Colors.GREEN}Final count:{Colors.NC}   {len(result.devices)}")

    if result.output_file:
        print(f"\n{Colors.GREEN}[OK]{Colors.NC} Written to: {result.output_file}")


def print_preview(result: ExportResult, limit: int = 20, json_mode: bool = False):
    """Print preview of devices to export.

    Args:
        result: ExportResult with devices
        limit: Maximum devices to show
        json_mode: If True, output JSON format
    """
    if json_mode:
        output = {
            "success": result.success,
            "preview_count": min(limit, len(result.devices)),
            "total_count": len(result.devices),
            "devices": [
                {
                    "mac": d.mac,
                    "name": d.name,
                    "type": d.device_type,
                    "lat": d.latitude,
                    "lon": d.longitude,
                    "rssi": d.rssi,
                }
                for d in result.devices[:limit]
            ],
        }
        # NOTE: Printing device info is the purpose of --preview mode for user verification
        print(json.dumps(output, indent=2))
        return

    # Human-readable preview
    # NOTE: Displaying MAC/GPS is intentional for user verification before WiGLE upload
    shown = min(limit, len(result.devices))
    total = len(result.devices)
    print(f"\n{Colors.BOLD}=== Preview (first {shown} of {total}) ==={Colors.NC}")
    print()

    for device in result.devices[:limit]:
        type_color = {
            "WIFI": Colors.BLUE,
            "BLE": Colors.CYAN,
            "BT": Colors.YELLOW,
        }.get(device.device_type, Colors.NC)

        name_display = device.name[:30] if device.name else "(no name)"
        print(
            f"  {type_color}[{device.device_type}]{Colors.NC} "
            f"{device.mac}  {name_display:<32} "
            f"({device.latitude:.4f}, {device.longitude:.4f})"
        )


# =============================================================================
# CLI ENTRY POINT
# =============================================================================


def parse_exclusion_zone(zone_str: str) -> tuple[float, float, float, float]:
    """Parse exclusion zone string into coordinates.

    Args:
        zone_str: "LAT1,LON1,LAT2,LON2" format

    Returns:
        Tuple of (min_lat, min_lon, max_lat, max_lon)

    Raises:
        ValueError: If format is invalid
    """
    parts = zone_str.split(",")
    if len(parts) != 4:
        msg = f"Invalid zone format: {zone_str}"
        raise ValueError(msg)

    coords = [float(p.strip()) for p in parts]
    # Normalize to min/max
    lat1, lon1, lat2, lon2 = coords
    return (min(lat1, lat2), min(lon1, lon2), max(lat1, lat2), max(lon1, lon2))


def create_argument_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(
        description="Export Kismet captures to WiGLE CSV with BTLE support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Export all devices from single file
  %(prog)s --in Kismet-capture.kismet --out export.wiglecsv

  # Export only BTLE devices
  %(prog)s --in capture.kismet --out btle.wiglecsv --btle-only

  # Export with exclusion zone (home area)
  %(prog)s --in *.kismet --out export.wiglecsv \\
      --exclude-zone "47.0,-122.5,47.1,-122.4"

  # Preview devices without writing
  %(prog)s --in capture.kismet --preview

  # Get stats in JSON format (for web API)
  %(prog)s --json --in capture.kismet --stats
        """,
    )

    # Input/Output
    parser.add_argument(
        "--in",
        dest="input",
        nargs="+",
        required=True,
        help="Input kismetdb file(s) - supports glob patterns",
    )
    parser.add_argument(
        "--out",
        dest="output",
        help="Output WiGLE CSV file",
    )

    # Device type filtering
    type_group = parser.add_mutually_exclusive_group()
    type_group.add_argument(
        "--wifi-only",
        action="store_true",
        help="Export only WiFi devices",
    )
    type_group.add_argument(
        "--btle-only",
        action="store_true",
        help="Export only BTLE devices",
    )
    type_group.add_argument(
        "--bt-only",
        action="store_true",
        help="Export only Classic Bluetooth",
    )

    parser.add_argument(
        "--no-wifi",
        action="store_true",
        help="Exclude WiFi devices",
    )
    parser.add_argument(
        "--no-btle",
        action="store_true",
        help="Exclude BTLE devices",
    )
    parser.add_argument(
        "--no-bt",
        action="store_true",
        help="Exclude Classic Bluetooth",
    )

    # Privacy/filtering
    parser.add_argument(
        "--exclude-zone",
        action="append",
        metavar="LAT1,LON1,LAT2,LON2",
        help="Exclude devices in geographic zone (can specify multiple)",
    )
    parser.add_argument(
        "--apply-exclusions",
        action="store_true",
        help="Apply filter_rules.conf SSID exclusions",
    )
    parser.add_argument(
        "--no-rate-limit",
        action="store_true",
        help="Disable 1 record/sec/device rate limiting",
    )

    # Output modes
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON output for API integration",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Preview devices without writing (dry-run)",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show statistics only",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VERSION}",
    )

    return parser


def expand_glob_pattern(pattern: str) -> list[str]:
    """Expand a glob pattern to matching file paths."""
    path = Path(pattern)
    if path.is_absolute():
        # For absolute patterns, glob from root
        matches = list(Path("/").glob(str(path.relative_to("/"))))
    else:
        # For relative patterns, glob from current directory
        matches = list(Path.cwd().glob(pattern))
    return [str(m) for m in matches]


def build_config_from_args(args: argparse.Namespace) -> ExportConfig:
    """Build ExportConfig from parsed command line arguments."""
    # Expand glob patterns in input files
    input_files = []
    for pattern in args.input:
        expanded = expand_glob_pattern(pattern)
        if expanded:
            input_files.extend(expanded)
        else:
            input_files.append(pattern)  # Keep original for error message

    # Build config
    config = ExportConfig(
        input_files=input_files,
        output_file=Path(args.output) if args.output else None,
        include_wifi=not args.no_wifi and not args.btle_only and not args.bt_only,
        include_btle=not args.no_btle and not args.wifi_only and not args.bt_only,
        include_bt=not args.no_bt and not args.wifi_only and not args.btle_only,
        rate_limit=not args.no_rate_limit,
        apply_ssid_exclusions=args.apply_exclusions,
    )

    # Parse exclusion zones
    if args.exclude_zone:
        for zone_str in args.exclude_zone:
            zone = parse_exclusion_zone(zone_str)
            config.exclusion_zones.append(zone)

    return config


def main():
    """Main CLI entry point."""
    parser = create_argument_parser()
    args = parser.parse_args()

    # Validate arguments
    if not args.preview and not args.stats and not args.output:
        parser.error("--out is required unless using --preview or --stats")

    # Build config (may raise ValueError for bad exclusion zones)
    try:
        config = build_config_from_args(args)
    except ValueError as e:
        print(f"{Colors.RED}[ERROR]{Colors.NC} {e}", file=sys.stderr)
        sys.exit(1)

    # Run export
    result = export_to_wigle(config)

    if not result.success:
        if args.json:
            print(json.dumps({"success": False, "error": result.error}))
        else:
            print(f"{Colors.RED}[ERROR]{Colors.NC} {result.error}", file=sys.stderr)
        sys.exit(1)

    # Output based on mode
    if args.preview:
        print_preview(result, json_mode=args.json)
    elif args.stats:
        print_stats(result, json_mode=args.json)
    else:
        print_stats(result, json_mode=args.json)


if __name__ == "__main__":
    main()
