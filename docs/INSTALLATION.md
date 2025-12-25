# WarPie Installation Guide

Detailed installation instructions for WarPie on Raspberry Pi 4B.

## Prerequisites

### Required Hardware

| Component | Model | Purpose |
|-----------|-------|---------|
| Raspberry Pi | 4B (4GB+ recommended) | Main platform |
| WiFi Adapter 1 | ALFA AWUS036AXML | 5GHz/6GHz monitor |
| WiFi Adapter 2 | RT3070-based | 2.4GHz monitor |
| GPS | GlobalSat BU-353S4 | Location tracking |
| Power | 5V 3A USB-C | Reliable power |
| Storage | 32GB+ microSD | OS and logs |

### Optional Hardware

| Component | Model | Purpose |
|-----------|-------|---------|
| BTLE Adapter | TI CC2540 | Bluetooth Low Energy scanning |

### WiFi Interface Mapping

| Interface | Device | Bands | Purpose |
|-----------|--------|-------|---------|
| wlan0 | Onboard RPi | 2.4/5GHz | Home network / AP |
| wlan1 | AWUS036AXML | 5/6GHz | Kismet monitor |
| wlan2 | RT3070 | 2.4GHz | Kismet monitor |

## Installation Methods

### Quick Install (Recommended)

```bash
# Copy install.sh to your Pi
scp install/install.sh pi@warpie:~/

# SSH in and run
ssh pi@warpie
chmod +x install.sh
sudo ./install.sh
```

The installer guides you through:

1. Home network SSID and password
2. BSSID discovery for your home APs
3. Kismet exclusion configuration
4. Optional neighbor network exclusions

### Manual Installation

#### 1. Install Dependencies

```bash
sudo apt update
sudo apt install -y gpsd gpsd-clients kismet hostapd dnsmasq python3-pip
pip3 install flask waitress
```

#### 2. Configure Udev Rules

Create `/etc/udev/rules.d/70-persistent-wifi.rules`:

```bash
# Map MAC addresses to consistent interface names
# Replace with your actual MAC addresses
SUBSYSTEM=="net", ACTION=="add", ATTR{address}=="d8:3a:dd:6c:0e:c1", NAME="wlan0"
SUBSYSTEM=="net", ACTION=="add", ATTR{address}=="00:c0:ca:b8:ff:ac", NAME="wlan1"
SUBSYSTEM=="net", ACTION=="add", ATTR{address}=="00:c0:ca:89:21:7e", NAME="wlan2"
```

Apply the rules:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

#### 3. Create Configuration Directory

```bash
sudo mkdir -p /etc/warpie
sudo mkdir -p /var/log/warpie
mkdir -p ~/kismet/logs
```

#### 4. Configure Known BSSIDs

Create `/etc/warpie/known_bssids.conf`:

```
# Format: BSSID|SSID|PRIORITY|DESCRIPTION
# Higher priority = preferred connection
94:2a:6f:0c:ed:85|HomeNetwork|10|Primary router - 5GHz
74:83:c2:8a:23:4c|HomeNetwork|20|Mesh node - 2.4GHz
```

#### 5. Configure WPA Supplicant

Create `/etc/wpa_supplicant/wpa_supplicant-wlan0.conf`:

```
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

#### 6. Configure hostapd (AP Mode)

Create `/etc/hostapd/hostapd-wlan0.conf`:

```
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

#### 7. Install Scripts

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

#### 8. Configure Systemd Services

Install service units and enable:

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

#### 9. Reboot

```bash
sudo reboot
```

## Post-Installation

### Verify Installation

```bash
sudo ./install.sh --test
```

This runs 26 validation checks on your installation.

### Access Points

| Service | URL | Purpose |
|---------|-----|---------|
| Control Panel | http://<pi-ip>:1337 | Mode switching, logs, filters |
| Kismet UI | http://<pi-ip>:2501 | Network viewer |

### Default AP Credentials

When away from home, WarPie creates an access point:

- **SSID**: WarPie
- **Password**: wardriving
- **Gateway IP**: 10.0.0.1

## Adding Trusted Networks

### Add a Mesh Node or Additional AP

1. Get the BSSID while connected:

   ```bash
   iw dev wlan0 link | grep -i bssid
   ```

2. Add to `/etc/warpie/known_bssids.conf`:

   ```
   XX:XX:XX:XX:XX:XX|HomeNetwork|20|Mesh node - upstairs
   ```

3. Add to `/etc/wpa_supplicant/wpa_supplicant-wlan0.conf`:

   ```
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
sudo ./install.sh --configure
```

This lets you:

- Change home network SSID
- Update Kismet exclusions
- Scan for new networks
- Add additional trusted BSSIDs

## Uninstallation

```bash
sudo ./install.sh --uninstall
```

This removes all WarPie configurations and restores default networking.
