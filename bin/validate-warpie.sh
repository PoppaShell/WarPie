#!/bin/bash
# =============================================================================
# WarPie Automated Test Runner
# Final validation for GPS, logging, and WiGLE integration
# =============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[PASS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_fail() { echo -e "${RED}[FAIL]${NC} $1"; }

PASS=0
FAIL=0
WARN=0

test_result() {
    local name="$1"
    local cmd="$2"
    local critical="${3:-false}"
    
    if eval "$cmd" &>/dev/null; then
        log_success "$name"
        ((PASS++))
        return 0
    else
        if [[ "$critical" == "true" ]]; then
            log_fail "$name"
            ((FAIL++))
        else
            log_warn "$name"
            ((WARN++))
        fi
        return 1
    fi
}

echo "============================================================================="
echo "WarPie Automated Test Runner"
echo "============================================================================="
echo ""

TODAY=$(date +%Y-%m-%d)

# =============================================================================
# SYSTEM HEALTH CHECKS
# =============================================================================
echo "--- System Health ---"

test_result "All services are enabled" "
    systemctl is-enabled gpsd-wardriver warpie-network wardrive warpie-control
" true

test_result "GPS device present" "
    [[ -e /dev/ttyUSB0 ]] || [[ -e /dev/serial/by-id/usb-Prolific* ]]
"

# Load adapter config to check configured interfaces
ADAPTERS_CONF="/etc/warpie/adapters.conf"
if [[ -f "${ADAPTERS_CONF}" ]]; then
    # shellcheck source=/dev/null
    source "${ADAPTERS_CONF}"
    read -ra WIFI_CAPTURE_IFACES <<< "${WIFI_CAPTURE_INTERFACES}"
fi

test_result "Adapter configuration exists" "
    [[ -f /etc/warpie/adapters.conf ]]
" true

test_result "WiFi capture adapters detected" "
    for iface in \${WIFI_CAPTURE_IFACES[@]:-wlan1 wlan2}; do
        if [[ -e /sys/class/net/\${iface} ]]; then
            continue
        else
            exit 1
        fi
    done
"

test_result "Control panel accessible" "
    curl -s --max-time 3 http://localhost:1337 | grep -q 'WarPie Control'
"

test_result "Kismet config files exist" "
    [[ -f /usr/local/etc/kismet_site.conf ]] &&
    [[ -f /usr/local/etc/kismet_wardrive.conf ]]
" true

# =============================================================================
# GPS INTEGRATION TESTS
# =============================================================================
echo ""
echo "--- GPS Integration ---"

test_result "GPS daemon is running" "
    systemctl is-active --quiet gpsd-wardriver
"

# Quick GPS test (non-critical since it may take time to get fix)
test_result "GPS responding" "
    timeout 5 gpspipe -w -n 1 | grep -q mode
"

test_result "GPS configured in Kismet" "
    grep -q 'gps=gpsd' /usr/local/etc/kismet_site.conf
"

# =============================================================================
# LOG STRUCTURE TESTS
# =============================================================================
echo ""
echo "--- Log Organization ---"

test_result "Log directory structure exists" "
    [[ -d ~/kismet/logs/normal ]] &&
    [[ -d ~/kismet/logs/wardrive ]]
"

# Check if any logs exist for today
if [[ -d ~/kismet/logs/normal/$TODAY ]] || [[ -d ~/kismet/logs/wardrive/$TODAY ]]; then
    log_info "Found logs for today ($TODAY) - running validation..."
    
    # =============================================================================
    # LOG CONTENT VALIDATION
    # =============================================================================
    echo ""
    echo "--- Log Content Validation ---"
    
    # Check for home network exclusions
    if find ~/kismet/logs -name "*.wiglecsv" -exec grep -l -E "(HOME|GUEST|PoppaShell)" {} \; 2>/dev/null | head -1 >/dev/null; then
        log_fail "Home networks found in WiGLE CSV (exclusions not working)"
        ((FAIL++))
    else
        log_success "Home networks properly excluded from logs"
        ((PASS++))
    fi
    
    # Check for WarPie AP exclusion
    if find ~/kismet/logs -name "*.wiglecsv" -exec grep -l "WarPie" {} \; 2>/dev/null | head -1 >/dev/null; then
        log_fail "WarPie AP found in logs (should be auto-excluded)"
        ((FAIL++))
    else
        log_success "WarPie AP properly excluded from logs"
        ((PASS++))
    fi
    
    # Check WiGLE CSV format
    LATEST_CSV=$(find ~/kismet/logs -name "*.wiglecsv" -exec ls -t {} \; 2>/dev/null | head -1)
    if [[ -n "$LATEST_CSV" ]]; then
        # Check for proper CSV header
        EXPECTED_HEADER="MAC,SSID,AuthMode,FirstSeen,Channel,RSSI,CurrentLatitude,CurrentLongitude,AltitudeMeters,AccuracyMeters,Type"
        if head -1 "$LATEST_CSV" | grep -q "MAC,SSID"; then
            log_success "WiGLE CSV header format correct"
            ((PASS++))
        else
            log_fail "WiGLE CSV header format incorrect"
            ((FAIL++))
        fi
        
        # Check for GPS coordinates (not 0,0)
        if tail -n +2 "$LATEST_CSV" | grep -E "^[^,]+,[^,]*,[^,]+,[^,]+,[^,]+,[^,]+,[0-9.-]+,[0-9.-]+" | grep -v ",0,0," | head -1 >/dev/null; then
            log_success "GPS coordinates present in WiGLE CSV"
            ((PASS++))
        else
            log_warn "No GPS coordinates found in WiGLE CSV (may need outdoor GPS fix)"
            ((WARN++))
        fi
        
        # Count entries
        ENTRY_COUNT=$(tail -n +2 "$LATEST_CSV" | wc -l)
        if [[ $ENTRY_COUNT -gt 0 ]]; then
            log_success "WiGLE CSV contains $ENTRY_COUNT network entries"
            ((PASS++))
        else
            log_warn "WiGLE CSV is empty (no networks logged)"
            ((WARN++))
        fi
    fi
    
else
    log_warn "No logs found for today ($TODAY) - run system to generate test data"
    ((WARN++))
fi

# =============================================================================
# CONFIGURATION VALIDATION
# =============================================================================
echo ""
echo "--- Configuration Validation ---"

test_result "Home BSSID exclusions configured" "
    grep -q 'kis_log_device_filter.*block' /usr/local/etc/kismet_site.conf
"

test_result "Known BSSIDs file exists and has entries" "
    [[ -f /etc/warpie/known_bssids.conf ]] && 
    grep -q '^[0-9a-fA-F]' /etc/warpie/known_bssids.conf
"

test_result "Wardrive config includes exclusions" "
    grep -q 'kis_log_device_filter.*block' /usr/local/etc/kismet_wardrive.conf
"

# =============================================================================
# NETWORK MANAGEMENT TESTS
# =============================================================================
echo ""
echo "--- Network Management ---"

test_result "Network manager script exists" "
    [[ -x /usr/local/bin/network-manager.sh ]]
" true

test_result "Hostapd config exists" "
    [[ -f /etc/hostapd/hostapd.conf ]] || [[ -f /etc/hostapd/hostapd-wlan0.conf ]]
"

# =============================================================================
# SECURITY VALIDATION
# =============================================================================
echo ""
echo "--- Security Checks ---"

test_result "Wardrive service runs as non-root" "
    grep -q '^User=' /etc/systemd/system/wardrive.service
"

test_result "User in kismet group" "
    id -nG \${SUDO_USER:-pi} | grep -qw kismet
"

# Check if Kismet capture binary is suid-root (needed for interface control)
if [[ -f /usr/bin/kismet_cap_linux_wifi ]]; then
    test_result "Kismet capture binary is suid-root" "
        [[ -u /usr/bin/kismet_cap_linux_wifi ]]
    "
elif [[ -f /usr/local/bin/kismet_cap_linux_wifi ]]; then
    test_result "Kismet capture binary is suid-root" "
        [[ -u /usr/local/bin/kismet_cap_linux_wifi ]]
    "
fi

# =============================================================================
# SUMMARY
# =============================================================================
echo ""
echo "============================================================================="
echo -e "Test Results: ${GREEN}${PASS} passed${NC}, ${RED}${FAIL} failed${NC}, ${YELLOW}${WARN} warnings${NC}"
echo "============================================================================="

if [[ $FAIL -gt 0 ]]; then
    echo ""
    log_fail "Critical issues found - system may not work properly"
    echo ""
    echo "Recommended actions:"
    echo "  1. Fix failed tests above"
    echo "  2. Run 'sudo ./install.sh --test' for detailed diagnostics"
    echo "  3. Check service logs: journalctl -u wardrive -n 50"
    echo ""
    exit 1
elif [[ $WARN -gt 0 ]]; then
    echo ""
    log_warn "System functional but some items need attention"
    echo ""
    echo "For field testing:"
    echo "  1. Move to outdoor location with clear sky view"
    echo "  2. Run system for 10+ minutes to establish GPS fix"
    echo "  3. Check WiGLE CSV files for coordinates"
    echo ""
    exit 0
else
    echo ""
    log_success "All tests passed! System ready for field testing"
    echo ""
    echo "Next steps:"
    echo "  1. Take WarPie to outdoor location"
    echo "  2. Follow Field Testing Guide for GPS validation"
    echo "  3. Test WiGLE.net upload"
    echo ""
    exit 0
fi
