# WarPie Troubleshooting Guide

Diagnostic procedures for common WarPie issues.

## Quick Diagnostics

Run the validation suite first:
```bash
sudo ./install.sh --test
```

## GPS Issues

### GPS Not Working

#### 1. Check Device Exists
```bash
ls -la /dev/ttyUSB*
ls -la /dev/serial/by-id/
```

Expected output: `/dev/ttyUSB0` or similar device file.

#### 2. Check gpsd Service
```bash
systemctl status gpsd-wardriver
journalctl -u gpsd-wardriver -n 20
```

#### 3. Test Raw GPS Data
```bash
sudo cat /dev/ttyUSB0
```

You should see NMEA sentences:
```
$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,47.0,M,,*47
$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A
```

#### 4. Check for Conflicting Services
```bash
systemctl status gpsd.socket
```
Should show "masked". If not:
```bash
sudo systemctl mask gpsd.service gpsd.socket
sudo systemctl restart gpsd-wardriver
```

#### 5. Test GPS Clients
```bash
cgps -s          # Text-based status
gpspipe -w -n 10 # Raw JSON output
gpsmon           # Interactive monitor
```

### GPS Fix Takes Too Long

GPS cold start can take 2-5 minutes. For faster fixes:
- Place the GPS receiver with clear sky view
- Wait for satellite acquisition before starting wardriving
- The BU-353S4 LED blinks when it has a fix

## WiFi Adapter Issues

### Interface Not Found

#### 1. Check USB Devices
```bash
lsusb
```

Expected output includes:
- MediaTek MT7921 (AWUS036AXML)
- Ralink RT3070 (2.4GHz adapter)

#### 2. Check Interface Names
```bash
iw dev
ip link show | grep wlan
```

Should show `wlan0`, `wlan1`, `wlan2`.

#### 3. Check Udev Rules
```bash
cat /etc/udev/rules.d/70-persistent-wifi.rules
```

Reload rules if changed:
```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

#### 4. Check MAC Addresses
```bash
ip link show | grep -A1 wlan
```

Compare MACs with udev rules configuration.

### Monitor Mode Not Working

#### 1. Check Current Mode
```bash
iw dev
```

Look for `type monitor` on wlan1 and wlan2.

#### 2. Manually Set Monitor Mode
```bash
sudo ip link set wlan1 down
sudo iw dev wlan1 set type monitor
sudo ip link set wlan1 up
```

#### 3. Check rfkill Status
```bash
rfkill list
```

Unblock if needed:
```bash
sudo rfkill unblock wifi
```

## Network Mode Issues

### AP Mode Not Starting

#### 1. Check hostapd Status
```bash
systemctl status hostapd
journalctl -u warpie-network -n 30
```

#### 2. Test hostapd Manually
```bash
sudo hostapd -dd /etc/hostapd/hostapd-wlan0.conf
```

Look for errors in the output.

#### 3. Check Interface State
```bash
iw dev wlan0 info
```

wlan0 must not be connected to another network when starting AP.

#### 4. Check DHCP Server
```bash
systemctl status dnsmasq
cat /var/log/warpie/dnsmasq.log
```

### Client Mode Not Connecting

#### 1. Scan for Networks
```bash
sudo iw dev wlan0 scan | grep -E "SSID|signal|BSS "
```

#### 2. Check WPA Supplicant
```bash
sudo wpa_cli -i wlan0 status
sudo wpa_cli -i wlan0 list_networks
```

#### 3. Manual Connection Test
```bash
sudo wpa_supplicant -i wlan0 -c /etc/wpa_supplicant/wpa_supplicant-wlan0.conf -d
```

#### 4. Verify BSSID Configuration
```bash
cat /etc/warpie/known_bssids.conf
```

Ensure BSSIDs match your actual access points.

## Kismet Issues

### Kismet Not Starting

#### 1. Check Service Status
```bash
systemctl status wardrive
journalctl -u wardrive -f
```

#### 2. Check Web Interface
```bash
curl -s http://localhost:2501/system/status.json | head
```

#### 3. Start Kismet Manually
```bash
sudo kismet -c wlan1 -c wlan2 --no-ncurses
```

Look for initialization errors.

#### 4. Check Permissions
```bash
ls -la ~/kismet/logs/
```

### Kismet UI Not Accessible

#### 1. Check Listening Port
```bash
ss -tlnp | grep 2501
```

#### 2. Check Firewall
```bash
sudo iptables -L -n | grep 2501
```

#### 3. Test Locally
```bash
curl http://localhost:2501
```

## Control Panel Issues

### Control Panel Not Accessible

#### 1. Check Service
```bash
systemctl status warpie-control
journalctl -u warpie-control -n 30
```

#### 2. Test Locally
```bash
curl http://localhost:1337
```

#### 3. Check Port
```bash
ss -tlnp | grep 1337
```

### Mode Switch Not Working

#### 1. Check Kismet API
```bash
curl -s http://localhost:2501/system/status.json
```

#### 2. Check Config Files
```bash
ls -la /usr/local/etc/kismet*.conf
```

## Service Recovery

### Emergency Recovery

If networking is broken, use the recovery script:
```bash
sudo warpie-recovery.sh
```

This:
- Stops all WarPie services
- Restores default network configuration
- Enables standard NetworkManager

### Restart All Services

```bash
sudo systemctl restart gpsd-wardriver
sudo systemctl restart warpie-network
sudo systemctl restart wardrive
sudo systemctl restart warpie-control
```

### View All Logs

```bash
# All WarPie logs
journalctl -u 'warpie-*' -u wardrive -u gpsd-wardriver -f

# Specific service
journalctl -u wardrive -f
```

## Log Locations

| Log | Location | Purpose |
|-----|----------|---------|
| Network Manager | `/var/log/warpie/network-manager.log` | Network decisions |
| Wardrive | `/var/log/warpie/wardrive.log` | Kismet startup |
| DHCP | `/var/log/warpie/dnsmasq.log` | AP mode DHCP |
| Kismet Captures | `~/kismet/logs/` | Wireless data |
| System Journal | `journalctl -u <service>` | Service logs |
