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

# Scan failure tracking - require multiple consecutive failures before switching
# This prevents flip-flopping due to intermittent scan failures (common on Broadcom)
SCAN_FAIL_COUNT=0
SCAN_FAIL_THRESHOLD=3  # Require 3 consecutive failures before switching to AP

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

# Wait for a condition with timeout and retries
# Usage: wait_for_condition "description" "check_command" max_attempts delay_seconds
wait_for_condition() {
    local description="$1"
    local check_cmd="$2"
    local max_attempts="${3:-10}"
    local delay="${4:-1}"
    local attempt=1

    while [[ ${attempt} -le ${max_attempts} ]]; do
        if eval "${check_cmd}"; then
            return 0
        fi
        log INFO "Waiting for ${description}... (${attempt}/${max_attempts})"
        sleep "${delay}"
        ((attempt++))
    done

    log ERROR "Timeout waiting for ${description}"
    return 1
}

# Start a service with retry logic
# Usage: start_service_with_retry "service_name" max_attempts
start_service_with_retry() {
    local service="$1"
    local max_attempts="${2:-3}"
    local attempt=1

    while [[ ${attempt} -le ${max_attempts} ]]; do
        log INFO "Starting ${service}... (attempt ${attempt}/${max_attempts})"

        # Stop first to ensure clean state
        systemctl stop "${service}" 2>/dev/null || true
        sleep 1

        # Start the service
        if systemctl start "${service}"; then
            # Verify it's actually running
            sleep 1
            if systemctl is-active --quiet "${service}"; then
                log SUCCESS "${service} started successfully"
                return 0
            fi
        fi

        log WARN "${service} failed to start, retrying..."
        ((attempt++))
        sleep 2
    done

    log ERROR "Failed to start ${service} after ${max_attempts} attempts"
    return 1
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

    # Scan for networks
    log INFO "Scanning for home WiFi: ${ssid}"
    local scan_result
    scan_result=$(iw dev "${iface}" scan 2>/dev/null || true)

    # Use [[ ]] pattern match instead of grep to avoid broken pipe issues
    if [[ "${scan_result}" == *"SSID: ${ssid}"* ]]; then
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

    # Wait for services to stop
    wait_for_condition "hostapd to stop" "! systemctl is-active --quiet hostapd" 5 1 || true
    wait_for_condition "dnsmasq to stop" "! systemctl is-active --quiet dnsmasq" 5 1 || true

    # Kill any existing wpa_supplicant on this interface (including NetworkManager's)
    log INFO "Stopping any existing wpa_supplicant..."
    pkill -f "wpa_supplicant.*${WIFI_AP}" 2>/dev/null || true
    rm -f "/var/run/wpa_supplicant/${WIFI_AP}" 2>/dev/null || true

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

    # Wait for wpa_supplicant to associate with AP
    if ! wait_for_condition "wpa_supplicant to associate with ${HOME_WIFI_SSID}" \
        "iw dev ${WIFI_AP} link 2>/dev/null | grep -q 'Connected'" 15 1; then
        log ERROR "wpa_supplicant failed to associate with ${HOME_WIFI_SSID}"
        return 1
    fi
    log SUCCESS "Associated with ${HOME_WIFI_SSID}"

    # Request DHCP address (run in background so we can poll for IP)
    log INFO "Requesting DHCP address via dhcpcd..."
    dhcpcd -n "${WIFI_AP}" 2>/dev/null &

    # Wait for IP address (exclude AP range 10.0.0.x)
    if ! wait_for_condition "DHCP IP address on ${WIFI_AP}" \
        "ip addr show ${WIFI_AP} 2>/dev/null | grep 'inet ' | grep -v '10.0.0.' | grep -q 'inet '" 20 1; then
        log ERROR "Failed to get DHCP IP address"
        return 1
    fi

    # Get and log the IP
    local ip_output ip_address
    ip_output=$(ip addr show "${WIFI_AP}" 2>/dev/null || true)
    ip_address=$(echo "${ip_output}" | grep "inet " | grep -v "10.0.0." | awk '{print $2}' | cut -d'/' -f1 | head -1 || true)

    log SUCCESS "Connected to home WiFi: ${HOME_WIFI_SSID} (IP: ${ip_address})"
    CURRENT_MODE="client"
    return 0
}

# Switch to AP mode (start WarPie access point)
switch_to_ap_mode() {
    log INFO "Switching to AP mode..."

    # =========================================================================
    # STEP 1: Stop all conflicting services (clean slate)
    # =========================================================================
    log INFO "Stopping conflicting services..."

    # Stop wpa_supplicant
    if [[ -f /var/run/wpa_supplicant.pid ]]; then
        kill "$(cat /var/run/wpa_supplicant.pid)" 2>/dev/null || true
        rm -f /var/run/wpa_supplicant.pid
    fi
    pkill -f "wpa_supplicant.*${WIFI_AP}" 2>/dev/null || true

    # Release DHCP lease
    dhcpcd -k "${WIFI_AP}" 2>/dev/null || true

    # Stop hostapd and dnsmasq if running (ensures clean slate)
    systemctl stop dnsmasq 2>/dev/null || true
    systemctl stop hostapd 2>/dev/null || true

    # Wait for services to fully stop
    wait_for_condition "hostapd to stop" \
        "! systemctl is-active --quiet hostapd" 5 1 || true
    wait_for_condition "dnsmasq to stop" \
        "! systemctl is-active --quiet dnsmasq" 5 1 || true

    # =========================================================================
    # STEP 2: Configure interface with static IP
    # =========================================================================
    log INFO "Configuring static IP for AP..."

    # Flush and bring interface down for clean state
    ip addr flush dev "${WIFI_AP}" 2>/dev/null || true
    ip link set "${WIFI_AP}" down 2>/dev/null || true
    sleep 1

    # Bring interface up and assign IP
    ip link set "${WIFI_AP}" up
    ip addr add 10.0.0.1/24 dev "${WIFI_AP}" 2>/dev/null || {
        # Check if already set (not an error)
        if ! ip addr show "${WIFI_AP}" 2>/dev/null | grep -q "10.0.0.1"; then
            log ERROR "Failed to set static IP on ${WIFI_AP}"
            return 1
        fi
    }

    # VERIFY: Wait for IP to be visible on interface
    if ! wait_for_condition "IP address 10.0.0.1 on ${WIFI_AP}" \
        "ip addr show ${WIFI_AP} 2>/dev/null | grep -q '10.0.0.1'" 5 1; then
        log ERROR "Static IP not applied to ${WIFI_AP}"
        return 1
    fi
    log SUCCESS "Static IP 10.0.0.1 configured on ${WIFI_AP}"

    # =========================================================================
    # STEP 3: Start hostapd (puts interface in AP mode)
    # =========================================================================
    if ! start_service_with_retry "hostapd" 3; then
        log ERROR "hostapd failed to start after retries"
        return 1
    fi

    # VERIFY: Interface is in AP mode
    if ! wait_for_condition "interface in AP mode" \
        "iw dev ${WIFI_AP} info 2>/dev/null | grep -q 'type AP'" 5 1; then
        log ERROR "${WIFI_AP} not in AP mode after hostapd start"
        systemctl stop hostapd 2>/dev/null || true
        return 1
    fi
    log SUCCESS "${WIFI_AP} is now in AP mode"

    # =========================================================================
    # STEP 4: Start dnsmasq (DHCP server for clients)
    # =========================================================================
    if ! start_service_with_retry "dnsmasq" 3; then
        log WARN "dnsmasq failed to start - AP will work but clients won't get DHCP"
        # Don't fail completely - AP can still work with manual IP config
    fi

    # =========================================================================
    # FINAL VERIFICATION
    # =========================================================================
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
        # Check if interface is associated
        local link_status
        link_status=$(iw dev "${WIFI_AP}" link 2>/dev/null || true)
        if [[ "${link_status}" == *"Connected"* ]]; then
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
            # Home WiFi available - reset failure counter
            SCAN_FAIL_COUNT=0

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
            # Home WiFi not detected in scan
            ((SCAN_FAIL_COUNT++)) || true

            if [[ "${CURRENT_MODE}" == "client" ]]; then
                # Currently in client mode - be conservative about switching
                if [[ ${SCAN_FAIL_COUNT} -ge ${SCAN_FAIL_THRESHOLD} ]]; then
                    log INFO "Home WiFi not detected for ${SCAN_FAIL_COUNT} consecutive scans, switching to AP mode"
                    if switch_to_ap_mode; then
                        log SUCCESS "Successfully switched to AP mode"
                        SCAN_FAIL_COUNT=0
                    else
                        log ERROR "Failed to switch to AP mode, will retry"
                    fi
                else
                    log INFO "Home WiFi not in scan (${SCAN_FAIL_COUNT}/${SCAN_FAIL_THRESHOLD}), staying in client mode"
                fi
            elif [[ "${CURRENT_MODE}" != "ap" ]]; then
                # Not in any mode yet - switch to AP immediately
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
