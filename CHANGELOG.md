# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.4.1] - 2025-12-25

### Added

- Flask + HTMX web control panel with cyberpunk terminal theme
- Filter manager Python implementation (`warpie-filter-manager.py`) with multi-PHY support
- Filter processor daemon (`warpie-filter-processor.py`) for dynamic exclusion post-processing
- BTLE/Classic Bluetooth support with TI CC2540 adapter
- Multi-PHY filter rules (WiFi, BTLE, Classic Bluetooth sections)
- Pre-upload sanitization workflow for WiGLE uploads
- Reboot button in control panel
- JavaScript testing infrastructure (Jest + JSDOM)

### Changed

- Migrated web control panel from custom `http.server` to Flask + Waitress
- Migrated filter manager from Bash to Python for better maintainability
- Web UI redesigned with terminal/cyberpunk aesthetic
- Improved mode switching with HTMX for seamless updates
- Enhanced filter management UI with static/dynamic exclusion paradigms

### Fixed

- Network manager mode detection using IP check instead of process detection
- AP startup stability with condition-based waiting
- Branch detection for installer script downloads
- BTLE device detection at runtime for USB path changes
- Subprocess and pipefail error handling in network manager
- 30+ UI/UX improvements including tooltips, font scaling, form handling

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
- Multiple Kismet capture modes (Normal, Wardrive)
- WiGLE CSV logging for network uploads

### Hardware Support

- Raspberry Pi 4B
- ALFA AWUS036AXML (5GHz/6GHz WiFi adapter)
- RT3070-based adapter (2.4GHz)
- GlobalSat BU-353S4 GPS receiver

[2.4.1]: https://github.com/PoppaShell/WarPie/compare/v2.4.0...v2.4.1
[2.4.0]: https://github.com/PoppaShell/WarPie/compare/v2.3.0...v2.4.0
[2.3.0]: https://github.com/PoppaShell/WarPie/releases/tag/v2.3.0
