# WarPie - Raspberry Pi Wardriving Platform

A complete wardriving and wireless research platform for Raspberry Pi OS, featuring multi-adapter WiFi capture, GPS logging, and a mobile-optimized web interface.

## Features

- **Multi-Adapter WiFi Capture**: Balance channels across multiple adapters with per-adapter band configuration
- **GPS Integration**: Location-tagged network logging for mapping and analysis
- **Automatic Network Switching**: Seamlessly switches between home WiFi and mobile access point
- **Web Control Panel**: Flask-based mobile interface with cyberpunk terminal theme (port 1337)
- **Network Filtering**: Static exclusions (MAC-based) and dynamic exclusions (pattern-based with wildcards)
- **Multiple Capture Modes**:
  - **Normal**: Full device capture with exclusions applied
  - **Wardrive**: AP-only optimized scanning for mobile use
  - **Targeted**: Target specific device manufacturers by OUI prefix
- **Optional BTLE Scanning**: Bluetooth Low Energy capture with supported adapters

## Minimum Requirements

| Component    | Requirement                                        |
| ------------ | -------------------------------------------------- |
| Platform     | Raspberry Pi 4B or newer                           |
| OS           | Raspberry Pi OS (64-bit recommended)               |
| GPS          | Any gpsd-compatible USB GPS receiver               |
| WiFi Adapter | At least one Kismet-supported monitor-mode adapter |
| Power        | 5V 3A USB-C (sufficient for Pi + adapters)         |
| Storage      | 32GB+ microSD (larger for extended captures)       |

### Optional Hardware

- **Additional WiFi adapters** for multi-band coverage
- **BTLE adapter** (e.g., TI CC2540) for Bluetooth scanning

## Quick Start

### Option 1: Release Tarball (Recommended)

```bash
# Download and extract latest release
VERSION=2.4.1
curl -L "https://github.com/PoppaShell/WarPie/releases/download/v${VERSION}/warpie-${VERSION}.tar.gz" | tar xz
cd warpie-${VERSION}
sudo ./install/install.sh
```

This downloads only runtime files (~128KB) - no dev tooling, tests, or node_modules.

### Option 2: Clone Repository

```bash
git clone https://github.com/PoppaShell/WarPie.git
cd WarPie
sudo ./install/install.sh
```

Use this if you want to contribute or need the full development environment.

The installer will guide you through:

1. WiFi adapter configuration (AP vs capture, bands, channels)
2. Home network BSSID discovery
3. Optional network exclusions
4. GPS device detection

### After Installation

1. **Reboot** to start all services: `sudo reboot`
2. **Access Control Panel**: `http://<pi-ip>:1337`
3. **Access Kismet UI**: `http://<pi-ip>:2501`

### Installation Options

```bash
sudo ./install/install.sh              # Full install with interactive setup
sudo ./install/install.sh --test       # Validate installation (26 checks)
sudo ./install/install.sh --configure  # Re-run WiFi and filter configuration
sudo ./install/install.sh --uninstall  # Remove WarPie
sudo ./install/install.sh --help       # Show help
```

## AP Mode (Mobile)

When away from configured home networks, WarPie creates an access point:

- **SSID**: WarPie
- **Password**: wardriving
- **IP**: 10.0.0.1

Connect to this network to access the control panel and Kismet UI while mobile.

## Capture Modes

### Normal Mode

Full device capture (APs and clients) with exclusion filters applied. Best for stationary monitoring.

### Wardrive Mode

Optimized for mobile scanning:

- AP-only tracking (no clients)
- Faster channel hopping (150ms dwell)
- Management frames only
- Lower CPU/memory usage

### Targeted Mode

Target specific device manufacturers by OUI prefix:

- Create custom target lists with OUI patterns (format: `XX:XX:XX:*`)
- Select one or more lists per capture session
- Capture only devices matching the patterns

## Network Filtering

### Static Exclusions

Block networks at capture time via BSSID. For networks with stable MAC addresses (home routers, corporate APs). Discovers BSSIDs from SSID scanning.

### Dynamic Exclusions

Removed during post-processing. For networks with rotating MACs. Wildcards supported:

- `Guest*` - matches Guest, Guest-5G
- `*Hotspot` - matches MyHotspot
- `Net?ork` - matches Network, Netw0rk

## Configuration Files

| File            | Location                          | Purpose                          |
| --------------- | --------------------------------- | -------------------------------- |
| Adapter Config  | `/etc/warpie/adapters.conf`       | Per-adapter band/channel settings |
| Known BSSIDs    | `/etc/warpie/known_bssids.conf`   | Home networks for AP switching   |
| Filter Rules    | `/etc/warpie/filter_rules.conf`   | Exclusions and target lists      |
| Kismet Site     | `/etc/kismet/kismet_site.conf`    | Main Kismet config + GPS         |
| Kismet Wardrive | `/etc/kismet/kismet_wardrive.conf` | Wardrive/Targeted optimizations  |

## Services

| Service                   | Purpose                            |
| ------------------------- | ---------------------------------- |
| `gpsd-wardriver`          | GPS daemon for location tagging    |
| `warpie-network`          | Auto AP/client network switching   |
| `wardrive`                | Kismet capture (all modes)         |
| `warpie-control`          | Web control panel (port 1337)      |
| `warpie-filter-processor` | Dynamic exclusion post-processing  |

## Service Commands

```bash
# View service status
systemctl status wardrive warpie-control warpie-network

# View live logs
journalctl -u wardrive -f

# Restart capture
sudo systemctl restart wardrive

# Recovery (restore normal WiFi)
sudo systemctl stop warpie-network
sudo ip link set wlan0 down
```

### Enable Persistent Logs (Recommended for Troubleshooting)

```bash
sudo mkdir -p /var/log/journal
sudo systemctl restart systemd-journald
```

## Filter Management

```bash
# List all exclusions
sudo warpie-filter-manager.py --list

# Add static exclusion (stable MAC network)
sudo warpie-filter-manager.py --add-static "HomeNetwork"

# Add dynamic exclusion (rotating MAC network)
sudo warpie-filter-manager.py --add-dynamic "Guest*"

# JSON mode for scripting
sudo warpie-filter-manager.py --json --list
```

## Reconfiguring

To change your home network or exclusions after installation:

```bash
sudo ./install/install.sh --configure
```

This lets you:

- Change home network SSID
- Add/remove Kismet exclusions
- Scan for new networks

## Troubleshooting

For detailed troubleshooting, see [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

### GPS Not Working

```bash
# Check GPS device
ls -la /dev/ttyUSB*
ls -la /dev/serial/by-id/

# Test GPS output
gpspipe -w -n 10

# Check service
systemctl status gpsd-wardriver
```

### WiFi Adapters Not Found

```bash
# List adapters
iw dev

# Check USB devices
lsusb

# View kernel messages
dmesg | grep -i wifi
```

### Control Panel Not Accessible

```bash
# Check service
systemctl status warpie-control

# Check for errors
journalctl -u warpie-control -n 30

# Test locally
curl http://localhost:1337
```

### Can't Connect to AP Mode

```bash
# Check hostapd
journalctl -u warpie-network

# Manual recovery
sudo warpie-recovery.sh
```

## WiGLE Upload

Kismet creates WiGLE-compatible CSV files organized by mode and date:

```text
/var/log/kismet/logs/<mode>/<date>/*.wiglecsv
```

Upload these to [wigle.net](https://wigle.net) to contribute to the wireless network database.

## Project Structure

```text
/etc/warpie/                    # WarPie configuration
  adapters.conf                 # WiFi adapter settings
  known_bssids.conf             # Home network BSSIDs
  filter_rules.conf             # Exclusions and target lists

/etc/kismet/                    # Kismet configuration
  kismet_site.conf              # Main config + GPS
  kismet_wardrive.conf          # Wardrive/Targeted mode

/usr/local/bin/                 # Executable scripts
  warpie-network-manager.sh     # AP/client switching
  wardrive.sh                   # Kismet launcher
  warpie-control                # Web control panel
  warpie-filter-manager.py      # Filter CLI tool
  warpie-filter-processor.py    # Post-processing daemon

/var/log/warpie/                # Application logs
/var/log/kismet/logs/           # Kismet capture files
```

## Documentation

| Document                                             | Description            |
| ---------------------------------------------------- | ---------------------- |
| [INSTALLATION.md](docs/INSTALLATION.md)              | Detailed setup guide   |
| [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)        | Diagnostic procedures  |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md)              | System design          |
| [QUICK_REFERENCE.md](docs/QUICK_REFERENCE.md)        | Field reference card   |

## Tested Hardware

The following hardware has been tested with WarPie:

| Component      | Model                  | Notes                       |
| -------------- | ---------------------- | --------------------------- |
| SBC            | Raspberry Pi 4B (4GB)  | Primary development platform |
| WiFi (5/6GHz)  | ALFA AWUS036AXML       | mt7921u driver              |
| WiFi (2.4GHz)  | RT3070-based adapter   | rt2800usb driver            |
| GPS            | GlobalSat BU-353S4     | USB GPS receiver            |
| BTLE           | TI CC2540              | Optional, for BLE scanning  |

Other Kismet-supported adapters should work. See [Kismet documentation](https://www.kismetwireless.net/) for compatibility.

## License

GPL-3.0-or-later

## Credits

Built with:

- [Kismet](https://www.kismetwireless.net/) - Wireless network detector
- [gpsd](https://gpsd.gitlab.io/gpsd/) - GPS daemon
- [Flask](https://flask.palletsprojects.com/) - Web framework
- [HTMX](https://htmx.org/) - Frontend interactivity
- [Waitress](https://docs.pylonsproject.org/projects/waitress/) - WSGI server
- Raspberry Pi OS
