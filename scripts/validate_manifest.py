#!/usr/bin/env python3
"""Validate all required files exist before installation/release.

This script prevents installation of incomplete packages and catches
missing files during development/CI.

Exit codes:
    0: All required files present
    1: Missing files detected
"""

import sys
from pathlib import Path

# Required files for WarPie installation
REQUIRED_FILES = [
    # Core scripts
    "bin/wardrive.sh",
    "bin/warpie-network-manager.sh",
    "bin/warpie-control",
    # Filter management (the missing scripts that caused issue #25!)
    "bin/warpie-filter-manager.py",
    "bin/warpie-filter-manager.sh",
    "bin/warpie-filter-processor.py",
    "bin/warpie-exclude-ssid.sh",
    # Utilities
    "bin/validate-warpie.sh",
    "bin/fix-kismet-root.sh",
    # Installation
    "install/install.sh",
    # Systemd services
    "systemd/gpsd-wardriver.service",
    "systemd/warpie-control.service",
    "systemd/warpie-network.service",
    "systemd/warpie-filter-processor.service",
    # Web application
    "web/app.py",
    "web/config.py",
    "web/routes/filters.py",
    "web/templates/index.html",
]


def validate_manifest() -> int:
    """Check all required files exist."""
    repo_root = Path(__file__).parent.parent
    missing = []

    for file_path in REQUIRED_FILES:
        full_path = repo_root / file_path
        if not full_path.exists():
            missing.append(file_path)

    if missing:
        print("ERROR: Missing required files:")
        for file in missing:
            print(f"  ❌ {file}")
        print(f"\nTotal missing: {len(missing)}/{len(REQUIRED_FILES)}")
        return 1

    print(f"✓ All {len(REQUIRED_FILES)} required files present")
    return 0


if __name__ == "__main__":
    sys.exit(validate_manifest())
