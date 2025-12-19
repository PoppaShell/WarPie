#!/bin/bash
# WarPie Intelligent WiFi Network Manager
# Automatically switches between home WiFi (client mode) and WarPie AP (access point mode)

set -euo pipefail

# Configuration
ADAPTERS_CONF="/etc/warpie/adapters.conf"
LOG_FILE="/var/log/warpie/network-manager.log"
SCAN_INTERVAL=30
WPA_SUPPLICANT_CONF="/etc/wpa_supplicant/wpa_supplicant.conf"
HOSTAPD_CONF="/etc/hostapd/hostapd.conf"

# Colors for logging
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Current mode tracking
CURRENT_MODE=""  # "client" or "ap"

# Logging function
log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    # Log to file
    echo "[${timestamp}] [${level}] ${message}" >> "${LOG_FILE}"

    # Also log to systemd journal
    case "${level}" in
        ERROR)
            echo -e "${RED}[${level}]${NC} ${message}" >&2
            ;;
        SUCCESS)
            echo -e "${GREEN}[${level}]${NC} ${message}"
            ;;
        WARN)
            echo -e "${YELLOW}[${level}]${NC} ${message}"
            ;;
        *)
            echo -e "${BLUE}[${level}]${NC} ${message}"
            ;;
    esac
}

# Load configuration
load_config() {
    if [[ ! -f "${ADAPTERS_CONF}" ]]; then
        log ERROR "Configuration file not found: ${ADAPTERS_CONF}"
        return 1
    fi

    # shellcheck source=/dev/null
    source "${ADAPTERS_CONF}"

    # Validate required variables
    if [[ -z "${WIFI_AP:-}" ]]; then
        log ERROR "WIFI_AP not defined in configuration"
        return 1
    fi

    if [[ -z "${HOME_WIFI_ENABLED:-}" ]]; then
        log WARN "HOME_WIFI_ENABLED not defined, defaulting to false"
        HOME_WIFI_ENABLED="false"
    fi

    log INFO "Configuration loaded: AP=${WIFI_AP}, HOME_WIFI_ENABLED=${HOME_WIFI_ENABLED}"
    return 0
}

# Check if interface exists
interface_exists() {
    local iface="$1"
    [[ -d "/sys/class/net/${iface}" ]]
}

# Check if home WiFi is in range
home_wifi_in_range() {
    local ssid="${HOME_WIFI_SSID}"
    local iface="${WIFI_AP}"

    # Bring interface up if needed
    if ! ip link show "${iface}" 2>/dev/null | grep -q "state UP"; then
        log INFO "Bringing ${iface} up for scanning"
        ip link set "${iface}" up 2>/dev/null || true
        sleep 2
    fi

    # Scan for networks (use || true to prevent pipefail crash)
    log INFO "Scanning for home WiFi: ${ssid}"
    local scan_result
    scan_result=$(iw dev "${iface}" scan 2>/dev/null || true)
    if echo "${scan_result}" | grep -q "SSID: ${ssid}"; then
        log INFO "Home WiFi detected: ${ssid}"
        return 0
    else
        log INFO "Home WiFi not in range: ${ssid}"
        return 1
    fi
}

# Switch to client mode (connect to home WiFi)
switch_to_client_mode() {
    log INFO "Switching to CLIENT mode..."

    # Stop hostapd if running
    if systemctl is-active --quiet hostapd; then
        log INFO "Stopping hostapd..."
        systemctl stop hostapd || log WARN "Failed to stop hostapd"
    fi

    # Stop dnsmasq if running
    if systemctl is-active --quiet dnsmasq; then
        log INFO "Stopping dnsmasq..."
        systemctl stop dnsmasq || log WARN "Failed to stop dnsmasq"
    fi

    # Flush any existing IP addresses (removes AP mode static IP)
    log INFO "Flushing existing IP addresses..."
    ip addr flush dev "${WIFI_AP}" 2>/dev/null || true

    # Configure wpa_supplicant for home WiFi
    log INFO "Configuring wpa_supplicant for ${HOME_WIFI_SSID}..."

    # Create wpa_supplicant configuration
    cat > "${WPA_SUPPLICANT_CONF}" <<EOF
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=US

network={
    ssid="${HOME_WIFI_SSID}"
    psk=${HOME_WIFI_PSK}
    key_mgmt=WPA-PSK
}
EOF

    # Start wpa_supplicant
    log INFO "Starting wpa_supplicant on ${WIFI_AP}..."
    wpa_supplicant -B -i "${WIFI_AP}" -c "${WPA_SUPPLICANT_CONF}" -P /var/run/wpa_supplicant.pid 2>/dev/null || {
        log WARN "wpa_supplicant already running or failed to start"
    }

    # Request DHCP address using dhcpcd (standard on Raspberry Pi OS)
    log INFO "Requesting DHCP address via dhcpcd..."
    dhcpcd -n "${WIFI_AP}" 2>&1 | while read -r line; do
        log INFO "DHCP: ${line}"
    done

    # Wait for connection
    sleep 5

    # Check if we got an IP (exclude 10.0.0.x which is the AP range)
    local ip_output ip_address
    ip_output=$(ip addr show "${WIFI_AP}" 2>/dev/null || true)
    ip_address=$(echo "${ip_output}" | grep "inet " | grep -v "10.0.0." | awk '{print $2}' | cut -d'/' -f1 | head -1 || true)
    if [[ -n "${ip_address}" ]]; then
        log SUCCESS "Connected to home WiFi: ${HOME_WIFI_SSID} (IP: ${ip_address})"
        CURRENT_MODE="client"
        return 0
    else
        log ERROR "Failed to get IP address from home WiFi"
        return 1
    fi
}

# Switch to AP mode (start WarPie access point)
switch_to_ap_mode() {
    log INFO "Switching to AP mode..."

    # Kill wpa_supplicant if running
    if [[ -f /var/run/wpa_supplicant.pid ]]; then
        log INFO "Stopping wpa_supplicant..."
        kill "$(cat /var/run/wpa_supplicant.pid)" 2>/dev/null || true
        rm -f /var/run/wpa_supplicant.pid
    fi
    # Also kill any wpa_supplicant processes we didn't start
    pkill -f "wpa_supplicant.*${WIFI_AP}" 2>/dev/null || true

    # Release DHCP lease using dhcpcd
    log INFO "Releasing DHCP lease..."
    dhcpcd -k "${WIFI_AP}" 2>/dev/null || true

    # Configure static IP for AP
    log INFO "Configuring static IP for AP..."
    ip addr flush dev "${WIFI_AP}" 2>/dev/null || true
    ip addr add 10.0.0.1/24 dev "${WIFI_AP}" 2>/dev/null || {
        log WARN "Failed to set static IP (may already be set)"
    }
    ip link set "${WIFI_AP}" up

    # Start dnsmasq
    log INFO "Starting dnsmasq..."
    systemctl start dnsmasq || log WARN "Failed to start dnsmasq"

    # Start hostapd
    log INFO "Starting hostapd..."
    systemctl start hostapd || log WARN "Failed to start hostapd"

    sleep 3

    # Verify AP is running
    if systemctl is-active --quiet hostapd; then
        log SUCCESS "WarPie AP started successfully"
        CURRENT_MODE="ap"
        return 0
    else
        log ERROR "Failed to start WarPie AP"
        return 1
    fi
}

# Get current mode
detect_current_mode() {
    # Check if hostapd is running (AP mode) - check this first as it's more definitive
    if systemctl is-active --quiet hostapd; then
        CURRENT_MODE="ap"
        return
    fi

    # Check if we have a non-AP IP address on the interface (client mode)
    # This is more reliable than checking for wpa_supplicant process
    # Use intermediate variable to avoid pipefail issues
    local ip_output client_ip
    ip_output=$(ip addr show "${WIFI_AP}" 2>/dev/null || true)
    client_ip=$(echo "${ip_output}" | grep "inet " | grep -v "10.0.0." | awk '{print $2}' | head -1 || true)
    if [[ -n "${client_ip}" ]]; then
        CURRENT_MODE="client"
        return
    fi

    # Check if wpa_supplicant is running for this interface
    if pgrep -f "wpa_supplicant" >/dev/null 2>&1; then
        # wpa_supplicant is running, but we may not have an IP yet
        # Check if interface is associated (use || true to avoid pipefail crash)
        local link_status
        link_status=$(iw dev "${WIFI_AP}" link 2>/dev/null || true)
        if echo "${link_status}" | grep -q "Connected"; then
            CURRENT_MODE="client"
            return
        fi
    fi

    # No mode active
    CURRENT_MODE=""
}

# Main monitoring loop
main() {
    log INFO "========================================="
    log INFO "WarPie Network Manager Starting"
    log INFO "========================================="

    # Ensure log directory exists
    mkdir -p "$(dirname "${LOG_FILE}")"

    # Load configuration
    if ! load_config; then
        log ERROR "Failed to load configuration, exiting"
        exit 1
    fi

    # Check if home WiFi is enabled
    if [[ "${HOME_WIFI_ENABLED}" != "true" ]]; then
        log INFO "Home WiFi disabled, ensuring AP mode is active..."
        switch_to_ap_mode
        log INFO "AP mode active. Network manager will monitor only (no switching)."

        # Run minimal monitoring loop
        while true; do
            sleep "${SCAN_INTERVAL}"
            if ! systemctl is-active --quiet hostapd; then
                log WARN "AP went down, restarting..."
                switch_to_ap_mode
            fi
        done
        exit 0
    fi

    # Check if interface exists
    if ! interface_exists "${WIFI_AP}"; then
        log ERROR "WiFi interface ${WIFI_AP} does not exist"
        exit 1
    fi

    log INFO "Home WiFi management enabled for SSID: ${HOME_WIFI_SSID}"
    log INFO "Scan interval: ${SCAN_INTERVAL} seconds"
    log INFO "Starting monitoring loop..."

    # Main loop
    while true; do
        detect_current_mode

        # Check if home WiFi is in range
        if home_wifi_in_range; then
            # Home WiFi available
            if [[ "${CURRENT_MODE}" != "client" ]]; then
                log INFO "Home WiFi available, switching from ${CURRENT_MODE:-none} to client mode"
                if switch_to_client_mode; then
                    log SUCCESS "Successfully switched to client mode"
                else
                    log ERROR "Failed to switch to client mode, will retry"
                fi
            else
                log INFO "Already in client mode, connection OK"
            fi
        else
            # Home WiFi not available
            if [[ "${CURRENT_MODE}" != "ap" ]]; then
                log INFO "Home WiFi unavailable, switching from ${CURRENT_MODE:-none} to AP mode"
                if switch_to_ap_mode; then
                    log SUCCESS "Successfully switched to AP mode"
                else
                    log ERROR "Failed to switch to AP mode, will retry"
                fi
            else
                log INFO "Already in AP mode, broadcast OK"
            fi
        fi

        # Wait before next scan
        sleep "${SCAN_INTERVAL}"
    done
}

# Handle signals gracefully
trap 'log INFO "Network manager stopping..."; exit 0' SIGTERM SIGINT

# Run main function
main
