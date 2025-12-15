# WarPie Architecture

System design and component interaction for the WarPie platform.

## System Overview

WarPie is a wardriving platform that manages:
- Dual-band WiFi capture with Kismet
- Intelligent network switching (home vs mobile AP)
- GPS location tracking
- Web-based control interface

## Hardware Layout

```
┌─────────────────────────────────────────────────────────────┐
│                     Raspberry Pi 4B                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   wlan0      │  │   wlan1      │  │   wlan2      │     │
│  │  (onboard)   │  │  (AWUS036)   │  │  (RT3070)    │     │
│  │   2.4/5GHz   │  │   5/6GHz     │  │   2.4GHz     │     │
│  │              │  │              │  │              │     │
│  │  Network     │  │  Kismet      │  │  Kismet      │     │
│  │  Connection  │  │  Monitor     │  │  Monitor     │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│                                                             │
│  ┌──────────────────────────────────────────────────┐      │
│  │                    GPS                            │      │
│  │              GlobalSat BU-353S4                   │      │
│  │                 /dev/gps0                         │      │
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
│                    └── Start web control panel (port 1337)  │
└─────────────────────────────────────────────────────────────┘
```

## Component Interaction

```
┌──────────────────┐     ┌──────────────────┐
│  warpie-control  │────►│     Kismet       │
│   (port 1337)    │     │   (port 2501)    │
│                  │     │                  │
│  - Mode switch   │     │  - Network data  │
│  - Log viewer    │     │  - GPS location  │
│  - Filter mgmt   │     │  - Capture files │
└──────────────────┘     └──────────────────┘
         │                        │
         │                        │
         ▼                        ▼
┌──────────────────────────────────────────┐
│           Configuration Files             │
│                                          │
│  /usr/local/etc/kismet_site.conf         │
│  /usr/local/etc/kismet_wardrive.conf     │
│  /etc/warpie/known_bssids.conf           │
│  /etc/warpie/filter_rules.conf           │
└──────────────────────────────────────────┘
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
├── filter_rules.conf           # SSID exclusion rules
└── ssid_exclusions.conf        # Legacy exclusions

/usr/local/etc/                 # Kismet configuration
├── kismet_site.conf            # Main config + exclusions
└── kismet_wardrive.conf        # Wardrive mode settings

/usr/local/bin/                 # Executable scripts
├── network-manager.sh          # AP/client switching
├── wardrive.sh                 # Kismet launcher
├── warpie-control.py           # Web control panel
├── warpie-exclude-ssid.sh      # Filter CLI
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

WarPie supports two filtering paradigms:

### Static Exclusions
For networks with stable MACs (home, neighbors):
- SSID → BSSID discovery
- Added to Kismet blocklist
- Blocked at capture time

### Dynamic Exclusions
For networks with rotating MACs (phone hotspots):
- SSID pattern stored only
- Post-processing removal
- Never added to blocklist

```
┌─────────────────┐     ┌─────────────────┐
│  Static (MAC)   │     │ Dynamic (SSID)  │
│                 │     │                 │
│  "HomeNetwork"  │     │  "iPhone-*"     │
│       │         │     │       │         │
│       ▼         │     │       ▼         │
│  Discover BSSID │     │  Store pattern  │
│       │         │     │       │         │
│       ▼         │     │       ▼         │
│  Kismet block   │     │  Post-process   │
└─────────────────┘     └─────────────────┘
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
