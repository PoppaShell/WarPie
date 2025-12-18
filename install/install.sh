#!/bin/bash
# =============================================================================
# WarPie Wardriving System - Complete Install Script
# =============================================================================
# Version: 2.2.0
# Date: 2025-12-11
#
# Components:
#   - Network Manager (auto AP/client switching)
#   - GPS (GlobalSat BU-353S4 via gpsd)
#   - Kismet (dual-band wardriving)
#   - Control Panel (web UI on port 1337)
#   - Kismet Modes (normal, wardrive, )
#
# Usage:
#   sudo ./install.sh              # Full install
#   sudo ./install.sh --test       # Test/validate installation
#   sudo ./install.sh --uninstall  # Remove WarPie
#   sudo ./install.sh --configure  # Re-run WiFi/filter configuration
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Configuration
WARPIE_USER="${SUDO_USER:-pi}"
WARPIE_DIR="/etc/warpie"
LOG_DIR="/var/log/warpie"
KISMET_CONF_DIR="/usr/local/etc"
ADAPTERS_CONF="${WARPIE_DIR}/adapters.conf"
UDEV_RULES="/etc/udev/rules.d/70-warpie-wifi.rules"

# WiFi adapter configuration (will be set by configure_adapters_interactive)
WIFI_AP=""
WIFI_AP_MAC=""

# Per-adapter configuration arrays (indexed by adapter number)
declare -a ADAPTER_IFACES=()
declare -a ADAPTER_MACS=()
declare -a ADAPTER_NAMES=()
declare -a ADAPTER_ENABLED_BANDS=()     # e.g., "2.4GHz,5GHz"
declare -a ADAPTER_CHANNELS_24=()       # e.g., "1,6,11" or "all" or ""
declare -a ADAPTER_CHANNELS_5=()        # e.g., "all" or "36,40,44,48"
declare -a ADAPTER_CHANNELS_6=()        # e.g., "5,21,37,53" or "all"

# Temporary arrays used during selection (before band config)
WIFI_CAPTURE_INTERFACES=()
WIFI_CAPTURE_MACS=()
CAPTURE_INTERFACE_INDICES=()            # Original detection indices for band lookup

# AP Configuration
AP_SSID="WarPie"
AP_PASS="wardriving"
AP_CHANNEL="6"
AP_IP="192.168.4.1"

# Standard WiFi Channel Lists
readonly CHANNELS_24_ALL="1,2,3,4,5,6,7,8,9,10,11"
readonly CHANNELS_24_NONOVERLAP="1,6,11"
readonly CHANNELS_5_ALL="36,40,44,48,52,56,60,64,100,104,108,112,116,120,124,128,132,136,140,144,149,153,157,161,165"
readonly CHANNELS_6_PSC="5,21,37,53,69,85,101,117,133,149,165,181,197,213,229"

# Script mode
MODE="install"

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_test() { echo -e "${CYAN}[TEST]${NC} $1"; }

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --test|-t)
                MODE="test"
                shift
                ;;
            --uninstall|-u)
                MODE="uninstall"
                shift
                ;;
            --configure|-c)
                MODE="configure"
                shift
                ;;
            --help|-h)
                echo "Usage: $0 [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --test, -t       Test/validate existing installation"
                echo "  --uninstall, -u  Remove WarPie installation"
                echo "  --configure, -c  Re-run WiFi and filter configuration"
                echo "  --help, -h       Show this help message"
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
}

# =============================================================================
# WIFI ADAPTER DETECTION AND CONFIGURATION
# =============================================================================

# Get driver name for an interface
get_interface_driver() {
    local iface="$1"
    local driver_path="/sys/class/net/${iface}/device/driver"
    if [[ -L "${driver_path}" ]]; then
        basename "$(readlink -f "${driver_path}")"
    else
        echo "unknown"
    fi
}

# Get friendly name based on driver
get_driver_friendly_name() {
    local driver="$1"
    case "${driver}" in
        brcmfmac)    echo "Raspberry Pi Internal (Broadcom)" ;;
        mt7921u)     echo "MediaTek MT7921AU (e.g., AWUS036AXML)" ;;
        mt76x2u)     echo "MediaTek MT76x2 (e.g., AWUS036ACM)" ;;
        rt2800usb)   echo "Ralink RT3070/RT5370 (2.4GHz)" ;;
        ath9k_htc)   echo "Atheros AR9271 (2.4GHz)" ;;
        rtl8xxxu|rtl88xxau|88XXau) echo "Realtek USB WiFi" ;;
        *)           echo "Unknown (${driver})" ;;
    esac
}

# Detect supported bands for an interface
get_interface_bands() {
    local iface="$1"
    local phy
    local bands=""

    # Get the phy for this interface
    phy=$(iw dev "${iface}" info 2>/dev/null | grep wiphy | awk '{print $2}')
    if [[ -z "${phy}" ]]; then
        echo "unknown"
        return
    fi

    # Check supported bands from phy info
    local phy_info
    phy_info=$(iw phy "phy${phy}" info 2>/dev/null)

    if echo "${phy_info}" | grep -q "Band 1:"; then
        bands="${bands}2.4GHz "
    fi
    if echo "${phy_info}" | grep -q "Band 2:"; then
        bands="${bands}5GHz "
    fi
    if echo "${phy_info}" | grep -q "Band 4:"; then
        bands="${bands}6GHz "
    fi

    if [[ -z "${bands}" ]]; then
        echo "unknown"
    else
        echo "${bands}" | xargs  # trim whitespace
    fi
}

# Detect all WiFi interfaces and their properties
detect_wifi_interfaces() {
    log_info "Detecting WiFi interfaces..."

    local -a interfaces=()
    local -a macs=()
    local -a drivers=()
    local -a driver_names=()
    local -a bands=()

    # Look for both standard wlan* and our persistent warpie_* names
    for iface_path in /sys/class/net/wlan* /sys/class/net/warpie_*; do
        [[ -e "${iface_path}" ]] || continue
        local iface
        iface=$(basename "${iface_path}")

        # Skip monitor interfaces
        [[ "${iface}" == *mon* ]] && continue

        # Check if this is actually a wireless interface
        if [[ ! -d "${iface_path}/wireless" ]] && ! iw dev "${iface}" info &>/dev/null; then
            continue
        fi

        local mac driver driver_name band
        mac=$(cat "${iface_path}/address" 2>/dev/null | tr '[:lower:]' '[:upper:]')
        driver=$(get_interface_driver "${iface}")
        driver_name=$(get_driver_friendly_name "${driver}")
        band=$(get_interface_bands "${iface}")

        interfaces+=("${iface}")
        macs+=("${mac}")
        drivers+=("${driver}")
        driver_names+=("${driver_name}")
        bands+=("${band}")
    done

    if [[ ${#interfaces[@]} -eq 0 ]]; then
        log_error "No WiFi interfaces detected!"
        log_info "Please ensure WiFi adapters are connected and drivers are loaded."
        log_info "Check with: ip link show"
        exit 1
    fi

    # Export for use by other functions
    DETECTED_INTERFACES=("${interfaces[@]}")
    DETECTED_MACS=("${macs[@]}")
    DETECTED_DRIVERS=("${drivers[@]}")
    DETECTED_DRIVER_NAMES=("${driver_names[@]}")
    DETECTED_BANDS=("${bands[@]}")

    # Display detected interfaces
    echo ""
    echo -e "${BOLD}Detected WiFi Interfaces:${NC}"
    echo ""
    printf "  %-3s  %-8s  %-19s  %-15s  %s\n" "#" "Interface" "MAC Address" "Bands" "Device"
    printf "  %-3s  %-8s  %-19s  %-15s  %s\n" "---" "--------" "-------------------" "---------------" "------"

    for i in "${!interfaces[@]}"; do
        printf "  %-3s  %-8s  %-19s  %-15s  %s\n" \
            "$((i+1))" \
            "${interfaces[$i]}" \
            "${macs[$i]}" \
            "${bands[$i]}" \
            "${driver_names[$i]}"
    done
    echo ""
}

# Interactive adapter assignment
configure_adapters_interactive() {
    echo ""
    echo -e "${BOLD}==============================================================================${NC}"
    echo -e "${BOLD}  WiFi Adapter Configuration${NC}"
    echo -e "${BOLD}==============================================================================${NC}"
    echo ""
    echo "WarPie needs to know which adapter to use for each function:"
    echo ""
    echo -e "  1. ${CYAN}Access Point / Home WiFi${NC} - For WarPie AP and connecting to your home network"
    echo -e "  2. ${CYAN}Capture Interfaces${NC}      - For Kismet wardriving (can be 1 or more)"
    echo ""

    # Detect interfaces first
    detect_wifi_interfaces

    # --- Select AP Interface ---
    echo -e "${BOLD}Step 1: Select Access Point Interface${NC}"
    echo ""
    echo "Which interface should be used for the WarPie AP and home WiFi connection?"
    echo "(Usually the Raspberry Pi's internal WiFi - look for 'Broadcom' or 'brcmfmac')"
    echo ""

    local ap_choice
    while true; do
        echo -n "Enter interface number [1-${#DETECTED_INTERFACES[@]}]: "
        read -r ap_choice || ap_choice=""
        if [[ "${ap_choice}" =~ ^[0-9]+$ ]] && \
           [[ "${ap_choice}" -ge 1 ]] && \
           [[ "${ap_choice}" -le ${#DETECTED_INTERFACES[@]} ]]; then
            break
        fi
        log_warn "Invalid choice. Please enter a number between 1 and ${#DETECTED_INTERFACES[@]}"
    done

    local ap_idx=$((ap_choice - 1))
    WIFI_AP="${DETECTED_INTERFACES[$ap_idx]}"
    WIFI_AP_MAC="${DETECTED_MACS[$ap_idx]}"

    log_success "AP Interface: ${WIFI_AP} (${DETECTED_DRIVER_NAMES[$ap_idx]})"
    echo ""

    # --- Select Capture Interfaces ---
    echo -e "${BOLD}Step 2: Select Capture Interface(s)${NC}"
    echo ""
    echo "Which interface(s) should be used for Kismet capture?"
    echo "(Select all external USB adapters you want to use for wardriving)"
    echo ""

    # Show remaining interfaces
    echo "Available interfaces (excluding AP):"
    local -a available_indices=()
    for i in "${!DETECTED_INTERFACES[@]}"; do
        if [[ $i -ne $ap_idx ]]; then
            available_indices+=("$i")
            printf "  %s) %s - %s [%s]\n" \
                "${#available_indices[@]}" \
                "${DETECTED_INTERFACES[$i]}" \
                "${DETECTED_DRIVER_NAMES[$i]}" \
                "${DETECTED_BANDS[$i]}"
        fi
    done
    echo ""

    if [[ ${#available_indices[@]} -eq 0 ]]; then
        log_error "No interfaces available for capture after selecting AP!"
        log_error "You need at least one USB WiFi adapter for wardriving."
        exit 1
    fi

    echo "Enter interface numbers separated by spaces (e.g., '1 2' for both):"
    local capture_choices
    echo -n "> "
    read -r capture_choices || capture_choices=""

    WIFI_CAPTURE_INTERFACES=()
    WIFI_CAPTURE_MACS=()
    CAPTURE_INTERFACE_INDICES=()

    for choice in ${capture_choices}; do
        if [[ "${choice}" =~ ^[0-9]+$ ]] && \
           [[ "${choice}" -ge 1 ]] && \
           [[ "${choice}" -le ${#available_indices[@]} ]]; then
            local idx=${available_indices[$((choice - 1))]}
            WIFI_CAPTURE_INTERFACES+=("${DETECTED_INTERFACES[$idx]}")
            WIFI_CAPTURE_MACS+=("${DETECTED_MACS[$idx]}")
            CAPTURE_INTERFACE_INDICES+=("$idx")
        else
            log_warn "Ignoring invalid choice: ${choice}"
        fi
    done

    if [[ ${#WIFI_CAPTURE_INTERFACES[@]} -eq 0 ]]; then
        log_error "No capture interfaces selected!"
        exit 1
    fi

    echo ""
    log_success "Selected ${#WIFI_CAPTURE_INTERFACES[@]} capture interface(s)"

    # --- Step 3: Configure bands and channels for each adapter ---
    configure_adapter_bands

    # --- Confirm Configuration ---
    echo -e "${BOLD}==============================================================================${NC}"
    echo -e "${BOLD}  Configuration Summary${NC}"
    echo -e "${BOLD}==============================================================================${NC}"
    echo ""
    echo "  AP/Home WiFi:  ${WIFI_AP} (MAC: ${WIFI_AP_MAC})"
    echo ""
    for i in "${!ADAPTER_IFACES[@]}"; do
        echo "  Capture ${i}: ${ADAPTER_IFACES[$i]} -> ${ADAPTER_NAMES[$i]}"
        echo "             Bands: ${ADAPTER_ENABLED_BANDS[$i]}"
        [[ -n "${ADAPTER_CHANNELS_24[$i]}" ]] && echo "             2.4GHz: ${ADAPTER_CHANNELS_24[$i]}"
        [[ -n "${ADAPTER_CHANNELS_5[$i]}" ]] && echo "             5GHz: ${ADAPTER_CHANNELS_5[$i]}"
        [[ -n "${ADAPTER_CHANNELS_6[$i]}" ]] && echo "             6GHz: ${ADAPTER_CHANNELS_6[$i]}"
        echo ""
    done

    echo -n "Is this correct? [Y/n]: "
    read -r confirm || confirm="y"
    if [[ "${confirm,,}" == "n" ]]; then
        log_info "Restarting adapter configuration..."
        configure_adapters_interactive
        return
    fi

    # Save configuration
    save_adapter_config
    generate_udev_rules
}

# Save adapter configuration to file
save_adapter_config() {
    log_info "Saving adapter configuration..."

    mkdir -p "${WARPIE_DIR}"

    cat > "${ADAPTERS_CONF}" << EOF
# WarPie WiFi Adapter Configuration
# Generated: $(date)
# Do not edit manually - run 'sudo install.sh --configure' to reconfigure

# Access Point / Home WiFi Interface
WIFI_AP="${WIFI_AP}"
WIFI_AP_MAC="${WIFI_AP_MAC}"

# Capture Adapter Count
WIFI_CAPTURE_COUNT=${#ADAPTER_IFACES[@]}

EOF

    # Write per-adapter configuration
    for i in "${!ADAPTER_IFACES[@]}"; do
        cat >> "${ADAPTERS_CONF}" << EOF
# Adapter ${i}: ${ADAPTER_NAMES[$i]}
ADAPTER_${i}_IFACE="${ADAPTER_IFACES[$i]}"
ADAPTER_${i}_MAC="${ADAPTER_MACS[$i]}"
ADAPTER_${i}_NAME="${ADAPTER_NAMES[$i]}"
ADAPTER_${i}_BANDS="${ADAPTER_ENABLED_BANDS[$i]}"
ADAPTER_${i}_CHANNELS_24="${ADAPTER_CHANNELS_24[$i]}"
ADAPTER_${i}_CHANNELS_5="${ADAPTER_CHANNELS_5[$i]}"
ADAPTER_${i}_CHANNELS_6="${ADAPTER_CHANNELS_6[$i]}"

EOF
    done

    chmod 644 "${ADAPTERS_CONF}"
    log_success "Configuration saved to ${ADAPTERS_CONF}"
}

# Load adapter configuration from file
load_adapter_config() {
    if [[ -f "${ADAPTERS_CONF}" ]]; then
        # shellcheck source=/dev/null
        source "${ADAPTERS_CONF}"

        # Reconstruct arrays from indexed variables
        ADAPTER_IFACES=()
        ADAPTER_MACS=()
        ADAPTER_NAMES=()
        ADAPTER_ENABLED_BANDS=()
        ADAPTER_CHANNELS_24=()
        ADAPTER_CHANNELS_5=()
        ADAPTER_CHANNELS_6=()

        for ((i=0; i<WIFI_CAPTURE_COUNT; i++)); do
            local iface_var="ADAPTER_${i}_IFACE"
            local mac_var="ADAPTER_${i}_MAC"
            local name_var="ADAPTER_${i}_NAME"
            local bands_var="ADAPTER_${i}_BANDS"
            local ch24_var="ADAPTER_${i}_CHANNELS_24"
            local ch5_var="ADAPTER_${i}_CHANNELS_5"
            local ch6_var="ADAPTER_${i}_CHANNELS_6"

            ADAPTER_IFACES+=("${!iface_var}")
            ADAPTER_MACS+=("${!mac_var}")
            ADAPTER_NAMES+=("${!name_var}")
            ADAPTER_ENABLED_BANDS+=("${!bands_var}")
            ADAPTER_CHANNELS_24+=("${!ch24_var}")
            ADAPTER_CHANNELS_5+=("${!ch5_var}")
            ADAPTER_CHANNELS_6+=("${!ch6_var}")
        done

        return 0
    fi
    return 1
}

# Generate udev rules for persistent interface naming
generate_udev_rules() {
    log_info "Generating udev rules for persistent interface naming..."

    cat > "${UDEV_RULES}" << EOF
# WarPie WiFi Adapter Persistent Naming Rules
# Generated: $(date)
# These rules ensure WiFi adapters get consistent names based on MAC address

# AP Interface (internal WiFi)
SUBSYSTEM=="net", ACTION=="add", ATTR{address}=="${WIFI_AP_MAC,,}", NAME="warpie_ap"

EOF

    # Add rules for each capture interface
    for i in "${!ADAPTER_IFACES[@]}"; do
        local mac="${ADAPTER_MACS[$i],,}"  # lowercase
        local name="warpie_cap${i}"
        cat >> "${UDEV_RULES}" << EOF
# Capture Interface ${i}: ${ADAPTER_NAMES[$i]}
SUBSYSTEM=="net", ACTION=="add", ATTR{address}=="${mac}", NAME="${name}"

EOF
    done

    chmod 644 "${UDEV_RULES}"
    log_success "udev rules written to ${UDEV_RULES}"

    # Reload udev rules
    udevadm control --reload-rules 2>/dev/null || true

    log_warn "Note: Interface names will change after reboot."
    log_info "After reboot, interfaces will be named:"
    echo "  - warpie_ap (AP/Home WiFi)"
    for i in "${!ADAPTER_IFACES[@]}"; do
        echo "  - warpie_cap${i} (${ADAPTER_NAMES[$i]})"
    done
}

# =============================================================================
# GRANULAR BAND AND CHANNEL CONFIGURATION
# =============================================================================

# Generate a descriptive adapter name based on selected bands
# Args: $1=adapter_index, $2=bands_string (comma-separated)
generate_adapter_name() {
    local idx="$1"
    local bands="$2"

    # Count bands (use assignment to avoid exit status issues with set -e)
    local count=0
    [[ "$bands" == *"2.4GHz"* ]] && count=$((count + 1))
    [[ "$bands" == *"5GHz"* ]] && count=$((count + 1))
    [[ "$bands" == *"6GHz"* ]] && count=$((count + 1))

    if [[ $count -eq 1 ]]; then
        # Single band - use specific name
        [[ "$bands" == *"6GHz"* ]] && echo "WiFi_6GHz_${idx}" && return
        [[ "$bands" == *"5GHz"* ]] && echo "WiFi_5GHz_${idx}" && return
        [[ "$bands" == *"2.4GHz"* ]] && echo "WiFi_24GHz_${idx}" && return
    elif [[ $count -eq 2 ]]; then
        # Dual band
        [[ "$bands" == *"2.4GHz"* && "$bands" == *"5GHz"* ]] && echo "WiFi_DualBand_${idx}" && return
        [[ "$bands" == *"5GHz"* && "$bands" == *"6GHz"* ]] && echo "WiFi_HighBand_${idx}" && return
        [[ "$bands" == *"2.4GHz"* && "$bands" == *"6GHz"* ]] && echo "WiFi_Mixed_${idx}" && return
    else
        # Tri-band
        echo "WiFi_TriBand_${idx}" && return
    fi

    # Fallback
    echo "WiFi_Cap_${idx}"
}

# Prompt user for channel selection within a band
# Args: $1=band
# Returns: channel string (via echo to stdout)
# Note: Menu output goes to stderr so it displays properly when called in subshell
select_channels_for_band() {
    local band="$1"

    echo "" >&2
    echo -e "${CYAN}${band} Channel Selection:${NC}" >&2

    # Build menu options based on band
    local -a options=()
    local -a values=()

    case "$band" in
        "2.4GHz")
            options=("All channels (1-11)" "Non-overlapping (1,6,11) - recommended" "Custom list")
            values=("$CHANNELS_24_ALL" "$CHANNELS_24_NONOVERLAP" "custom")
            ;;
        "5GHz")
            options=("All channels (36-165)" "Custom list")
            values=("$CHANNELS_5_ALL" "custom")
            ;;
        "6GHz")
            options=("PSC channels (15 channels) - recommended" "All channels (59 channels)" "Custom list")
            values=("$CHANNELS_6_PSC" "all_6ghz" "custom")
            ;;
    esac

    # Display numbered menu
    for i in "${!options[@]}"; do
        echo "  [$((i + 1))] ${options[$i]}" >&2
    done

    local choice
    echo -n "> " >&2
    read -r choice || choice=""

    # Validate and process choice
    if [[ "$choice" =~ ^[0-9]+$ ]] && [[ "$choice" -ge 1 ]] && [[ "$choice" -le ${#options[@]} ]]; then
        local selected="${values[$((choice - 1))]}"

        if [[ "$selected" == "custom" ]]; then
            echo -e "${CYAN}Enter comma-separated channel list:${NC}" >&2
            local custom
            echo -n "> " >&2
            read -r custom || custom=""
            if [[ -n "$custom" ]]; then
                echo "$custom"
            else
                log_warn "Empty input, using default" >&2
                # Return first non-custom option as default
                echo "${values[0]}"
            fi
        elif [[ "$selected" == "all_6ghz" ]]; then
            # Full 6GHz channel list (all PSC + additional)
            echo "$CHANNELS_6_PSC"
        else
            echo "$selected"
        fi
    else
        # Invalid input - use first option as default
        log_warn "Invalid choice, using default" >&2
        if [[ "${values[0]}" == "custom" ]]; then
            echo "${values[1]}"
        else
            echo "${values[0]}"
        fi
    fi
}

# Configure bands and channels for a single adapter
# Args: $1=adapter_index, $2=interface, $3=capable_bands, $4=driver_name
configure_single_adapter() {
    local adapter_idx="$1"
    local iface="$2"
    local capable="$3"
    local driver="$4"
    local mac="$5"

    echo ""
    echo -e "${BOLD}━━━ Adapter $((adapter_idx + 1)): ${iface} - ${driver} ━━━${NC}"
    echo -e "    Capable bands: ${CYAN}${capable}${NC}"
    echo ""

    # Parse capable bands into array
    local -a cap_array=()
    [[ "$capable" == *"2.4GHz"* ]] && cap_array+=("2.4GHz")
    [[ "$capable" == *"5GHz"* ]] && cap_array+=("5GHz")
    [[ "$capable" == *"6GHz"* ]] && cap_array+=("6GHz")

    # Show band selection menu
    echo "Select bands to capture (space-separated numbers, or 'all'):"
    for j in "${!cap_array[@]}"; do
        echo "  [$((j + 1))] ${cap_array[$j]}"
    done

    local band_input
    echo -n "> "
    read -r band_input || band_input=""

    # Process band selection
    local -a selected_bands=()
    if [[ "${band_input,,}" == "all" ]]; then
        selected_bands=("${cap_array[@]}")
    else
        for choice in ${band_input}; do
            if [[ "$choice" =~ ^[0-9]+$ ]] && \
               [[ "$choice" -ge 1 ]] && \
               [[ "$choice" -le ${#cap_array[@]} ]]; then
                selected_bands+=("${cap_array[$((choice - 1))]}")
            else
                log_warn "Ignoring invalid band choice: $choice"
            fi
        done
    fi

    # If nothing selected, default to all
    if [[ ${#selected_bands[@]} -eq 0 ]]; then
        log_warn "No bands selected, defaulting to all available"
        selected_bands=("${cap_array[@]}")
    fi

    # Configure channels for each selected band
    local channels_24="" channels_5="" channels_6=""

    for band in "${selected_bands[@]}"; do
        case "$band" in
            "2.4GHz")
                channels_24=$(select_channels_for_band "2.4GHz")
                ;;
            "5GHz")
                channels_5=$(select_channels_for_band "5GHz")
                ;;
            "6GHz")
                channels_6=$(select_channels_for_band "6GHz")
                ;;
        esac
    done

    # Generate adapter name based on bands
    local bands_str
    bands_str=$(IFS=','; echo "${selected_bands[*]}")
    local adapter_name
    adapter_name=$(generate_adapter_name "$adapter_idx" "$bands_str")

    # Store configuration in global arrays
    ADAPTER_IFACES+=("$iface")
    ADAPTER_MACS+=("$mac")
    ADAPTER_NAMES+=("$adapter_name")
    ADAPTER_ENABLED_BANDS+=("$bands_str")
    ADAPTER_CHANNELS_24+=("$channels_24")
    ADAPTER_CHANNELS_5+=("$channels_5")
    ADAPTER_CHANNELS_6+=("$channels_6")

    # Display confirmation
    echo ""
    log_success "${iface} -> ${adapter_name}"
    echo "    Bands: ${bands_str}"
    [[ -n "$channels_24" ]] && echo "    2.4GHz channels: ${channels_24}"
    [[ -n "$channels_5" ]] && echo "    5GHz channels: ${channels_5}"
    [[ -n "$channels_6" ]] && echo "    6GHz channels: ${channels_6}"
}

# Configure bands and channels for each selected capture adapter
# Reads from: WIFI_CAPTURE_INTERFACES, CAPTURE_INTERFACE_INDICES, DETECTED_BANDS
# Populates: ADAPTER_* arrays
configure_adapter_bands() {
    echo ""
    echo -e "${BOLD}==============================================================================${NC}"
    echo -e "${BOLD}  Step 3: Configure Capture Adapter Bands${NC}"
    echo -e "${BOLD}==============================================================================${NC}"
    echo ""
    echo "For each adapter, select which bands to capture and channel configuration."
    echo "Quick options: 'all' selects all bands, '1' typically selects recommended channels."

    # Clear adapter arrays before populating
    ADAPTER_IFACES=()
    ADAPTER_MACS=()
    ADAPTER_NAMES=()
    ADAPTER_ENABLED_BANDS=()
    ADAPTER_CHANNELS_24=()
    ADAPTER_CHANNELS_5=()
    ADAPTER_CHANNELS_6=()

    for i in "${!WIFI_CAPTURE_INTERFACES[@]}"; do
        local iface="${WIFI_CAPTURE_INTERFACES[$i]}"
        local mac="${WIFI_CAPTURE_MACS[$i]}"
        local idx="${CAPTURE_INTERFACE_INDICES[$i]}"
        local capable="${DETECTED_BANDS[$idx]}"
        local driver="${DETECTED_DRIVER_NAMES[$idx]}"

        configure_single_adapter "$i" "$iface" "$capable" "$driver" "$mac"
    done

    echo ""
}

# =============================================================================
# KISMET INSTALLATION
# =============================================================================
install_kismet_from_repo() {
    log_info "Installing Kismet from official repository..."

    # Detect OS version
    if [[ -f /etc/os-release ]]; then
        # shellcheck source=/dev/null
        . /etc/os-release
        DISTRO="${ID}"
        VERSION="${VERSION_CODENAME}"
    else
        log_error "Cannot detect OS version"
        exit 1
    fi

    # Add Kismet repository GPG key
    log_info "Adding Kismet repository key..."
    wget -O - https://www.kismetwireless.net/repos/kismet-release.gpg.key --quiet | \
        gpg --dearmor | tee /usr/share/keyrings/kismet-archive-keyring.gpg > /dev/null || true

    # Add Kismet repository based on distribution
    case "${DISTRO}" in
        debian|raspbian)
            log_info "Configuring for Debian/Raspbian (${VERSION})..."
            echo "deb [signed-by=/usr/share/keyrings/kismet-archive-keyring.gpg] https://www.kismetwireless.net/repos/apt/release/${VERSION} ${VERSION} main" | \
                tee /etc/apt/sources.list.d/kismet.list > /dev/null
            ;;
        ubuntu)
            log_info "Configuring for Ubuntu (${VERSION})..."
            echo "deb [signed-by=/usr/share/keyrings/kismet-archive-keyring.gpg] https://www.kismetwireless.net/repos/apt/release/${VERSION} ${VERSION} main" | \
                tee /etc/apt/sources.list.d/kismet.list > /dev/null
            ;;
        *)
            log_error "Unsupported distribution: ${DISTRO}"
            log_info "Please install Kismet manually from: https://www.kismetwireless.net/docs/readme/installing/linux/"
            exit 1
            ;;
    esac

    # Update package lists
    log_info "Updating package lists..."
    apt-get update

    # Install Kismet
    log_info "Installing Kismet packages..."
    apt-get install -y kismet

    # Run suidinstall for non-root capture capability
    log_info "Configuring Kismet for non-root capture..."

    # Add user to kismet group (will be created by package)
    if getent group kismet > /dev/null 2>&1; then
        usermod -aG kismet "${WARPIE_USER}"
        log_success "Added ${WARPIE_USER} to kismet group"
    fi

    # Verify installation
    if command -v kismet &> /dev/null; then
        local kismet_version
        kismet_version=$(kismet --version 2>&1 | head -1)
        log_success "Kismet installed: $kismet_version"
    else
        log_error "Kismet installation failed"
        exit 1
    fi
}

# =============================================================================
# PRE-FLIGHT CHECKS
# =============================================================================
preflight_checks() {
    log_info "Running pre-flight checks..."
    
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (use sudo)"
        exit 1
    fi
    
    # Check for required packages
    local required_packages=(hostapd dnsmasq gpsd gpsd-clients python3 curl iw)
    local missing_packages=()
    
    for pkg in "${required_packages[@]}"; do
        if ! dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "install ok installed"; then
            missing_packages+=("$pkg")
        fi
    done
    
    if [[ ${#missing_packages[@]} -gt 0 ]]; then
        log_warn "Missing packages: ${missing_packages[*]}"
        log_info "Installing missing packages..."
        apt-get update
        apt-get install -y "${missing_packages[@]}"
    fi
    
    # Check if Kismet is installed
    if ! command -v kismet &> /dev/null; then
        log_warn "Kismet is not installed."
        echo ""
        echo -e "${BOLD}Kismet Installation Options:${NC}"
        echo ""
        echo "  1) Install from Kismet repository (recommended)"
        echo "     - Latest stable release with automatic updates"
        echo "     - Faster installation"
        echo ""
        echo "  2) Skip Kismet installation"
        echo "     - Install Kismet manually later"
        echo "     - See: https://www.kismetwireless.net/docs/readme/installing/linux/"
        echo ""
        read -p "Choose option [1-2]: " kismet_choice

        case "$kismet_choice" in
            1)
                install_kismet_from_repo
                ;;
            2)
                log_error "Kismet is required for WarPie. Please install it manually and re-run this script."
                exit 1
                ;;
            *)
                log_error "Invalid choice. Exiting."
                exit 1
                ;;
        esac
    fi

    log_success "Pre-flight checks passed"
}

# =============================================================================
# CREATE DIRECTORIES
# =============================================================================
create_directories() {
    log_info "Creating directories..."
    
    mkdir -p "$WARPIE_DIR"
    mkdir -p "$LOG_DIR"
    mkdir -p "/home/${WARPIE_USER}/kismet"
    
    chown -R "${WARPIE_USER}:${WARPIE_USER}" "/home/${WARPIE_USER}/kismet"
    
    log_success "Directories created"
}

# =============================================================================
# CONFIGURE KISMET USER PERMISSIONS
# =============================================================================
configure_kismet_permissions() {
    log_info "Configuring Kismet user permissions..."
    
    # Check if kismet group exists (created by Kismet suidinstall)
    if getent group kismet > /dev/null 2>&1; then
        log_info "Kismet group exists"
    else
        log_warn "Kismet group not found - creating it"
        groupadd -r kismet 2>/dev/null || true
    fi
    
    # Add user to kismet group
    if id -nG "${WARPIE_USER}" | grep -qw "kismet"; then
        log_info "User ${WARPIE_USER} already in kismet group"
    else
        log_info "Adding ${WARPIE_USER} to kismet group..."
        usermod -aG kismet "${WARPIE_USER}"
        log_success "User ${WARPIE_USER} added to kismet group"
    fi
    
    # Ensure kismet capture binaries are suid-root if they exist
    local KISMET_CAP="/usr/bin/kismet_cap_linux_wifi"
    if [[ -f "$KISMET_CAP" ]]; then
        if [[ ! -u "$KISMET_CAP" ]]; then
            log_warn "Kismet capture binary not suid-root"
            log_info "If you compiled Kismet from source, run: sudo make suidinstall"
            log_info "This is needed for non-root users to control WiFi interfaces"
        else
            log_success "Kismet capture binary is properly configured (suid-root)"
        fi
    fi
    
    # Ensure log directory is writable by kismet group
    chown -R "${WARPIE_USER}:kismet" "$LOG_DIR"
    chmod 775 "$LOG_DIR"
    
    # Ensure kismet data directory is writable
    chown -R "${WARPIE_USER}:kismet" "/home/${WARPIE_USER}/kismet"
    chmod 775 "/home/${WARPIE_USER}/kismet"
    
    log_success "Kismet permissions configured"
    log_info "Note: User may need to log out and back in for group changes to take effect"
}

# =============================================================================
# INTERACTIVE WIFI CONFIGURATION
# =============================================================================
configure_wifi_interactive() {
    echo ""
    echo -e "${BOLD}==============================================================================${NC}"
    echo -e "${BOLD}  WiFi Network Configuration${NC}"
    echo -e "${BOLD}==============================================================================${NC}"
    echo ""
    echo "This will configure:"
    echo "  1. Your home WiFi network (for auto-connect when in range)"
    echo "  2. Networks to exclude from Kismet logging"
    echo ""

    # Load adapter config to get AP interface for scanning
    load_adapter_config || {
        log_error "Adapter configuration not found. Run adapter configuration first."
        return 1
    }

    # Determine scan interface (prefer persistent name if available)
    local scan_iface
    if [[ -e "/sys/class/net/warpie_ap" ]]; then
        scan_iface="warpie_ap"
    else
        scan_iface="${WIFI_AP}"
    fi

    # Ensure interface is up for scanning
    ip link set "${scan_iface}" up 2>/dev/null || true
    sleep 2

    # Ask for home network SSID
    echo -e "${CYAN}Step 1: Home Network Configuration${NC}"
    echo ""
    echo -n "Enter your home WiFi network name (SSID): "
    read -r HOME_SSID || HOME_SSID=""

    if [[ -z "$HOME_SSID" ]]; then
        log_warn "No SSID entered, skipping WiFi configuration"
        return 1
    fi

    echo ""
    log_info "Scanning for networks matching '$HOME_SSID' using ${scan_iface}..."

    # Scan for networks
    SCAN_RESULTS=$(iw dev "${scan_iface}" scan 2>/dev/null || true)

    if [[ -z "$SCAN_RESULTS" ]]; then
        log_warn "Scan returned no results. Retrying..."
        sleep 3
        SCAN_RESULTS=$(iw dev "${scan_iface}" scan 2>/dev/null || true)
    fi
    
    # Parse scan results to find matching SSIDs and their BSSIDs
    # This creates a list of "BSSID|SSID" pairs
    declare -a FOUND_BSSIDS=()
    declare -a FOUND_ENTRIES=()
    
    current_bssid=""
    current_ssid=""
    current_signal=""
    
    while IFS= read -r line; do
        if [[ "$line" =~ ^BSS[[:space:]]([0-9a-fA-F:]+) ]]; then
            # Save previous entry if SSID matches
            if [[ -n "$current_bssid" && "$current_ssid" == "$HOME_SSID" ]]; then
                FOUND_BSSIDS+=("$current_bssid")
                FOUND_ENTRIES+=("$current_bssid|$current_ssid|$current_signal")
            fi
            current_bssid="${BASH_REMATCH[1]}"
            current_ssid=""
            current_signal=""
        elif [[ "$line" =~ SSID:[[:space:]]*(.*) ]]; then
            current_ssid="${BASH_REMATCH[1]}"
        elif [[ "$line" =~ signal:[[:space:]]*(.*)dBm ]]; then
            current_signal="${BASH_REMATCH[1]}"
        fi
    done <<< "$SCAN_RESULTS"
    
    # Don't forget the last entry
    if [[ -n "$current_bssid" && "$current_ssid" == "$HOME_SSID" ]]; then
        FOUND_BSSIDS+=("$current_bssid")
        FOUND_ENTRIES+=("$current_bssid|$current_ssid|$current_signal")
    fi
    
    if [[ ${#FOUND_BSSIDS[@]} -eq 0 ]]; then
        log_warn "No networks found matching '$HOME_SSID'"
        echo ""
        echo "Options:"
        echo "  1. Enter BSSID manually"
        echo "  2. Skip WiFi configuration"
        echo ""
        read -p "Choice [1/2]: " choice
        
        if [[ "$choice" == "1" ]]; then
            read -p "Enter BSSID (format XX:XX:XX:XX:XX:XX): " manual_bssid
            if [[ "$manual_bssid" =~ ^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$ ]]; then
                FOUND_BSSIDS+=("$manual_bssid")
                FOUND_ENTRIES+=("$manual_bssid|$HOME_SSID|manual")
            else
                log_error "Invalid BSSID format"
                return 1
            fi
        else
            return 1
        fi
    else
        echo ""
        log_success "Found ${#FOUND_BSSIDS[@]} access point(s) for '$HOME_SSID':"
        echo ""
        for entry in "${FOUND_ENTRIES[@]}"; do
            IFS='|' read -r bssid ssid signal <<< "$entry"
            echo "  BSSID: $bssid  Signal: ${signal}dBm"
        done
        echo ""
    fi
    
    # Write known_bssids.conf
    log_info "Writing known BSSIDs configuration..."
    
    cat > "${WARPIE_DIR}/known_bssids.conf" << BSSID_HEADER
# /etc/warpie/known_bssids.conf
# Trusted home network BSSIDs - auto-generated by install.sh
# Format: BSSID|SSID|PRIORITY|DESCRIPTION
#
# When any of these BSSIDs are detected, WarPie will let NetworkManager
# handle the connection instead of starting AP mode.
#
BSSID_HEADER

    local idx=1
    for entry in "${FOUND_ENTRIES[@]}"; do
        IFS='|' read -r bssid ssid signal <<< "$entry"
        echo "${bssid}|${ssid}|10|AP${idx}" >> "${WARPIE_DIR}/known_bssids.conf"
        ((idx++))
    done
    
    log_success "Saved ${#FOUND_BSSIDS[@]} BSSID(s) to known_bssids.conf"
    
    # Ask about Kismet exclusion
    echo ""
    echo -e "${CYAN}Step 2: Kismet Network Exclusion${NC}"
    echo ""
    echo "Do you want to exclude '$HOME_SSID' from Kismet logs?"
    echo "This prevents your home network from appearing in wardriving data."
    echo ""
    read -p "Exclude from Kismet? [Y/n]: " exclude_choice
    
    if [[ ! "$exclude_choice" =~ ^[Nn]$ ]]; then
        configure_kismet_exclusions "${FOUND_BSSIDS[@]}"
    fi
    
    # Ask about additional networks to exclude
    echo ""
    echo -e "${CYAN}Step 3: Additional Exclusions (Optional)${NC}"
    echo ""
    echo "Do you want to exclude any other networks from Kismet?"
    echo "(e.g., neighbor's WiFi, work network)"
    echo ""
    read -p "Add more exclusions? [y/N]: " more_choice
    
    if [[ "$more_choice" =~ ^[Yy]$ ]]; then
        configure_additional_exclusions
    fi
    
    log_success "WiFi configuration complete"
    return 0
}

# =============================================================================
# CONFIGURE KISMET EXCLUSIONS
# =============================================================================
configure_kismet_exclusions() {
    local bssids=("$@")
    
    log_info "Generating Kismet exclusion filters..."
    
    # We'll append to kismet_site.conf after it's created
    # Store exclusions for later
    KISMET_EXCLUSIONS=()
    
    for bssid in "${bssids[@]}"; do
        # Convert to uppercase and create mask that ignores first octet
        # This catches HOME and HOME-GUEST variants
        local upper_bssid=$(echo "$bssid" | tr '[:lower:]' '[:upper:]')
        # Replace first octet with 00 for the filter
        local masked_bssid="00${upper_bssid:2}"
        KISMET_EXCLUSIONS+=("kis_log_device_filter=IEEE802.11,${masked_bssid}/00:FF:FF:FF:FF:FF,block")
    done
    
    log_success "Generated ${#KISMET_EXCLUSIONS[@]} exclusion filter(s)"
}

# =============================================================================
# CONFIGURE ADDITIONAL EXCLUSIONS
# =============================================================================
configure_additional_exclusions() {
    while true; do
        echo ""
        echo "Enter network to exclude (SSID name or BSSID):"
        echo "  - Enter SSID name to scan and find all matching BSSIDs"
        echo "  - Enter BSSID directly (XX:XX:XX:XX:XX:XX)"
        echo "  - Press Enter when done"
        echo ""
        read -p "> " input
        
        if [[ -z "$input" ]]; then
            break
        fi
        
        # Check if it's a BSSID format
        if [[ "$input" =~ ^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$ ]]; then
            local upper_bssid=$(echo "$input" | tr '[:lower:]' '[:upper:]')
            local masked_bssid="00${upper_bssid:2}"
            KISMET_EXCLUSIONS+=("kis_log_device_filter=IEEE802.11,${masked_bssid}/00:FF:FF:FF:FF:FF,block")
            log_success "Added exclusion for BSSID: $input"
        else
            # It's an SSID, scan for it
            log_info "Scanning for '$input'..."
            
            local scan_bssids=()
            current_bssid=""
            current_ssid=""
            
            while IFS= read -r line; do
                if [[ "$line" =~ ^BSS[[:space:]]([0-9a-fA-F:]+) ]]; then
                    if [[ -n "$current_bssid" && "$current_ssid" == "$input" ]]; then
                        scan_bssids+=("$current_bssid")
                    fi
                    current_bssid="${BASH_REMATCH[1]}"
                    current_ssid=""
                elif [[ "$line" =~ SSID:[[:space:]]*(.*) ]]; then
                    current_ssid="${BASH_REMATCH[1]}"
                fi
            done <<< "$(iw dev wlan0 scan 2>/dev/null)"
            
            if [[ -n "$current_bssid" && "$current_ssid" == "$input" ]]; then
                scan_bssids+=("$current_bssid")
            fi
            
            if [[ ${#scan_bssids[@]} -eq 0 ]]; then
                log_warn "No networks found matching '$input'"
            else
                log_success "Found ${#scan_bssids[@]} BSSID(s) for '$input'"
                for bssid in "${scan_bssids[@]}"; do
                    local upper_bssid=$(echo "$bssid" | tr '[:lower:]' '[:upper:]')
                    local masked_bssid="00${upper_bssid:2}"
                    KISMET_EXCLUSIONS+=("kis_log_device_filter=IEEE802.11,${masked_bssid}/00:FF:FF:FF:FF:FF,block")
                    echo "  Added: $bssid"
                done
            fi
        fi
    done
}

# =============================================================================
# CONFIGURE KNOWN BSSIDS (fallback if interactive skipped)
# =============================================================================
configure_known_bssids() {
    if [[ -f "${WARPIE_DIR}/known_bssids.conf" ]]; then
        log_info "Known BSSIDs config exists, preserving..."
        return
    fi
    
    log_info "Creating default known_bssids.conf..."
    
    cat > "${WARPIE_DIR}/known_bssids.conf" << 'BSSID_EOF'
# /etc/warpie/known_bssids.conf
# Trusted home network BSSIDs
# Format: BSSID|SSID|PRIORITY|DESCRIPTION
#
# To find your BSSIDs, run: sudo iw dev wlan0 scan | grep -E "BSS|SSID"
# Or re-run: sudo ./install.sh --configure
#
# Example entries (replace with your own):
# 74:83:c2:8a:23:4c|HOME|10|AP1 2.4GHz
# 7a:83:c2:8b:23:4c|HOME|10|AP1 5GHz
BSSID_EOF
    
    log_warn "Please configure known_bssids.conf or run: sudo ./install.sh --configure"
}

# =============================================================================
# CONFIGURE NETWORK MANAGER SCRIPT
# =============================================================================
configure_network_manager() {
    log_info "Installing network manager script..."
    
    cat > /usr/local/bin/network-manager.sh << 'NETMGR_EOF'
#!/bin/bash
# =============================================================================
# WarPie Network Manager - Simplified
# =============================================================================
# Checks if known home networks are in range.
# If yes: exits and lets NetworkManager handle connection
# If no: starts Access Point mode for mobile connectivity
# =============================================================================

set -u

readonly ADAPTERS_CONF="/etc/warpie/adapters.conf"
readonly BSSID_CONFIG="/etc/warpie/known_bssids.conf"
readonly HOSTAPD_CONFIG="/etc/hostapd/hostapd.conf"
readonly LOG_FILE="/var/log/warpie/network-manager.log"
readonly AP_IP="192.168.4.1"

# Load adapter configuration to get AP interface
if [[ -f "$ADAPTERS_CONF" ]]; then
    # shellcheck source=/dev/null
    source "$ADAPTERS_CONF"
else
    echo "ERROR: Adapter configuration not found" >&2
    exit 1
fi

# Determine which interface to use (prefer persistent name)
if [[ -e "/sys/class/net/warpie_ap" ]]; then
    readonly INTERFACE="warpie_ap"
else
    readonly INTERFACE="${WIFI_AP}"
fi

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"; }

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

log "=== WarPie Network Manager Starting ==="

# Load known BSSIDs into array
declare -a KNOWN_BSSIDS=()
while IFS='|' read -r bssid rest; do
    [[ -z "$bssid" || "$bssid" =~ ^# ]] && continue
    KNOWN_BSSIDS+=("$(echo "$bssid" | tr '[:upper:]' '[:lower:]' | xargs)")
done < "$BSSID_CONFIG"

log "Loaded ${#KNOWN_BSSIDS[@]} trusted BSSIDs"

if [[ ${#KNOWN_BSSIDS[@]} -eq 0 ]]; then
    log "WARNING: No trusted BSSIDs configured, starting AP mode"
fi

# Ensure interface is up for scanning
ip link set "$INTERFACE" up 2>/dev/null
sleep 2

# Scan for networks
log "Scanning for networks..."
SCAN_RESULT=$(iw dev "$INTERFACE" scan 2>/dev/null | grep -i "bss " | awk '{print tolower($2)}')

if [[ -z "$SCAN_RESULT" ]]; then
    log "WARNING: Scan returned no results, retrying..."
    sleep 3
    SCAN_RESULT=$(iw dev "$INTERFACE" scan 2>/dev/null | grep -i "bss " | awk '{print tolower($2)}')
fi

# Check if any known BSSID is in range
FOUND_HOME=false
for bssid in "${KNOWN_BSSIDS[@]}"; do
    if echo "$SCAN_RESULT" | grep -q "$bssid"; then
        log "Found trusted network: $bssid"
        FOUND_HOME=true
        break
    fi
done

if [[ "$FOUND_HOME" == true ]]; then
    log "Home network in range - letting NetworkManager handle connection"
    log "=== Exiting (NetworkManager mode) ==="
    exit 0
fi

# No home network found - start AP mode
log "No trusted networks found - starting Access Point mode"

# Tell NetworkManager to ignore wlan0
log "Removing $INTERFACE from NetworkManager..."
nmcli device set "$INTERFACE" managed no 2>/dev/null || true
sleep 1

# Kill any existing wpa_supplicant on wlan0
pkill -f "wpa_supplicant.*$INTERFACE" 2>/dev/null || true

# Configure interface for AP
log "Configuring $INTERFACE with static IP $AP_IP..."
ip addr flush dev "$INTERFACE" 2>/dev/null
ip addr add "$AP_IP/24" dev "$INTERFACE"
ip link set "$INTERFACE" up

# Start hostapd
log "Starting hostapd..."
if hostapd -B "$HOSTAPD_CONFIG"; then
    log "hostapd started successfully"
else
    log "ERROR: hostapd failed to start"
    exit 1
fi

# Start dnsmasq for DHCP
log "Starting DHCP server..."
pkill -f "dnsmasq.*$INTERFACE" 2>/dev/null || true
sleep 1
dnsmasq \
    --interface="$INTERFACE" \
    --bind-interfaces \
    --dhcp-range=192.168.4.10,192.168.4.50,255.255.255.0,24h \
    --dhcp-option=option:router,"$AP_IP" \
    --no-resolv \
    --no-poll \
    --log-facility="$LOG_FILE" \
    || log "WARNING: dnsmasq may have failed"

log "Access Point started!"
log "  SSID: WarPie"
log "  IP: $AP_IP"
log "  DHCP: 192.168.4.10 - 192.168.4.50"
log "=== AP Mode Active ==="

exit 0
NETMGR_EOF

    chmod +x /usr/local/bin/network-manager.sh
    log_success "Network manager script installed"
}

# =============================================================================
# CONFIGURE HOSTAPD
# =============================================================================
configure_hostapd() {
    log_info "Configuring hostapd..."

    # Load adapter config to get AP interface
    load_adapter_config || {
        log_error "Adapter configuration not found. Run adapter configuration first."
        exit 1
    }

    # Determine which interface name to use
    # Use persistent name if udev rules exist, otherwise use original name
    local ap_interface
    if [[ -f "${UDEV_RULES}" ]]; then
        ap_interface="warpie_ap"
    else
        ap_interface="${WIFI_AP}"
    fi

    cat > /etc/hostapd/hostapd.conf << HOSTAPD_EOF
# WarPie Access Point Configuration
interface=${ap_interface}
driver=nl80211
ssid=${AP_SSID}
hw_mode=g
channel=${AP_CHANNEL}
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=${AP_PASS}
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
HOSTAPD_EOF

    log_success "hostapd configured (Interface: ${ap_interface}, SSID: ${AP_SSID})"
}

# =============================================================================
# CONFIGURE GPS
# =============================================================================
configure_gps() {
    log_info "Configuring GPS..."
    
    # Find GPS device
    local GPS_DEVICE=""
    if [[ -e /dev/serial/by-id/usb-Prolific_Technology_Inc._USB-Serial_Controller_D-if00-port0 ]]; then
        GPS_DEVICE="/dev/serial/by-id/usb-Prolific_Technology_Inc._USB-Serial_Controller_D-if00-port0"
    elif [[ -e /dev/ttyUSB0 ]]; then
        GPS_DEVICE="/dev/ttyUSB0"
    else
        log_warn "GPS device not found, using default /dev/ttyUSB0"
        GPS_DEVICE="/dev/ttyUSB0"
    fi
    
    # Mask the default gpsd service
    systemctl stop gpsd 2>/dev/null || true
    systemctl disable gpsd 2>/dev/null || true
    systemctl mask gpsd 2>/dev/null || true
    
    # Create custom gpsd service
    cat > /etc/systemd/system/gpsd-wardriver.service << GPS_EOF
[Unit]
Description=GPS daemon for wardriving
Before=wardrive.service
After=network.target

[Service]
Type=forking
ExecStart=/usr/sbin/gpsd -n ${GPS_DEVICE}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
GPS_EOF

    log_success "GPS configured (device: ${GPS_DEVICE})"
}

# =============================================================================
# CONFIGURE KISMET
# =============================================================================
configure_kismet() {
    log_info "Configuring Kismet..."
    
    # Auto-exclude the WarPie AP (wlan0's MAC address)
    if [[ -f /sys/class/net/wlan0/address ]]; then
        local WLAN0_MAC=$(cat /sys/class/net/wlan0/address | tr '[:lower:]' '[:upper:]')
        if [[ -n "$WLAN0_MAC" ]]; then
            log_info "Auto-excluding WarPie AP (wlan0 MAC: ${WLAN0_MAC})"
            # Add exact MAC match for the WarPie AP
            KISMET_EXCLUSIONS+=("kis_log_device_filter=IEEE802.11,${WLAN0_MAC}/FF:FF:FF:FF:FF:FF,block")
        fi
    fi
    
    # Main site configuration
    cat > "${KISMET_CONF_DIR}/kismet_site.conf" << 'KISMET_SITE_EOF'
# WarPie Kismet Configuration

# GPS via gpsd
gps=gpsd:host=localhost,port=2947,name=GlobalSat_BU353S4

# Logging
log_types+=wiglecsv

# =============================================================================
# HOME NETWORK EXCLUSIONS
# Auto-generated filters are appended below
# These filters affect LOG FILES ONLY - Kismet UI will still show all devices
# =============================================================================
KISMET_SITE_EOF

    # Append any exclusions we collected during interactive config
    if [[ ${#KISMET_EXCLUSIONS[@]} -gt 0 ]]; then
        echo "" >> "${KISMET_CONF_DIR}/kismet_site.conf"
        echo "# Excluded networks (auto-generated)" >> "${KISMET_CONF_DIR}/kismet_site.conf"
        for exclusion in "${KISMET_EXCLUSIONS[@]}"; do
            echo "$exclusion" >> "${KISMET_CONF_DIR}/kismet_site.conf"
        done
        log_success "Added ${#KISMET_EXCLUSIONS[@]} network exclusion(s) to Kismet site config"
    fi

    # Wardrive mode configuration (optimized for mobile scanning)
    cat > "${KISMET_CONF_DIR}/kismet_wardrive.conf" << 'WARDRIVE_EOF'
# Wardrive Mode - Optimized for Mobile AP Scanning
# Use with: kismet --override wardrive
#
# NOTE: Home network exclusions are included below to ensure they're applied
# These filters only affect LOG FILES - Kismet UI will still show all devices

load_alert=WARDRIVE:Optimized wardrive mode - APs only, fast channel hopping

# Only track APs, not clients (major performance boost)
dot11_ap_only_survey=true

# Skip HT/VHT channels for faster hopping
dot11_datasource_opt=ht_channels,false
dot11_datasource_opt=vht_channels,false

# Only capture management frames (beacons, probes)
dot11_datasource_opt=filter_mgmt,true

# Disable fingerprinting (not needed for basic wardriving)
dot11_fingerprint_devices=false

# Don't store IE tags (saves memory)
dot11_keep_ietags=false

# Don't capture EAPOL for WPA handshakes
dot11_keep_eapol=false

# Enable WiGLE CSV logging
log_types+=wiglecsv

# Faster channel dwell time for mobile use (default is 200ms)
channel_dwell=150

# =============================================================================
# HOME NETWORK EXCLUSIONS (from kismet_site.conf)
# =============================================================================
WARDRIVE_EOF

    # Also add exclusions to wardrive config
    if [[ ${#KISMET_EXCLUSIONS[@]} -gt 0 ]]; then
        echo "# Excluded networks (auto-generated)" >> "${KISMET_CONF_DIR}/kismet_wardrive.conf"
        for exclusion in "${KISMET_EXCLUSIONS[@]}"; do
            echo "$exclusion" >> "${KISMET_CONF_DIR}/kismet_wardrive.conf"
        done
        log_success "Added ${#KISMET_EXCLUSIONS[@]} network exclusion(s) to Wardrive config"
    fi

    log_success "Kismet configurations created"
}

# =============================================================================
# CONFIGURE WARDRIVE SERVICE
# =============================================================================
configure_wardrive_service() {
    log_info "Configuring wardrive service..."
    
    cat > /usr/local/bin/wardrive.sh << 'WARDRIVE_EOF'
#!/bin/bash
# WarPie Wardrive Launcher

set -e

LOG_FILE="/var/log/warpie/wardrive.log"
ADAPTERS_CONF="/etc/warpie/adapters.conf"
KISMET_BASE="\${HOME}/kismet"

log() { echo "[\$(date '+%Y-%m-%d %H:%M:%S')] [INFO] \$1" | tee -a "\$LOG_FILE"; }

# Load adapter configuration
if [[ -f "\${ADAPTERS_CONF}" ]]; then
    # shellcheck source=/dev/null
    source "\${ADAPTERS_CONF}"
    # Convert space-separated strings to arrays
    read -ra WIFI_CAPTURE_INTERFACES <<< "\${WIFI_CAPTURE_INTERFACES}"
    read -ra WIFI_CAPTURE_NAMES <<< "\${WIFI_CAPTURE_NAMES}"
else
    log "ERROR: Adapter configuration not found at \${ADAPTERS_CONF}"
    log "Please run: sudo /path/to/install.sh --configure"
    exit 1
fi

# Determine mode from environment or default
MODE="\${KISMET_MODE:-normal}"

# Create organized log directory structure: ~/kismet/logs/<mode>/<date>/
TODAY=\$(date '+%Y-%m-%d')
KISMET_DIR="\${KISMET_BASE}/logs/\${MODE}/\${TODAY}"
mkdir -p "\$KISMET_DIR"

log "Log directory: \$KISMET_DIR"

cd "\$KISMET_DIR"

# Check GPS status
log "Checking GPS status..."
GPS_STATUS=\$(gpspipe -w -n 1 2>/dev/null | grep -o '"mode":[0-9]' | head -1 || true)
if [[ "\$GPS_STATUS" == *"3"* ]]; then
    log "GPS status: 3D Fix"
elif [[ "\$GPS_STATUS" == *"2"* ]]; then
    log "GPS status: 2D Fix"
else
    log "GPS status: No fix (searching for satellites)"
fi

# Try to sync time from GPS
log "Attempting GPS time synchronization..."
GPS_TIME=\$(gpspipe -w -n 5 2>/dev/null | grep -o '"time":"[^"]*"' | head -1 | cut -d'"' -f4 || true)
if [[ -n "\$GPS_TIME" ]]; then
    log "GPS time received: \$GPS_TIME"
    date -s "\$GPS_TIME" 2>/dev/null && log "System time synchronized from GPS" || log "Could not set system time"
fi

log "Starting Kismet in \$MODE mode..."

# Build capture interface arguments dynamically
CAPTURE_ARGS=""
for i in "\${!WIFI_CAPTURE_INTERFACES[@]}"; do
    iface="\${WIFI_CAPTURE_INTERFACES[\$i]}"
    name="\${WIFI_CAPTURE_NAMES[\$i]}"
    # Use persistent name if available, otherwise use original interface name
    if [[ -e "/sys/class/net/warpie_cap\${i}" ]]; then
        CAPTURE_ARGS="\${CAPTURE_ARGS} -c warpie_cap\${i}:name=\${name}"
    else
        CAPTURE_ARGS="\${CAPTURE_ARGS} -c \${iface}:name=\${name}"
    fi
done

log "Capture interfaces:\${CAPTURE_ARGS}"

case "\$MODE" in
    wardrive)
        # shellcheck disable=SC2086
        exec kismet --no-ncurses --override wardrive \${CAPTURE_ARGS}
        ;;
    *)
        # shellcheck disable=SC2086
        exec kismet --no-ncurses \${CAPTURE_ARGS}
        ;;
esac
WARDRIVE_EOF

    chmod +x /usr/local/bin/wardrive.sh
    
    # Create systemd service - runs as non-root user in kismet group
    cat > /etc/systemd/system/wardrive.service << SERVICE_EOF
[Unit]
Description=WarPie Wardrive (Kismet)
After=gpsd-wardriver.service warpie-network.service
Wants=gpsd-wardriver.service

[Service]
Type=simple
User=${WARPIE_USER}
Group=kismet
Environment=KISMET_MODE=normal
ExecStart=/usr/local/bin/wardrive.sh
Restart=on-failure
RestartSec=10
WorkingDirectory=/home/${WARPIE_USER}/kismet

[Install]
WantedBy=multi-user.target
SERVICE_EOF

    log_success "Wardrive service configured"
}

# =============================================================================
# CONFIGURE NETWORK SERVICE
# =============================================================================
configure_network_service() {
    log_info "Configuring network service..."
    
    cat > /etc/systemd/system/warpie-network.service << 'SERVICE_EOF'
[Unit]
Description=WarPie Network Manager (Auto AP/Client)
After=NetworkManager.service
Wants=NetworkManager.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/bin/network-manager.sh
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
SERVICE_EOF

    log_success "Network service configured"
}

# =============================================================================
# CONFIGURE CONTROL PANEL
# =============================================================================
configure_control_panel() {
    log_info "Installing control panel..."
    
    # NOTE: CSS curly braces are doubled ({{ }}) to escape Python's .format()
    cat > /usr/local/bin/warpie-control.py << 'CONTROL_EOF'
#!/usr/bin/env python3
"""
WarPie Control Panel - Kismet Mode Switcher
Runs on port 1337
"""

import http.server
import subprocess
import json
import os
import glob
from datetime import date
from urllib.parse import parse_qs

PORT = 1337

MODES = {
    "normal": {"name": "Normal Mode", "desc": "Full capture, home networks excluded", "env": "normal"},
    "wardrive": {"name": "Wardrive Mode", "desc": "Optimized AP-only scanning, faster channel hopping", "env": "wardrive"},
    "": {"name": " Mode", "desc": "Target only  target devices", "env": ""}
}

HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <title>WarPie Control Panel</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a2e;
            color: #eee;
            margin: 0;
            padding: 20px;
            min-height: 100vh;
        }}
        .container {{ max-width: 600px; margin: 0 auto; }}
        h1 {{ color: #00ff88; text-align: center; margin-bottom: 10px; }}
        .subtitle {{ text-align: center; color: #888; margin-bottom: 30px; }}
        .status-box {{
            background: #16213e;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            border: 1px solid #0f3460;
        }}
        .status-label {{ color: #888; font-size: 12px; text-transform: uppercase; }}
        .status-value {{ font-size: 24px; font-weight: bold; margin: 5px 0; }}
        .status-running {{ color: #00ff88; }}
        .status-stopped {{ color: #ff4757; }}
        .mode-btn {{
            display: block;
            width: 100%;
            padding: 20px;
            margin: 10px 0;
            border: none;
            border-radius: 10px;
            font-size: 18px;
            font-weight: bold;
            cursor: pointer;
            transition: transform 0.1s, box-shadow 0.1s;
        }}
        .mode-btn:hover {{ transform: translateY(-2px); box-shadow: 0 5px 20px rgba(0,0,0,0.3); }}
        .mode-btn:active {{ transform: translateY(0); }}
        .mode-btn.normal {{ background: #4834d4; color: white; }}
        .mode-btn.wardrive {{ background: #6c5ce7; color: white; }}
        .mode-btn. {{ background: #e84393; color: white; }}
        .mode-btn.stop {{ background: #ff4757; color: white; }}
        .mode-btn.active {{ box-shadow: 0 0 0 3px #00ff88; }}
        .mode-desc {{ font-size: 12px; color: rgba(255,255,255,0.7); margin-top: 5px; font-weight: normal; }}
        .links {{ text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #0f3460; }}
        .links a, .links button {{ 
            color: #00ff88; 
            text-decoration: none; 
            margin: 0 15px; 
            background: none;
            border: none;
            font-size: 16px;
            cursor: pointer;
            font-family: inherit;
        }}
        .links a:hover, .links button:hover {{ text-decoration: underline; }}
        .toast {{
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: #00ff88;
            color: #1a1a2e;
            padding: 15px 30px;
            border-radius: 10px;
            font-weight: bold;
            display: none;
            z-index: 1000;
        }}
        .gps-info {{ display: flex; justify-content: space-between; margin-top: 10px; padding-top: 10px; border-top: 1px solid #0f3460; }}
        .gps-item {{ text-align: center; }}
        .gps-label {{ font-size: 10px; color: #888; }}
        .gps-value {{ font-size: 14px; color: #00ff88; }}
        
        /* Log Viewer Flyout */
        .log-overlay {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0,0,0,0.5);
            opacity: 0;
            visibility: hidden;
            transition: opacity 0.3s, visibility 0.3s;
            z-index: 1001;
        }}
        .log-overlay.open {{ opacity: 1; visibility: visible; }}
        .log-flyout {{
            position: fixed;
            top: 0;
            right: -400px;
            width: 400px;
            max-width: 90vw;
            height: 100%;
            background: #16213e;
            border-left: 2px solid #00ff88;
            transition: right 0.3s ease;
            z-index: 1002;
            display: flex;
            flex-direction: column;
        }}
        .log-flyout.open {{ right: 0; }}
        .log-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 15px 20px;
            border-bottom: 1px solid #0f3460;
            background: #1a1a2e;
        }}
        .log-header h2 {{ margin: 0; color: #00ff88; font-size: 18px; }}
        .log-close {{
            background: none;
            border: none;
            color: #888;
            font-size: 28px;
            cursor: pointer;
            line-height: 1;
        }}
        .log-close:hover {{ color: #ff4757; }}
        .log-controls {{
            display: flex;
            gap: 10px;
            padding: 10px 20px;
            border-bottom: 1px solid #0f3460;
            background: #1a1a2e;
        }}
        .log-controls select, .log-controls button {{
            padding: 8px 12px;
            border-radius: 5px;
            border: 1px solid #0f3460;
            background: #16213e;
            color: #eee;
            font-size: 14px;
            cursor: pointer;
        }}
        .log-controls button:hover {{ background: #0f3460; }}
        .log-content {{
            flex: 1;
            overflow-y: auto;
            padding: 15px;
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
            font-size: 12px;
            line-height: 1.5;
            white-space: pre-wrap;
            word-break: break-all;
            background: #0d1117;
            color: #c9d1d9;
        }}
        .log-content .info {{ color: #58a6ff; }}
        .log-content .warn {{ color: #d29922; }}
        .log-content .error {{ color: #f85149; }}
        .log-content .device {{ color: #7ee787; }}
        .log-status {{
            padding: 8px 20px;
            border-top: 1px solid #0f3460;
            font-size: 12px;
            color: #888;
            background: #1a1a2e;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>WarPie Control</h1>
        <p class="subtitle">Kismet Mode Switcher</p>
        <div class="status-box">
            <div class="status-label">Kismet Status</div>
            <div class="status-value {status_class}">{status}</div>
            <div style="color: #888; font-size: 14px;">Mode: {current_mode}</div>
            <div class="gps-info">
                <div class="gps-item"><div class="gps-label">GPS</div><div class="gps-value">{gps_status}</div></div>
                <div class="gps-item"><div class="gps-label">Devices</div><div class="gps-value">{device_count}</div></div>
                <div class="gps-item"><div class="gps-label">Uptime</div><div class="gps-value">{uptime}</div></div>
            </div>
        </div>
        <form method="POST" id="modeForm">
            <button type="submit" name="mode" value="normal" class="mode-btn normal {active_normal}">Normal Mode<div class="mode-desc">Full capture, home networks excluded from logs</div></button>
            <button type="submit" name="mode" value="wardrive" class="mode-btn wardrive {active_wardrive}">Wardrive Mode<div class="mode-desc">AP-only, fast scan, home excluded from logs</div></button>
            <button type="submit" name="mode" value="" class="mode-btn  {active_}"> Mode<div class="mode-desc">Only LOG custom targets (UI shows all)</div></button>
            <button type="submit" name="mode" value="stop" class="mode-btn stop">Stop Kismet<div class="mode-desc">Stop all capture</div></button>
        </form>
        <div class="links">
            <a href="http://{host}:2501" target="_blank">Kismet UI</a>
            <button onclick="openLogs()">View Logs</button>
            <a href="/api/status">API Status</a>
        </div>
    </div>
    
    <!-- Log Viewer Flyout -->
    <div class="log-overlay" id="logOverlay" onclick="closeLogs()"></div>
    <div class="log-flyout" id="logFlyout">
        <div class="log-header">
            <h2>Live Logs</h2>
            <button class="log-close" onclick="closeLogs()">&times;</button>
        </div>
        <div class="log-controls">
            <select id="logSource" onchange="refreshLogs()">
                <option value="wigle">WiGLE CSV (Filtered Output)</option>
                <option value="wardrive">Wardrive Service</option>
                <option value="kismet">Kismet Output</option>
                <option value="gps">GPS Daemon</option>
                <option value="network">Network Manager</option>
            </select>
            <button onclick="refreshLogs()">Refresh</button>
        </div>
        <div class="log-content" id="logContent">Loading...</div>
        <div class="log-status" id="logStatus">Last updated: --</div>
    </div>
    
    <div class="toast" id="toast">Mode switched!</div>
    <script>
        let logInterval = null;
        let autoRefresh = true;
        
        function openLogs() {{
            document.getElementById('logOverlay').classList.add('open');
            document.getElementById('logFlyout').classList.add('open');
            refreshLogs();
            // Auto-refresh logs every 3 seconds
            logInterval = setInterval(refreshLogs, 3000);
        }}
        
        function closeLogs() {{
            document.getElementById('logOverlay').classList.remove('open');
            document.getElementById('logFlyout').classList.remove('open');
            if (logInterval) clearInterval(logInterval);
        }}
        
        function refreshLogs() {{
            const source = document.getElementById('logSource').value;
            const content = document.getElementById('logContent');
            const status = document.getElementById('logStatus');
            
            fetch('/api/logs?source=' + source)
                .then(r => r.json())
                .then(data => {{
                    // Colorize log lines
                    let html = data.logs.map(line => {{
                        if (line.includes('ERROR') || line.includes('error')) 
                            return '<span class="error">' + escapeHtml(line) + '</span>';
                        if (line.includes('WARN') || line.includes('warn'))
                            return '<span class="warn">' + escapeHtml(line) + '</span>';
                        if (line.includes('INFO') || line.includes('info'))
                            return '<span class="info">' + escapeHtml(line) + '</span>';
                        if (line.includes('Detected new') || line.includes('advertising SSID'))
                            return '<span class="device">' + escapeHtml(line) + '</span>';
                        return escapeHtml(line);
                    }}).join('\\n');
                    content.innerHTML = html || '<span style="color:#888">No log entries</span>';
                    content.scrollTop = content.scrollHeight;
                    status.textContent = 'Last updated: ' + new Date().toLocaleTimeString() + ' (' + data.lines + ' lines)';
                }})
                .catch(err => {{
                    content.innerHTML = '<span class="error">Failed to load logs</span>';
                    status.textContent = 'Error: ' + err.message;
                }});
        }}
        
        function escapeHtml(text) {{
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }}
        
        // Close flyout on Escape key
        document.addEventListener('keydown', e => {{ if (e.key === 'Escape') closeLogs(); }});
        
        // Auto-refresh status every 5 seconds (but not logs, to avoid interference)
        setInterval(() => {{
            if (!document.getElementById('logFlyout').classList.contains('open')) {{
                location.reload();
            }}
        }}, 5000);
        
        // Show toast on mode switch, then clear the URL parameter
        if (window.location.search.includes('switched')) {{
            const toast = document.getElementById('toast');
            toast.style.display = 'block';
            
            // Clear the URL parameter so toast doesn't show again on refresh
            if (window.history.replaceState) {{
                window.history.replaceState(null, null, window.location.pathname);
            }}
            
            // Hide toast after 2 seconds
            setTimeout(() => toast.style.display = 'none', 2000);
        }}
    </script>
</body>
</html>
"""

class WarPieHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args): pass
    
    def get_kismet_status(self):
        try:
            result = subprocess.run(['pgrep', '-a', 'kismet'], capture_output=True, text=True)
            if result.returncode == 0:
                cmdline = result.stdout
                if '--override ' in cmdline: return True, ''
                elif '--override wardrive' in cmdline: return True, 'Wardrive'
                else: return True, 'Normal'
            return False, 'Stopped'
        except: return False, 'Unknown'
    
    def get_gps_status(self):
        try:
            result = subprocess.run(['gpspipe', '-w', '-n', '1'], capture_output=True, text=True, timeout=2)
            if '"mode":3' in result.stdout: return '3D Fix'
            elif '"mode":2' in result.stdout: return '2D Fix'
            elif '"mode":1' in result.stdout: return 'No Fix'
            return 'Active'
        except: return 'N/A'
    
    def get_device_count(self):
        try:
            result = subprocess.run(['curl', '-s', '-u', 'kismet:kismet', '--max-time', '2',
                 'http://localhost:2501/devices/views/all/devices.json?fields=kismet.device.base.key'],
                capture_output=True, text=True, timeout=3)
            return str(len(json.loads(result.stdout)))
        except: return 'N/A'
    
    def get_uptime(self):
        try:
            with open('/proc/uptime', 'r') as f:
                secs = float(f.readline().split()[0])
            return f"{int(secs//3600)}h {int((secs%3600)//60)}m"
        except: return 'N/A'
    
    def get_logs(self, source='wardrive', lines=100):
        """Fetch recent log entries from various sources"""
        try:
            if source == 'wigle':
                # Find latest WiGLE CSV from current mode
                _, current_mode = self.get_kismet_status()
                mode_dir = current_mode.lower().replace(' ', '')
                if mode_dir == 'stopped':
                    mode_dir = 'normal'
                today = date.today().strftime('%Y-%m-%d')
                pattern = f'/home/pi/kismet/logs/{mode_dir}/{today}/*.wiglecsv'
                files = glob.glob(pattern)
                if not files:
                    # Try finding any wiglecsv
                    pattern = f'/home/pi/kismet/logs/*/{today}/*.wiglecsv'
                    files = glob.glob(pattern)
                if not files:
                    return [f'No WiGLE CSV found for today ({today})', f'Pattern: {pattern}', '', 'Waiting for Kismet to create log file...']
                latest = max(files, key=os.path.getmtime)
                result = subprocess.run(
                    ['tail', '-n', str(lines), latest],
                    capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    output = [f'=== {os.path.basename(latest)} ===', '']
                    output.extend(result.stdout.strip().split('\n') if result.stdout.strip() else ['(empty - no matching devices logged yet)'])
                    # Add line count
                    wc_result = subprocess.run(['wc', '-l', latest], capture_output=True, text=True, timeout=2)
                    if wc_result.returncode == 0:
                        count = wc_result.stdout.strip().split()[0]
                        output.append('')
                        output.append(f'Total lines in file: {count}')
                    return output
                return ['Error reading WiGLE CSV']
            elif source == 'wardrive':
                # Kismet wardrive service logs
                result = subprocess.run(
                    ['journalctl', '-u', 'wardrive', '-n', str(lines), '--no-pager', '-o', 'short'],
                    capture_output=True, text=True, timeout=5)
            elif source == 'kismet':
                # Raw Kismet output (more detailed)
                result = subprocess.run(
                    ['journalctl', '-u', 'wardrive', '-n', str(lines), '--no-pager', '-o', 'cat'],
                    capture_output=True, text=True, timeout=5)
            elif source == 'gps':
                # GPS daemon logs
                result = subprocess.run(
                    ['journalctl', '-u', 'gpsd-wardriver', '-n', str(lines), '--no-pager', '-o', 'short'],
                    capture_output=True, text=True, timeout=5)
            elif source == 'network':
                # Network manager logs
                result = subprocess.run(
                    ['journalctl', '-u', 'warpie-network', '-n', str(lines), '--no-pager', '-o', 'short'],
                    capture_output=True, text=True, timeout=5)
            else:
                return ['Unknown log source']
            
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip().split('\n')
            return ['No log entries found']
        except subprocess.TimeoutExpired:
            return ['Log fetch timed out']
        except Exception as e:
            return [f'Error fetching logs: {str(e)}']
    
    def switch_mode(self, mode):
        subprocess.run(['sudo', 'systemctl', 'stop', 'wardrive'], capture_output=True)
        subprocess.run(['sudo', 'pkill', '-9', 'kismet'], capture_output=True)
        subprocess.run(['sleep', '2'])
        if mode == 'stop': return True
        if mode in MODES:
            env_dir = '/etc/systemd/system/wardrive.service.d'
            os.makedirs(env_dir, exist_ok=True)
            with open(f'{env_dir}/mode.conf', 'w') as f:
                f.write(f'[Service]\nEnvironment=KISMET_MODE={mode}\n')
            subprocess.run(['sudo', 'systemctl', 'daemon-reload'], capture_output=True)
            subprocess.run(['sudo', 'systemctl', 'start', 'wardrive'], capture_output=True)
            return True
        return False
    
    def do_GET(self):
        if self.path == '/api/status':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            running, mode = self.get_kismet_status()
            self.wfile.write(json.dumps({'running': running, 'mode': mode, 'gps': self.get_gps_status(),
                'devices': self.get_device_count(), 'uptime': self.get_uptime()}).encode())
            return
        if self.path.startswith('/api/logs'):
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            # Parse source parameter
            source = 'wardrive'
            if '?' in self.path:
                params = parse_qs(self.path.split('?')[1])
                source = params.get('source', ['wardrive'])[0]
            logs = self.get_logs(source)
            self.wfile.write(json.dumps({'logs': logs, 'lines': len(logs), 'source': source}).encode())
            return
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        running, current_mode = self.get_kismet_status()
        host = self.headers.get('Host', 'localhost').split(':')[0]
        html = HTML_TEMPLATE.format(
            status='Running' if running else 'Stopped',
            status_class='status-running' if running else 'status-stopped',
            current_mode=current_mode, gps_status=self.get_gps_status(),
            device_count=self.get_device_count() if running else '0',
            uptime=self.get_uptime(), host=host,
            active_normal='active' if current_mode == 'Normal' else '',
            active_wardrive='active' if current_mode == 'Wardrive' else '',
            active_='active' if current_mode == '' else '')
        self.wfile.write(html.encode())
    
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        params = parse_qs(self.rfile.read(content_length).decode())
        mode = params.get('mode', [''])[0]
        if mode: self.switch_mode(mode)
        self.send_response(303)
        self.send_header('Location', '/?switched=1')
        self.end_headers()

def main():
    server = http.server.HTTPServer(('0.0.0.0', PORT), WarPieHandler)
    print(f"WarPie Control Panel running on port {PORT}")
    server.serve_forever()

if __name__ == '__main__':
    main()
CONTROL_EOF

    chmod +x /usr/local/bin/warpie-control.py
    
    cat > /etc/systemd/system/warpie-control.service << 'SERVICE_EOF'
[Unit]
Description=WarPie Control Panel
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /usr/local/bin/warpie-control.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE_EOF

    log_success "Control panel installed"
}

# =============================================================================
# CONFIGURE RECOVERY SCRIPT
# =============================================================================
configure_recovery() {
    log_info "Installing recovery script..."
    
    cat > /usr/local/bin/warpie-recovery.sh << 'RECOVERY_EOF'
#!/bin/bash
# WarPie Recovery Script - Restores normal WiFi operation

echo "=== WarPie Recovery ==="

# Stop all WarPie services
echo "Stopping WarPie services..."
systemctl stop wardrive 2>/dev/null
systemctl stop warpie-network 2>/dev/null
systemctl stop warpie-control 2>/dev/null

# Kill any stuck processes
pkill -9 kismet 2>/dev/null
pkill -9 hostapd 2>/dev/null
pkill -f "dnsmasq.*wlan0" 2>/dev/null

# Reset wlan0
ip link set wlan0 down 2>/dev/null
ip addr flush dev wlan0 2>/dev/null
ip link set wlan0 up 2>/dev/null

# Return wlan0 to NetworkManager
nmcli device set wlan0 managed yes 2>/dev/null

# Restart NetworkManager
systemctl restart NetworkManager

# Wait and reconnect
sleep 3
nmcli device wifi rescan 2>/dev/null

echo "=== Recovery Complete ==="
echo "Check connection: iw dev wlan0 link"
RECOVERY_EOF

    chmod +x /usr/local/bin/warpie-recovery.sh
    
    log_success "Recovery script installed"
}

# =============================================================================
# ENABLE SERVICES
# =============================================================================
enable_services() {
    log_info "Enabling services..."
    
    systemctl daemon-reload
    
    systemctl enable gpsd-wardriver
    systemctl enable warpie-network
    systemctl enable wardrive
    systemctl enable warpie-control
    
    log_success "Services enabled"
}

# =============================================================================
# START SERVICES
# =============================================================================
start_services() {
    log_info "Starting services..."
    
    systemctl start gpsd-wardriver || log_warn "gpsd-wardriver failed to start"
    systemctl restart warpie-control || log_warn "warpie-control failed to start"
    
    log_success "Services started"
}

# =============================================================================
# PRINT SUMMARY
# =============================================================================
print_summary() {
    local IP_ADDR=$(hostname -I | awk '{print $1}')
    
    echo ""
    echo "============================================================================="
    echo -e "${GREEN}WarPie Installation Complete!${NC}"
    echo "============================================================================="
    echo ""
    echo "Services installed:"
    echo "  - gpsd-wardriver    : GPS daemon"
    echo "  - warpie-network    : Auto AP/Client switching"
    echo "  - wardrive          : Kismet wardriving (runs as ${WARPIE_USER})"
    echo "  - warpie-control    : Web control panel"
    echo ""
    echo "Security:"
    echo "  - Kismet runs as user '${WARPIE_USER}' (not root)"
    echo "  - User '${WARPIE_USER}' added to 'kismet' group"
    echo "  - Capture binaries use suid-root for interface control only"
    echo ""
    echo "Access points:"
    echo "  - Control Panel     : http://${IP_ADDR}:1337"
    echo "  - Kismet UI         : http://${IP_ADDR}:2501"
    echo ""
    echo "AP Mode (when away from home):"
    echo "  - SSID              : ${AP_SSID}"
    echo "  - Password          : ${AP_PASS}"
    echo "  - IP                : ${AP_IP}"
    echo ""
    echo "Configuration files:"
    echo "  - Known BSSIDs      : ${WARPIE_DIR}/known_bssids.conf"
    echo "  - Kismet site       : ${KISMET_CONF_DIR}/kismet_site.conf"
    echo "  - Wardrive mode     : ${KISMET_CONF_DIR}/kismet_wardrive.conf"
    echo ""
    echo "Commands:"
    echo "  - Recovery          : sudo warpie-recovery.sh"
    echo "  - Reconfigure       : sudo ./install.sh --configure"
    echo "  - Test install      : sudo ./install.sh --test"
    echo "  - View logs         : journalctl -u wardrive -f"
    echo ""
    echo -e "${YELLOW}IMPORTANT: Log out and back in (or reboot) for group changes to take effect${NC}"
    echo ""
    echo "Reboot to start all services: sudo reboot"
    echo "============================================================================="
}

# =============================================================================
# TEST/VALIDATE INSTALLATION
# =============================================================================
run_tests() {
    echo "============================================================================="
    echo "WarPie Installation Test Suite"
    echo "============================================================================="
    echo ""
    
    local PASS=0
    local FAIL=0
    local WARN=0
    
    test_check() {
        local name="$1"
        local cmd="$2"
        local required="${3:-true}"
        
        if eval "$cmd" &>/dev/null; then
            log_success "$name"
            PASS=$((PASS + 1))
        else
            if [[ "$required" == "true" ]]; then
                log_error "$name"
                FAIL=$((FAIL + 1))
            else
                log_warn "$name (optional)"
                WARN=$((WARN + 1))
            fi
        fi
    }
    
    echo "--- Directories ---"
    test_check "Config directory exists" "[[ -d ${WARPIE_DIR} ]]"
    test_check "Log directory exists" "[[ -d ${LOG_DIR} ]]"
    test_check "Kismet log directory exists" "[[ -d /home/${WARPIE_USER}/kismet ]]"
    
    echo ""
    echo "--- Configuration Files ---"
    test_check "known_bssids.conf exists" "[[ -f ${WARPIE_DIR}/known_bssids.conf ]]"
    test_check "known_bssids.conf has entries" "grep -q '^[0-9a-fA-F]' ${WARPIE_DIR}/known_bssids.conf"
    test_check "kismet_site.conf exists" "[[ -f ${KISMET_CONF_DIR}/kismet_site.conf ]]"
    test_check "kismet_wardrive.conf exists" "[[ -f ${KISMET_CONF_DIR}/kismet_wardrive.conf ]]"
    test_check "hostapd config exists" "[[ -f /etc/hostapd/hostapd-wlan0.conf ]]"
    
    echo ""
    echo "--- Scripts ---"
    test_check "network-manager.sh exists" "[[ -x /usr/local/bin/network-manager.sh ]]"
    test_check "wardrive.sh exists" "[[ -x /usr/local/bin/wardrive.sh ]]"
    test_check "warpie-control.py exists" "[[ -x /usr/local/bin/warpie-control.py ]]"
    test_check "warpie-recovery.sh exists" "[[ -x /usr/local/bin/warpie-recovery.sh ]]"
    
    echo ""
    echo "--- Systemd Services ---"
    test_check "gpsd-wardriver.service exists" "[[ -f /etc/systemd/system/gpsd-wardriver.service ]]"
    test_check "warpie-network.service exists" "[[ -f /etc/systemd/system/warpie-network.service ]]"
    test_check "wardrive.service exists" "[[ -f /etc/systemd/system/wardrive.service ]]"
    test_check "warpie-control.service exists" "[[ -f /etc/systemd/system/warpie-control.service ]]"
    
    test_check "gpsd-wardriver enabled" "systemctl is-enabled gpsd-wardriver"
    test_check "warpie-network enabled" "systemctl is-enabled warpie-network"
    test_check "wardrive enabled" "systemctl is-enabled wardrive"
    test_check "warpie-control enabled" "systemctl is-enabled warpie-control"
    
    echo ""
    echo "--- Service Status ---"
    test_check "gpsd-wardriver running" "systemctl is-active gpsd-wardriver" "false"
    test_check "warpie-control running" "systemctl is-active warpie-control" "false"
    
    echo ""
    echo "--- Hardware Detection ---"
    test_check "GPS device present" "[[ -e /dev/ttyUSB0 ]] || [[ -e /dev/serial/by-id/usb-Prolific* ]]" "false"
    test_check "wlan1 exists" "ip link show wlan1" "false"
    test_check "wlan2 exists" "ip link show wlan2" "false"
    
    echo ""
    echo "--- Dependencies ---"
    test_check "Kismet installed" "command -v kismet"
    test_check "gpsd installed" "command -v gpsd"
    test_check "hostapd installed" "command -v hostapd"
    test_check "dnsmasq installed" "command -v dnsmasq"
    test_check "python3 installed" "command -v python3"
    
    echo ""
    echo "--- Security & Permissions ---"
    test_check "kismet group exists" "getent group kismet"
    test_check "User ${WARPIE_USER} in kismet group" "id -nG ${WARPIE_USER} | grep -qw kismet"
    test_check "Kismet capture binary suid-root" "[[ -u /usr/bin/kismet_cap_linux_wifi ]] || [[ -u /usr/local/bin/kismet_cap_linux_wifi ]]" "false"
    test_check "wardrive.service runs as non-root" "grep -q 'User=' /etc/systemd/system/wardrive.service"
    
    echo ""
    echo "--- Control Panel ---"
    if curl -s --max-time 3 http://localhost:1337 &>/dev/null; then
        log_success "Control panel accessible on port 1337"
        ((PASS++))
    else
        log_warn "Control panel not responding"
        ((WARN++))
    fi
    
    echo ""
    echo "============================================================================="
    echo -e "Results: ${GREEN}${PASS} passed${NC}, ${RED}${FAIL} failed${NC}, ${YELLOW}${WARN} warnings${NC}"
    echo "============================================================================="
    
    if [[ $FAIL -gt 0 ]]; then
        return 1
    fi
    return 0
}

# =============================================================================
# UNINSTALL
# =============================================================================
uninstall() {
    echo "============================================================================="
    echo "WarPie Uninstaller"
    echo "============================================================================="
    echo ""
    
    echo -e "${YELLOW}This will remove all WarPie components.${NC}"
    read -p "Are you sure? (yes/no): " confirm
    
    if [[ "$confirm" != "yes" ]]; then
        echo "Uninstall cancelled."
        exit 0
    fi
    
    log_info "Stopping services..."
    systemctl stop wardrive 2>/dev/null || true
    systemctl stop warpie-control 2>/dev/null || true
    systemctl stop warpie-network 2>/dev/null || true
    systemctl stop gpsd-wardriver 2>/dev/null || true
    
    log_info "Disabling services..."
    systemctl disable wardrive 2>/dev/null || true
    systemctl disable warpie-control 2>/dev/null || true
    systemctl disable warpie-network 2>/dev/null || true
    systemctl disable gpsd-wardriver 2>/dev/null || true
    
    log_info "Removing service files..."
    rm -f /etc/systemd/system/wardrive.service
    rm -f /etc/systemd/system/warpie-control.service
    rm -f /etc/systemd/system/warpie-network.service
    rm -f /etc/systemd/system/gpsd-wardriver.service
    rm -rf /etc/systemd/system/wardrive.service.d
    
    log_info "Removing scripts..."
    rm -f /usr/local/bin/network-manager.sh
    rm -f /usr/local/bin/wardrive.sh
    rm -f /usr/local/bin/warpie-control.py
    rm -f /usr/local/bin/warpie-recovery.sh
    
    log_info "Removing configurations..."
    rm -f "${KISMET_CONF_DIR}/kismet_site.conf"
    rm -f "${KISMET_CONF_DIR}/kismet_wardrive.conf"
    rm -f /etc/hostapd/hostapd-wlan0.conf
    
    echo ""
    read -p "Remove user data (BSSIDs, logs)? (yes/no): " remove_data
    if [[ "$remove_data" == "yes" ]]; then
        rm -rf "${WARPIE_DIR}"
        rm -rf "${LOG_DIR}"
        log_info "User data removed"
    else
        log_info "User data preserved in ${WARPIE_DIR}"
    fi
    
    log_info "Reloading systemd..."
    systemctl daemon-reload
    
    systemctl unmask gpsd 2>/dev/null || true
    
    log_success "WarPie uninstalled"
}

# =============================================================================
# CONFIGURE ONLY MODE
# =============================================================================
run_configure() {
    echo "============================================================================="
    echo "WarPie Configuration"
    echo "============================================================================="
    
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (use sudo)"
        exit 1
    fi
    
    # Initialize exclusions array
    KISMET_EXCLUSIONS=()

    # Load adapter config to get AP MAC for auto-exclusion
    if load_adapter_config && [[ -n "${WIFI_AP_MAC}" ]]; then
        local AP_MAC_UPPER
        AP_MAC_UPPER=$(echo "${WIFI_AP_MAC}" | tr '[:lower:]' '[:upper:]')
        log_info "Auto-excluding WarPie AP (MAC: ${AP_MAC_UPPER})"
        KISMET_EXCLUSIONS+=("kis_log_device_filter=IEEE802.11,${AP_MAC_UPPER}/FF:FF:FF:FF:FF:FF,block")
    fi

    configure_wifi_interactive
    
    # Update Kismet config with new exclusions
    if [[ ${#KISMET_EXCLUSIONS[@]} -gt 0 ]]; then
        log_info "Updating Kismet configuration..."
        
        # Update site config
        if [[ -f "${KISMET_CONF_DIR}/kismet_site.conf" ]]; then
            # Remove existing auto-generated exclusions
            sed -i '/# Excluded networks (auto-generated)/,$d' "${KISMET_CONF_DIR}/kismet_site.conf"
        fi
        
        echo "" >> "${KISMET_CONF_DIR}/kismet_site.conf"
        echo "# Excluded networks (auto-generated)" >> "${KISMET_CONF_DIR}/kismet_site.conf"
        for exclusion in "${KISMET_EXCLUSIONS[@]}"; do
            echo "$exclusion" >> "${KISMET_CONF_DIR}/kismet_site.conf"
        done
        
        log_success "Site config updated with ${#KISMET_EXCLUSIONS[@]} exclusion(s)"
        
        # Update wardrive config too
        if [[ -f "${KISMET_CONF_DIR}/kismet_wardrive.conf" ]]; then
            sed -i '/# Excluded networks (auto-generated)/,$d' "${KISMET_CONF_DIR}/kismet_wardrive.conf"
            sed -i '/# HOME NETWORK EXCLUSIONS/,$d' "${KISMET_CONF_DIR}/kismet_wardrive.conf"
            
            echo "" >> "${KISMET_CONF_DIR}/kismet_wardrive.conf"
            echo "# HOME NETWORK EXCLUSIONS" >> "${KISMET_CONF_DIR}/kismet_wardrive.conf"
            echo "# Excluded networks (auto-generated)" >> "${KISMET_CONF_DIR}/kismet_wardrive.conf"
            for exclusion in "${KISMET_EXCLUSIONS[@]}"; do
                echo "$exclusion" >> "${KISMET_CONF_DIR}/kismet_wardrive.conf"
            done
            
            log_success "Wardrive config updated with ${#KISMET_EXCLUSIONS[@]} exclusion(s)"
        fi
    fi
    
    echo ""
    log_success "Configuration complete!"
    echo ""
    echo "Changes will take effect after reboot or service restart."
}

# =============================================================================
# MAIN
# =============================================================================
main() {
    parse_args "$@"
    
    # Initialize exclusions array
    KISMET_EXCLUSIONS=()
    
    case "$MODE" in
        test)
            run_tests
            ;;
        uninstall)
            if [[ $EUID -ne 0 ]]; then
                log_error "This script must be run as root (use sudo)"
                exit 1
            fi
            uninstall
            ;;
        configure)
            run_configure
            ;;
        install)
            echo "============================================================================="
            echo "WarPie Wardriving System Installer v2.3.0"
            echo "============================================================================="
            echo ""

            preflight_checks
            create_directories
            configure_kismet_permissions

            # WiFi adapter detection and configuration (must run before other WiFi config)
            configure_adapters_interactive

            # Interactive WiFi network configuration (home networks, exclusions)
            configure_wifi_interactive || configure_known_bssids

            configure_network_manager
            configure_hostapd
            configure_gps
            configure_kismet
            configure_wardrive_service
            configure_network_service
            configure_control_panel
            configure_recovery
            enable_services
            start_services
            print_summary
            ;;
    esac
}

main "$@"
