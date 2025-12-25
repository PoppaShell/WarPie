# WarPie Quick Reference Card

## Network Connections

### Home Mode (Connected to HOME)

```
Control Panel:  http://<pi-ip>:1337
Kismet UI:      http://<pi-ip>:2501
SSH:            ssh pi@<pi-ip>
```

### Mobile Mode (AP Active)

```
WiFi SSID:      WarPie
Password:       wardriving
Control Panel:  http://10.0.0.1:1337
Kismet UI:      http://10.0.0.1:2501
SSH:            ssh pi@10.0.0.1
```

---

## Common Commands

### Service Control

```bash
# Check all services
sudo systemctl status gpsd-wardriver warpie-network wardrive warpie-control

# Restart wardriving
sudo systemctl restart wardrive

# Force AP mode
sudo warpie-network-manager.sh --force-ap

# Scan networks
sudo warpie-network-manager.sh --scan-only

# Set/change WiFi password
sudo warpie-set-password
```

### Filter Management

```bash
# List all exclusions
sudo warpie-filter-manager.py --list

# Add static exclusion (stable MAC network)
sudo warpie-filter-manager.py --add-static "NetworkName"

# Add dynamic exclusion (rotating MAC network)
sudo warpie-filter-manager.py --add-dynamic "iPhone-*"

# Remove an exclusion
sudo warpie-filter-manager.py --remove "NetworkName"

# JSON mode for scripting
sudo warpie-filter-manager.py --json --list
```

### GPS

```bash
cgps                    # Interactive GPS display
gpspipe -w -n 5         # Raw JSON output
gpsmon                  # Detailed GPS monitor
```

### WiFi Diagnostics

```bash
iw dev                  # Show all interfaces
iw dev wlan0 link       # Check connection status
iw dev wlan1 info       # Check adapter mode
```

### Logs

```bash
# Live service logs
journalctl -u wardrive -f
journalctl -u gpsd-wardriver -f
journalctl -u warpie-network -f
journalctl -u warpie-control -f

# Application logs
tail -f /var/log/warpie/wardrive.log
tail -f /var/log/warpie/network-manager.log
```

---

## Adding a New Trusted Network

1. Get the BSSID:

   ```bash
   iw dev wlan0 link | grep -i bssid
   ```

2. Edit `/etc/warpie/known_bssids.conf`:

   ```
   XX:XX:XX:XX:XX:XX|SSID|PRIORITY|Description
   ```

3. Edit `/etc/wpa_supplicant/wpa_supplicant-wlan0.conf` and add:

   ```
   network={
       ssid="SSID"
       bssid=XX:XX:XX:XX:XX:XX
       psk=PLACEHOLDER_RUN_WARPIE_SET_PASSWORD
       key_mgmt=WPA-PSK
       priority=20
   }
   ```

4. Set the password:

   ```bash
   sudo warpie-set-password --ssid SSID
   ```

5. Restart:

   ```bash
   sudo systemctl restart warpie-network
   ```

---

## Interface Assignments

| Interface | Device | MAC | Role |
|-----------|--------|-----|------|
| wlan0 | Onboard | d8:3a:dd:6c:0e:c1 | Home/AP |
| wlan1 | AWUS036AXML | 00:c0:ca:b8:ff:ac | Kismet 5/6GHz |
| wlan2 | RT3070 | 00:c0:ca:89:21:7e | Kismet 2.4GHz |
| /dev/ttyUSB0 | BU-353-S4 | - | GPS |

## HOME Network BSSIDs

| BSSID | Description |
|-------|-------------|
| 94:2a:6f:0c:ed:85 | HOME AP 1 |
| 74:83:c2:8a:23:4c | HOME AP 2 |

---

## Troubleshooting

### GPS No Fix

- Move device to location with sky view
- Check antenna connection
- Verify: `ls /dev/ttyUSB0`

### Kismet Not Starting

- Check: `sudo systemctl status wardrive`
- Logs: `journalctl -u wardrive -f`
- Manual: `sudo kismet -c wlan1 --no-ncurses`

### Can't Connect to AP

- Verify AP mode: `iw dev wlan0 info`
- Check hostapd: `sudo systemctl status hostapd`
- Debug: `sudo hostapd -dd /etc/hostapd/hostapd-wlan0.conf`

### Interface Names Wrong

- Reload udev: `sudo udevadm control --reload-rules && sudo udevadm trigger`
- Check MACs: `ip link show | grep -A1 wlan`

### Control Panel Not Loading

- Check: `sudo systemctl status warpie-control`
- Logs: `journalctl -u warpie-control -n 50`
- Test: `curl http://localhost:1337`
