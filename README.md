# WarPie - Raspberry Pi Wardriving Platform

A complete wardriving system for Raspberry Pi 4B with dual-band WiFi capture, BTLE scanning, GPS logging, and automatic network management.

## Features

- **Dual-Band WiFi Capture**: Simultaneous 2.4GHz and 5/6GHz WiFi monitoring
- **BTLE Support**: Optional Bluetooth Low Energy scanning with TI CC2540
- **GPS Integration**: Location logging with GlobalSat BU-353S4 (or compatible)
- **Auto Network Switching**: Connects to home WiFi when in range, creates AP when mobile
- **Web Control Panel**: Flask-based control interface with cyberpunk terminal theme (port 1337)
- **Network Filtering**: Static exclusions (MAC-based) and dynamic exclusions (SSID-based)
- **Interactive Setup**: Guided configuration for home networks and exclusions
- **Multiple Capture Modes**:
  - **Normal**: Full capture with home network exclusion
  - **Wardrive**: Optimized AP-only scanning for mobile use

## Hardware Requirements

- Raspberry Pi 4B (4GB+ recommended)
- USB WiFi Adapter 1: ALFA AWUS036AXML (5GHz/6GHz)
- USB WiFi Adapter 2: RT3070-based (2.4GHz)
- GPS: GlobalSat BU-353S4 or similar USB GPS
- Optional: TI CC2540 BTLE adapter
- Power: 5V 3A USB-C power supply
- Storage: 32GB+ microSD card

## Quick Start

For detailed installation instructions, see [docs/INSTALLATION.md](docs/INSTALLATION.md).

```bash
# Copy install.sh to your Pi
scp install/install.sh pi@warpie:~/

# SSH in and run installer
ssh pi@warpie
chmod +x install.sh
sudo ./install.sh
```

The installer will guide you through:
1. **Home Network Setup** - Enter your WiFi SSID, it auto-discovers all BSSIDs
2. **Kismet Exclusions** - Choose to exclude home network from wardriving logs
3. **Additional Exclusions** - Optionally exclude neighbor/work networks

## Usage

### Installation Options

```bash
sudo ./install.sh              # Full install with interactive setup
sudo ./install.sh --test       # Validate installation (26 checks)
sudo ./install.sh --configure  # Re-run WiFi and filter configuration
sudo ./install.sh --uninstall  # Remove WarPie
sudo ./install.sh --help       # Show help
```

### After Installation

1. **Access Control Panel**: Browse to `http://<pi-ip>:1337`
2. **Access Kismet UI**: Browse to `http://<pi-ip>:2501`
3. **Reboot** to start all services: `sudo reboot`

### AP Mode (Mobile)

When away from home networks, WarPie creates an access point:
- **SSID**: WarPie
- **Password**: wardriving
- **IP**: 192.168.4.1

Connect to this network to access the control panel and Kismet UI while mobile.

## Kismet Modes

### Normal Mode
Full device capture with home network exclusion. Good for stationary monitoring.

### Wardrive Mode
Optimized for mobile scanning:
- AP-only tracking (no clients)
- Faster channel hopping (150ms dwell)
- Management frames only
- Lower CPU/memory usage

## Network Filtering

WarPie supports two filtering paradigms for excluding unwanted networks:

### Static Exclusions
For networks with stable MAC addresses (home, neighbors, corporate):
- Discovers BSSIDs from SSID
- Adds to Kismet blocklist
- Blocked at capture time (most efficient)

### Dynamic Exclusions
For networks with rotating MAC addresses (iPhone hotspots, Android):
- Stores SSID pattern only
- Post-processing removal by filter processor daemon
- Never adds to MAC blocklist (MACs rotate)

## Configuration Files

| File | Location | Purpose |
|------|----------|---------|
| Known BSSIDs | `/etc/warpie/known_bssids.conf` | Home network list for AP switching |
| Filter Rules | `/etc/warpie/filter_rules.conf` | Static/dynamic exclusion rules |
| Adapter Config | `/etc/warpie/adapters.conf` | WiFi adapter band/channel settings |
| Kismet Site | `/etc/kismet/kismet_site.conf` | GPS config, exclusion filters |
| Wardrive Mode | `/etc/kismet/kismet_wardrive.conf` | Optimized scanning settings |

## Services

| Service | Purpose |
|---------|---------|
| `gpsd-wardriver` | GPS daemon |
| `warpie-network` | Auto AP/client switching |
| `wardrive` | Kismet capture |
| `warpie-control` | Web control panel (port 1337) |
| `warpie-filter-processor` | Dynamic exclusion post-processing |

### Service Commands

```bash
# View service status
systemctl status wardrive

# View logs
journalctl -u wardrive -f

# Restart Kismet
sudo systemctl restart wardrive

# Recovery (restore normal WiFi)
sudo warpie-recovery.sh
```

## Filter Management

```bash
# List all exclusions
sudo warpie-filter-manager.py --list

# Add static exclusion (stable MAC network)
sudo warpie-filter-manager.py --add-static "HomeNetwork"

# Add dynamic exclusion (rotating MAC network)
sudo warpie-filter-manager.py --add-dynamic "iPhone-*"

# JSON mode for scripting
sudo warpie-filter-manager.py --json --list
```

## Reconfiguring

To change your home network or exclusions after installation:

```bash
sudo ./install.sh --configure
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

Kismet creates WiGLE-compatible CSV files in `/home/pi/kismet/`. Upload these to [wigle.net](https://wigle.net) to contribute to the wireless network database.

## Documentation

| Document | Description |
|----------|-------------|
| [INSTALLATION.md](docs/INSTALLATION.md) | Detailed setup guide |
| [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Diagnostic procedures |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design |
| [QUICK_REFERENCE.md](docs/QUICK_REFERENCE.md) | Field reference card |

## Project Structure

```
/etc/warpie/                    # Configuration
  known_bssids.conf             # Home network BSSIDs
  filter_rules.conf             # Exclusion/targeting rules
  adapters.conf                 # WiFi adapter settings

/etc/kismet/                    # Kismet configs
  kismet_site.conf              # Main config + exclusions
  kismet_wardrive.conf          # Wardrive mode

/usr/local/bin/                 # Scripts
  warpie-network-manager.sh     # AP/client switching
  wardrive.sh                   # Kismet launcher
  warpie-control                # Web control panel
  warpie-filter-manager.py      # Filter CLI tool
  warpie-filter-processor.py    # Post-processing daemon
  warpie-recovery.sh            # Emergency recovery

/var/log/warpie/                # Logs
/home/pi/kismet/                # Capture files
```

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
