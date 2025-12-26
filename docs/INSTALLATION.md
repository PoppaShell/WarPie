# WarPie Installation Guide

Complete installation guide for WarPie on Raspberry Pi.

## Prerequisites

### Minimum Requirements

| Component    | Requirement                                        |
| ------------ | -------------------------------------------------- |
| Platform     | Raspberry Pi 4B or newer                           |
| OS           | Raspberry Pi OS (64-bit recommended)               |
| GPS          | Any gpsd-compatible USB GPS receiver               |
| WiFi Adapter | At least one Kismet-supported monitor-mode adapter |
| Power        | 5V 3A USB-C (sufficient for Pi + adapters)         |
| Storage      | 32GB+ microSD (larger for extended captures)       |

### Optional Hardware

- **Additional WiFi adapters** for multi-band coverage (2.4GHz + 5GHz + 6GHz)
- **BTLE adapter** (e.g., TI CC2540) for Bluetooth Low Energy scanning

### WiFi Interface Mapping

The installer auto-detects adapters and lets you assign roles:

| Role | Purpose | Example |
|------|---------|---------|
| AP Interface | Home WiFi client / Mobile AP | Onboard wlan0 |
| Capture Interface(s) | Kismet monitor mode | USB adapters |

You'll configure bands and channels per adapter during installation.

## Installation Methods

### Option 1: Release Tarball (Recommended)

Download the latest release - smaller and includes only runtime files (~128KB):

```bash
# Download and extract
VERSION=2.4.1
curl -L "https://github.com/PoppaShell/WarPie/releases/download/v${VERSION}/warpie-${VERSION}.tar.gz" | tar xz
cd warpie-${VERSION}
sudo ./install/install.sh
```

### Option 2: Git Clone

Clone the full repository (includes development files, tests, CI):

```bash
git clone https://github.com/PoppaShell/WarPie.git
cd WarPie
sudo ./install/install.sh
```

Use this if you want to contribute or need the full development environment.

### Installer Options

```bash
sudo ./install/install.sh              # Full install with interactive setup
sudo ./install/install.sh --test       # Validate installation (26 checks)
sudo ./install/install.sh --configure  # Re-run WiFi and filter configuration
sudo ./install/install.sh --uninstall  # Remove WarPie
sudo ./install/install.sh --help       # Show all options
```

## Interactive Setup

The installer guides you through:

1. **WiFi Adapter Configuration**
   - Select AP interface (for home WiFi and mobile AP)
   - Select capture interface(s) for Kismet
   - Configure bands per adapter (2.4GHz, 5GHz, 6GHz)
   - Set channel lists or use defaults

2. **Home Network Setup**
   - Enter home WiFi SSID and password
   - Discover BSSIDs for your home APs (supports mesh networks)
   - Configure Kismet exclusions for home networks

3. **Optional Configuration**
   - Add neighbor network exclusions
   - Configure BTLE adapter (if detected)
   - Set Kismet auto-start mode (wardrive/normal/targeted)

## Post-Installation

### Verify Installation

```bash
sudo ./install/install.sh --test
```

This runs 26 validation checks covering services, configs, and permissions.

### Reboot

```bash
sudo reboot
```

Services start automatically after reboot.

### Access Points

| Service       | URL                       | Purpose                       |
| ------------- | ------------------------- | ----------------------------- |
| Control Panel | `http://<pi-ip>:1337`     | Mode switching, logs, filters |
| Kismet UI     | `http://<pi-ip>:2501`     | Network viewer                |

### Default AP Credentials

When away from home networks, WarPie creates an access point:

- **SSID**: WarPie
- **Password**: wardriving
- **Gateway IP**: 10.0.0.1

## Manual Installation

For advanced users who want to understand or customize the setup.

### 1. Install Dependencies

```bash
sudo apt update
sudo apt install -y gpsd gpsd-clients kismet hostapd dnsmasq python3-pip
pip3 install flask waitress inquirerpy rich
```

### 2. Configure Udev Rules

Create `/etc/udev/rules.d/70-warpie-wifi.rules` to pin interface names by MAC:

```bash
# Replace with your actual MAC addresses
SUBSYSTEM=="net", ACTION=="add", ATTR{address}=="xx:xx:xx:xx:xx:xx", NAME="wlan0"
SUBSYSTEM=="net", ACTION=="add", ATTR{address}=="yy:yy:yy:yy:yy:yy", NAME="wlan1"
SUBSYSTEM=="net", ACTION=="add", ATTR{address}=="zz:zz:zz:zz:zz:zz", NAME="wlan2"
```

Apply the rules:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### 3. Create Directories

```bash
sudo mkdir -p /etc/warpie
sudo mkdir -p /var/log/warpie
sudo mkdir -p /var/log/kismet/logs
sudo chown -R root:kismet /var/log/kismet
sudo chmod -R 775 /var/log/kismet
```

### 4. Configure Known BSSIDs

Create `/etc/warpie/known_bssids.conf`:

```text
# Format: BSSID|SSID|PRIORITY|DESCRIPTION
# Higher priority = preferred connection
94:2a:6f:0c:ed:85|HomeNetwork|10|Primary router - 5GHz
74:83:c2:8a:23:4c|HomeNetwork|20|Mesh node - 2.4GHz
```

### 5. Configure WPA Supplicant

Create `/etc/wpa_supplicant/wpa_supplicant-wlan0.conf`:

```ini
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=US

network={
    ssid="HomeNetwork"
    bssid=94:2a:6f:0c:ed:85
    psk="your_password"
    key_mgmt=WPA-PSK
    priority=10
}
```

### 6. Configure hostapd (AP Mode)

Create `/etc/hostapd/hostapd-wlan0.conf`:

```ini
interface=wlan0
driver=nl80211
ssid=WarPie
hw_mode=g
channel=6
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=wardriving
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
```

### 7. Install Scripts

```bash
sudo cp bin/warpie-network-manager.sh /usr/local/bin/
sudo cp bin/wardrive.sh /usr/local/bin/
sudo cp bin/warpie-control /usr/local/bin/
sudo cp bin/warpie-filter-manager.py /usr/local/bin/
sudo cp bin/warpie-filter-processor.py /usr/local/bin/
sudo cp -r web /usr/local/lib/warpie-web
sudo chmod +x /usr/local/bin/warpie-*
sudo chmod +x /usr/local/bin/wardrive.sh
```

### 8. Configure Systemd Services

```bash
sudo cp systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl mask gpsd.service gpsd.socket
sudo systemctl enable gpsd-wardriver
sudo systemctl enable warpie-network
sudo systemctl enable wardrive
sudo systemctl enable warpie-control
sudo systemctl enable warpie-filter-processor
```

### 9. Reboot

```bash
sudo reboot
```

## Adding Trusted Networks

### Add a Mesh Node or Additional AP

1. Get the BSSID while connected:

   ```bash
   iw dev wlan0 link | grep -i bssid
   ```

2. Add to `/etc/warpie/known_bssids.conf`:

   ```text
   XX:XX:XX:XX:XX:XX|HomeNetwork|20|Mesh node - upstairs
   ```

3. Add to `/etc/wpa_supplicant/wpa_supplicant-wlan0.conf`:

   ```ini
   network={
       ssid="HomeNetwork"
       bssid=XX:XX:XX:XX:XX:XX
       psk="your_password"
       key_mgmt=WPA-PSK
       priority=20
   }
   ```

4. Restart the network service:

   ```bash
   sudo systemctl restart warpie-network
   ```

## Reconfiguration

To change settings after installation:

```bash
sudo ./install/install.sh --configure
```

This lets you:

- Change home network SSID/password
- Re-scan for WiFi adapters
- Update Kismet exclusions
- Add additional trusted BSSIDs
- Change startup mode

## Uninstallation

```bash
sudo ./install/install.sh --uninstall
```

This removes all WarPie configurations and restores default networking.

## Troubleshooting Installation

### Enable Persistent Journal Logs

For debugging issues that persist across reboots:

```bash
sudo mkdir -p /var/log/journal
sudo sed -i 's/#Storage=auto/Storage=persistent/' /etc/systemd/journald.conf
sudo systemctl restart systemd-journald
```

Then view logs with:

```bash
journalctl -u warpie-network -u wardrive -u warpie-control --since "1 hour ago"
```

### Common Issues

| Issue | Solution |
|-------|----------|
| Adapters not detected | Ensure USB adapters are connected before running installer |
| Kismet won't start | Run `sudo make suidinstall` in Kismet source directory |
| GPS not working | Check `/dev/ttyUSB0` exists, verify with `gpsmon` |
| AP mode not starting | Verify hostapd config, check `journalctl -u warpie-network` |

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for detailed diagnostic procedures.

## Tested Hardware

The following hardware has been verified with WarPie:

| Component      | Model                  | Driver      | Notes                        |
| -------------- | ---------------------- | ----------- | ---------------------------- |
| SBC            | Raspberry Pi 4B (4GB)  | -           | Primary development platform |
| WiFi (5/6GHz)  | ALFA AWUS036AXML       | mt7921u     | Excellent 6GHz support       |
| WiFi (2.4GHz)  | RT3070-based adapter   | rt2800usb   | Reliable 2.4GHz monitor mode |
| GPS            | GlobalSat BU-353S4     | -           | USB GPS, works with gpsd     |
| BTLE           | TI CC2540              | -           | Optional, for BLE scanning   |

Other Kismet-supported adapters should work. See [Kismet documentation](https://www.kismetwireless.net/) for compatibility lists.
