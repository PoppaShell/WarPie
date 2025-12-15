# WarPie - Raspberry Pi Wardriving Platform

## Table of Contents

1. [Overview](#overview)
2. [Hardware Configuration](#hardware-configuration)
3. [Architecture](#architecture)
4. [Installation](#installation)
5. [Configuration Files](#configuration-files)
6. [Services](#services)
7. [Usage](#usage)
8. [Troubleshooting](#troubleshooting)
9. [Adding Trusted Networks](#adding-trusted-networks)
10. [File Locations](#file-locations)

---

## Overview

WarPie is a comprehensive wardriving platform built on Raspberry Pi. It features:

- **Dual WiFi adapter monitoring** for simultaneous 2.4GHz and 5GHz/6GHz capture
- **Intelligent network switching** between home network and mobile Access Point
- **BSSID-pinned connections** for security against evil twin attacks
- **GPS integration** for location tagging and time synchronization
- **Kismet** for wireless network detection and logging

### Key Features

| Feature | Description |
|---------|-------------|
| Tri-band WiFi capture | 2.4GHz, 5GHz, and 6GHz (WiFi 6E) |
| Auto AP fallback | Creates hotspot when away from home |
| BSSID security | Prevents connection to spoofed networks |
| GPS time sync | Accurate timestamps even without internet |
| Web interface | Kismet UI accessible from any device |

---

## Hardware Configuration

### WiFi Adapters

| Interface | Device | Chipset | Bands | Purpose |
|-----------|--------|---------|-------|---------|
| wlan0 | Onboard RPi | BCM43455 | 2.4/5GHz | Home network / AP |
| wlan1 | Alfa AWUS036AXML | MT7921AU | 2.4/5/6GHz | Kismet monitor (5/6GHz) |
| wlan2 | Alfa RT3070 | RT3070 | 2.4GHz | Kismet monitor (2.4GHz) |

### GPS

| Device | Model | Interface | Baud Rate |
|--------|-------|-----------|-----------|
| GPS | GlobalSat BU-353-S4 | /dev/ttyUSB0 | 4800 |

### Interface Pinning

Interfaces are pinned to consistent names via udev rules based on MAC address.
This ensures the same physical adapter always gets the same interface name
regardless of USB port or boot order.

**MAC Address Assignments:**
```
d8:3a:dd:6c:0e:c1 → wlan0 (Onboard)
00:c0:ca:b8:ff:ac → wlan1 (AWUS036AXML)
00:c0:ca:89:21:7e → wlan2 (RT3070)
```

**HOME Network BSSIDs:**
```
94:2a:6f:0c:ed:85 → HOME AP 1
74:83:c2:8a:23:4c → HOME AP 2
```

---

## Architecture

### Network Modes

WarPie operates in two network modes:

#### Client Mode (Home)
```
┌─────────────────────────────────────────────────────────┐
│                      HOME NETWORK                        │
│  ┌──────────┐                                           │
│  │  Router  │◄─────── wlan0 (connected via BSSID)       │
│  └──────────┘                                           │
└─────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │     WarPie        │
                    │  ┌─────────────┐  │
                    │  │   Kismet    │  │
                    │  │  wlan1 (5G) │  │
                    │  │  wlan2 (2.4)│  │
                    │  └─────────────┘  │
                    └───────────────────┘
```

#### AP Mode (Mobile)
```
┌─────────────────────────────────────────────────────────┐
│                    WARPIE ACCESS POINT                   │
│                                                         │
│    Phone/Laptop ──────► wlan0 (AP: "WarPie")           │
│         │                    │                          │
│         │              192.168.4.1                      │
│         │                    │                          │
│         └──────► Kismet UI (port 2501)                 │
│                SSH access (port 22)                     │
└─────────────────────────────────────────────────────────┘
                    │
          ┌─────────┴─────────┐
          │     WarPie        │
          │  ┌─────────────┐  │
          │  │   Kismet    │  │
          │  │  wlan1 (5G) │  │
          │  │  wlan2 (2.4)│  │
          │  └─────────────┘  │
          └───────────────────┘
```

### Boot Sequence

```
1. System boot
   │
2. udev rules apply (interface naming)
   │
3. gpsd-wardriver.service starts
   │   └── GPS device initialization
   │
4. warpie-network.service starts
   │   ├── Scan for WiFi networks
   │   ├── Check against known BSSIDs
   │   └── Connect to network OR start AP
   │
5. wardrive.service starts
   │   ├── Configure wlan1 monitor mode
   │   ├── Configure wlan2 monitor mode
   │   ├── Attempt GPS time sync
   │   └── Start Kismet
   │
6. Ready for wardriving!
```

---

## Installation

### Prerequisites

```bash
sudo apt update
sudo apt install -y gpsd gpsd-clients kismet hostapd dnsmasq
```

### Installation Steps

1. **Copy udev rules:**
   ```bash
   sudo cp /path/to/70-persistent-wifi.rules /etc/udev/rules.d/
   sudo udevadm control --reload-rules
   sudo udevadm trigger
   ```

2. **Create configuration directory:**
   ```bash
   sudo mkdir -p /etc/warpie
   sudo cp known_bssids.conf /etc/warpie/
   ```

3. **Install WPA supplicant config:**
   ```bash
   sudo cp wpa_supplicant-wlan0.conf /etc/wpa_supplicant/
   ```

4. **Install hostapd config:**
   ```bash
   sudo cp hostapd-wlan0.conf /etc/hostapd/
   ```

5. **Install scripts:**
   ```bash
   sudo cp network-manager.sh /usr/local/bin/
   sudo cp wardrive.sh /usr/local/bin/
   sudo chmod +x /usr/local/bin/network-manager.sh
   sudo chmod +x /usr/local/bin/wardrive.sh
   ```

6. **Install systemd services:**
   ```bash
   sudo cp gpsd-wardriver.service /etc/systemd/system/
   sudo cp wardrive.service /etc/systemd/system/
   sudo cp warpie-network.service /etc/systemd/system/
   ```

7. **Mask conflicting services:**
   ```bash
   sudo systemctl mask gpsd.service gpsd.socket
   ```

8. **Enable services:**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable gpsd-wardriver
   sudo systemctl enable warpie-network
   sudo systemctl enable wardrive
   ```

9. **Create log directory:**
   ```bash
   sudo mkdir -p /var/log/warpie
   mkdir -p ~/kismet_logs
   ```

10. **Set your WiFi password:**
    ```bash
    sudo warpie-set-password
    ```

11. **Reboot to apply all changes:**
    ```bash
    sudo reboot
    ```

---

## Configuration Files

### /etc/warpie/known_bssids.conf

List of trusted networks (by BSSID) that WarPie will connect to.

**Format:** `BSSID|SSID|PRIORITY|DESCRIPTION`

```
# Home Networks
7a:83:c2:8b:23:4c|HOME|10|Primary router - 5GHz

# Add mesh nodes or other APs:
# aa:bb:cc:dd:ee:ff|HOME|20|Mesh node upstairs
```

### /etc/wpa_supplicant/wpa_supplicant-wlan0.conf

WPA supplicant configuration with BSSID-pinned networks.

**Important:** You must edit this file to add your actual WiFi password!

### /etc/hostapd/hostapd-wlan0.conf

Access Point configuration for mobile mode.

**Default credentials:**
- SSID: `WarPie`
- Password: `wardriving`
- IP: `192.168.4.1`

**Security Note:** Change the default password before using in public!

### /etc/udev/rules.d/70-persistent-wifi.rules

Maps MAC addresses to consistent interface names.

---

## Services

### gpsd-wardriver.service

Manages the GPS daemon for the GlobalSat BU-353-S4.

```bash
sudo systemctl status gpsd-wardriver
sudo systemctl restart gpsd-wardriver
journalctl -u gpsd-wardriver -f
```

### warpie-network.service

Manages intelligent network switching (client vs AP mode).

```bash
sudo systemctl status warpie-network
sudo systemctl restart warpie-network
journalctl -u warpie-network -f
```

### wardrive.service

Manages Kismet and WiFi monitoring.

```bash
sudo systemctl status wardrive
sudo systemctl restart wardrive
journalctl -u wardrive -f
```

---

## Usage

### Normal Operation

After installation and reboot, WarPie operates automatically:

1. If home network detected → connects and starts Kismet
2. If away from home → starts AP and Kismet

### Accessing Kismet Web UI

**When connected to home network:**
```
http://<pi-ip>:2501
```

**When using WarPie AP:**
```
1. Connect phone/laptop to "WarPie" WiFi
2. Open http://192.168.4.1:2501
```

### Manual Network Mode Switching

```bash
# Force Access Point mode
/usr/local/bin/network-manager.sh --force-ap

# Force client mode (will fail if no known networks)
/usr/local/bin/network-manager.sh --force-client

# Just scan without changing anything
/usr/local/bin/network-manager.sh --scan-only
```

### Checking GPS Status

```bash
# Text-based GPS client
cgps

# Raw GPS data
gpspipe -w -n 10

# GPS monitor
gpsmon
```

### Checking WiFi Status

```bash
# View all interfaces
iw dev

# Check wlan0 connection
iw dev wlan0 link

# View adapter capabilities
iw phy phy0 info | head -50
```

---

## Troubleshooting

### GPS Not Working

1. **Check device exists:**
   ```bash
   ls -la /dev/ttyUSB0
   ```

2. **Check gpsd is running:**
   ```bash
   sudo systemctl status gpsd-wardriver
   ```

3. **Test raw GPS data:**
   ```bash
   sudo cat /dev/ttyUSB0
   ```
   You should see NMEA sentences ($GPGGA, $GPRMC, etc.)

4. **Check for conflicting services:**
   ```bash
   sudo systemctl status gpsd.socket
   # Should show "masked"
   ```

### WiFi Interface Not Found

1. **Check udev rules applied:**
   ```bash
   ls -la /etc/udev/rules.d/70-persistent-wifi.rules
   sudo udevadm control --reload-rules
   sudo udevadm trigger
   ```

2. **Verify MAC addresses:**
   ```bash
   ip link show | grep -A1 wlan
   ```

3. **Check USB devices:**
   ```bash
   lsusb
   ```

### AP Mode Not Starting

1. **Check hostapd status:**
   ```bash
   sudo systemctl status hostapd
   sudo hostapd -dd /etc/hostapd/hostapd-wlan0.conf
   ```

2. **Check for interface conflicts:**
   ```bash
   # wlan0 should not be connected to another network
   iw dev wlan0 link
   ```

### Kismet Not Starting

1. **Check service status:**
   ```bash
   sudo systemctl status wardrive
   journalctl -u wardrive -f
   ```

2. **Check adapters are in monitor mode:**
   ```bash
   iw dev
   # Should show "type monitor" for wlan1 and wlan2
   ```

3. **Start Kismet manually:**
   ```bash
   sudo kismet -c wlan1 -c wlan2 --no-ncurses
   ```

---

## Adding Trusted Networks

### Adding a New Home Network (Mesh Node, etc.)

1. **Connect to the network and get BSSID:**
   ```bash
   iw dev wlan0 link | grep -i bssid
   ```

2. **Add to /etc/warpie/known_bssids.conf:**
   ```
   XX:XX:XX:XX:XX:XX|HOME|20|Mesh node - upstairs
   ```

3. **Add to /etc/wpa_supplicant/wpa_supplicant-wlan0.conf:**
   ```
   network={
       ssid="HOME"
       bssid=XX:XX:XX:XX:XX:XX
       psk="your_password"
       key_mgmt=WPA-PSK
       priority=20
   }
   ```

4. **Restart network service:**
   ```bash
   sudo systemctl restart warpie-network
   ```

### Adding a Work/Other Network

Same process as above, but use a different SSID and adjust priority
(higher number = lower priority).

---

## File Locations

### Configuration Files
| File | Purpose |
|------|---------|
| `/etc/warpie/known_bssids.conf` | Trusted network BSSIDs |
| `/etc/wpa_supplicant/wpa_supplicant-wlan0.conf` | WiFi credentials |
| `/etc/hostapd/hostapd-wlan0.conf` | Access Point settings |
| `/etc/udev/rules.d/70-persistent-wifi.rules` | Interface naming |

### Scripts
| File | Purpose |
|------|---------|
| `/usr/local/bin/network-manager.sh` | Network mode switching |
| `/usr/local/bin/wardrive.sh` | Wardriving service |

### Systemd Services
| File | Purpose |
|------|---------|
| `/etc/systemd/system/gpsd-wardriver.service` | GPS daemon |
| `/etc/systemd/system/warpie-network.service` | Network manager |
| `/etc/systemd/system/wardrive.service` | Wardriving service |

### Logs
| File | Purpose |
|------|---------|
| `/var/log/warpie/network-manager.log` | Network decisions |
| `/var/log/warpie/wardrive.log` | Wardriving activity |
| `/var/log/warpie/dnsmasq.log` | DHCP server (AP mode) |
| `/home/pi/kismet_logs/` | Kismet capture files |

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2025-12-11 | Initial release |

---

## License

This configuration is provided as-is for educational and personal use.

---

## Credits

- Kismet: https://www.kismetwireless.net/
- GPSD: https://gpsd.gitlab.io/gpsd/
- Raspberry Pi Foundation
