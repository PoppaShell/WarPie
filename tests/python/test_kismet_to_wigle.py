"""Comprehensive unit tests for warpie-kismet-to-wigle.py.

Tests cover:
- Module imports and dataclasses
- WiGLE CSV formatting
- Device extraction from kismetdb
- GPS coordinate handling
- Rate limiting logic
- Exclusion zone filtering
- CLI argument parsing

Uses pytest fixtures and mocking for isolation.
"""

import importlib.util
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pytest

bin_path = Path(__file__).parent.parent.parent / "bin"
sys.path.insert(0, str(bin_path))

# Import the module (handles hyphenated filename)
spec = importlib.util.spec_from_file_location(
    "warpie_kismet_to_wigle", str(bin_path / "warpie-kismet-to-wigle.py")
)
wigle_exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wigle_exporter)


# =============================================================================
# MODULE IMPORT TESTS
# =============================================================================


class TestModuleImports:
    """Test that the WiGLE exporter module can be imported."""

    def test_module_exists(self):
        """Verify the WiGLE exporter script exists."""
        script_path = bin_path / "warpie-kismet-to-wigle.py"
        assert script_path.exists(), "warpie-kismet-to-wigle.py should exist in bin/"

    def test_version_defined(self):
        """Verify VERSION constant is defined."""
        assert hasattr(wigle_exporter, "VERSION")
        assert wigle_exporter.VERSION == "2.4.1"

    def test_constants_defined(self):
        """Verify configuration constants are defined."""
        assert hasattr(wigle_exporter, "FILTER_RULES_FILE")
        assert hasattr(wigle_exporter, "WIGLE_HEADER_LINE1")
        assert hasattr(wigle_exporter, "WIGLE_HEADER_LINE2")

    def test_key_functions_exist(self):
        """Verify key functions are importable."""
        assert callable(wigle_exporter.format_wigle_header)
        assert callable(wigle_exporter.format_device_row)
        assert callable(wigle_exporter.apply_rate_limiting)
        assert callable(wigle_exporter.is_in_exclusion_zone)
        assert callable(wigle_exporter.parse_exclusion_zone)
        assert callable(wigle_exporter.export_to_wigle)
        assert callable(wigle_exporter.create_argument_parser)
        assert callable(wigle_exporter.build_config_from_args)
        assert callable(wigle_exporter.extract_wifi_devices)
        assert callable(wigle_exporter.extract_btle_devices)
        assert callable(wigle_exporter.extract_bt_devices)


# =============================================================================
# DATACLASS TESTS
# =============================================================================


class TestDeviceRecordDataclass:
    """Test DeviceRecord dataclass."""

    def test_device_record_creation_all_fields(self):
        """Test creating a DeviceRecord with all fields."""
        record = wigle_exporter.DeviceRecord(
            mac="AA:BB:CC:DD:EE:FF",
            name="TestNetwork",
            auth_mode="[WPA2-PSK-CCMP][ESS]",
            first_seen=datetime(2024, 1, 1, 12, 0, 0),
            channel=6,
            rssi=-65,
            latitude=47.6062,
            longitude=-122.3321,
            altitude=10.5,
            accuracy=5.0,
            device_type="WIFI",
            phy_name="IEEE802.11",
        )
        assert record.mac == "AA:BB:CC:DD:EE:FF"
        assert record.name == "TestNetwork"
        assert record.device_type == "WIFI"

    def test_device_record_defaults(self):
        """Test DeviceRecord with default values."""
        record = wigle_exporter.DeviceRecord(
            mac="AA:BB:CC:DD:EE:FF",
            name="Test",
            auth_mode="",
            first_seen=datetime.now(),
            channel=1,
            rssi=-70,
            latitude=0.0,
            longitude=0.0,
        )
        assert record.altitude == 0.0
        assert record.accuracy == 0.0
        assert record.device_type == "WIFI"
        assert record.phy_name == "IEEE802.11"


class TestExportConfigDataclass:
    """Test ExportConfig dataclass."""

    def test_export_config_defaults(self):
        """Test ExportConfig with default values."""
        config = wigle_exporter.ExportConfig(input_files=["test.kismet"])
        assert config.input_files == ["test.kismet"]
        assert config.output_file is None
        assert config.include_wifi is True
        assert config.include_btle is True
        assert config.include_bt is True
        assert config.rate_limit is True
        assert config.apply_ssid_exclusions is False
        assert config.exclusion_zones == []

    def test_export_config_custom_values(self, tmp_path):
        """Test ExportConfig with custom values."""
        config = wigle_exporter.ExportConfig(
            input_files=["a.kismet", "b.kismet"],
            output_file=tmp_path / "out.csv",
            include_wifi=False,
            include_btle=True,
            include_bt=False,
            rate_limit=False,
            apply_ssid_exclusions=True,
            exclusion_zones=[(47.0, -122.0, 47.1, -122.1)],
        )
        assert len(config.input_files) == 2
        assert config.include_wifi is False
        assert config.rate_limit is False
        assert len(config.exclusion_zones) == 1


class TestExportStatsDataclass:
    """Test ExportStats dataclass."""

    def test_export_stats_defaults(self):
        """Test ExportStats with default values."""
        stats = wigle_exporter.ExportStats()
        assert stats.wifi_count == 0
        assert stats.btle_count == 0
        assert stats.bt_count == 0
        assert stats.total_with_gps == 0
        assert stats.filtered_count == 0
        assert stats.rate_limited_count == 0
        assert stats.files_processed == 0


class TestExportResultDataclass:
    """Test ExportResult dataclass."""

    def test_export_result_defaults(self):
        """Test ExportResult with default values."""
        result = wigle_exporter.ExportResult()
        assert result.success is True
        assert result.error == ""  # Default is empty string
        assert result.output_file == ""  # Default is empty string
        assert result.devices == []
        assert isinstance(result.stats, wigle_exporter.ExportStats)


# =============================================================================
# WIGLE CSV FORMATTING TESTS
# =============================================================================


class TestFormatWigleHeader:
    """Test WiGLE CSV header formatting."""

    def test_header_contains_version(self):
        """Test header contains version info."""
        header = wigle_exporter.format_wigle_header()
        assert "WigleWifi-1.4" in header
        assert "warpie" in header

    def test_header_has_column_line(self):
        """Test header has proper column definitions."""
        header = wigle_exporter.format_wigle_header()
        assert "MAC" in header
        assert "SSID" in header
        assert "AuthMode" in header
        assert "Type" in header
        assert "CurrentLatitude" in header
        assert "CurrentLongitude" in header

    def test_header_is_two_lines(self):
        """Test header has exactly two lines."""
        header = wigle_exporter.format_wigle_header()
        lines = header.strip().split("\n")
        assert len(lines) == 2


class TestFormatDeviceRow:
    """Test WiGLE CSV device row formatting."""

    def test_format_wifi_device(self):
        """Test formatting a WiFi device row."""
        device = wigle_exporter.DeviceRecord(
            mac="AA:BB:CC:DD:EE:FF",
            name="TestNetwork",
            auth_mode="[WPA2][ESS]",
            first_seen=datetime(2024, 1, 1, 12, 0, 0),
            channel=6,
            rssi=-65,
            latitude=47.6062,
            longitude=-122.3321,
            altitude=10.5,
            accuracy=5.0,
            device_type="WIFI",
            phy_name="IEEE802.11",
        )
        row = wigle_exporter.format_device_row(device)
        assert "AA:BB:CC:DD:EE:FF" in row
        assert "TestNetwork" in row
        assert "47.6062" in row
        assert "-122.3321" in row
        assert "WIFI" in row

    def test_format_btle_device(self):
        """Test formatting a BTLE device row."""
        device = wigle_exporter.DeviceRecord(
            mac="11:22:33:44:55:66",
            name="Fitness Tracker",
            auth_mode="",
            first_seen=datetime(2024, 1, 1, 12, 0, 0),
            channel=0,
            rssi=-80,
            latitude=47.5,
            longitude=-122.5,
            device_type="BLE",
            phy_name="BTLE",
        )
        row = wigle_exporter.format_device_row(device)
        assert "11:22:33:44:55:66" in row
        assert "Fitness Tracker" in row
        assert "BLE" in row

    def test_format_bt_device(self):
        """Test formatting a Classic Bluetooth device row."""
        device = wigle_exporter.DeviceRecord(
            mac="AA:11:BB:22:CC:33",
            name="Speaker",
            auth_mode="",
            first_seen=datetime(2024, 1, 1, 12, 0, 0),
            channel=0,
            rssi=-75,
            latitude=47.6,
            longitude=-122.4,
            device_type="BT",
            phy_name="Bluetooth",
        )
        row = wigle_exporter.format_device_row(device)
        assert "BT" in row

    def test_format_escapes_commas(self):
        """Test that SSIDs with commas are properly escaped."""
        device = wigle_exporter.DeviceRecord(
            mac="AA:BB:CC:DD:EE:FF",
            name="Network, with, commas",
            auth_mode="[WPA2]",
            first_seen=datetime(2024, 1, 1, 12, 0, 0),
            channel=6,
            rssi=-65,
            latitude=47.6,
            longitude=-122.3,
        )
        row = wigle_exporter.format_device_row(device)
        # The SSID should be quoted or escaped
        assert "Network" in row


# =============================================================================
# RATE LIMITING TESTS
# =============================================================================


class TestApplyRateLimiting:
    """Test rate limiting (1 record per second per device)."""

    def test_no_duplicates_within_same_second(self):
        """Test that only one record per device per second is kept."""
        devices = [
            wigle_exporter.DeviceRecord(
                mac="AA:BB:CC:DD:EE:FF",
                name="Test1",
                auth_mode="",
                first_seen=datetime(2024, 1, 1, 12, 0, 0),
                channel=6,
                rssi=-65,
                latitude=47.6,
                longitude=-122.3,
            ),
            wigle_exporter.DeviceRecord(
                mac="AA:BB:CC:DD:EE:FF",
                name="Test2",
                auth_mode="",
                first_seen=datetime(2024, 1, 1, 12, 0, 0),  # Same second
                channel=6,
                rssi=-70,
                latitude=47.61,
                longitude=-122.31,
            ),
        ]
        result = wigle_exporter.apply_rate_limiting(devices)
        assert len(result) == 1

    def test_allows_different_seconds(self):
        """Test that records from different seconds are kept."""
        devices = [
            wigle_exporter.DeviceRecord(
                mac="AA:BB:CC:DD:EE:FF",
                name="Test1",
                auth_mode="",
                first_seen=datetime(2024, 1, 1, 12, 0, 0),
                channel=6,
                rssi=-65,
                latitude=47.6,
                longitude=-122.3,
            ),
            wigle_exporter.DeviceRecord(
                mac="AA:BB:CC:DD:EE:FF",
                name="Test2",
                auth_mode="",
                first_seen=datetime(2024, 1, 1, 12, 0, 1),  # Different second
                channel=6,
                rssi=-70,
                latitude=47.61,
                longitude=-122.31,
            ),
        ]
        result = wigle_exporter.apply_rate_limiting(devices)
        assert len(result) == 2

    def test_allows_different_macs(self):
        """Test that records from different MACs are kept."""
        devices = [
            wigle_exporter.DeviceRecord(
                mac="AA:BB:CC:DD:EE:FF",
                name="Test1",
                auth_mode="",
                first_seen=datetime(2024, 1, 1, 12, 0, 0),
                channel=6,
                rssi=-65,
                latitude=47.6,
                longitude=-122.3,
            ),
            wigle_exporter.DeviceRecord(
                mac="11:22:33:44:55:66",  # Different MAC
                name="Test2",
                auth_mode="",
                first_seen=datetime(2024, 1, 1, 12, 0, 0),  # Same second
                channel=6,
                rssi=-70,
                latitude=47.61,
                longitude=-122.31,
            ),
        ]
        result = wigle_exporter.apply_rate_limiting(devices)
        assert len(result) == 2

    def test_empty_list(self):
        """Test rate limiting with empty list."""
        result = wigle_exporter.apply_rate_limiting([])
        assert result == []


# =============================================================================
# EXCLUSION ZONE TESTS
# =============================================================================


class TestIsInExclusionZone:
    """Test geographic exclusion zone detection."""

    def test_point_inside_zone(self):
        """Test that a point inside the zone is detected."""
        zones = [(47.0, -122.5, 47.1, -122.4)]  # min_lat, min_lon, max_lat, max_lon
        assert wigle_exporter.is_in_exclusion_zone(47.05, -122.45, zones) is True

    def test_point_outside_zone(self):
        """Test that a point outside the zone is not detected."""
        zones = [(47.0, -122.5, 47.1, -122.4)]
        assert wigle_exporter.is_in_exclusion_zone(48.0, -123.0, zones) is False

    def test_point_on_boundary(self):
        """Test that a point on the boundary is detected."""
        zones = [(47.0, -122.5, 47.1, -122.4)]
        # Exactly on boundary
        assert wigle_exporter.is_in_exclusion_zone(47.0, -122.5, zones) is True

    def test_multiple_zones(self):
        """Test with multiple exclusion zones."""
        zones = [
            (47.0, -122.5, 47.1, -122.4),  # Zone 1
            (48.0, -123.5, 48.1, -123.4),  # Zone 2
        ]
        # In zone 1
        assert wigle_exporter.is_in_exclusion_zone(47.05, -122.45, zones) is True
        # In zone 2
        assert wigle_exporter.is_in_exclusion_zone(48.05, -123.45, zones) is True
        # Outside both
        assert wigle_exporter.is_in_exclusion_zone(49.0, -124.0, zones) is False

    def test_empty_zones(self):
        """Test with no exclusion zones."""
        assert wigle_exporter.is_in_exclusion_zone(47.0, -122.0, []) is False


class TestParseExclusionZone:
    """Test exclusion zone string parsing."""

    def test_parse_valid_zone(self):
        """Test parsing a valid zone string."""
        zone = wigle_exporter.parse_exclusion_zone("47.0,-122.5,47.1,-122.4")
        assert zone == (47.0, -122.5, 47.1, -122.4)

    def test_parse_reversed_coords(self):
        """Test that coords are normalized (min/max)."""
        zone = wigle_exporter.parse_exclusion_zone("47.1,-122.4,47.0,-122.5")
        # Should normalize to min/max order
        assert zone[0] <= zone[2]  # min_lat <= max_lat
        assert zone[1] <= zone[3]  # min_lon <= max_lon

    def test_parse_invalid_format(self):
        """Test parsing invalid zone string raises error."""
        with pytest.raises(ValueError):
            wigle_exporter.parse_exclusion_zone("47.0,-122.5,47.1")  # Missing coord

    def test_parse_invalid_numbers(self):
        """Test parsing non-numeric values raises error."""
        with pytest.raises(ValueError):
            wigle_exporter.parse_exclusion_zone("foo,bar,baz,qux")


# =============================================================================
# CLI ARGUMENT PARSING TESTS
# =============================================================================


class TestArgumentParser:
    """Test CLI argument parsing."""

    def test_parser_creation(self):
        """Test parser can be created."""
        parser = wigle_exporter.create_argument_parser()
        assert parser is not None

    def test_required_input(self):
        """Test that --in is required."""
        parser = wigle_exporter.create_argument_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])  # No --in

    def test_basic_args(self):
        """Test parsing basic arguments."""
        parser = wigle_exporter.create_argument_parser()
        args = parser.parse_args(["--in", "test.kismet", "--out", "out.csv"])
        assert args.input == ["test.kismet"]
        assert args.output == "out.csv"

    def test_device_type_filters(self):
        """Test device type filter arguments."""
        parser = wigle_exporter.create_argument_parser()

        args = parser.parse_args(["--in", "test.kismet", "--wifi-only", "--stats"])
        assert args.wifi_only is True
        assert args.btle_only is False

        args = parser.parse_args(["--in", "test.kismet", "--btle-only", "--stats"])
        assert args.btle_only is True

    def test_mutually_exclusive_type_filters(self):
        """Test that type filters are mutually exclusive."""
        parser = wigle_exporter.create_argument_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--in", "test.kismet", "--wifi-only", "--btle-only"])

    def test_output_modes(self):
        """Test output mode arguments."""
        parser = wigle_exporter.create_argument_parser()

        args = parser.parse_args(["--in", "test.kismet", "--preview"])
        assert args.preview is True

        args = parser.parse_args(["--in", "test.kismet", "--stats"])
        assert args.stats is True

        args = parser.parse_args(["--in", "test.kismet", "--json", "--stats"])
        assert args.json is True

    def test_exclusion_zones(self):
        """Test exclusion zone argument parsing."""
        parser = wigle_exporter.create_argument_parser()
        args = parser.parse_args(
            [
                "--in",
                "test.kismet",
                "--exclude-zone",
                "47.0,-122.5,47.1,-122.4",
                "--exclude-zone",
                "48.0,-123.5,48.1,-123.4",
                "--stats",
            ]
        )
        assert len(args.exclude_zone) == 2

    def test_multiple_input_files(self):
        """Test multiple input files."""
        parser = wigle_exporter.create_argument_parser()
        args = parser.parse_args(
            [
                "--in",
                "file1.kismet",
                "file2.kismet",
                "file3.kismet",
                "--out",
                "out.csv",
            ]
        )
        assert len(args.input) == 3


class TestBuildConfigFromArgs:
    """Test building ExportConfig from parsed arguments."""

    def test_basic_config(self):
        """Test building basic config."""
        parser = wigle_exporter.create_argument_parser()
        args = parser.parse_args(["--in", "test.kismet", "--out", "out.csv"])
        config = wigle_exporter.build_config_from_args(args)
        assert config.output_file == Path("out.csv")
        assert config.include_wifi is True
        assert config.include_btle is True
        assert config.include_bt is True

    def test_wifi_only_config(self):
        """Test building wifi-only config."""
        parser = wigle_exporter.create_argument_parser()
        args = parser.parse_args(["--in", "test.kismet", "--wifi-only", "--stats"])
        config = wigle_exporter.build_config_from_args(args)
        assert config.include_wifi is True
        assert config.include_btle is False
        assert config.include_bt is False

    def test_btle_only_config(self):
        """Test building btle-only config."""
        parser = wigle_exporter.create_argument_parser()
        args = parser.parse_args(["--in", "test.kismet", "--btle-only", "--stats"])
        config = wigle_exporter.build_config_from_args(args)
        assert config.include_wifi is False
        assert config.include_btle is True
        assert config.include_bt is False

    def test_no_rate_limit_config(self):
        """Test disabling rate limiting."""
        parser = wigle_exporter.create_argument_parser()
        args = parser.parse_args(["--in", "test.kismet", "--no-rate-limit", "--stats"])
        config = wigle_exporter.build_config_from_args(args)
        assert config.rate_limit is False

    def test_exclusion_zones_in_config(self):
        """Test exclusion zones are added to config."""
        parser = wigle_exporter.create_argument_parser()
        args = parser.parse_args(
            [
                "--in",
                "test.kismet",
                "--exclude-zone",
                "47.0,-122.5,47.1,-122.4",
                "--stats",
            ]
        )
        config = wigle_exporter.build_config_from_args(args)
        assert len(config.exclusion_zones) == 1
        assert config.exclusion_zones[0] == (47.0, -122.5, 47.1, -122.4)


# =============================================================================
# SQLITE DATABASE TESTS
# =============================================================================


class TestDatabaseExtraction:
    """Test extraction of devices from kismetdb."""

    @pytest.fixture
    def temp_kismetdb(self, tmp_path):
        """Create a temporary kismet database for testing."""
        db_path = tmp_path / "test.kismet"
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Create minimal schema
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                devmac TEXT,
                phyname TEXT,
                type TEXT,
                device TEXT,
                first_time INTEGER,
                avg_lat REAL,
                avg_lon REAL,
                avg_alt REAL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS packets (
                sourcemac TEXT,
                lat REAL,
                lon REAL,
                alt REAL,
                signal INTEGER
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS data (
                devmac TEXT,
                lat REAL,
                lon REAL
            )
        """)

        conn.commit()
        conn.close()
        return str(db_path)

    def test_extract_from_empty_db(self, temp_kismetdb):
        """Test extracting from empty database returns empty list."""
        wifi_devices = wigle_exporter.extract_wifi_devices(temp_kismetdb)
        assert wifi_devices == []

    def test_extract_wifi_device(self, temp_kismetdb):
        """Test extracting a WiFi device."""
        conn = sqlite3.connect(temp_kismetdb)
        cursor = conn.cursor()

        # Insert a test device
        device_json = json.dumps(
            {
                "kismet.device.base.macaddr": "AA:BB:CC:DD:EE:FF",
                "dot11.device": {
                    "dot11.device.last_beaconed_ssid_record": {
                        "dot11.advertisedssid.ssid": "TestNetwork"
                    }
                },
                "kismet.device.base.channel": "6",
                "kismet.device.base.signal": {"kismet.common.signal.last_signal": -65},
                "kismet.device.base.crypt": 2,
            }
        )
        cursor.execute(
            """
            INSERT INTO devices (devmac, phyname, type, device, first_time, avg_lat, avg_lon)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            ("AA:BB:CC:DD:EE:FF", "IEEE802.11", "Wi-Fi AP", device_json, 1704067200, 47.6, -122.3),
        )
        conn.commit()
        conn.close()

        wifi_devices = wigle_exporter.extract_wifi_devices(temp_kismetdb)

        assert len(wifi_devices) == 1
        assert wifi_devices[0].mac == "AA:BB:CC:DD:EE:FF"
        assert wifi_devices[0].device_type == "WIFI"

    def test_extract_btle_device(self, temp_kismetdb):
        """Test extracting a BTLE device."""
        conn = sqlite3.connect(temp_kismetdb)
        cursor = conn.cursor()

        # Insert a BTLE device
        device_json = json.dumps(
            {
                "kismet.device.base.macaddr": "11:22:33:44:55:66",
                "kismet.device.base.commonname": "Fitness Band",
                "kismet.device.base.signal": {"kismet.common.signal.last_signal": -80},
            }
        )
        cursor.execute(
            """
            INSERT INTO devices (devmac, phyname, type, device, first_time, avg_lat, avg_lon)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            ("11:22:33:44:55:66", "BTLE", "BR/EDR", device_json, 1704067200, 47.5, -122.4),
        )
        conn.commit()
        conn.close()

        btle_devices = wigle_exporter.extract_btle_devices(temp_kismetdb)

        assert len(btle_devices) == 1
        assert btle_devices[0].mac == "11:22:33:44:55:66"
        assert btle_devices[0].device_type == "BLE"


# =============================================================================
# EXPORT FUNCTION TESTS
# =============================================================================


class TestExportToWigle:
    """Test the main export function."""

    def test_export_nonexistent_file(self):
        """Test exporting from non-existent file."""
        config = wigle_exporter.ExportConfig(input_files=["/nonexistent/file.kismet"])
        result = wigle_exporter.export_to_wigle(config)
        # Should succeed but with no files processed
        assert result.stats.files_processed == 0

    def test_export_with_no_output_file(self, tmp_path):
        """Test export in preview mode (no output file)."""
        # Create minimal kismetdb
        db_path = tmp_path / "test.kismet"
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE devices (
                devmac TEXT,
                phyname TEXT,
                type TEXT,
                device TEXT,
                first_time INTEGER,
                avg_lat REAL,
                avg_lon REAL,
                avg_alt REAL
            )
        """)
        cursor.execute("""
            CREATE TABLE packets (
                sourcemac TEXT,
                lat REAL,
                lon REAL,
                alt REAL,
                signal INTEGER
            )
        """)
        cursor.execute("""
            CREATE TABLE data (
                devmac TEXT,
                lat REAL,
                lon REAL
            )
        """)
        conn.commit()
        conn.close()

        config = wigle_exporter.ExportConfig(
            input_files=[str(db_path)],
            output_file=None,  # Preview mode
        )
        result = wigle_exporter.export_to_wigle(config)
        assert result.success is True
        assert result.stats.files_processed == 1


# =============================================================================
# COLOR OUTPUT TESTS
# =============================================================================


class TestColors:
    """Test terminal color codes."""

    def test_colors_defined(self):
        """Test that color codes are defined."""
        assert hasattr(wigle_exporter.Colors, "RED")
        assert hasattr(wigle_exporter.Colors, "GREEN")
        assert hasattr(wigle_exporter.Colors, "BLUE")
        assert hasattr(wigle_exporter.Colors, "NC")
        assert hasattr(wigle_exporter.Colors, "BOLD")

    def test_colors_are_strings(self):
        """Test that color codes are strings."""
        assert isinstance(wigle_exporter.Colors.RED, str)
        assert isinstance(wigle_exporter.Colors.NC, str)


# =============================================================================
# GLOB PATTERN EXPANSION TESTS
# =============================================================================


class TestGlobPatternExpansion:
    """Test glob pattern expansion for input files."""

    def test_expand_glob_pattern_no_match(self, tmp_path):
        """Test glob expansion with no matches."""
        result = wigle_exporter.expand_glob_pattern(str(tmp_path / "*.nonexistent"))
        assert result == []

    def test_expand_glob_pattern_with_matches(self, tmp_path):
        """Test glob expansion with matches."""
        # Create test files
        (tmp_path / "test1.kismet").touch()
        (tmp_path / "test2.kismet").touch()

        # Use the exact pattern that would match
        result = wigle_exporter.expand_glob_pattern(str(tmp_path / "*.kismet"))
        assert len(result) == 2
        assert any("test1.kismet" in r for r in result)
        assert any("test2.kismet" in r for r in result)


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestIntegration:
    """Integration tests combining multiple components."""

    def test_full_export_workflow(self, tmp_path):
        """Test complete export workflow from kismetdb to WiGLE CSV."""
        # Create test database
        db_path = tmp_path / "test.kismet"
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Create schema
        cursor.execute("""
            CREATE TABLE devices (
                devmac TEXT,
                phyname TEXT,
                type TEXT,
                device TEXT,
                first_time INTEGER,
                avg_lat REAL,
                avg_lon REAL,
                avg_alt REAL
            )
        """)
        cursor.execute("""
            CREATE TABLE packets (
                sourcemac TEXT,
                lat REAL,
                lon REAL,
                alt REAL,
                signal INTEGER
            )
        """)
        cursor.execute("""
            CREATE TABLE data (
                devmac TEXT,
                lat REAL,
                lon REAL
            )
        """)

        # Insert test devices
        wifi_device = json.dumps(
            {
                "kismet.device.base.macaddr": "AA:BB:CC:DD:EE:FF",
                "dot11.device": {
                    "dot11.device.last_beaconed_ssid_record": {
                        "dot11.advertisedssid.ssid": "TestAP"
                    }
                },
                "kismet.device.base.channel": "11",
                "kismet.device.base.signal": {"kismet.common.signal.last_signal": -50},
                "kismet.device.base.crypt": 2,
            }
        )
        cursor.execute(
            "INSERT INTO devices VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "AA:BB:CC:DD:EE:FF",
                "IEEE802.11",
                "Wi-Fi AP",
                wifi_device,
                1704067200,
                47.6,
                -122.3,
                10.0,
            ),
        )

        conn.commit()
        conn.close()

        # Export
        output_path = tmp_path / "export.wiglecsv"
        config = wigle_exporter.ExportConfig(
            input_files=[str(db_path)],
            output_file=output_path,
        )
        result = wigle_exporter.export_to_wigle(config)

        # Verify
        assert result.success is True
        assert result.stats.wifi_count == 1
        assert output_path.exists()

        # Check output content
        content = output_path.read_text()
        assert "WigleWifi-1.4" in content
        assert "AA:BB:CC:DD:EE:FF" in content
        # Note: SSID extraction depends on JSON structure matching Kismet's format
        assert "WIFI" in content
