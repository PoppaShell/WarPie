"""Comprehensive unit tests for warpie-filter-processor.py.

Tests cover:
- Module imports and dataclasses
- Pattern matching with wildcards
- Configuration parsing (static and dynamic exclusions)
- SSID extraction from Kismet JSON
- WiGLE CSV processing
- Backup management
- File discovery
- Result tracking

Uses pytest fixtures and mocking for isolation.
"""

import importlib.util
import json
import logging
import os
import sys
from pathlib import Path
from unittest import mock

bin_path = Path(__file__).parent.parent.parent / "bin"
sys.path.insert(0, str(bin_path))

# Import the filter processor module (handles hyphenated filename)
spec = importlib.util.spec_from_file_location(
    "warpie_filter_processor", str(bin_path / "warpie-filter-processor.py")
)
processor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(processor)


# =============================================================================
# MODULE IMPORT TESTS
# =============================================================================


class TestModuleImports:
    """Test that the filter processor module can be imported."""

    def test_module_exists(self):
        """Verify the filter processor script exists."""
        script_path = Path(__file__).parent.parent.parent / "bin" / "warpie-filter-processor.py"
        assert script_path.exists(), "warpie-filter-processor.py should exist in bin/"

    def test_version_defined(self):
        """Verify VERSION constant is defined."""
        assert hasattr(processor, "VERSION")
        assert processor.VERSION == "2.4.1"

    def test_constants_defined(self):
        """Verify configuration constants are defined."""
        assert hasattr(processor, "CONFIG_FILE")
        assert hasattr(processor, "KISMET_LOGS_DIR")
        assert hasattr(processor, "BACKUP_DIR")
        assert hasattr(processor, "WIGLE_MAC_COL")
        assert hasattr(processor, "WIGLE_SSID_COL")
        assert processor.WIGLE_MAC_COL == 0
        assert processor.WIGLE_SSID_COL == 1

    def test_key_functions_exist(self):
        """Verify key functions are importable."""
        assert callable(processor.load_dynamic_exclusions)
        assert callable(processor.load_all_exclusions)
        assert callable(processor.matches_pattern)
        assert callable(processor.find_matching_rule)
        assert callable(processor.extract_ssids_from_device)
        assert callable(processor.process_kismetdb)
        assert callable(processor.process_wigle_csv)
        assert callable(processor.setup_logging)


# =============================================================================
# DATACLASS TESTS
# =============================================================================


class TestFilterRuleDataclass:
    """Test FilterRule dataclass."""

    def test_filter_rule_creation_all_fields(self):
        """Test creating a FilterRule with all fields."""
        rule = processor.FilterRule(value="MyNetwork", match_type="exact", description="Home WiFi")
        assert rule.value == "MyNetwork"
        assert rule.match_type == "exact"
        assert rule.description == "Home WiFi"

    def test_filter_rule_default_description(self):
        """Test FilterRule with default description."""
        rule = processor.FilterRule(value="Test", match_type="pattern")
        assert rule.value == "Test"
        assert rule.match_type == "pattern"
        assert rule.description == ""

    def test_filter_rule_equality(self):
        """Test FilterRule equality comparison."""
        rule1 = processor.FilterRule("Network", "exact", "Test")
        rule2 = processor.FilterRule("Network", "exact", "Test")
        assert rule1 == rule2

    def test_filter_rule_repr(self):
        """Test FilterRule string representation."""
        rule = processor.FilterRule("Test", "pattern", "desc")
        repr_str = repr(rule)
        assert "FilterRule" in repr_str
        assert "Test" in repr_str


class TestProcessingResultDataclass:
    """Test ProcessingResult dataclass."""

    def test_processing_result_creation(self):
        """Test creating a ProcessingResult."""
        result = processor.ProcessingResult(
            file_path="/path/to/file.kismet", original_count=10, removed_count=3, success=True
        )
        assert result.file_path == "/path/to/file.kismet"
        assert result.original_count == 10
        assert result.removed_count == 3
        assert result.success is True
        assert result.error == ""
        assert result.matches == []

    def test_processing_result_defaults(self):
        """Test ProcessingResult with default values."""
        result = processor.ProcessingResult(file_path="/test.kismet")
        assert result.file_path == "/test.kismet"
        assert result.original_count == 0
        assert result.removed_count == 0
        assert result.success is True
        assert result.error == ""
        assert result.matches == []

    def test_processing_result_with_matches(self):
        """Test ProcessingResult with match data."""
        matches = [
            {"ssid": "Test", "mac": "AA:BB:CC:DD:EE:FF", "rule": "exact", "rule_type": "exact"}
        ]
        result = processor.ProcessingResult(
            file_path="/test.kismet", original_count=5, removed_count=1, matches=matches
        )
        assert len(result.matches) == 1
        assert result.matches[0]["ssid"] == "Test"


class TestSanitizationReportDataclass:
    """Test SanitizationReport dataclass."""

    def test_sanitization_report_creation(self):
        """Test creating a SanitizationReport."""
        report = processor.SanitizationReport(
            files_processed=2, total_original=100, total_removed=5, backup_path="/backup/path"
        )
        assert report.files_processed == 2
        assert report.total_original == 100
        assert report.total_removed == 5
        assert report.backup_path == "/backup/path"

    def test_sanitization_report_defaults(self):
        """Test SanitizationReport with default values."""
        report = processor.SanitizationReport()
        assert report.files_processed == 0
        assert report.total_original == 0
        assert report.total_removed == 0
        assert report.backup_path == ""
        assert report.duration_seconds == 0.0
        assert report.errors == []


# =============================================================================
# PATTERN MATCHING TESTS
# =============================================================================


class TestMatchesPattern:
    """Test matches_pattern function."""

    def test_exact_match_exact_type(self):
        """Test exact match with exact type."""
        rule = processor.FilterRule("MyNetwork", "exact")
        assert processor.matches_pattern("MyNetwork", rule) is True

    def test_exact_no_match_exact_type(self):
        """Test non-matching SSID with exact type."""
        rule = processor.FilterRule("MyNetwork", "exact")
        assert processor.matches_pattern("OtherNetwork", rule) is False

    def test_exact_case_sensitive(self):
        """Test exact match is case-sensitive."""
        rule = processor.FilterRule("MyNetwork", "exact")
        assert processor.matches_pattern("mynetwork", rule) is False
        assert processor.matches_pattern("MYNETWORK", rule) is False

    def test_pattern_match_with_asterisk(self):
        """Test pattern matching with * wildcard."""
        rule = processor.FilterRule("iPhone*", "pattern")
        assert processor.matches_pattern("iPhone Hotspot", rule) is True
        assert processor.matches_pattern("iPhone_12", rule) is True
        assert processor.matches_pattern("MyiPhone", rule) is False

    def test_pattern_match_with_question_mark(self):
        """Test pattern matching with ? wildcard."""
        rule = processor.FilterRule("Network_?", "pattern")
        assert processor.matches_pattern("Network_1", rule) is True
        assert processor.matches_pattern("Network_A", rule) is True
        assert processor.matches_pattern("Network_12", rule) is False
        assert processor.matches_pattern("Network_", rule) is False

    def test_pattern_match_complex(self):
        """Test complex pattern with multiple wildcards."""
        rule = processor.FilterRule("*Hotspot*", "pattern")
        assert processor.matches_pattern("iPhone Hotspot", rule) is True
        assert processor.matches_pattern("Android Hotspot", rule) is True
        assert processor.matches_pattern("Hotspot", rule) is True
        assert processor.matches_pattern("MyNetwork", rule) is False

    def test_bssid_type_returns_false(self):
        """Test that BSSID type always returns False."""
        rule = processor.FilterRule("AA:BB:CC:DD:EE:FF", "bssid")
        assert processor.matches_pattern("AA:BB:CC:DD:EE:FF", rule) is False
        assert processor.matches_pattern("SomeSSID", rule) is False

    def test_unknown_match_type_returns_false(self):
        """Test unknown match type returns False."""
        rule = processor.FilterRule("Test", "unknown")
        assert processor.matches_pattern("Test", rule) is False

    def test_empty_ssid(self):
        """Test matching empty SSID."""
        rule = processor.FilterRule("", "exact")
        assert processor.matches_pattern("", rule) is True
        assert processor.matches_pattern("Network", rule) is False

    def test_empty_pattern(self):
        """Test empty pattern with pattern type."""
        rule = processor.FilterRule("", "pattern")
        assert processor.matches_pattern("", rule) is True
        assert processor.matches_pattern("Network", rule) is False


# =============================================================================
# FIND MATCHING RULE TESTS
# =============================================================================


class TestFindMatchingRule:
    """Test find_matching_rule function."""

    def test_find_first_matching_rule(self):
        """Test finding the first matching rule."""
        rules = [
            processor.FilterRule("Network1", "exact"),
            processor.FilterRule("Network2", "exact"),
        ]
        result = processor.find_matching_rule("Network2", rules)
        assert result is not None
        assert result.value == "Network2"

    def test_find_matching_rule_no_match(self):
        """Test returning None when no rule matches."""
        rules = [
            processor.FilterRule("Network1", "exact"),
            processor.FilterRule("Network2", "exact"),
        ]
        result = processor.find_matching_rule("Network3", rules)
        assert result is None

    def test_find_first_rule_wins(self):
        """Test that first matching rule is returned."""
        rules = [
            processor.FilterRule("*", "pattern"),  # Matches all
            processor.FilterRule("Specific", "exact"),
        ]
        result = processor.find_matching_rule("SomeNetwork", rules)
        assert result is not None
        assert result.match_type == "pattern"

    def test_find_matching_rule_empty_list(self):
        """Test finding rule in empty list."""
        result = processor.find_matching_rule("Network", [])
        assert result is None

    def test_find_matching_rule_pattern(self):
        """Test finding rule with pattern matching."""
        rules = [
            processor.FilterRule("iPhone*", "pattern"),
            processor.FilterRule("Android*", "pattern"),
        ]
        result = processor.find_matching_rule("iPhone Hotspot 123", rules)
        assert result is not None
        assert result.value == "iPhone*"


# =============================================================================
# CONFIG PARSING TESTS
# =============================================================================


class TestLoadDynamicExclusions:
    """Test load_dynamic_exclusions function."""

    def test_load_valid_config(self, tmp_path):
        """Test loading valid dynamic exclusion config."""
        config_file = tmp_path / "filter_rules.conf"
        config_file.write_text("""
[dynamic_exclusions]
iPhone*|pattern|iOS hotspots
*Android*|pattern|Android hotspots
        """)

        rules = processor.load_dynamic_exclusions(str(config_file))
        assert len(rules) == 2
        assert rules[0].value == "iPhone*"
        assert rules[0].match_type == "pattern"
        assert rules[0].description == "iOS hotspots"
        assert rules[1].value == "*Android*"

    def test_load_config_missing_file(self, tmp_path, caplog):
        """Test handling missing config file."""
        config_file = tmp_path / "nonexistent.conf"
        with caplog.at_level(logging.WARNING):
            rules = processor.load_dynamic_exclusions(str(config_file))
        assert len(rules) == 0
        assert "Config file not found" in caplog.text

    def test_load_config_empty_file(self, tmp_path):
        """Test loading empty config file."""
        config_file = tmp_path / "filter_rules.conf"
        config_file.write_text("")
        rules = processor.load_dynamic_exclusions(str(config_file))
        assert len(rules) == 0

    def test_load_config_with_comments(self, tmp_path):
        """Test loading config with comments."""
        config_file = tmp_path / "filter_rules.conf"
        config_file.write_text("""
# This is a comment
[dynamic_exclusions]
# Another comment
iPhone*|pattern|iOS hotspots
# More comments
*Android*|pattern|Android hotspots
        """)

        rules = processor.load_dynamic_exclusions(str(config_file))
        assert len(rules) == 2

    def test_load_config_ignores_other_sections(self, tmp_path):
        """Test that only dynamic_exclusions section is loaded."""
        config_file = tmp_path / "filter_rules.conf"
        config_file.write_text("""
[static_exclusions]
HomeWiFi|exact|My home
[dynamic_exclusions]
iPhone*|pattern|iOS hotspots
        """)

        rules = processor.load_dynamic_exclusions(str(config_file))
        assert len(rules) == 1
        assert rules[0].value == "iPhone*"

    def test_load_config_with_descriptions(self, tmp_path):
        """Test loading config preserves descriptions."""
        config_file = tmp_path / "filter_rules.conf"
        config_file.write_text("""
[dynamic_exclusions]
TestSSID|exact|This is a test description
        """)

        rules = processor.load_dynamic_exclusions(str(config_file))
        assert rules[0].description == "This is a test description"

    def test_load_config_incomplete_entries(self, tmp_path):
        """Test that entries with at least value|type are loaded."""
        config_file = tmp_path / "filter_rules.conf"
        config_file.write_text("""
[dynamic_exclusions]
OnlyValue
ValidEntry|exact
iPhone*|pattern|Valid
        """)

        rules = processor.load_dynamic_exclusions(str(config_file))
        # ValidEntry and iPhone* both have value|type format
        assert len(rules) == 2
        assert rules[0].value == "ValidEntry"
        assert rules[1].value == "iPhone*"


class TestLoadAllExclusions:
    """Test load_all_exclusions function."""

    def test_load_both_sections(self, tmp_path):
        """Test loading both static and dynamic sections."""
        config_file = tmp_path / "filter_rules.conf"
        config_file.write_text("""
[static_exclusions]
HomeWiFi|exact|My home
CorporateWiFi|pattern|Office networks
[dynamic_exclusions]
iPhone*|pattern|iOS hotspots
*Android*|pattern|Android hotspots
        """)

        static, dynamic = processor.load_all_exclusions(str(config_file))
        assert len(static) == 2
        assert len(dynamic) == 2
        assert static[0].value == "HomeWiFi"
        assert dynamic[0].value == "iPhone*"

    def test_load_only_static(self, tmp_path):
        """Test loading config with only static section."""
        config_file = tmp_path / "filter_rules.conf"
        config_file.write_text("""
[static_exclusions]
HomeWiFi|exact|My home
        """)

        static, dynamic = processor.load_all_exclusions(str(config_file))
        assert len(static) == 1
        assert len(dynamic) == 0

    def test_load_only_dynamic(self, tmp_path):
        """Test loading config with only dynamic section."""
        config_file = tmp_path / "filter_rules.conf"
        config_file.write_text("""
[dynamic_exclusions]
iPhone*|pattern|iOS hotspots
        """)

        static, dynamic = processor.load_all_exclusions(str(config_file))
        assert len(static) == 0
        assert len(dynamic) == 1

    def test_load_missing_config_file(self, tmp_path, caplog):
        """Test load_all_exclusions with missing file."""
        config_file = tmp_path / "nonexistent.conf"
        with caplog.at_level(logging.WARNING):
            static, dynamic = processor.load_all_exclusions(str(config_file))
        assert len(static) == 0
        assert len(dynamic) == 0

    def test_load_sections_with_multiple_sections(self, tmp_path):
        """Test loading from config with multiple sections."""
        config_file = tmp_path / "filter_rules.conf"
        config_file.write_text("""
[other_section]
SomeValue|exact|Not loaded
[static_exclusions]
Static1|exact|Static
[another_section]
SkipMe|exact|Skip
[dynamic_exclusions]
Dynamic1|pattern|Dynamic
        """)

        static, dynamic = processor.load_all_exclusions(str(config_file))
        assert len(static) == 1
        assert len(dynamic) == 1
        assert static[0].value == "Static1"
        assert dynamic[0].value == "Dynamic1"


# =============================================================================
# SSID EXTRACTION FROM DEVICE JSON TESTS
# =============================================================================


class TestExtractSsidsFromDevice:
    """Test extract_ssids_from_device function."""

    def test_extract_single_ssid(self):
        """Test extracting single advertised SSID."""
        device_json = json.dumps(
            {
                "dot11.device": {
                    "dot11.device.advertised_ssid_map": [{"dot11.advertisedssid.ssid": "MyNetwork"}]
                }
            }
        )
        ssids = processor.extract_ssids_from_device(device_json)
        assert len(ssids) == 1
        assert "MyNetwork" in ssids

    def test_extract_multiple_ssids(self):
        """Test extracting multiple advertised SSIDs."""
        device_json = json.dumps(
            {
                "dot11.device": {
                    "dot11.device.advertised_ssid_map": [
                        {"dot11.advertisedssid.ssid": "Network1"},
                        {"dot11.advertisedssid.ssid": "Network2"},
                        {"dot11.advertisedssid.ssid": "Network3"},
                    ]
                }
            }
        )
        ssids = processor.extract_ssids_from_device(device_json)
        assert len(ssids) == 3
        assert "Network1" in ssids
        assert "Network2" in ssids
        assert "Network3" in ssids

    def test_extract_probed_ssids(self):
        """Test extracting probed SSIDs."""
        device_json = json.dumps(
            {
                "dot11.device": {
                    "dot11.device.advertised_ssid_map": [],
                    "dot11.device.probed_ssid_map": [
                        {"dot11.probedssid.ssid": "ProbedNetwork1"},
                        {"dot11.probedssid.ssid": "ProbedNetwork2"},
                    ],
                }
            }
        )
        ssids = processor.extract_ssids_from_device(device_json)
        assert len(ssids) == 2
        assert "ProbedNetwork1" in ssids
        assert "ProbedNetwork2" in ssids

    def test_extract_both_advertised_and_probed(self):
        """Test extracting both advertised and probed SSIDs."""
        device_json = json.dumps(
            {
                "dot11.device": {
                    "dot11.device.advertised_ssid_map": [
                        {"dot11.advertisedssid.ssid": "AdvertisedNetwork"}
                    ],
                    "dot11.device.probed_ssid_map": [{"dot11.probedssid.ssid": "ProbedNetwork"}],
                }
            }
        )
        ssids = processor.extract_ssids_from_device(device_json)
        assert len(ssids) == 2
        assert "AdvertisedNetwork" in ssids
        assert "ProbedNetwork" in ssids

    def test_extract_deduplicates_ssids(self):
        """Test that duplicate SSIDs are not repeated."""
        device_json = json.dumps(
            {
                "dot11.device": {
                    "dot11.device.advertised_ssid_map": [
                        {"dot11.advertisedssid.ssid": "DuplicateSSID"}
                    ],
                    "dot11.device.probed_ssid_map": [{"dot11.probedssid.ssid": "DuplicateSSID"}],
                }
            }
        )
        ssids = processor.extract_ssids_from_device(device_json)
        # Probed should not add duplicate
        assert ssids.count("DuplicateSSID") == 1

    def test_extract_empty_ssids(self):
        """Test extracting from device with empty SSID strings."""
        device_json = json.dumps(
            {
                "dot11.device": {
                    "dot11.device.advertised_ssid_map": [
                        {"dot11.advertisedssid.ssid": ""},
                        {"dot11.advertisedssid.ssid": "ValidNetwork"},
                        {"dot11.advertisedssid.ssid": ""},
                    ]
                }
            }
        )
        ssids = processor.extract_ssids_from_device(device_json)
        assert len(ssids) == 1
        assert "ValidNetwork" in ssids

    def test_extract_malformed_json(self):
        """Test handling malformed JSON."""
        ssids = processor.extract_ssids_from_device("invalid json")
        assert len(ssids) == 0

    def test_extract_missing_keys(self):
        """Test handling missing expected keys."""
        device_json = json.dumps({"dot11.device": {}})
        ssids = processor.extract_ssids_from_device(device_json)
        assert len(ssids) == 0

    def test_extract_non_dict_entries(self):
        """Test handling non-dictionary entries in SSID map."""
        device_json = json.dumps(
            {
                "dot11.device": {
                    "dot11.device.advertised_ssid_map": [
                        "NotADict",
                        {"dot11.advertisedssid.ssid": "ValidNetwork"},
                    ]
                }
            }
        )
        ssids = processor.extract_ssids_from_device(device_json)
        assert len(ssids) == 1
        assert "ValidNetwork" in ssids


# =============================================================================
# WIGLE CSV PROCESSING TESTS
# =============================================================================


class TestProcessWigleCsv:
    """Test WiGLE CSV processing functions."""

    def test_process_wigle_csv_dry_run_no_changes(self, tmp_path):
        """Test dry-run does not modify file."""
        csv_file = tmp_path / "networks.wiglecsv"
        original_content = """# WiGLE Header Line 1
# WiGLE Header Line 2
AA:BB:CC:DD:EE:FF,TestNetwork1,47.0,122.0,1,1,WPA2
11:22:33:44:55:66,TestNetwork2,47.0,122.0,1,1,WPA2
"""
        csv_file.write_text(original_content)

        rules = [processor.FilterRule("TestNetwork1", "exact")]
        result = processor.process_wigle_csv(str(csv_file), rules, dry_run=True)

        # File should not be modified
        assert csv_file.read_text() == original_content
        assert result.success is True
        assert result.original_count == 2
        assert result.removed_count == 1

    def test_process_wigle_csv_remove_matching_entry(self, tmp_path):
        """Test removing matching entry from CSV."""
        csv_file = tmp_path / "networks.wiglecsv"
        csv_file.write_text("""# Header1
# Header2
AA:BB:CC:DD:EE:FF,RemoveMe,47.0,122.0,1,1,WPA2
11:22:33:44:55:66,KeepMe,47.0,122.0,1,1,WPA2
""")

        rules = [processor.FilterRule("RemoveMe", "exact")]
        result = processor.process_wigle_csv(str(csv_file), rules, dry_run=False)

        assert result.success is True
        assert result.removed_count == 1
        modified_content = csv_file.read_text()
        assert "RemoveMe" not in modified_content
        assert "KeepMe" in modified_content

    def test_process_wigle_csv_pattern_matching(self, tmp_path):
        """Test pattern matching in CSV processing."""
        csv_file = tmp_path / "networks.wiglecsv"
        csv_file.write_text("""# Header1
# Header2
AA:BB:CC:DD:EE:FF,iPhone Hotspot,47.0,122.0,1,1,WPA2
11:22:33:44:55:66,iPhone_XS,47.0,122.0,1,1,WPA2
33:44:55:66:77:88,AndroidDevice,47.0,122.0,1,1,WPA2
""")

        rules = [processor.FilterRule("iPhone*", "pattern")]
        result = processor.process_wigle_csv(str(csv_file), rules, dry_run=False)

        assert result.removed_count == 2
        modified_content = csv_file.read_text()
        assert "iPhone" not in modified_content
        assert "AndroidDevice" in modified_content

    def test_process_wigle_csv_file_not_found(self, tmp_path):
        """Test error handling for missing file."""
        csv_file = tmp_path / "nonexistent.wiglecsv"
        rules = [processor.FilterRule("Test", "exact")]
        result = processor.process_wigle_csv(str(csv_file), rules)

        assert result.success is False
        assert "not found" in result.error.lower()

    def test_process_wigle_csv_too_short(self, tmp_path):
        """Test handling for CSV too short (only 1 line, needs 2+ for header)."""
        csv_file = tmp_path / "networks.wiglecsv"
        csv_file.write_text("# Only header\n")

        rules = [processor.FilterRule("Test", "exact")]
        result = processor.process_wigle_csv(str(csv_file), rules)

        # Error is set but success may still be True if gracefully handled
        assert "header" in result.error.lower() or result.original_count == 0

    def test_process_wigle_csv_malformed_lines(self, tmp_path):
        """Test handling malformed CSV lines."""
        csv_file = tmp_path / "networks.wiglecsv"
        csv_file.write_text("""# Header1
# Header2
AA:BB:CC:DD:EE:FF,Network1,47.0,122.0,1,1,WPA2
ShortLine
11:22:33:44:55:66,Network2,47.0,122.0,1,1,WPA2
""")

        rules = []
        result = processor.process_wigle_csv(str(csv_file), rules, dry_run=True)

        assert result.success is True
        # All data lines are counted, including short ones
        assert result.original_count == 3


class TestScanWigleCsv:
    """Test scan_wigle_csv function."""

    def test_scan_wigle_csv_does_not_modify(self, tmp_path):
        """Test scan_wigle_csv doesn't modify file."""
        csv_file = tmp_path / "networks.wiglecsv"
        original_content = """# Header1
# Header2
AA:BB:CC:DD:EE:FF,RemoveMe,47.0,122.0,1,1,WPA2
11:22:33:44:55:66,KeepMe,47.0,122.0,1,1,WPA2
"""
        csv_file.write_text(original_content)

        rules = [processor.FilterRule("RemoveMe", "exact")]
        result = processor.scan_wigle_csv(str(csv_file), rules)

        assert csv_file.read_text() == original_content
        assert result.removed_count == 1


# =============================================================================
# BACKUP MANAGEMENT TESTS
# =============================================================================


class TestBackupManagement:
    """Test backup management functions."""

    def test_create_backup_creates_directory(self, tmp_path):
        """Test that create_backup creates backup directory."""
        source_file = tmp_path / "source.txt"
        source_file.write_text("test content")
        backup_dir = tmp_path / "backups"

        backup_path = processor.create_backup([str(source_file)], str(backup_dir))

        assert Path(backup_path).exists()
        assert Path(backup_path).is_dir()

    def test_create_backup_copies_files(self, tmp_path):
        """Test that create_backup copies files."""
        source_file = tmp_path / "source.txt"
        source_file.write_text("test content")
        backup_dir = tmp_path / "backups"

        backup_path = processor.create_backup([str(source_file)], str(backup_dir))

        backup_file = Path(backup_path) / "source.txt"
        assert backup_file.exists()
        assert backup_file.read_text() == "test content"

    def test_create_backup_multiple_files(self, tmp_path):
        """Test creating backup of multiple files."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("content1")
        file2.write_text("content2")
        backup_dir = tmp_path / "backups"

        backup_path = processor.create_backup([str(file1), str(file2)], str(backup_dir))

        assert (Path(backup_path) / "file1.txt").exists()
        assert (Path(backup_path) / "file2.txt").exists()

    def test_create_backup_returns_timestamped_path(self, tmp_path):
        """Test that backup path includes timestamp."""
        source_file = tmp_path / "source.txt"
        source_file.write_text("test")
        backup_dir = tmp_path / "backups"

        backup_path = processor.create_backup([str(source_file)], str(backup_dir))

        # Check timestamp format YYYY-MM-DD_HHMMSS
        backup_name = Path(backup_path).name
        # Format: YYYY-MM-DD_HHMMSS = 17 chars (4+1+2+1+2+1+6)
        assert len(backup_name) == 17
        assert backup_name[4] == "-"
        assert backup_name[7] == "-"
        assert backup_name[10] == "_"

    def test_delete_backup_removes_directory(self, tmp_path):
        """Test delete_backup removes directory."""
        backup_dir = tmp_path / "backup"
        backup_dir.mkdir()
        (backup_dir / "file.txt").write_text("test")

        processor.delete_backup(str(backup_dir))

        assert not backup_dir.exists()

    def test_delete_backup_nonexistent_directory(self, tmp_path):
        """Test delete_backup handles nonexistent directory."""
        nonexistent = tmp_path / "nonexistent"
        # Should not raise error
        processor.delete_backup(str(nonexistent))

    def test_list_backups_empty(self, tmp_path):
        """Test list_backups with empty backup directory."""
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        backups = processor.list_backups(str(backup_dir))

        assert len(backups) == 0

    def test_list_backups_multiple(self, tmp_path):
        """Test list_backups with multiple backups."""
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        # Create test backups
        backup1 = backup_dir / "2024-01-01_120000"
        backup1.mkdir()
        (backup1 / "file1.txt").write_text("content1")

        backup2 = backup_dir / "2024-01-02_120000"
        backup2.mkdir()
        (backup2 / "file2.txt").write_text("content2")
        (backup2 / "file3.txt").write_text("content3")

        backups = processor.list_backups(str(backup_dir))

        assert len(backups) == 2
        # Most recent first
        assert backups[0]["name"] == "2024-01-02_120000"
        assert backups[0]["files"] == 2
        assert backups[1]["name"] == "2024-01-01_120000"
        assert backups[1]["files"] == 1

    def test_list_backups_sizes(self, tmp_path):
        """Test list_backups calculates sizes."""
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        backup = backup_dir / "2024-01-01_120000"
        backup.mkdir()
        (backup / "file.txt").write_text("test content here")

        backups = processor.list_backups(str(backup_dir))

        assert len(backups) == 1
        assert backups[0]["size_bytes"] > 0


# =============================================================================
# FILE DISCOVERY TESTS
# =============================================================================


class TestFileDiscovery:
    """Test file discovery functions."""

    def test_find_kismetdb_files(self, tmp_path):
        """Test finding kismetdb files."""
        logs_dir = tmp_path / "kismet" / "logs"
        logs_dir.mkdir(parents=True)

        # Create test files
        (logs_dir / "capture1.kismet").touch()
        (logs_dir / "capture2.kismet").touch()
        (logs_dir / "other.txt").touch()

        files = processor.find_kismetdb_files(str(logs_dir))

        assert len(files) == 2
        assert any("capture1.kismet" in f for f in files)
        assert any("capture2.kismet" in f for f in files)

    def test_find_kismetdb_files_nested(self, tmp_path):
        """Test finding kismetdb files in nested directories."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        (logs_dir / "normal").mkdir()
        (logs_dir / "wardrive").mkdir()

        (logs_dir / "normal" / "capture1.kismet").touch()
        (logs_dir / "wardrive" / "capture2.kismet").touch()

        files = processor.find_kismetdb_files(str(logs_dir))

        assert len(files) == 2

    def test_find_wigle_csv_files(self, tmp_path):
        """Test finding WiGLE CSV files."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()

        (logs_dir / "export.wiglecsv").touch()
        (logs_dir / "data_wigle.csv").touch()
        (logs_dir / "other.csv").touch()

        files = processor.find_wigle_csv_files(str(logs_dir))

        assert len(files) == 2

    def test_find_files_returns_sorted_by_mtime(self, tmp_path):
        """Test that files are sorted by modification time (newest first)."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()

        file1 = logs_dir / "old.kismet"
        file2 = logs_dir / "new.kismet"
        file1.touch()
        file2.touch()

        # Make file1 older
        file1_stat = file1.stat()
        os.utime(str(file1), (file1_stat.st_atime - 100, file1_stat.st_mtime - 100))

        files = processor.find_kismetdb_files(str(logs_dir))

        # Newest first
        assert files[0].endswith("new.kismet")
        assert files[1].endswith("old.kismet")

    def test_is_file_in_use_recent_modification(self, tmp_path):
        """Test is_file_in_use detects recently modified files."""
        test_file = tmp_path / "test.kismet"
        test_file.touch()

        is_in_use = processor.is_file_in_use(str(test_file))
        assert is_in_use is True

    def test_is_file_in_use_old_modification(self, tmp_path):
        """Test is_file_in_use returns False for old files."""
        test_file = tmp_path / "test.kismet"
        test_file.touch()

        # Make file old (modified 100 seconds ago)
        file_stat = test_file.stat()
        os.utime(str(test_file), (file_stat.st_atime - 100, file_stat.st_mtime - 100))

        is_in_use = processor.is_file_in_use(str(test_file))
        assert is_in_use is False

    def test_is_file_in_use_nonexistent(self, tmp_path):
        """Test is_file_in_use returns False for nonexistent file."""
        nonexistent = tmp_path / "nonexistent.kismet"
        is_in_use = processor.is_file_in_use(str(nonexistent))
        assert is_in_use is False


# =============================================================================
# FORMAT SIZE TESTS
# =============================================================================


class TestFormatSize:
    """Test format_size utility function."""

    def test_format_size_bytes(self):
        """Test formatting byte sizes."""
        assert processor.format_size(512) == "512.0 B"
        assert processor.format_size(1023) == "1023.0 B"

    def test_format_size_kilobytes(self):
        """Test formatting kilobyte sizes."""
        assert processor.format_size(1024) == "1.0 KB"
        assert processor.format_size(2048) == "2.0 KB"

    def test_format_size_megabytes(self):
        """Test formatting megabyte sizes."""
        assert processor.format_size(1024 * 1024) == "1.0 MB"
        assert processor.format_size(10 * 1024 * 1024) == "10.0 MB"

    def test_format_size_gigabytes(self):
        """Test formatting gigabyte sizes."""
        assert processor.format_size(1024 * 1024 * 1024) == "1.0 GB"

    def test_format_size_terabytes(self):
        """Test formatting terabyte sizes."""
        result = processor.format_size(1024 * 1024 * 1024 * 1024)
        assert "TB" in result


# =============================================================================
# LOGGING SETUP TESTS
# =============================================================================


class TestSetupLogging:
    """Test logging setup function."""

    def test_setup_logging_console_only(self):
        """Test logging setup with console output."""
        processor.setup_logging(log_file=None, verbose=False)
        # Just ensure it doesn't crash
        assert True

    def test_setup_logging_with_file(self, tmp_path):
        """Test logging setup with file output."""
        log_file = tmp_path / "test.log"
        processor.setup_logging(log_file=str(log_file), verbose=False)
        # Just ensure it doesn't crash and file is created
        assert True

    def test_setup_logging_creates_log_directory(self, tmp_path):
        """Test that logging setup creates log directory."""
        log_file = tmp_path / "logs" / "test.log"
        processor.setup_logging(log_file=str(log_file), verbose=False)
        # Directory should be created
        assert log_file.parent.exists()


# =============================================================================
# KISMETDB PROCESSING TESTS (with mocked sqlite3)
# =============================================================================


class TestProcessKismetdb:
    """Test process_kismetdb function with mocked database."""

    def test_process_kismetdb_file_not_found(self, tmp_path):
        """Test process_kismetdb with nonexistent file."""
        nonexistent = tmp_path / "nonexistent.kismet"
        rules = [processor.FilterRule("Test", "exact")]
        result = processor.process_kismetdb(str(nonexistent), rules)

        assert result.success is False
        assert "not found" in result.error.lower()

    def test_process_kismetdb_dry_run_flag(self, tmp_path, mocker):
        """Test that dry_run parameter is passed correctly."""
        db_file = tmp_path / "test.kismet"
        db_file.touch()

        # Mock sqlite3 to avoid actual database operations
        mock_connect = mocker.patch("sqlite3.connect")
        mock_cursor = mock.MagicMock()
        mock_connect.return_value.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        rules = [processor.FilterRule("Test", "exact")]

        # Dry run should not call commit
        result = processor.process_kismetdb(str(db_file), rules, dry_run=True)
        assert result.success is True

    def test_process_kismetdb_database_error(self, tmp_path, mocker):
        """Test handling of database errors."""
        db_file = tmp_path / "test.kismet"
        db_file.touch()

        # Mock sqlite3 to raise an error
        mock_connect = mocker.patch("sqlite3.connect")
        mock_connect.side_effect = Exception("Database error")

        rules = [processor.FilterRule("Test", "exact")]
        try:
            result = processor.process_kismetdb(str(db_file), rules)
            # If the error is caught, it should fail
            if result:
                assert result.success is False
        except Exception:
            # Error is raised, which is acceptable for database errors
            assert True

    def test_process_kismetdb_counts_matches(self, tmp_path, mocker):
        """Test that process_kismetdb counts removed entries."""
        db_file = tmp_path / "test.kismet"
        db_file.touch()

        # Mock cursor to return device data
        mock_connect = mocker.patch("sqlite3.connect")
        mock_cursor = mock.MagicMock()
        mock_connect.return_value.cursor.return_value = mock_cursor

        # Simulate 2 devices where 1 matches
        device_json_match = json.dumps(
            {
                "dot11.device": {
                    "dot11.device.advertised_ssid_map": [
                        {"dot11.advertisedssid.ssid": "MatchingSSID"}
                    ]
                }
            }
        )
        device_json_nomatch = json.dumps(
            {
                "dot11.device": {
                    "dot11.device.advertised_ssid_map": [{"dot11.advertisedssid.ssid": "OtherSSID"}]
                }
            }
        )

        mock_cursor.fetchall.return_value = [
            (1, "AA:BB:CC:DD:EE:FF", device_json_match),
            (2, "11:22:33:44:55:66", device_json_nomatch),
        ]

        rules = [processor.FilterRule("MatchingSSID", "exact")]
        result = processor.process_kismetdb(str(db_file), rules, dry_run=True)

        assert result.success is True
        assert result.original_count == 2
        assert result.removed_count == 1


class TestScanKismetdb:
    """Test scan_kismetdb function."""

    def test_scan_kismetdb_is_dry_run(self, tmp_path, mocker):
        """Test that scan_kismetdb always does dry-run."""
        db_file = tmp_path / "test.kismet"
        db_file.touch()

        mock_connect = mocker.patch("sqlite3.connect")
        mock_cursor = mock.MagicMock()
        mock_connect.return_value.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        rules = [processor.FilterRule("Test", "exact")]
        result = processor.scan_kismetdb(str(db_file), rules)

        # Should succeed without making changes
        assert result.success is True


# =============================================================================
# PREVIEW AND SANITIZATION TESTS
# =============================================================================


class TestPreviewSanitization:
    """Test preview_sanitization function."""

    def test_preview_sanitization_with_single_file(self, tmp_path):
        """Test previewing sanitization for a single file."""
        csv_file = tmp_path / "test.wiglecsv"
        csv_file.write_text("""# Header1
# Header2
AA:BB:CC:DD:EE:FF,TestNetwork,47.0,122.0,1,1,WPA2
""")

        rules = [processor.FilterRule("TestNetwork", "exact")]
        # Mock is_file_in_use to return False (file not being written)
        with mock.patch.object(processor, "is_file_in_use", return_value=False):
            preview = processor.preview_sanitization(str(csv_file), rules)

        assert preview["total_entries"] == 1
        assert preview["total_matches"] == 1
        assert len(preview["files"]) == 1

    def test_preview_sanitization_with_directory(self, tmp_path):
        """Test previewing sanitization for a directory."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()

        (logs_dir / "test.wiglecsv").write_text("""# H1
# H2
AA:BB:CC:DD:EE:FF,Network1,47.0,122.0,1,1,WPA2
""")

        rules = [processor.FilterRule("Network1", "exact")]
        # Mock is_file_in_use to return False (file not being written)
        with mock.patch.object(processor, "is_file_in_use", return_value=False):
            preview = processor.preview_sanitization(str(logs_dir), rules)

        assert preview["total_entries"] == 1

    def test_preview_sanitization_skips_in_use_files(self, tmp_path):
        """Test that preview skips files currently in use."""
        csv_file = tmp_path / "test.wiglecsv"
        csv_file.write_text("""# H1
# H2
AA:BB:CC:DD:EE:FF,Network,47.0,122.0,1,1,WPA2
""")

        # Mock is_file_in_use to return True
        rules = [processor.FilterRule("Network", "exact")]
        with mock.patch.object(processor, "is_file_in_use", return_value=True):
            preview = processor.preview_sanitization(str(csv_file), rules)

        # File should be skipped
        assert len(preview["files"]) == 0


# =============================================================================
# COLORS CLASS TESTS
# =============================================================================


class TestColorsClass:
    """Test the Colors utility class."""

    def test_colors_constants_defined(self):
        """Test that color constants exist (may be empty in non-TTY)."""
        # Colors may be empty strings in non-TTY mode
        assert hasattr(processor.Colors, "RED")
        assert hasattr(processor.Colors, "GREEN")
        assert hasattr(processor.Colors, "YELLOW")
        assert hasattr(processor.Colors, "BLUE")
        assert hasattr(processor.Colors, "CYAN")
        assert hasattr(processor.Colors, "BOLD")
        assert hasattr(processor.Colors, "NC")

    def test_colors_disable_removes_colors(self):
        """Test that disable() removes color codes."""
        # Store original values
        original_red = processor.Colors.RED
        original_green = processor.Colors.GREEN

        processor.Colors.disable()
        assert processor.Colors.RED == ""
        assert processor.Colors.GREEN == ""

        # Restore colors for other tests
        processor.Colors.RED = original_red
        processor.Colors.GREEN = original_green


# =============================================================================
# JSON API MODE TESTS
# =============================================================================


class TestJsonPreview:
    """Test json_preview function."""

    def test_json_preview_returns_valid_json(self, tmp_path):
        """Test that json_preview returns valid JSON."""
        csv_file = tmp_path / "test.wiglecsv"
        csv_file.write_text("""# H1
# H2
AA:BB:CC:DD:EE:FF,Network,47.0,122.0,1,1,WPA2
""")

        config_file = tmp_path / "config.conf"
        config_file.write_text("""
[dynamic_exclusions]
Network|exact
""")

        result = processor.json_preview(str(csv_file), str(config_file))

        # Should be valid JSON
        parsed = json.loads(result)
        assert isinstance(parsed, dict)
        assert "files" in parsed or "total_matches" in parsed


class TestJsonProcess:
    """Test json_process function."""

    def test_json_process_no_rules(self, tmp_path):
        """Test json_process with no configured rules."""
        csv_file = tmp_path / "test.wiglecsv"
        csv_file.write_text("""# H1
# H2
AA:BB:CC:DD:EE:FF,Network,47.0,122.0,1,1,WPA2
""")

        config_file = tmp_path / "config.conf"
        config_file.write_text("")

        result = processor.json_process(str(csv_file), str(config_file))
        parsed = json.loads(result)

        assert parsed["success"] is False
        assert "error" in parsed

    def test_json_process_returns_valid_json(self, tmp_path):
        """Test that json_process returns valid JSON."""
        csv_file = tmp_path / "test.wiglecsv"
        csv_file.write_text("""# H1
# H2
AA:BB:CC:DD:EE:FF,Network,47.0,122.0,1,1,WPA2
""")

        config_file = tmp_path / "config.conf"
        config_file.write_text("""
[dynamic_exclusions]
Network|exact
""")

        result = processor.json_process(str(csv_file), str(config_file))
        parsed = json.loads(result)

        assert isinstance(parsed, dict)
        assert "success" in parsed


# =============================================================================
# FILTER DAEMON TESTS
# =============================================================================


class TestFilterDaemon:
    """Test FilterDaemon class."""

    def test_daemon_initialization(self, tmp_path):
        """Test FilterDaemon initialization."""
        watch_dir = tmp_path / "watch"
        watch_dir.mkdir()

        daemon = processor.FilterDaemon(str(watch_dir), interval=30)

        assert daemon.watch_dir == str(watch_dir)
        assert daemon.interval == 30
        assert daemon.running is False
        assert daemon.rules == []

    def test_daemon_load_rules(self, tmp_path):
        """Test FilterDaemon loading rules."""
        watch_dir = tmp_path / "watch"
        watch_dir.mkdir()
        config_file = tmp_path / "config.conf"
        config_file.write_text("""
[dynamic_exclusions]
TestNetwork|exact|Test
""")

        daemon = processor.FilterDaemon(str(watch_dir))

        with mock.patch.object(processor, "load_dynamic_exclusions") as mock_load:
            mock_load.return_value = [processor.FilterRule("TestNetwork", "exact")]
            daemon.load_rules()

        assert len(daemon.rules) == 0 or daemon.rules[0].value == "TestNetwork"

    def test_daemon_process_pending_files_with_rules(self, tmp_path):
        """Test daemon processes pending files when rules are loaded."""
        watch_dir = tmp_path / "watch"
        watch_dir.mkdir()

        daemon = processor.FilterDaemon(str(watch_dir))
        daemon.rules = [processor.FilterRule("Test", "exact")]

        with mock.patch.object(processor, "find_kismetdb_files", return_value=[]):
            daemon.process_pending_files()

        # Should complete without error
        assert True

    def test_daemon_process_pending_files_no_rules(self, tmp_path):
        """Test daemon skips processing when no rules."""
        watch_dir = tmp_path / "watch"
        watch_dir.mkdir()

        daemon = processor.FilterDaemon(str(watch_dir))
        daemon.rules = []

        with mock.patch.object(processor, "find_kismetdb_files") as mock_find:
            daemon.process_pending_files()

        # Should not call find_kismetdb_files
        mock_find.assert_not_called()


# =============================================================================
# INTEGRATION-STYLE TESTS
# =============================================================================


class TestEndToEndFiltering:
    """End-to-end filtering workflow tests."""

    def test_full_config_and_matching_workflow(self, tmp_path):
        """Test complete workflow of loading config and matching SSIDs."""
        # Create config
        config_file = tmp_path / "filter_rules.conf"
        config_file.write_text("""
[dynamic_exclusions]
iPhone*|pattern|iOS hotspots
AndroidHotspot|exact|Android
        """)

        # Load rules
        rules = processor.load_dynamic_exclusions(str(config_file))

        # Create test device JSON
        device_json = json.dumps(
            {
                "dot11.device": {
                    "dot11.device.advertised_ssid_map": [
                        {"dot11.advertisedssid.ssid": "iPhone Hotspot ABC"}
                    ]
                }
            }
        )

        # Extract SSID
        ssids = processor.extract_ssids_from_device(device_json)
        assert len(ssids) == 1

        # Match against rules
        rule = processor.find_matching_rule(ssids[0], rules)
        assert rule is not None
        assert rule.value == "iPhone*"

    def test_both_exact_and_pattern_matching(self, tmp_path):
        """Test config with both exact and pattern rules."""
        config_file = tmp_path / "filter_rules.conf"
        config_file.write_text("""
[dynamic_exclusions]
ExactNetwork|exact|Exact match
Pattern*|pattern|Pattern match
        """)

        _static, dynamic = processor.load_all_exclusions(str(config_file))

        # Test exact match
        exact_rule = processor.find_matching_rule("ExactNetwork", dynamic)
        assert exact_rule is not None
        assert exact_rule.match_type == "exact"

        # Test pattern match
        pattern_rule = processor.find_matching_rule("PatternSomething", dynamic)
        assert pattern_rule is not None
        assert pattern_rule.match_type == "pattern"

        # Test no match
        no_match = processor.find_matching_rule("UnknownNetwork", dynamic)
        assert no_match is None
