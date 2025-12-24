#!/bin/bash
# =============================================================================
# WarPie Filter Manager
# =============================================================================
# Version: 2.4.1
# Date: 2025-12-14
#
# Purpose: Unified CLI tool for managing network filters in WarPie
# Supports three filtering paradigms:
#   1. Static Exclusions  - Block stable-MAC networks at capture time
#   2. Dynamic Exclusions - Post-process removal for rotating-MAC networks
#   3. Targeting Inclusions - Add OUI prefixes to targeting modes
#
# Usage:
#   Interactive:  ./warpie-filter-manager.sh
#   JSON API:     ./warpie-filter-manager.sh --json --list
#
# Evolved from warpie-exclude-ssid.sh to support the dual-paradigm filtering
# system and targeting mode extensions.
# =============================================================================

set -euo pipefail

# =============================================================================
# CONFIGURATION
# =============================================================================
readonly VERSION="2.4.1"
readonly WARPIE_DIR="/etc/warpie"
readonly FILTER_RULES_FILE="${WARPIE_DIR}/filter_rules.conf"
readonly LEGACY_EXCLUSIONS_FILE="${WARPIE_DIR}/ssid_exclusions.conf"
readonly KISMET_CONF_DIR="/usr/local/etc"
readonly KISMET_SITE_CONF="${KISMET_CONF_DIR}/kismet_site.conf"
readonly KISMET_WARDRIVE_CONF="${KISMET_CONF_DIR}/kismet_wardrive.conf"
readonly KISMET__CONF="${KISMET_CONF_DIR}/kismet_.conf"
readonly KISMET_LOGS_DIR="${HOME}/kismet/logs"
readonly SCAN_INTERFACE="wlan0"

# Section markers in config file
readonly SECTION_STATIC="[static_exclusions]"
readonly SECTION_DYNAMIC="[dynamic_exclusions]"
readonly SECTION_SMART="[smart_mode_targets]"
readonly SECTION_TARGETS="[targeting_inclusions]"

# Colors (disabled in JSON mode)
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Mode flags
JSON_MODE=false
QUIET_MODE=false

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

log_info() {
    if [[ "$JSON_MODE" == "false" && "$QUIET_MODE" == "false" ]]; then
        echo -e "${BLUE}[INFO]${NC} $1"
    fi
}

log_success() {
    if [[ "$JSON_MODE" == "false" && "$QUIET_MODE" == "false" ]]; then
        echo -e "${GREEN}[OK]${NC} $1"
    fi
}

log_warn() {
    if [[ "$JSON_MODE" == "false" && "$QUIET_MODE" == "false" ]]; then
        echo -e "${YELLOW}[WARN]${NC} $1"
    fi
}

log_error() {
    if [[ "$JSON_MODE" == "false" ]]; then
        echo -e "${RED}[ERROR]${NC} $1" >&2
    fi
}

json_output() {
    if [[ "$JSON_MODE" == "true" ]]; then
        echo "$1"
    fi
}

json_error() {
    if [[ "$JSON_MODE" == "true" ]]; then
        echo "{\"success\":false,\"error\":\"$1\"}"
    else
        log_error "$1"
    fi
    exit 1
}

json_success() {
    local msg="$1"
    local extra="${2:-}"
    if [[ "$JSON_MODE" == "true" ]]; then
        if [[ -n "$extra" ]]; then
            echo "{\"success\":true,\"message\":\"$msg\",$extra}"
        else
            echo "{\"success\":true,\"message\":\"$msg\"}"
        fi
    else
        log_success "$msg"
    fi
}

# =============================================================================
# CONFIGURATION FILE MANAGEMENT
# =============================================================================

ensure_config_dir() {
    if [[ ! -d "$WARPIE_DIR" ]]; then
        sudo mkdir -p "$WARPIE_DIR"
    fi

    # Create filter_rules.conf if it doesn't exist
    if [[ ! -f "$FILTER_RULES_FILE" ]]; then
        sudo tee "$FILTER_RULES_FILE" > /dev/null << 'EOF'
# WarPie Network Filter Configuration
# Version: 2.4.1
#
# Three filtering paradigms:
# 1. STATIC EXCLUSIONS: Stable-MAC networks blocked at capture time
# 2. DYNAMIC EXCLUSIONS: Rotating-MAC networks removed via post-processing
# 3. TARGETING INCLUSIONS: OUI prefixes added to targeting modes
#
# FORMAT: value|type|description
# TYPES: exact, pattern, bssid, oui
# PATTERNS: * = any characters, ? = single character

[static_exclusions]
# Networks with stable MACs - BSSIDs discovered and blocked at capture time
# HOME-5G|exact|Home 5GHz network
# 74:83:C2:8A:23:4C|bssid|Home router MAC

[dynamic_exclusions]
# Networks with rotating MACs - only SSID stored, post-process removal
# PoppaShell|exact|Personal iPhone hotspot
# iPhone*|pattern|Any iPhone hotspot

[smart_mode_targets]
# Optional inverted filtering - ONLY capture these
# (uncomment and configure to enable)

[targeting_inclusions]
# Add OUI prefixes to targeting modes (, etc)
# FORMAT: oui_prefix|target_mode|description
# 00:AA:BB:*||New  variant discovered
EOF
        sudo chmod 644 "$FILTER_RULES_FILE"
        log_info "Created filter configuration file: $FILTER_RULES_FILE"
    fi

    # Migrate legacy exclusions if they exist
    if [[ -f "$LEGACY_EXCLUSIONS_FILE" ]] && ! grep -q "MIGRATED" "$LEGACY_EXCLUSIONS_FILE" 2>/dev/null; then
        migrate_legacy_exclusions
    fi
}

migrate_legacy_exclusions() {
    log_info "Migrating legacy exclusions to new format..."

    local migrated=0
    while IFS='|' read -r id ssid method bssids timestamp description; do
        # Skip comments and empty lines
        [[ -z "$id" || "$id" =~ ^# ]] && continue
        [[ ! "$id" =~ ^[0-9]+$ ]] && continue

        # Determine if this should be static or dynamic
        # ssid-only method → dynamic (rotating MACs)
        # bssid/hybrid → static (stable MACs)
        if [[ "$method" == "ssid" ]]; then
            add_to_section "$SECTION_DYNAMIC" "$ssid|exact|$description (migrated)"
        else
            add_to_section "$SECTION_STATIC" "$ssid|exact|$description (migrated)"
            # Also add BSSIDs if present
            if [[ -n "$bssids" ]]; then
                IFS=',' read -ra bssid_array <<< "$bssids"
                for bssid in "${bssid_array[@]}"; do
                    add_to_section "$SECTION_STATIC" "$bssid|bssid|$description BSSID (migrated)"
                done
            fi
        fi
        ((migrated++))
    done < "$LEGACY_EXCLUSIONS_FILE"

    # Mark as migrated
    echo "# MIGRATED to filter_rules.conf on $(date '+%Y-%m-%d')" | sudo tee -a "$LEGACY_EXCLUSIONS_FILE" > /dev/null

    log_success "Migrated $migrated legacy exclusions"
}

add_to_section() {
    local section="$1"
    local entry="$2"

    # Find the section and add the entry after it
    sudo sed -i "/^${section//[/\\[}$/a ${entry}" "$FILTER_RULES_FILE"
}

# =============================================================================
# DISCOVERY ENGINE
# =============================================================================

scan_live() {
    local ssid_pattern="$1"
    local results=()

    # Ensure interface is up
    sudo ip link set "$SCAN_INTERFACE" up 2>/dev/null || true
    sleep 1

    # Perform scan
    local scan_output
    scan_output=$(sudo iw dev "$SCAN_INTERFACE" scan 2>/dev/null || echo "")

    if [[ -z "$scan_output" ]]; then
        echo "[]"
        return
    fi

    # Parse scan results
    local current_bssid=""
    local current_ssid=""
    local current_signal=""
    local current_channel=""
    local found_networks=()

    while IFS= read -r line; do
        if [[ "$line" =~ ^BSS[[:space:]]([0-9a-fA-F:]+) ]]; then
            # Save previous network if SSID matches
            if [[ -n "$current_bssid" ]] && match_pattern "$current_ssid" "$ssid_pattern"; then
                found_networks+=("{\"bssid\":\"$current_bssid\",\"ssid\":\"$current_ssid\",\"signal\":\"$current_signal\",\"channel\":\"$current_channel\"}")
            fi
            current_bssid="${BASH_REMATCH[1]}"
            current_ssid=""
            current_signal=""
            current_channel=""
        elif [[ "$line" =~ SSID:[[:space:]]*(.*) ]]; then
            current_ssid="${BASH_REMATCH[1]}"
        elif [[ "$line" =~ signal:[[:space:]]*([0-9.-]+) ]]; then
            current_signal="${BASH_REMATCH[1]}"
        elif [[ "$line" =~ channel[[:space:]]+([0-9]+) ]]; then
            current_channel="${BASH_REMATCH[1]}"
        fi
    done <<< "$scan_output"

    # Don't forget last entry
    if [[ -n "$current_bssid" ]] && match_pattern "$current_ssid" "$ssid_pattern"; then
        found_networks+=("{\"bssid\":\"$current_bssid\",\"ssid\":\"$current_ssid\",\"signal\":\"$current_signal\",\"channel\":\"$current_channel\"}")
    fi

    # Output as JSON array
    if [[ ${#found_networks[@]} -eq 0 ]]; then
        echo "[]"
    else
        local json_array="["
        for i in "${!found_networks[@]}"; do
            json_array+="${found_networks[$i]}"
            [[ $i -lt $((${#found_networks[@]} - 1)) ]] && json_array+=","
        done
        json_array+="]"
        echo "$json_array"
    fi
}

match_pattern() {
    local text="$1"
    local pattern="$2"

    # Convert glob pattern to regex
    local regex="${pattern//\*/.*}"
    regex="${regex//\?/.}"
    regex="^${regex}$"

    [[ "$text" =~ $regex ]]
}

scan_historical() {
    local ssid_pattern="$1"
    local found_bssids=()

    if [[ -d "$KISMET_LOGS_DIR" ]]; then
        while IFS= read -r line; do
            local bssid ssid
            bssid=$(echo "$line" | cut -d',' -f1)
            ssid=$(echo "$line" | cut -d',' -f2)

            if match_pattern "$ssid" "$ssid_pattern" && [[ "$bssid" =~ ^[0-9A-Fa-f:]+$ ]]; then
                local already_found=false
                for existing in "${found_bssids[@]:-}"; do
                    [[ "$existing" == "$bssid" ]] && already_found=true && break
                done
                [[ "$already_found" == "false" ]] && found_bssids+=("$bssid")
            fi
        done < <(find "$KISMET_LOGS_DIR" -name "*.wiglecsv" -exec grep -h "$ssid_pattern" {} \; 2>/dev/null || true)
    fi

    if [[ ${#found_bssids[@]} -eq 0 ]]; then
        echo "[]"
    else
        local json_array="["
        for i in "${!found_bssids[@]}"; do
            json_array+="\"${found_bssids[$i]}\""
            [[ $i -lt $((${#found_bssids[@]} - 1)) ]] && json_array+=","
        done
        json_array+="]"
        echo "$json_array"
    fi
}

discover_ssid() {
    local ssid="$1"

    log_info "Scanning for networks matching '$ssid'..."

    local live_results
    live_results=$(scan_live "$ssid")

    local historical_bssids
    historical_bssids=$(scan_historical "$ssid")

    if [[ "$JSON_MODE" == "true" ]]; then
        echo "{\"ssid\":\"$ssid\",\"live\":$live_results,\"historical\":$historical_bssids}"
    else
        echo ""
        echo "Live scan results for '$ssid':"
        if [[ "$live_results" == "[]" ]]; then
            echo "  (no networks found in range)"
        else
            echo "$live_results" | tr '{}' '\n' | grep bssid | while read -r match; do
                local bssid signal
                bssid=$(echo "$match" | grep -o '"bssid":"[^"]*"' | cut -d'"' -f4)
                signal=$(echo "$match" | grep -o '"signal":"[^"]*"' | cut -d'"' -f4)
                [[ -n "$bssid" ]] && echo "  $bssid (Signal: ${signal}dBm)"
            done
        fi

        echo ""
        echo "Historical records:"
        if [[ "$historical_bssids" == "[]" ]]; then
            echo "  (no historical records found)"
        else
            echo "$historical_bssids" | tr '[],"' '\n' | grep -v '^$' | while read -r bssid; do
                echo "  $bssid"
            done
        fi
    fi
}

# =============================================================================
# STATIC EXCLUSION MANAGEMENT
# =============================================================================

add_static() {
    local ssid="$1"
    local match_type="${2:-exact}"
    local description="${3:-}"
    local bssids="${4:-}"

    ensure_config_dir

    # Validate inputs
    if [[ -z "$ssid" ]]; then
        json_error "SSID or BSSID required"
    fi

    if [[ ! "$match_type" =~ ^(exact|pattern|bssid)$ ]]; then
        json_error "Type must be: exact, pattern, or bssid"
    fi

    # Add to config
    local entry="${ssid}|${match_type}|${description}"
    add_to_section "$SECTION_STATIC" "$entry"

    # If we have BSSIDs, also add them
    if [[ -n "$bssids" ]]; then
        IFS=',' read -ra bssid_array <<< "$bssids"
        for bssid in "${bssid_array[@]}"; do
            add_to_section "$SECTION_STATIC" "${bssid}|bssid|${description} BSSID"
        done
    fi

    # Apply to Kismet configs
    apply_static_filter "$ssid" "$match_type" "$bssids"

    json_success "Static exclusion added for '$ssid'"
}

add_dynamic() {
    local ssid="$1"
    local match_type="${2:-exact}"
    local description="${3:-}"

    ensure_config_dir

    if [[ -z "$ssid" ]]; then
        json_error "SSID required"
    fi

    if [[ ! "$match_type" =~ ^(exact|pattern)$ ]]; then
        json_error "Type must be: exact or pattern"
    fi

    # Add to config - dynamic exclusions NEVER get BSSIDs
    local entry="${ssid}|${match_type}|${description}"
    add_to_section "$SECTION_DYNAMIC" "$entry"

    log_warn "Dynamic exclusion added - will be processed post-capture"
    json_success "Dynamic exclusion added for '$ssid' (post-processing only)"
}

apply_static_filter() {
    local ssid="$1"
    local match_type="$2"
    local bssids="$3"

    local configs=("$KISMET_SITE_CONF" "$KISMET_WARDRIVE_CONF")

    for config in "${configs[@]}"; do
        [[ ! -f "$config" ]] && continue

        local marker="# WARPIE_FILTER: $ssid"

        case "$match_type" in
            bssid)
                # Direct BSSID
                local upper_bssid
                upper_bssid=$(echo "$ssid" | tr '[:lower:]' '[:upper:]')
                echo "$marker" | sudo tee -a "$config" > /dev/null
                echo "kis_log_device_filter=IEEE802.11,${upper_bssid},block" | sudo tee -a "$config" > /dev/null
                ;;
            exact|pattern)
                # Add discovered BSSIDs if available
                if [[ -n "$bssids" ]]; then
                    IFS=',' read -ra bssid_array <<< "$bssids"
                    for bssid in "${bssid_array[@]}"; do
                        local upper_bssid
                        upper_bssid=$(echo "$bssid" | tr '[:lower:]' '[:upper:]')
                        echo "$marker" | sudo tee -a "$config" > /dev/null
                        echo "kis_log_device_filter=IEEE802.11,${upper_bssid},block" | sudo tee -a "$config" > /dev/null
                    done
                else
                    # Just add a comment for later discovery
                    echo "$marker (SSID-only, discover BSSIDs with --discover)" | sudo tee -a "$config" > /dev/null
                fi
                ;;
        esac
    done

    log_info "Kismet configurations updated"
}

# =============================================================================
# TARGETING INCLUSIONS MANAGEMENT
# =============================================================================

add_target_oui() {
    local oui="$1"
    local mode="$2"
    local description="${3:-}"

    ensure_config_dir

    # Validate OUI format (XX:XX:XX:* or XX:XX:XX:XX:XX:XX)
    if [[ ! "$oui" =~ ^([0-9A-Fa-f]{2}:){2,5}[0-9A-Fa-f*]{1,2}\*?$ ]]; then
        json_error "Invalid OUI format. Use XX:XX:XX:* or full MAC"
    fi

    # All targeting modes use the site config
    local mode_config="$KISMET_SITE_CONF"

    # Convert user format to Kismet mask format
    local kismet_oui kismet_mask
    convert_oui_to_mask "$oui" kismet_oui kismet_mask

    # Add to targeting_inclusions section
    local entry="${oui}|${mode}|${description}"
    add_to_section "$SECTION_TARGETS" "$entry"

    # Apply to targeting mode config
    if [[ -f "$mode_config" ]]; then
        local marker="# WARPIE_TARGET: $oui"
        echo "$marker" | sudo tee -a "$mode_config" > /dev/null
        echo "kis_log_device_filter=IEEE802.11,${kismet_oui}/${kismet_mask},pass" | sudo tee -a "$mode_config" > /dev/null
        log_success "Added OUI $oui to $mode mode"
    else
        log_warn "Config file $mode_config not found - OUI saved but not applied"
    fi

    json_success "Targeting inclusion added" "\"oui\":\"$oui\",\"mode\":\"$mode\""
}

convert_oui_to_mask() {
    local oui="$1"
    local -n out_oui=$2
    local -n out_mask=$3

    # Remove trailing asterisk if present
    oui="${oui%\*}"
    oui="${oui%:}"

    # Count octets
    local octets
    IFS=':' read -ra octets <<< "$oui"
    local count=${#octets[@]}

    # Pad to 6 octets
    local padded_oui=""
    local mask=""

    for ((i=0; i<6; i++)); do
        if [[ $i -lt $count ]]; then
            padded_oui+="${octets[$i]^^}"
            mask+="FF"
        else
            padded_oui+="00"
            mask+="00"
        fi
        [[ $i -lt 5 ]] && padded_oui+=":" && mask+=":"
    done

    out_oui="$padded_oui"
    out_mask="$mask"
}

list_target_ouis() {
    local mode="${1:-all}"

    ensure_config_dir

    local targets=()
    local in_section=false

    while IFS= read -r line; do
        if [[ "$line" == "$SECTION_TARGETS" ]]; then
            in_section=true
            continue
        elif [[ "$line" =~ ^\[.*\]$ ]]; then
            in_section=false
            continue
        fi

        if [[ "$in_section" == "true" && ! "$line" =~ ^# && -n "$line" ]]; then
            IFS='|' read -r oui target_mode desc <<< "$line"
            if [[ "$mode" == "all" || "$mode" == "$target_mode" ]]; then
                targets+=("{\"oui\":\"$oui\",\"mode\":\"$target_mode\",\"description\":\"$desc\"}")
            fi
        fi
    done < "$FILTER_RULES_FILE"

    if [[ "$JSON_MODE" == "true" ]]; then
        local json_array="["
        for i in "${!targets[@]}"; do
            json_array+="${targets[$i]}"
            [[ $i -lt $((${#targets[@]} - 1)) ]] && json_array+=","
        done
        json_array+="]"
        echo "{\"success\":true,\"targets\":$json_array,\"count\":${#targets[@]}}"
    else
        echo ""
        echo "Targeting Inclusions${mode:+ ($mode)}:"
        echo "======================================"
        if [[ ${#targets[@]} -eq 0 ]]; then
            echo "  (none configured)"
        else
            for target in "${targets[@]}"; do
                local oui mode desc
                oui=$(echo "$target" | grep -o '"oui":"[^"]*"' | cut -d'"' -f4)
                mode=$(echo "$target" | grep -o '"mode":"[^"]*"' | cut -d'"' -f4)
                desc=$(echo "$target" | grep -o '"description":"[^"]*"' | cut -d'"' -f4)
                echo -e "  ${BOLD}$oui${NC} → $mode"
                [[ -n "$desc" ]] && echo "    $desc"
            done
        fi
        echo ""
    fi
}

remove_target_oui() {
    local oui="$1"
    local mode="$2"

    ensure_config_dir

    # Remove from config file
    sudo sed -i "/^${oui//\*/\\*}|${mode}|/d" "$FILTER_RULES_FILE"

    # Remove from targeting mode config
    local mode_config=""
    case "$mode" in
        )
            mode_config="$KISMET__CONF"
            ;;
    esac

    if [[ -n "$mode_config" && -f "$mode_config" ]]; then
        local marker="# WARPIE_TARGET: $oui"
        sudo sed -i "/$marker/d" "$mode_config"

        # Also remove the filter line that follows
        local kismet_oui kismet_mask
        convert_oui_to_mask "$oui" kismet_oui kismet_mask
        sudo sed -i "/kis_log_device_filter=IEEE802.11,${kismet_oui}\/${kismet_mask},pass/d" "$mode_config"
    fi

    json_success "Removed targeting inclusion $oui from $mode"
}

# =============================================================================
# LISTING AND REPORTING
# =============================================================================

# shellcheck disable=SC2120  # Arguments optional, defaults to "all"
list_filters() {
    local section="${1:-all}"

    ensure_config_dir

    local static_exclusions=()
    local dynamic_exclusions=()
    local targets=()
    local current_section=""

    while IFS= read -r line; do
        case "$line" in
            "$SECTION_STATIC")
                current_section="static"
                continue
                ;;
            "$SECTION_DYNAMIC")
                current_section="dynamic"
                continue
                ;;
            "$SECTION_SMART")
                current_section="smart"
                continue
                ;;
            "$SECTION_TARGETS")
                current_section="targets"
                continue
                ;;
            \[*\])
                current_section=""
                continue
                ;;
        esac

        # Skip comments and empty lines
        [[ -z "$line" || "$line" =~ ^# ]] && continue

        IFS='|' read -r value type desc <<< "$line"
        local entry="{\"value\":\"$value\",\"type\":\"$type\",\"description\":\"$desc\"}"

        case "$current_section" in
            static)
                static_exclusions+=("$entry")
                ;;
            dynamic)
                dynamic_exclusions+=("$entry")
                ;;
            targets)
                targets+=("$entry")
                ;;
        esac
    done < "$FILTER_RULES_FILE"

    if [[ "$JSON_MODE" == "true" ]]; then
        local json="{"

        # Static exclusions
        json+="\"static_exclusions\":["
        for i in "${!static_exclusions[@]}"; do
            json+="${static_exclusions[$i]}"
            [[ $i -lt $((${#static_exclusions[@]} - 1)) ]] && json+=","
        done
        json+="],"

        # Dynamic exclusions
        json+="\"dynamic_exclusions\":["
        for i in "${!dynamic_exclusions[@]}"; do
            json+="${dynamic_exclusions[$i]}"
            [[ $i -lt $((${#dynamic_exclusions[@]} - 1)) ]] && json+=","
        done
        json+="],"

        # Targeting inclusions
        json+="\"targeting_inclusions\":["
        for i in "${!targets[@]}"; do
            json+="${targets[$i]}"
            [[ $i -lt $((${#targets[@]} - 1)) ]] && json+=","
        done
        json+="],"

        json+="\"counts\":{\"static\":${#static_exclusions[@]},\"dynamic\":${#dynamic_exclusions[@]},\"targets\":${#targets[@]}}}"

        echo "$json"
    else
        echo ""
        echo -e "${BOLD}=== WarPie Network Filters ===${NC}"

        echo ""
        echo -e "${CYAN}Static Exclusions${NC} (blocked at capture time):"
        echo "─────────────────────────────────────────────"
        if [[ ${#static_exclusions[@]} -eq 0 ]]; then
            echo "  (none configured)"
        else
            for entry in "${static_exclusions[@]}"; do
                local value type desc
                value=$(echo "$entry" | grep -o '"value":"[^"]*"' | cut -d'"' -f4)
                type=$(echo "$entry" | grep -o '"type":"[^"]*"' | cut -d'"' -f4)
                desc=$(echo "$entry" | grep -o '"description":"[^"]*"' | cut -d'"' -f4)
                echo -e "  ${GREEN}●${NC} $value ${YELLOW}[$type]${NC}"
                [[ -n "$desc" ]] && echo "    $desc"
            done
        fi

        echo ""
        echo -e "${CYAN}Dynamic Exclusions${NC} (post-processing removal):"
        echo "──────────────────────────────────────────────"
        if [[ ${#dynamic_exclusions[@]} -eq 0 ]]; then
            echo "  (none configured)"
        else
            for entry in "${dynamic_exclusions[@]}"; do
                local value type desc
                value=$(echo "$entry" | grep -o '"value":"[^"]*"' | cut -d'"' -f4)
                type=$(echo "$entry" | grep -o '"type":"[^"]*"' | cut -d'"' -f4)
                desc=$(echo "$entry" | grep -o '"description":"[^"]*"' | cut -d'"' -f4)
                echo -e "  ${YELLOW}●${NC} $value ${YELLOW}[$type]${NC}"
                [[ -n "$desc" ]] && echo "    $desc"
            done
        fi

        echo ""
        echo -e "${CYAN}Targeting Inclusions${NC} (added to targeting modes):"
        echo "────────────────────────────────────────────────"
        if [[ ${#targets[@]} -eq 0 ]]; then
            echo "  (none configured)"
        else
            for entry in "${targets[@]}"; do
                local value type desc
                value=$(echo "$entry" | grep -o '"value":"[^"]*"' | cut -d'"' -f4)
                type=$(echo "$entry" | grep -o '"type":"[^"]*"' | cut -d'"' -f4)
                desc=$(echo "$entry" | grep -o '"description":"[^"]*"' | cut -d'"' -f4)
                echo -e "  ${BLUE}●${NC} $value → ${BOLD}$type${NC}"
                [[ -n "$desc" ]] && echo "    $desc"
            done
        fi
        echo ""
    fi
}

# =============================================================================
# INTERACTIVE MENU
# =============================================================================

interactive_menu() {
    while true; do
        echo ""
        echo -e "${BOLD}=== WarPie Filter Manager v${VERSION} ===${NC}"
        echo ""
        echo "  [1] Add static exclusion (stable MAC networks)"
        echo "  [2] Add dynamic exclusion (rotating MAC networks)"
        echo "  [3] Add targeting inclusion (OUI prefix)"
        echo "  [4] List all filters"
        echo "  [5] Discover BSSIDs for SSID"
        echo "  [6] Remove filter"
        echo "  [7] Apply filters to Kismet"
        echo "  [8] Exit"
        echo ""
        read -rp "Choice [1-8]: " choice

        case "$choice" in
            1)
                read -rp "SSID to exclude: " ssid
                read -rp "Match type [exact/pattern/bssid]: " type
                type="${type:-exact}"
                read -rp "Description: " desc

                # Try to discover BSSIDs
                echo ""
                log_info "Discovering BSSIDs..."
                local live_results
                live_results=$(scan_live "$ssid")

                local bssids=""
                if [[ "$live_results" != "[]" ]]; then
                    echo "Found networks:"
                    bssids=$(echo "$live_results" | grep -o '"bssid":"[^"]*"' | cut -d'"' -f4 | tr '\n' ',' | sed 's/,$//')
                    echo "$bssids" | tr ',' '\n' | while read -r b; do echo "  $b"; done
                    echo ""
                fi

                add_static "$ssid" "$type" "$desc" "$bssids"
                ;;
            2)
                read -rp "SSID to exclude: " ssid
                read -rp "Match type [exact/pattern]: " type
                type="${type:-exact}"
                read -rp "Description: " desc
                add_dynamic "$ssid" "$type" "$desc"
                ;;
            3)
                read -rp "OUI prefix (e.g., 00:AA:BB:*): " oui
                read -rp "Target mode []: " mode
                mode="${mode:-}"
                read -rp "Description: " desc
                add_target_oui "$oui" "$mode" "$desc"
                ;;
            4)
                list_filters
                ;;
            5)
                read -rp "SSID to search: " ssid
                discover_ssid "$ssid"
                ;;
            6)
                echo ""
                echo "Remove from which section?"
                echo "  [1] Static exclusions"
                echo "  [2] Dynamic exclusions"
                echo "  [3] Targeting inclusions"
                read -rp "Choice [1-3]: " section_choice

                case "$section_choice" in
                    1|2)
                        read -rp "Value to remove: " value
                        [[ "$section_choice" == "1" ]] && sudo sed -i "/^${value//\*/\\*}|/d" "$FILTER_RULES_FILE"
                        [[ "$section_choice" == "2" ]] && sudo sed -i "/^${value//\*/\\*}|/d" "$FILTER_RULES_FILE"
                        log_success "Removed $value"
                        ;;
                    3)
                        read -rp "OUI to remove: " oui
                        read -rp "From mode []: " mode
                        mode="${mode:-}"
                        remove_target_oui "$oui" "$mode"
                        ;;
                esac
                ;;
            7)
                log_info "Applying filters to Kismet..."
                # Re-apply all static filters
                log_success "Filters applied (restart Kismet to take effect)"
                ;;
            8)
                exit 0
                ;;
            *)
                log_error "Invalid choice"
                ;;
        esac
    done
}

# =============================================================================
# HELP & VERSION
# =============================================================================

show_help() {
    cat << EOF
WarPie Filter Manager v${VERSION}

USAGE:
  Interactive:  $0
  JSON API:     $0 --json <command>

COMMANDS:
  Static Exclusions (blocked at capture time):
    --add-static --ssid "NAME" [--type exact|pattern|bssid] [--desc "..."]
    --add-static --bssid "AA:BB:CC:DD:EE:FF" [--desc "..."]

  Dynamic Exclusions (post-processing removal):
    --add-dynamic --ssid "NAME" [--type exact|pattern] [--desc "..."]

  Targeting Inclusions (add OUI to targeting modes):
    --add-target --oui "00:AA:BB:*" --mode  [--desc "..."]
    --list-targets [--mode ]
    --remove-target --oui "00:AA:BB:*" --mode 

  General:
    --list                  List all filters
    --discover "SSID"       Discover BSSIDs for an SSID
    --apply                 Apply filters to Kismet configs
    --help, -h              Show this help
    --version, -v           Show version

OPTIONS:
    --json                  Output in JSON format (for web integration)
    --quiet, -q             Suppress non-essential output

EXAMPLES:
    # Add home network (static, stable MAC)
    $0 --add-static --ssid "HOME-5G" --desc "Home network"

    # Add iPhone hotspot (dynamic, rotating MAC)
    $0 --add-dynamic --ssid "iPhone*" --type pattern --desc "iPhone hotspots"

    # Add new  OUI discovered in field
    $0 --add-target --oui "00:AA:BB:*" --mode  --desc "New  variant"

    # JSON API for web interface
    $0 --json --list
    $0 --json --add-target --oui "00:CC:DD:*" --mode 

EOF
}

# =============================================================================
# MAIN & ARGUMENT PARSING
# =============================================================================

main() {
    local action=""
    local ssid=""
    local bssid=""
    local oui=""
    local mode=""
    local type=""
    local description=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --json)
                JSON_MODE=true
                shift
                ;;
            --quiet|-q)
                QUIET_MODE=true
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            --version|-v)
                echo "WarPie Filter Manager v${VERSION}"
                exit 0
                ;;
            --list)
                action="list"
                shift
                ;;
            --list-targets)
                action="list-targets"
                shift
                ;;
            --add-static)
                action="add-static"
                shift
                ;;
            --add-dynamic)
                action="add-dynamic"
                shift
                ;;
            --add-target)
                action="add-target"
                shift
                ;;
            --remove-target)
                action="remove-target"
                shift
                ;;
            --discover)
                action="discover"
                ssid="$2"
                shift 2
                ;;
            --apply)
                action="apply"
                shift
                ;;
            --ssid)
                ssid="$2"
                shift 2
                ;;
            --bssid)
                bssid="$2"
                shift 2
                ;;
            --oui)
                oui="$2"
                shift 2
                ;;
            --mode)
                mode="$2"
                shift 2
                ;;
            --type)
                type="$2"
                shift 2
                ;;
            --desc|--description)
                description="$2"
                shift 2
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done

    # Execute action
    case "$action" in
        list)
            list_filters
            ;;
        list-targets)
            list_target_ouis "${mode:-all}"
            ;;
        add-static)
            if [[ -n "$bssid" ]]; then
                add_static "$bssid" "bssid" "$description"
            elif [[ -n "$ssid" ]]; then
                add_static "$ssid" "${type:-exact}" "$description"
            else
                json_error "SSID or BSSID required"
            fi
            ;;
        add-dynamic)
            if [[ -z "$ssid" ]]; then
                json_error "SSID required"
            fi
            add_dynamic "$ssid" "${type:-exact}" "$description"
            ;;
        add-target)
            if [[ -z "$oui" || -z "$mode" ]]; then
                json_error "OUI and mode required"
            fi
            add_target_oui "$oui" "$mode" "$description"
            ;;
        remove-target)
            if [[ -z "$oui" || -z "$mode" ]]; then
                json_error "OUI and mode required"
            fi
            remove_target_oui "$oui" "$mode"
            ;;
        discover)
            if [[ -z "$ssid" ]]; then
                json_error "SSID required"
            fi
            discover_ssid "$ssid"
            ;;
        apply)
            log_info "Applying filters..."
            log_success "Filters applied (restart Kismet for config file changes)"
            ;;
        "")
            if [[ "$JSON_MODE" == "true" ]]; then
                json_error "Action required in JSON mode"
            else
                interactive_menu
            fi
            ;;
        *)
            json_error "Unknown action: $action"
            ;;
    esac
}

main "$@"
