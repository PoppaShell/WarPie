# WarPie Architecture

System design and component interaction for the WarPie platform.

## System Overview

WarPie is a wardriving platform that manages:

- Dual-band WiFi capture with Kismet
- Optional BTLE scanning
- Intelligent network switching (home vs mobile AP)
- GPS location tracking
- Flask-based web control interface

## Hardware Layout

```
┌─────────────────────────────────────────────────────────────┐
│                     Raspberry Pi 4B                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   wlan0      │  │   wlan1      │  │   wlan2      │      │
│  │  (onboard)   │  │  (AWUS036)   │  │  (RT3070)    │      │
│  │   2.4/5GHz   │  │   5/6GHz     │  │   2.4GHz     │      │
│  │              │  │              │  │              │      │
│  │  Network     │  │  Kismet      │  │  Kismet      │      │
│  │  Connection  │  │  Monitor     │  │  Monitor     │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                             │
│  ┌──────────────────────────────────────────────────┐      │
│  │                    GPS                            │      │
│  │              GlobalSat BU-353S4                   │      │
│  │                 /dev/gps0                         │      │
│  └──────────────────────────────────────────────────┘      │
│                                                             │
│  ┌──────────────────────────────────────────────────┐      │
│  │              BTLE (Optional)                      │      │
│  │              TI CC2540 Adapter                    │      │
│  └──────────────────────────────────────────────────┘      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Network Modes

### Client Mode (At Home)

```
┌─────────────────────────────────────────────────────────────┐
│                      HOME NETWORK                           │
│  ┌──────────┐                                               │
│  │  Router  │◄─────── wlan0 (BSSID-pinned connection)       │
│  └──────────┘                                               │
└─────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │     WarPie        │
                    │  ┌─────────────┐  │
                    │  │   Kismet    │  │
                    │  │  wlan1 (5G) │  │
                    │  │  wlan2 (2.4)│  │
                    │  └─────────────┘  │
                    │                   │
                    │  Port 1337: Web   │
                    │  Port 2501: Kismet│
                    └───────────────────┘
```

**Behavior:**

- Connects to home network using BSSID-pinned configuration
- Prevents evil twin attacks by requiring specific MAC address
- All services accessible on home network IP

### AP Mode (Mobile)

```
┌─────────────────────────────────────────────────────────────┐
│                    WARPIE ACCESS POINT                      │
│                                                             │
│    Phone/Laptop ──────► wlan0 (AP: "WarPie")               │
│         │                    │                              │
│         │              192.168.4.1                          │
│         │                    │                              │
│         └──────► Web Control (1337)                        │
│                  Kismet UI (2501)                          │
└─────────────────────────────────────────────────────────────┘
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

**Behavior:**

- Creates WiFi hotspot when no home network detected
- Provides DHCP via dnsmasq
- Access UI at 192.168.4.1

## Service Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Boot Sequence                            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 1. gpsd-wardriver.service                   │
│                    └── Initialize GPS                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 2. warpie-network.service                   │
│                    ├── Scan for WiFi networks               │
│                    ├── Check known BSSIDs                   │
│                    └── Connect OR start AP                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 3. wardrive.service                         │
│                    ├── Set wlan1/2 to monitor mode          │
│                    ├── Sync time from GPS                   │
│                    └── Start Kismet                         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 4. warpie-control.service                   │
│                    └── Start Flask web panel (port 1337)    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 5. warpie-filter-processor.service          │
│                    └── Post-processing daemon for dynamic   │
│                        exclusions                           │
└─────────────────────────────────────────────────────────────┘
```

## Component Interaction

```
┌──────────────────┐     ┌──────────────────┐
│  warpie-control  │────►│     Kismet       │
│   (Flask/HTMX)   │     │   (port 2501)    │
│   (port 1337)    │     │                  │
│                  │     │  - Network data  │
│  - Mode switch   │     │  - GPS location  │
│  - Log viewer    │     │  - Capture files │
│  - Filter mgmt   │     │                  │
└──────────────────┘     └──────────────────┘
         │                        │
         │                        │
         ▼                        ▼
┌──────────────────────────────────────────┐
│           Configuration Files             │
│                                          │
│  /etc/kismet/kismet_site.conf            │
│  /etc/kismet/kismet_wardrive.conf        │
│  /etc/warpie/known_bssids.conf           │
│  /etc/warpie/filter_rules.conf           │
│  /etc/warpie/adapters.conf               │
└──────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────┐
│        warpie-filter-processor           │
│                                          │
│  - Monitors capture files                │
│  - Removes dynamic exclusions            │
│  - Pre-upload sanitization               │
└──────────────────────────────────────────┘
```

## Web Application Structure

```
/workspaces/WarPie/
├── bin/
│   └── warpie-control          # Entry point (Python)
│
└── web/                        # Flask application
    ├── __init__.py
    ├── app.py                  # Application factory
    ├── config.py               # Configuration
    ├── routes/
    │   ├── main.py             # Dashboard, status, modes
    │   ├── filters.py          # Filter management API
    │   ├── targets.py          # Target list management
    │   └── logs.py             # Log viewing
    ├── templates/              # Jinja2 templates
    │   ├── base.html
    │   ├── index.html
    │   └── partials/           # HTMX partials
    └── static/
        ├── css/
        └── js/
            └── htmx.min.js     # HTMX library
```

## Kismet Modes

### Normal Mode

- Full device capture (APs and clients)
- Standard channel dwell times
- Home network excluded from logs

### Wardrive Mode

- AP-only tracking (no clients)
- Fast channel hopping (150ms dwell)
- Management frames only
- Optimized for mobile scanning

## File System Layout

```
/etc/warpie/                    # WarPie configuration
├── known_bssids.conf           # Trusted network BSSIDs
├── filter_rules.conf           # Static/dynamic exclusion rules
├── adapters.conf               # WiFi adapter settings
└── ssid_exclusions.conf        # Legacy exclusions

/etc/kismet/                    # Kismet configuration
├── kismet_site.conf            # Main config + exclusions
└── kismet_wardrive.conf        # Wardrive mode settings

/usr/local/bin/                 # Executable scripts
├── warpie-network-manager.sh   # AP/client switching
├── wardrive.sh                 # Kismet launcher
├── warpie-control              # Web control panel (Flask)
├── warpie-filter-manager.py    # Filter CLI tool
├── warpie-filter-processor.py  # Post-processing daemon
└── warpie-recovery.sh          # Emergency recovery

/var/log/warpie/                # Runtime logs
├── network-manager.log
├── wardrive.log
└── dnsmasq.log

/home/pi/kismet/                # Capture data
└── logs/
    ├── normal/
    └── wardrive/
```

## Network Filtering

WarPie supports three filtering paradigms:

### Static Exclusions

For networks with stable MACs (home, neighbors):

- SSID → BSSID discovery
- Added to Kismet blocklist
- Blocked at capture time (most efficient)

### Dynamic Exclusions

For networks with rotating MACs (phone hotspots):

- SSID pattern stored only
- Post-processing removal by filter processor
- Never added to blocklist (MACs rotate)

### Targeting Inclusions

For focused capture modes:

- OUI prefix matching
- Specific vendor targeting
- Research/testing scenarios

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Static (MAC)   │     │ Dynamic (SSID)  │     │ Targeting (OUI) │
│                 │     │                 │     │                 │
│  "HomeNetwork"  │     │  "iPhone-*"     │     │  "00:1A:2B:*"   │
│       │         │     │       │         │     │       │         │
│       ▼         │     │       ▼         │     │       ▼         │
│  Discover BSSID │     │  Store pattern  │     │  Add to include │
│       │         │     │       │         │     │       │         │
│       ▼         │     │       ▼         │     │       ▼         │
│  Kismet block   │     │  Post-process   │     │  Filter output  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

## Multi-PHY Support

Filter rules support multiple PHY types:

```ini
# /etc/warpie/filter_rules.conf

[wifi_static]
# Stable-MAC WiFi networks blocked at capture
HomeNetwork|AA:BB:CC:DD:EE:FF|Home router

[wifi_dynamic]
# Rotating-MAC WiFi networks removed post-capture
iPhone-*||Mobile hotspots

[btle_static]
# BTLE devices blocked at capture
MyFitbit|11:22:33:44:55:66|Personal device

[btle_dynamic]
# BTLE devices removed post-capture
Apple Watch*||Apple devices

[bt_static]
# Classic Bluetooth blocked at capture

[bt_dynamic]
# Classic Bluetooth removed post-capture
```

## Security Considerations

### BSSID Pinning

Connections use exact BSSID matching to prevent:

- Evil twin attacks
- Rogue access points
- Network impersonation

### Capture Isolation

Monitor interfaces (wlan1, wlan2) are separate from network interface (wlan0):

- No injection capability
- Passive monitoring only
- Network connection unaffected by capture

### Default Credentials

AP mode defaults should be changed before public use:

- **SSID**: WarPie (changeable)
- **Password**: wardriving (change this!)
