#!/usr/bin/env python3
"""
WarPie Dynamic Filter Processor

Post-processing daemon for removing network entries matching dynamic exclusions
from kismetdb files and WiGLE CSV exports. Dynamic exclusions are networks with
rotating MAC addresses (e.g., iPhone hotspots) that cannot be effectively
blocked at capture time.

This processor:
- Monitors kismetdb files for dynamic exclusion SSID matches
- Removes entries by SSID (never by MAC - MACs rotate)
- Sanitizes WiGLE CSV files before upload
- Supports daemon mode with inotify monitoring
- Provides pre-upload interactive sanitization workflow

Version: 2.4.1
"""

import argparse
import fnmatch
import json
import logging
import os
import shutil
import signal
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime

# Optional: inotify for daemon mode (may not be installed)
try:
    import inotify.adapters

    INOTIFY_AVAILABLE = True
except ImportError:
    INOTIFY_AVAILABLE = False

# =============================================================================
# CONFIGURATION
# =============================================================================

VERSION = "2.4.1"
CONFIG_FILE = "/etc/warpie/filter_rules.conf"
KISMET_LOGS_DIR = os.path.expanduser("~/kismet/logs")
BACKUP_DIR = os.path.expanduser("~/kismet/backups")
LOG_FILE = "/var/log/warpie/filter-processor.log"
DAEMON_INTERVAL = 60  # seconds between processing runs

# WiGLE CSV columns (1.4 format)
WIGLE_MAC_COL = 0
WIGLE_SSID_COL = 1


# Colors for terminal output
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
        cls.RED = cls.GREEN = cls.YELLOW = cls.BLUE = cls.CYAN = cls.BOLD = cls.NC = ""


# Disable colors if not a TTY
if not sys.stdout.isatty():
    Colors.disable()


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class FilterRule:
    """Represents a single filter rule."""

    value: str
    match_type: str  # exact, pattern
    description: str = ""


@dataclass
class ProcessingResult:
    """Results from processing a single file."""

    file_path: str
    original_count: int = 0
    removed_count: int = 0
    matches: list = field(default_factory=list)
    success: bool = True
    error: str = ""


@dataclass
class SanitizationReport:
    """Summary report for a sanitization run."""

    files_processed: int = 0
    total_original: int = 0
    total_removed: int = 0
    backup_path: str = ""
    duration_seconds: float = 0.0
    errors: list = field(default_factory=list)


# =============================================================================
# LOGGING SETUP
# =============================================================================


def setup_logging(log_file: str | None = None, verbose: bool = False):
    """Configure logging for the processor."""
    log_level = logging.DEBUG if verbose else logging.INFO

    handlers = [logging.StreamHandler()]

    if log_file:
        try:
            log_dir = os.path.dirname(log_file)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)
            handlers.append(logging.FileHandler(log_file))
        except (OSError, PermissionError) as e:
            print(f"Warning: Could not create log file: {e}", file=sys.stderr)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )


# =============================================================================
# CONFIGURATION PARSING
# =============================================================================


def load_dynamic_exclusions(config_path: str = CONFIG_FILE) -> list[FilterRule]:
    """
    Load dynamic exclusion rules from the filter configuration file.

    Only loads [dynamic_exclusions] section - these are SSID patterns for
    networks with rotating MACs that need post-processing removal.

    Args:
        config_path: Path to the filter_rules.conf file.

    Returns:
        List of FilterRule objects for dynamic exclusions.
    """
    rules = []

    if not os.path.exists(config_path):
        logging.warning(f"Config file not found: {config_path}")
        return rules

    in_section = False

    try:
        with open(config_path) as f:
            for line in f:
                line = line.strip()

                # Check for section markers
                if line == "[dynamic_exclusions]":
                    in_section = True
                    continue
                elif line.startswith("[") and line.endswith("]"):
                    in_section = False
                    continue

                # Skip comments and empty lines
                if not line or line.startswith("#"):
                    continue

                # Parse entry in dynamic section
                if in_section:
                    parts = line.split("|")
                    if len(parts) >= 2:
                        value = parts[0]
                        match_type = parts[1]
                        description = parts[2] if len(parts) > 2 else ""
                        rules.append(FilterRule(value, match_type, description))

    except OSError as e:
        logging.error(f"Failed to read config file: {e}")

    logging.info(f"Loaded {len(rules)} dynamic exclusion rules")
    return rules


def load_all_exclusions(
    config_path: str = CONFIG_FILE,
) -> tuple[list[FilterRule], list[FilterRule]]:
    """
    Load both static and dynamic exclusion rules.

    Args:
        config_path: Path to the filter_rules.conf file.

    Returns:
        Tuple of (static_rules, dynamic_rules).
    """
    static_rules = []
    dynamic_rules = []

    if not os.path.exists(config_path):
        logging.warning(f"Config file not found: {config_path}")
        return static_rules, dynamic_rules

    current_section = None

    try:
        with open(config_path) as f:
            for line in f:
                line = line.strip()

                if line == "[static_exclusions]":
                    current_section = "static"
                    continue
                elif line == "[dynamic_exclusions]":
                    current_section = "dynamic"
                    continue
                elif line.startswith("[") and line.endswith("]"):
                    current_section = None
                    continue

                if not line or line.startswith("#"):
                    continue

                if current_section:
                    parts = line.split("|")
                    if len(parts) >= 2:
                        rule = FilterRule(
                            value=parts[0],
                            match_type=parts[1],
                            description=parts[2] if len(parts) > 2 else "",
                        )
                        if current_section == "static":
                            static_rules.append(rule)
                        elif current_section == "dynamic":
                            dynamic_rules.append(rule)

    except OSError as e:
        logging.error(f"Failed to read config file: {e}")

    return static_rules, dynamic_rules


# =============================================================================
# PATTERN MATCHING
# =============================================================================


def matches_pattern(ssid: str, rule: FilterRule) -> bool:
    """
    Check if an SSID matches a filter rule.

    Args:
        ssid: The SSID to check.
        rule: The FilterRule to match against.

    Returns:
        True if the SSID matches the rule.
    """
    if rule.match_type == "exact":
        return ssid == rule.value
    elif rule.match_type == "pattern":
        # fnmatch handles * and ? wildcards
        return fnmatch.fnmatch(ssid, rule.value)
    elif rule.match_type == "bssid":
        # BSSIDs don't match SSIDs
        return False
    return False


def find_matching_rule(ssid: str, rules: list[FilterRule]) -> FilterRule | None:
    """
    Find the first rule that matches an SSID.

    Args:
        ssid: The SSID to check.
        rules: List of rules to check against.

    Returns:
        The matching FilterRule or None.
    """
    for rule in rules:
        if matches_pattern(ssid, rule):
            return rule
    return None


# =============================================================================
# KISMETDB PROCESSING
# =============================================================================


def extract_ssids_from_device(device_json: str) -> list[str]:
    """
    Extract all SSIDs from a kismetdb device JSON blob.

    Args:
        device_json: JSON string from devices.device column.

    Returns:
        List of SSIDs found in the device data.
    """
    ssids = []

    try:
        device = json.loads(device_json)

        # Primary SSID location
        ssid_map = device.get("dot11.device", {}).get("dot11.device.advertised_ssid_map", [])

        for ssid_entry in ssid_map:
            if isinstance(ssid_entry, dict):
                ssid = ssid_entry.get("dot11.advertisedssid.ssid", "")
                if ssid:
                    ssids.append(ssid)

        # Also check probed SSIDs
        probed_map = device.get("dot11.device", {}).get("dot11.device.probed_ssid_map", [])
        for probed_entry in probed_map:
            if isinstance(probed_entry, dict):
                ssid = probed_entry.get("dot11.probedssid.ssid", "")
                if ssid and ssid not in ssids:
                    ssids.append(ssid)

    except (json.JSONDecodeError, TypeError, KeyError):
        pass

    return ssids


def process_kismetdb(
    db_path: str, rules: list[FilterRule], dry_run: bool = False
) -> ProcessingResult:
    """
    Process a kismetdb file, removing entries matching dynamic exclusion rules.

    IMPORTANT: This only removes by SSID match. We NEVER add rotating MACs to
    any blocklist - the whole point of dynamic exclusions is that the MAC
    changes every session.

    Args:
        db_path: Path to the kismetdb SQLite file.
        rules: List of dynamic exclusion FilterRules.
        dry_run: If True, don't actually delete, just report what would be deleted.

    Returns:
        ProcessingResult with statistics.
    """
    result = ProcessingResult(file_path=db_path)

    if not os.path.exists(db_path):
        result.success = False
        result.error = "File not found"
        return result

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Get all WiFi devices
        cursor.execute("""
            SELECT key, devmac, device FROM devices
            WHERE phyname = 'IEEE802.11'
        """)

        keys_to_remove = []
        macs_to_remove = []

        for key, devmac, device_json in cursor.fetchall():
            result.original_count += 1
            ssids = extract_ssids_from_device(device_json)

            for ssid in ssids:
                rule = find_matching_rule(ssid, rules)
                if rule:
                    keys_to_remove.append(key)
                    macs_to_remove.append(devmac)
                    result.matches.append(
                        {
                            "ssid": ssid,
                            "mac": devmac,
                            "rule": rule.value,
                            "rule_type": rule.match_type,
                        }
                    )
                    break  # Only count each device once

        result.removed_count = len(keys_to_remove)

        if not dry_run and keys_to_remove:
            # Remove from devices table
            for key in keys_to_remove:
                cursor.execute("DELETE FROM devices WHERE key = ?", (key,))

            # Remove associated packets
            for mac in macs_to_remove:
                cursor.execute(
                    """
                    DELETE FROM packets
                    WHERE sourcemac = ? OR destmac = ?
                """,
                    (mac, mac),
                )

            # Also clean up data_source_records if they exist
            for mac in macs_to_remove:
                try:
                    cursor.execute(
                        """
                        DELETE FROM datasources
                        WHERE json_extract(source_json, '$.kismet.datasource.source_mac') = ?
                    """,
                        (mac,),
                    )
                except sqlite3.OperationalError:
                    pass  # Table might not exist in all versions

            conn.commit()
            logging.info(f"Removed {result.removed_count} entries from {db_path}")

        conn.close()

    except sqlite3.Error as e:
        result.success = False
        result.error = f"Database error: {e}"
        logging.error(f"Failed to process {db_path}: {e}")

    return result


def scan_kismetdb(db_path: str, rules: list[FilterRule]) -> ProcessingResult:
    """
    Scan a kismetdb file without modifying it. Returns what would be removed.

    Args:
        db_path: Path to the kismetdb SQLite file.
        rules: List of exclusion FilterRules (static or dynamic).

    Returns:
        ProcessingResult with scan results (no modifications made).
    """
    return process_kismetdb(db_path, rules, dry_run=True)


# =============================================================================
# WIGLE CSV PROCESSING
# =============================================================================


def process_wigle_csv(
    csv_path: str, rules: list[FilterRule], dry_run: bool = False
) -> ProcessingResult:
    """
    Process a WiGLE CSV file, removing entries matching exclusion rules.

    Args:
        csv_path: Path to the WiGLE CSV file.
        rules: List of exclusion FilterRules.
        dry_run: If True, don't actually modify, just report.

    Returns:
        ProcessingResult with statistics.
    """
    result = ProcessingResult(file_path=csv_path)

    if not os.path.exists(csv_path):
        result.success = False
        result.error = "File not found"
        return result

    try:
        with open(csv_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        if len(lines) < 2:
            result.error = "File too short (missing header)"
            return result

        # Preserve header lines (first 2 lines in WiGLE format)
        header = lines[:2]
        data_lines = lines[2:]

        result.original_count = len(data_lines)
        filtered_lines = []

        for line in data_lines:
            parts = line.split(",")
            if len(parts) > WIGLE_SSID_COL:
                ssid = parts[WIGLE_SSID_COL]

                rule = find_matching_rule(ssid, rules)
                if rule:
                    mac = parts[WIGLE_MAC_COL] if len(parts) > WIGLE_MAC_COL else ""
                    result.matches.append(
                        {"ssid": ssid, "mac": mac, "rule": rule.value, "rule_type": rule.match_type}
                    )
                else:
                    filtered_lines.append(line)
            else:
                filtered_lines.append(line)

        result.removed_count = result.original_count - len(filtered_lines)

        if not dry_run and result.removed_count > 0:
            with open(csv_path, "w", encoding="utf-8") as f:
                f.writelines(header)
                f.writelines(filtered_lines)
            logging.info(f"Removed {result.removed_count} entries from {csv_path}")

    except OSError as e:
        result.success = False
        result.error = f"File error: {e}"
        logging.error(f"Failed to process {csv_path}: {e}")

    return result


def scan_wigle_csv(csv_path: str, rules: list[FilterRule]) -> ProcessingResult:
    """
    Scan a WiGLE CSV file without modifying it.

    Args:
        csv_path: Path to the WiGLE CSV file.
        rules: List of exclusion FilterRules.

    Returns:
        ProcessingResult with scan results (no modifications made).
    """
    return process_wigle_csv(csv_path, rules, dry_run=True)


# =============================================================================
# BACKUP MANAGEMENT
# =============================================================================


def create_backup(files: list[str], backup_dir: str = BACKUP_DIR) -> str:
    """
    Create a backup of files before processing.

    Args:
        files: List of file paths to back up.
        backup_dir: Base directory for backups.

    Returns:
        Path to the backup directory.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    backup_path = os.path.join(backup_dir, timestamp)

    os.makedirs(backup_path, exist_ok=True)

    for file_path in files:
        if os.path.exists(file_path):
            dest = os.path.join(backup_path, os.path.basename(file_path))
            shutil.copy2(file_path, dest)
            logging.debug(f"Backed up {file_path} to {dest}")

    logging.info(f"Created backup at {backup_path}")
    return backup_path


def delete_backup(backup_path: str):
    """
    Delete a backup directory.

    Args:
        backup_path: Path to the backup directory to delete.
    """
    if os.path.exists(backup_path) and os.path.isdir(backup_path):
        shutil.rmtree(backup_path)
        logging.info(f"Deleted backup at {backup_path}")


def list_backups(backup_dir: str = BACKUP_DIR) -> list[dict]:
    """
    List available backups.

    Args:
        backup_dir: Base directory for backups.

    Returns:
        List of backup info dicts.
    """
    backups = []

    if not os.path.exists(backup_dir):
        return backups

    for name in sorted(os.listdir(backup_dir), reverse=True):
        path = os.path.join(backup_dir, name)
        if os.path.isdir(path):
            files = os.listdir(path)
            total_size = sum(
                os.path.getsize(os.path.join(path, f))
                for f in files
                if os.path.isfile(os.path.join(path, f))
            )
            backups.append(
                {"name": name, "path": path, "files": len(files), "size_bytes": total_size}
            )

    return backups


# =============================================================================
# FILE DISCOVERY
# =============================================================================


def find_kismetdb_files(base_dir: str = KISMET_LOGS_DIR) -> list[str]:
    """
    Find all kismetdb files in the logs directory.

    Args:
        base_dir: Base directory to search.

    Returns:
        List of kismetdb file paths.
    """
    files = []

    for root, _, filenames in os.walk(base_dir):
        for filename in filenames:
            if filename.endswith(".kismet"):
                files.append(os.path.join(root, filename))

    return sorted(files, key=os.path.getmtime, reverse=True)


def find_wigle_csv_files(base_dir: str = KISMET_LOGS_DIR) -> list[str]:
    """
    Find all WiGLE CSV files in the logs directory.

    Args:
        base_dir: Base directory to search.

    Returns:
        List of WiGLE CSV file paths.
    """
    files = []

    for root, _, filenames in os.walk(base_dir):
        for filename in filenames:
            if filename.endswith(".wiglecsv") or "wigle" in filename.lower():
                files.append(os.path.join(root, filename))

    return sorted(files, key=os.path.getmtime, reverse=True)


def is_file_in_use(file_path: str) -> bool:
    """
    Check if a file is currently being written to (by Kismet).

    Uses file modification time - if modified within last 30 seconds,
    consider it in use.

    Args:
        file_path: Path to check.

    Returns:
        True if file appears to be in use.
    """
    if not os.path.exists(file_path):
        return False

    mtime = os.path.getmtime(file_path)
    age_seconds = time.time() - mtime

    return age_seconds < 30


# =============================================================================
# PRE-UPLOAD SANITIZATION WORKFLOW
# =============================================================================


def format_size(size_bytes: int) -> str:
    """Format byte size as human-readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def print_header(text: str):
    """Print a section header."""
    print(f"\n{Colors.BOLD}{text}{Colors.NC}")
    print("─" * 50)


def preview_sanitization(path: str, rules: list[FilterRule]) -> dict:
    """
    Preview what would be removed during sanitization.

    Args:
        path: Path to directory or specific file to process.
        rules: Exclusion rules to apply.

    Returns:
        Preview data dict with files and matches.
    """
    preview = {"files": [], "total_entries": 0, "total_matches": 0, "total_size": 0}

    if os.path.isfile(path):
        files = [path]
    else:
        files = find_kismetdb_files(path) + find_wigle_csv_files(path)

    for file_path in files:
        if is_file_in_use(file_path):
            logging.warning(f"Skipping {file_path} - currently in use")
            continue

        if file_path.endswith(".kismet"):
            result = scan_kismetdb(file_path, rules)
        elif file_path.endswith(".wiglecsv") or "wigle" in file_path.lower():
            result = scan_wigle_csv(file_path, rules)
        else:
            continue

        if result.success:
            file_size = os.path.getsize(file_path)
            preview["files"].append(
                {
                    "path": file_path,
                    "name": os.path.basename(file_path),
                    "original_count": result.original_count,
                    "match_count": result.removed_count,
                    "matches": result.matches,
                    "size_bytes": file_size,
                }
            )
            preview["total_entries"] += result.original_count
            preview["total_matches"] += result.removed_count
            preview["total_size"] += file_size

    return preview


def interactive_pre_upload(path: str):
    """
    Run the interactive pre-upload sanitization workflow.

    This is the main user-facing workflow for cleaning files before
    uploading to WiGLE or other services.

    Args:
        path: Path to directory or file to sanitize.
    """
    print(f"\n{Colors.BOLD}{'=' * 60}{Colors.NC}")
    print(f"{Colors.BOLD}       PRE-UPLOAD SANITIZATION WORKFLOW{Colors.NC}")
    print(f"{Colors.BOLD}{'=' * 60}{Colors.NC}")

    # Load all exclusion rules (both static and dynamic for pre-upload)
    static_rules, dynamic_rules = load_all_exclusions()
    all_rules = static_rules + dynamic_rules

    if not all_rules:
        print(f"\n{Colors.YELLOW}No exclusion rules configured.{Colors.NC}")
        print("Add exclusions using: warpie-filter-manager.sh --add-static/--add-dynamic")
        return

    print(f"\nLoaded {len(static_rules)} static + {len(dynamic_rules)} dynamic exclusion rules")

    # Step 1: Scan and preview
    print_header("STEP 1: SCANNING FILES")
    print(f"Scanning: {path}")

    preview = preview_sanitization(path, all_rules)

    if not preview["files"]:
        print(f"\n{Colors.YELLOW}No processable files found.{Colors.NC}")
        return

    if preview["total_matches"] == 0:
        print(f"\n{Colors.GREEN}No matches found - files are clean!{Colors.NC}")
        return

    # Step 2: Show preview results
    print_header("STEP 2: SCAN RESULTS")

    for file_info in preview["files"]:
        if file_info["match_count"] > 0:
            print(f"\n{Colors.CYAN}{file_info['name']}{Colors.NC}")
            print(f"  Entries: {file_info['original_count']}")
            print(f"  Matches: {Colors.YELLOW}{file_info['match_count']}{Colors.NC}")

            # Group matches by rule
            rule_counts = {}
            for match in file_info["matches"]:
                rule_key = f"{match['rule']} ({match['rule_type']})"
                rule_counts[rule_key] = rule_counts.get(rule_key, 0) + 1

            for rule, count in rule_counts.items():
                print(f"    - {rule}: {count} entries")

    print(f"\n{Colors.BOLD}SUMMARY:{Colors.NC}")
    print(f"  Files to process: {len([f for f in preview['files'] if f['match_count'] > 0])}")
    print(f"  Total entries to remove: {Colors.YELLOW}{preview['total_matches']}{Colors.NC}")
    print(f"  Current total size: {format_size(preview['total_size'])}")

    # Step 3: Confirmation
    print_header("STEP 3: CONFIRMATION")

    print(f"\n{Colors.YELLOW}WARNING: This will permanently modify the files.{Colors.NC}")
    print("A backup will be created before processing.\n")

    try:
        response = input("Proceed with removal? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        return

    if response != "y":
        print("Cancelled.")
        return

    # Step 4: Create backup
    print_header("STEP 4: CREATING BACKUP")

    files_to_process = [f["path"] for f in preview["files"] if f["match_count"] > 0]
    backup_path = create_backup(files_to_process)
    print(f"Backup created: {Colors.GREEN}{backup_path}{Colors.NC}")

    # Step 5: Process files
    print_header("STEP 5: PROCESSING")

    start_time = time.time()
    total_removed = 0
    errors = []

    for i, file_info in enumerate(preview["files"]):
        if file_info["match_count"] == 0:
            continue

        file_path = file_info["path"]
        print(f"Processing [{i + 1}/{len(files_to_process)}]: {file_info['name']}...", end=" ")

        if file_path.endswith(".kismet"):
            result = process_kismetdb(file_path, all_rules)
        else:
            result = process_wigle_csv(file_path, all_rules)

        if result.success:
            print(f"{Colors.GREEN}{result.removed_count} removed{Colors.NC}")
            total_removed += result.removed_count
        else:
            print(f"{Colors.RED}ERROR: {result.error}{Colors.NC}")
            errors.append(f"{file_info['name']}: {result.error}")

    duration = time.time() - start_time

    # Step 6: Final report
    print_header("STEP 6: FINAL REPORT")

    print(f"\n{Colors.GREEN}SANITIZATION COMPLETE{Colors.NC}")
    print(f"{'─' * 40}")
    print(f"  Files processed:      {len(files_to_process)}")
    print(f"  Total entries removed: {total_removed}")
    print(f"  Processing time:      {duration:.1f} seconds")

    if errors:
        print(f"\n{Colors.RED}Errors:{Colors.NC}")
        for error in errors:
            print(f"  - {error}")

    print("\n  Backup location:")
    print(f"  {backup_path}")

    # Step 7: Backup disposition
    print_header("STEP 7: BACKUP DISPOSITION")

    print("\nWhat would you like to do with the backup?")

    try:
        response = input("[K]eep backup  [D]elete backup  [default: Keep]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        response = ""

    if response == "d":
        delete_backup(backup_path)
        print(f"{Colors.GREEN}Backup deleted.{Colors.NC}")
    else:
        print(f"{Colors.GREEN}Backup retained at: {backup_path}{Colors.NC}")

    print(f"\n{Colors.GREEN}Files ready for upload!{Colors.NC}")


# =============================================================================
# DAEMON MODE
# =============================================================================


class FilterDaemon:
    """
    Daemon for continuous monitoring and processing of capture files.

    Uses inotify to watch for new/modified files, processes them when
    they're no longer being written to.
    """

    def __init__(self, watch_dir: str = KISMET_LOGS_DIR, interval: int = DAEMON_INTERVAL):
        self.watch_dir = watch_dir
        self.interval = interval
        self.running = False
        self.rules = []
        self.processed_files = set()

        # Track file modification times to avoid reprocessing
        self.file_mtimes = {}

    def load_rules(self):
        """Reload dynamic exclusion rules from config."""
        self.rules = load_dynamic_exclusions()
        logging.info(f"Daemon loaded {len(self.rules)} dynamic exclusion rules")

    def process_pending_files(self):
        """Process any files that need sanitization."""
        if not self.rules:
            return

        # Find all capture files
        kismet_files = find_kismetdb_files(self.watch_dir)

        for file_path in kismet_files:
            # Skip files currently being written
            if is_file_in_use(file_path):
                continue

            # Skip already processed files (unless modified)
            mtime = os.path.getmtime(file_path)
            if file_path in self.file_mtimes and self.file_mtimes[file_path] == mtime:
                continue

            # Process the file
            result = process_kismetdb(file_path, self.rules)

            if result.success and result.removed_count > 0:
                logging.info(
                    f"Daemon processed {file_path}: removed {result.removed_count} entries"
                )

            # Mark as processed
            self.file_mtimes[file_path] = mtime

    def run(self):
        """Run the daemon main loop."""
        self.running = True
        logging.info(f"Filter processor daemon started, watching {self.watch_dir}")

        # Initial rule load
        self.load_rules()

        while self.running:
            try:
                # Reload rules periodically in case they changed
                self.load_rules()

                # Process any pending files
                self.process_pending_files()

                # Sleep until next interval
                time.sleep(self.interval)

            except KeyboardInterrupt:
                logging.info("Daemon received interrupt, shutting down")
                self.running = False
            except Exception as e:
                logging.error(f"Daemon error: {e}")
                time.sleep(self.interval)

        logging.info("Filter processor daemon stopped")

    def stop(self):
        """Stop the daemon."""
        self.running = False


def run_daemon_with_inotify(watch_dir: str = KISMET_LOGS_DIR):
    """
    Run daemon with inotify-based file watching (more efficient).

    Requires the inotify package to be installed.

    Args:
        watch_dir: Directory to watch for new/modified files.
    """
    if not INOTIFY_AVAILABLE:
        logging.warning("inotify not available, falling back to polling mode")
        daemon = FilterDaemon(watch_dir)
        daemon.run()
        return

    logging.info(f"Starting inotify-based daemon, watching {watch_dir}")

    rules = load_dynamic_exclusions()
    i = inotify.adapters.InotifyTree(watch_dir)

    processed_files = {}

    try:
        for event in i.event_gen(yield_nones=False):
            (_, type_names, path, filename) = event

            if not filename:
                continue

            file_path = os.path.join(path, filename)

            # Only process kismet files
            if not filename.endswith(".kismet"):
                continue

            # Wait for file to be fully written
            if "IN_CLOSE_WRITE" in type_names or "IN_MOVED_TO" in type_names:
                # Small delay to ensure file is complete
                time.sleep(2)

                if is_file_in_use(file_path):
                    continue

                # Reload rules in case they changed
                rules = load_dynamic_exclusions()

                if rules:
                    result = process_kismetdb(file_path, rules)
                    if result.success and result.removed_count > 0:
                        logging.info(
                            f"Processed {filename}: removed {result.removed_count} entries"
                        )

                processed_files[file_path] = time.time()

    except KeyboardInterrupt:
        logging.info("Daemon shutting down")


# =============================================================================
# JSON API MODE
# =============================================================================


def json_preview(path: str, config_path: str = CONFIG_FILE) -> str:
    """
    Generate JSON preview of what would be sanitized.

    Args:
        path: Path to scan.
        config_path: Path to the filter configuration file.

    Returns:
        JSON string with preview data.
    """
    _, dynamic_rules = load_all_exclusions(config_path)
    preview = preview_sanitization(path, dynamic_rules)
    return json.dumps(preview, indent=2)


def json_process(path: str, config_path: str = CONFIG_FILE) -> str:
    """
    Process files and return JSON result.

    Args:
        path: Path to file or directory to process.
        config_path: Path to the filter configuration file.

    Returns:
        JSON string with results.
    """
    rules = load_dynamic_exclusions(config_path)

    if not rules:
        return json.dumps({"success": False, "error": "No dynamic exclusion rules configured"})

    results = []
    total_removed = 0

    if os.path.isfile(path):
        files = [path]
    else:
        files = find_kismetdb_files(path) + find_wigle_csv_files(path)

    for file_path in files:
        if is_file_in_use(file_path):
            continue

        if file_path.endswith(".kismet"):
            result = process_kismetdb(file_path, rules)
        elif file_path.endswith(".wiglecsv"):
            result = process_wigle_csv(file_path, rules)
        else:
            continue

        results.append(
            {
                "file": file_path,
                "success": result.success,
                "removed": result.removed_count,
                "error": result.error,
            }
        )
        total_removed += result.removed_count

    return json.dumps(
        {
            "success": True,
            "files_processed": len(results),
            "total_removed": total_removed,
            "results": results,
        },
        indent=2,
    )


# =============================================================================
# MAIN / CLI
# =============================================================================


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="WarPie Filter Processor - Post-processing for rotating-MAC exclusions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive pre-upload sanitization
  %(prog)s --pre-upload ~/kismet/logs/

  # Process a single file
  %(prog)s --process /path/to/capture.kismet

  # Dry-run to see what would be removed
  %(prog)s --dry-run --process /path/to/capture.kismet

  # Run as daemon (continuous monitoring)
  %(prog)s --daemon

  # JSON mode for web API integration
  %(prog)s --json --preview ~/kismet/logs/
        """,
    )

    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")

    # Mode selection
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--pre-upload", metavar="PATH", help="Run interactive pre-upload sanitization workflow"
    )
    mode_group.add_argument(
        "--process", metavar="PATH", help="Process a specific file or directory"
    )
    mode_group.add_argument(
        "--preview", metavar="PATH", help="Preview what would be removed (no changes)"
    )
    mode_group.add_argument(
        "--daemon",
        action="store_true",
        help="Run as daemon, continuously monitoring for new captures",
    )
    mode_group.add_argument("--list-backups", action="store_true", help="List available backups")

    # Options
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't actually modify files, just show what would be done",
    )
    parser.add_argument(
        "--json", action="store_true", help="Output results as JSON (for API integration)"
    )
    parser.add_argument(
        "--config",
        metavar="FILE",
        default=CONFIG_FILE,
        help=f"Config file path (default: {CONFIG_FILE})",
    )
    parser.add_argument(
        "--watch-dir",
        metavar="DIR",
        default=KISMET_LOGS_DIR,
        help=f"Directory to watch in daemon mode (default: {KISMET_LOGS_DIR})",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DAEMON_INTERVAL,
        help=f"Processing interval in daemon mode (default: {DAEMON_INTERVAL}s)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    # Setup logging
    log_file = LOG_FILE if args.daemon else None
    setup_logging(log_file, args.verbose)

    # Store config path for use in processing
    config_path = args.config

    # Disable colors in JSON mode
    if args.json:
        Colors.disable()

    # Execute requested mode
    if args.pre_upload:
        if args.json:
            print(json.dumps({"error": "Pre-upload mode not available in JSON mode"}))
            sys.exit(1)
        interactive_pre_upload(args.pre_upload)

    elif args.process:
        if args.json:
            if args.dry_run:
                print(json_preview(args.process, config_path))
            else:
                print(json_process(args.process, config_path))
        else:
            rules = load_dynamic_exclusions(config_path)
            if not rules:
                print("No dynamic exclusion rules configured.")
                sys.exit(0)

            if os.path.isfile(args.process):
                files = [args.process]
            else:
                files = find_kismetdb_files(args.process) + find_wigle_csv_files(args.process)

            for file_path in files:
                if is_file_in_use(file_path):
                    print(f"Skipping {file_path} - currently in use")
                    continue

                print(f"Processing {file_path}...")

                if file_path.endswith(".kismet"):
                    result = process_kismetdb(file_path, rules, dry_run=args.dry_run)
                else:
                    result = process_wigle_csv(file_path, rules, dry_run=args.dry_run)

                if result.success:
                    action = "Would remove" if args.dry_run else "Removed"
                    print(f"  {action} {result.removed_count} entries")
                else:
                    print(f"  Error: {result.error}")

    elif args.preview:
        if args.json:
            print(json_preview(args.preview, config_path))
        else:
            _, dynamic_rules = load_all_exclusions(config_path)
            preview = preview_sanitization(args.preview, dynamic_rules)

            print(f"\nPreview for: {args.preview}")
            print(f"{'─' * 50}")

            for file_info in preview["files"]:
                print(f"\n{file_info['name']}:")
                print(f"  Entries: {file_info['original_count']}")
                print(f"  Would remove: {file_info['match_count']}")

            print(f"\nTotal entries to remove: {preview['total_matches']}")

    elif args.daemon:
        # Setup signal handlers for clean shutdown
        def signal_handler(signum, frame):
            logging.info(f"Received signal {signum}, shutting down")
            sys.exit(0)

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        if INOTIFY_AVAILABLE:
            run_daemon_with_inotify(args.watch_dir)
        else:
            daemon = FilterDaemon(args.watch_dir, args.interval)
            daemon.run()

    elif args.list_backups:
        backups = list_backups()

        if args.json:
            print(json.dumps(backups, indent=2))
        elif not backups:
            print("No backups found.")
        else:
            print("\nAvailable backups:")
            print(f"{'─' * 50}")
            for backup in backups:
                print(f"\n  {backup['name']}")
                print(f"    Files: {backup['files']}")
                print(f"    Size: {format_size(backup['size_bytes'])}")
                print(f"    Path: {backup['path']}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
