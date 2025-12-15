# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Unified filter manager script (`warpie-filter-manager.sh`) with support for:
  - Static exclusions (block stable-MAC networks at capture time)
  - Dynamic exclusions (post-processing removal for rotating-MAC networks)
  - Targeting inclusions (add OUI prefixes to targeting modes like )
- JSON API mode for all filter management operations (web integration)
- Web filter management UI with tabbed Filters flyout (Exclusions + Targeting tabs)
- Filter API endpoints in `warpie-control.py`:
  - `GET/POST/DELETE /api/filters` for static/dynamic exclusions
  - `GET/POST/DELETE /api/filters/targets` for targeting inclusions
- JavaScript tooling:
  - ESLint for embedded JavaScript linting
  - Jest + JSDOM for JavaScript unit tests (15 tests)
  - Extraction script for linting JS embedded in Python templates
- Project tooling configuration (Ruff, ShellCheck, pytest, pre-commit)
- GPL-3.0 License (kept existing)
- EditorConfig for consistent formatting
- Pre-commit hooks for automated code quality checks
- GitHub repository structure
- Initial test suite with pytest and Jest

### Changed

- Migrated project from Claude Project to GitHub repository
- Updated NETWORK_FILTERING_ENHANCEMENT.md with targeting inclusions paradigm
- Web control panel upgraded to v2.4.1
- Refactored `do_POST` handler for better code organization

## [2.4.0] - 2024-12-11

### Added

- Web control panel (`warpie-control.py`) on port 1337
- SSID exclusion CLI tool (`warpie-exclude-ssid.sh`)
- Live log viewer flyout in web interface
- Toast notifications for mode switching
- Logs organized by mode and date
- Interactive WiFi SSID configuration during install

### Changed

- Kismet runs as non-root user (kismet group)
- Improved home network BSSID detection
- Enhanced AP mode stability

### Fixed

- GPS persistent device path configuration
- Home network exclusion in wardrive mode
- WarPie AP auto-excluded from capture logs

## [2.3.0] - 2024-12-10

### Added

- Dual-band WiFi capture (2.4GHz + 5GHz/6GHz)
- GPS integration with GlobalSat BU-353S4
- Mobile access point mode (WarPie network)
- Automatic home/away network detection
- Multiple Kismet capture modes (Normal, Wardrive, )
- WiGLE CSV logging for network uploads

### Hardware Support

- Raspberry Pi 4B
- ALFA AWUS036AXML (5GHz/6GHz WiFi adapter)
- RT3070-based adapter (2.4GHz)
- GlobalSat BU-353S4 GPS receiver

[Unreleased]: https://github.com/warpie/warpie/compare/v2.4.0...HEAD
[2.4.0]: https://github.com/warpie/warpie/compare/v2.3.0...v2.4.0
[2.3.0]: https://github.com/warpie/warpie/releases/tag/v2.3.0
