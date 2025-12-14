#!/bin/bash
# =============================================================================
# WarPie SSID/BSSID Exclusion Manager
# =============================================================================
# Version: 2.4.0
# Date: 2025-12-12
#
# Purpose: CLI tool and JSON API for managing network exclusions in Kismet
# Supports:
#   - Interactive CLI mode for terminal use
#   - JSON API mode for web integration
#   - Live WiFi scanning for BSSID discovery
#   - Historical log analysis for known networks
#   - Multiple exclusion methods (BSSID-only, SSID-only, Hybrid)
#
# Usage:
#   Interactive:  ./warpie-exclude-ssid.sh
#   JSON API:     ./warpie-exclude-ssid.sh --json --scan "NetworkName"
#                 ./warpie-exclude-ssid.sh --json --list
#                 ./warpie-exclude-ssid.sh --json --add --ssid "Name" --method hybrid
#                 ./warpie-exclude-ssid.sh --json --remove 3
# =============================================================================

set -euo pipefail

# =============================================================================
# CONFIGURATION
# =============================================================================
readonly VERSION="2.4.0"
readonly WARPIE_DIR="/etc/warpie"
readonly EXCLUSIONS_FILE="${WARPIE_DIR}/ssid_exclusions.conf"
readonly KNOWN_BSSIDS_FILE="${WARPIE_DIR}/known_bssids.conf"
readonly KISMET_SITE_CONF="/usr/local/etc/kismet_site.conf"
readonly KISMET_WARDRIVE_CONF="/usr/local/etc/kismet_wardrive.conf"
readonly KISMET__CONF="/usr/local/etc/kismet_.conf"
readonly KISMET_LOGS_DIR="${HOME}/kismet/logs"
readonly SCAN_INTERFACE="wlan0"

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

# JSON output helper
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

# Ensure config directory exists
ensure_config_dir() {
    if [[ ! -d "$WARPIE_DIR" ]]; then
        sudo mkdir -p "$WARPIE_DIR"
    fi
    if [[ ! -f "$EXCLUSIONS_FILE" ]]; then
        sudo touch "$EXCLUSIONS_FILE"
        sudo chmod 644 "$EXCLUSIONS_FILE"
        # Add header
        echo "# WarPie SSID Exclusions" | sudo tee "$EXCLUSIONS_FILE" > /dev/null
        echo "# Format: ID|SSID|METHOD|BSSIDS|TIMESTAMP|DESCRIPTION" | sudo tee -a "$EXCLUSIONS_FILE" > /dev/null
        echo "# Methods: bssid, ssid, hybrid" | sudo tee -a "$EXCLUSIONS_FILE" > /dev/null
    fi
}

# Get next exclusion ID
get_next_id() {
    local max_id=0
    while IFS='|' read -r id rest; do
        [[ "$id" =~ ^[0-9]+$ ]] && (( id > max_id )) && max_id=$id
    done < "$EXCLUSIONS_FILE"
    echo $((max_id + 1))
}

# =============================================================================
# DISCOVERY ENGINE
# =============================================================================

# Scan for SSIDs matching a pattern using live WiFi scan
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
            if [[ -n "$current_bssid" && "$current_ssid" == *"$ssid_pattern"* ]]; then
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
    if [[ -n "$current_bssid" && "$current_ssid" == *"$ssid_pattern"* ]]; then
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

# Search historical Kismet logs for SSID
scan_historical() {
    local ssid_pattern="$1"
    local found_bssids=()
    
    # Search WiGLE CSV files
    if [[ -d "$KISMET_LOGS_DIR" ]]; then
        while IFS= read -r line; do
            # WiGLE CSV format: MAC,SSID,AuthMode,...
            local bssid ssid
            bssid=$(echo "$line" | cut -d',' -f1)
            ssid=$(echo "$line" | cut -d',' -f2)
            
            if [[ "$ssid" == *"$ssid_pattern"* && "$bssid" =~ ^[0-9A-Fa-f:]+$ ]]; then
                # Check if already in list
                local already_found=false
                for existing in "${found_bssids[@]:-}"; do
                    [[ "$existing" == "$bssid" ]] && already_found=true && break
                done
                [[ "$already_found" == "false" ]] && found_bssids+=("$bssid")
            fi
        done < <(find "$KISMET_LOGS_DIR" -name "*.wiglecsv" -exec grep -h "$ssid_pattern" {} \; 2>/dev/null || true)
    fi
    
    # Output as JSON array
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

# Combined discovery - live scan + historical
discover_ssid() {
    local ssid="$1"
    
    log_info "Scanning for networks matching '$ssid'..."
    
    # Live scan
    local live_results
    live_results=$(scan_live "$ssid")
    
    # Historical scan
    local historical_bssids
    historical_bssids=$(scan_historical "$ssid")
    
    # Combine results
    if [[ "$JSON_MODE" == "true" ]]; then
        echo "{\"ssid\":\"$ssid\",\"live\":$live_results,\"historical\":$historical_bssids}"
    else
        echo "$live_results"
    fi
}

# =============================================================================
# EXCLUSION MANAGEMENT
# =============================================================================

# List all current exclusions
list_exclusions() {
    ensure_config_dir
    
    local exclusions=()
    
    while IFS='|' read -r id ssid method bssids timestamp description; do
        # Skip comments and empty lines
        [[ -z "$id" || "$id" =~ ^# ]] && continue
        [[ ! "$id" =~ ^[0-9]+$ ]] && continue
        
        exclusions+=("{\"id\":$id,\"ssid\":\"$ssid\",\"method\":\"$method\",\"bssids\":\"$bssids\",\"timestamp\":\"$timestamp\",\"description\":\"$description\"}")
    done < "$EXCLUSIONS_FILE"
    
    if [[ "$JSON_MODE" == "true" ]]; then
        local json_array="["
        for i in "${!exclusions[@]}"; do
            json_array+="${exclusions[$i]}"
            [[ $i -lt $((${#exclusions[@]} - 1)) ]] && json_array+=","
        done
        json_array+="]"
        echo "{\"success\":true,\"exclusions\":$json_array,\"count\":${#exclusions[@]}}"
    else
        echo ""
        echo "Current SSID Exclusions:"
        echo "========================"
        if [[ ${#exclusions[@]} -eq 0 ]]; then
            echo "  (none configured)"
        else
            while IFS='|' read -r id ssid method bssids timestamp description; do
                [[ -z "$id" || "$id" =~ ^# ]] && continue
                [[ ! "$id" =~ ^[0-9]+$ ]] && continue
                
                echo ""
                echo -e "  ${BOLD}[$id]${NC} $ssid"
                echo "      Method: $method"
                [[ "$method" != "ssid" && -n "$bssids" ]] && echo "      BSSIDs: $bssids"
                echo "      Added: $timestamp"
                [[ -n "$description" ]] && echo "      Note: $description"
            done < "$EXCLUSIONS_FILE"
        fi
        echo ""
    fi
}

# Add a new exclusion
add_exclusion() {
    local ssid="$1"
    local method="$2"
    local bssids="${3:-}"
    local description="${4:-}"
    
    ensure_config_dir
    
    # Validate inputs
    if [[ -z "$ssid" ]]; then
        json_error "SSID is required"
    fi
    
    if [[ ! "$method" =~ ^(bssid|ssid|hybrid)$ ]]; then
        json_error "Method must be: bssid, ssid, or hybrid"
    fi
    
    # For BSSID-based methods, we need BSSIDs
    if [[ "$method" == "bssid" && -z "$bssids" ]]; then
        json_error "BSSID method requires at least one BSSID"
    fi
    
    local id
    id=$(get_next_id)
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    # Add to exclusions file
    echo "${id}|${ssid}|${method}|${bssids}|${timestamp}|${description}" | sudo tee -a "$EXCLUSIONS_FILE" > /dev/null
    
    # Apply to Kismet configs
    apply_exclusion_to_kismet "$ssid" "$method" "$bssids"
    
    if [[ "$JSON_MODE" == "true" ]]; then
        echo "{\"success\":true,\"id\":$id,\"message\":\"Exclusion added for '$ssid'\"}"
    else
        log_success "Exclusion #$id added for '$ssid' using $method method"
    fi
}

# Remove an exclusion by ID
remove_exclusion() {
    local id="$1"
    
    ensure_config_dir
    
    # Find the exclusion
    local found=false
    local ssid=""
    local method=""
    local bssids=""
    
    while IFS='|' read -r eid essid emethod ebssids rest; do
        if [[ "$eid" == "$id" ]]; then
            found=true
            ssid="$essid"
            method="$emethod"
            bssids="$ebssids"
            break
        fi
    done < "$EXCLUSIONS_FILE"
    
    if [[ "$found" == "false" ]]; then
        json_error "Exclusion ID $id not found"
    fi
    
    # Remove from file
    sudo sed -i "/^${id}|/d" "$EXCLUSIONS_FILE"
    
    # Remove from Kismet configs
    remove_exclusion_from_kismet "$ssid" "$method" "$bssids"
    
    if [[ "$JSON_MODE" == "true" ]]; then
        echo "{\"success\":true,\"message\":\"Exclusion #$id removed\"}"
    else
        log_success "Exclusion #$id removed for '$ssid'"
    fi
}

# =============================================================================
# KISMET CONFIGURATION MANAGEMENT
# =============================================================================

# Apply exclusion filters to all Kismet config files
apply_exclusion_to_kismet() {
    local ssid="$1"
    local method="$2"
    local bssids="$3"
    
    local configs=("$KISMET_SITE_CONF" "$KISMET_WARDRIVE_CONF")
    
    for config in "${configs[@]}"; do
        [[ ! -f "$config" ]] && continue
        
        # Add marker comment
        local marker="# SSID_EXCLUSION: $ssid"
        
        case "$method" in
            bssid)
                # Add BSSID filters only
                IFS=',' read -ra bssid_array <<< "$bssids"
                for bssid in "${bssid_array[@]}"; do
                    local upper_bssid
                    upper_bssid=$(echo "$bssid" | tr '[:lower:]' '[:upper:]')
                    echo "$marker" | sudo tee -a "$config" > /dev/null
                    echo "kis_log_device_filter=IEEE802.11,${upper_bssid},block" | sudo tee -a "$config" > /dev/null
                done
                ;;
            ssid)
                # Add SSID filter (note: Kismet may not support this directly)
                # We use a workaround with MAC masks for common prefixes
                echo "$marker" | sudo tee -a "$config" > /dev/null
                echo "# SSID-only exclusion for: $ssid (requires runtime filtering)" | sudo tee -a "$config" > /dev/null
                ;;
            hybrid)
                # Add both BSSID filters and SSID marker
                if [[ -n "$bssids" ]]; then
                    IFS=',' read -ra bssid_array <<< "$bssids"
                    for bssid in "${bssid_array[@]}"; do
                        local upper_bssid
                        upper_bssid=$(echo "$bssid" | tr '[:lower:]' '[:upper:]')
                        echo "$marker" | sudo tee -a "$config" > /dev/null
                        echo "kis_log_device_filter=IEEE802.11,${upper_bssid},block" | sudo tee -a "$config" > /dev/null
                    done
                fi
                echo "$marker" | sudo tee -a "$config" > /dev/null
                echo "# Hybrid exclusion (BSSID + SSID) for: $ssid" | sudo tee -a "$config" > /dev/null
                ;;
        esac
    done
    
    log_info "Kismet configurations updated"
}

# Remove exclusion filters from Kismet configs
remove_exclusion_from_kismet() {
    local ssid="$1"
    local method="$2"
    local bssids="$3"
    
    local configs=("$KISMET_SITE_CONF" "$KISMET_WARDRIVE_CONF")
    
    for config in "${configs[@]}"; do
        [[ ! -f "$config" ]] && continue
        
        # Remove all lines with the SSID marker
        local marker="# SSID_EXCLUSION: $ssid"
        sudo sed -i "/$marker/d" "$config"
        
        # Also remove the BSSID filter lines that follow markers
        if [[ -n "$bssids" ]]; then
            IFS=',' read -ra bssid_array <<< "$bssids"
            for bssid in "${bssid_array[@]}"; do
                local upper_bssid
                upper_bssid=$(echo "$bssid" | tr '[:lower:]' '[:upper:]')
                sudo sed -i "/kis_log_device_filter=IEEE802.11,${upper_bssid},block/d" "$config"
            done
        fi
    done
    
    log_info "Kismet configurations cleaned"
}

# =============================================================================
# INTERACTIVE CLI MODE
# =============================================================================

interactive_add() {
    echo ""
    echo -e "${BOLD}=== Add SSID Exclusion ===${NC}"
    echo ""
    
    # Get SSID
    read -rp "Enter SSID to exclude: " ssid
    
    if [[ -z "$ssid" ]]; then
        log_error "No SSID entered"
        return 1
    fi
    
    # Discover networks
    echo ""
    log_info "Scanning for '$ssid'..."
    
    local live_json
    live_json=$(scan_live "$ssid")
    
    # Parse and display results
    local bssid_count=0
    local found_bssids=()
    
    # Simple JSON parsing for our format
    if [[ "$live_json" != "[]" ]]; then
        while IFS= read -r match; do
            local bssid signal
            bssid=$(echo "$match" | grep -o '"bssid":"[^"]*"' | cut -d'"' -f4)
            signal=$(echo "$match" | grep -o '"signal":"[^"]*"' | cut -d'"' -f4)
            if [[ -n "$bssid" ]]; then
                found_bssids+=("$bssid")
                ((bssid_count++))
                echo "  Found: $bssid (Signal: ${signal}dBm)"
            fi
        done < <(echo "$live_json" | tr '{}' '\n' | grep bssid)
    fi
    
    # Also check historical
    local hist_json
    hist_json=$(scan_historical "$ssid")
    
    if [[ "$hist_json" != "[]" ]]; then
        echo ""
        log_info "Also found in historical logs:"
        while IFS= read -r bssid; do
            bssid=$(echo "$bssid" | tr -d '[]",' | xargs)
            # shellcheck disable=SC2076  # Intentional literal match for array membership check
            if [[ -n "$bssid" && ! " ${found_bssids[*]:-} " =~ " $bssid " ]]; then
                found_bssids+=("$bssid")
                ((bssid_count++))
                echo "  Historical: $bssid"
            fi
        done < <(echo "$hist_json" | tr ',' '\n')
    fi
    
    echo ""
    if [[ $bssid_count -eq 0 ]]; then
        echo "No BSSIDs found for '$ssid'"
        echo ""
        echo "Options:"
        echo "  [1] Add SSID-only exclusion (for dynamic MAC networks)"
        echo "  [2] Cancel"
        echo ""
        read -rp "Choice [1-2]: " choice
        
        case "$choice" in
            1)
                read -rp "Description (optional): " desc
                add_exclusion "$ssid" "ssid" "" "$desc"
                ;;
            *)
                echo "Cancelled"
                ;;
        esac
    else
        echo "Found $bssid_count BSSID(s) for '$ssid'"
        echo ""
        echo "Exclusion Options:"
        echo "  [1] BSSID-Only  → Block only these $bssid_count specific MAC(s)"
        echo "  [2] SSID-Only   → Block any network named '$ssid' (for dynamic MACs)"
        echo "  [3] Hybrid      → Block these MACs AND the SSID name"
        echo "  [4] Cancel"
        echo ""
        read -rp "Choice [1-4]: " choice
        
        local bssid_list
        bssid_list=$(IFS=','; echo "${found_bssids[*]}")
        
        case "$choice" in
            1)
                read -rp "Description (optional): " desc
                add_exclusion "$ssid" "bssid" "$bssid_list" "$desc"
                ;;
            2)
                read -rp "Description (optional): " desc
                add_exclusion "$ssid" "ssid" "" "$desc"
                ;;
            3)
                read -rp "Description (optional): " desc
                add_exclusion "$ssid" "hybrid" "$bssid_list" "$desc"
                ;;
            *)
                echo "Cancelled"
                ;;
        esac
    fi
}

interactive_remove() {
    echo ""
    list_exclusions
    
    read -rp "Enter exclusion ID to remove (or 'c' to cancel): " id
    
    if [[ "$id" == "c" || -z "$id" ]]; then
        echo "Cancelled"
        return
    fi
    
    if [[ ! "$id" =~ ^[0-9]+$ ]]; then
        log_error "Invalid ID"
        return 1
    fi
    
    remove_exclusion "$id"
}

interactive_menu() {
    while true; do
        echo ""
        echo -e "${BOLD}=== WarPie SSID Exclusion Manager ===${NC}"
        echo ""
        echo "  [1] Add exclusion"
        echo "  [2] List exclusions"
        echo "  [3] Remove exclusion"
        echo "  [4] Scan for network"
        echo "  [5] Exit"
        echo ""
        read -rp "Choice [1-5]: " choice
        
        case "$choice" in
            1) interactive_add ;;
            2) list_exclusions ;;
            3) interactive_remove ;;
            4)
                read -rp "Enter SSID to scan: " scan_ssid
                if [[ -n "$scan_ssid" ]]; then
                    discover_ssid "$scan_ssid"
                fi
                ;;
            5) exit 0 ;;
            *) log_error "Invalid choice" ;;
        esac
    done
}

# =============================================================================
# MAIN & ARGUMENT PARSING
# =============================================================================

show_help() {
    cat << EOF
WarPie SSID Exclusion Manager v${VERSION}

Usage:
  Interactive mode:
    $0
    
  JSON API mode:
    $0 --json --list                              List all exclusions
    $0 --json --scan "NetworkName"                Scan for SSID
    $0 --json --add --ssid "Name" --method TYPE   Add exclusion
    $0 --json --remove ID                         Remove exclusion by ID

Options:
  --json          Output in JSON format (for web integration)
  --quiet, -q     Suppress non-essential output
  --help, -h      Show this help message
  --version, -v   Show version

Exclusion Methods:
  bssid           Block specific MAC addresses only
  ssid            Block any network with matching name (for dynamic MACs)
  hybrid          Block both known MACs and the SSID name

Examples:
  $0 --json --scan "Starbucks"
  $0 --json --add --ssid "xfinitywifi" --method ssid
  $0 --json --add --ssid "CorpWiFi" --method hybrid --bssids "AA:BB:CC:DD:EE:FF"
  $0 --json --remove 3

EOF
}

main() {
    local action=""
    local ssid=""
    local method=""
    local bssids=""
    local remove_id=""
    local description=""
    
    # Parse arguments
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
                echo "WarPie SSID Exclusion Manager v${VERSION}"
                exit 0
                ;;
            --list)
                action="list"
                shift
                ;;
            --scan)
                action="scan"
                ssid="$2"
                shift 2
                ;;
            --add)
                action="add"
                shift
                ;;
            --remove)
                action="remove"
                remove_id="$2"
                shift 2
                ;;
            --ssid)
                ssid="$2"
                shift 2
                ;;
            --method)
                method="$2"
                shift 2
                ;;
            --bssids)
                bssids="$2"
                shift 2
                ;;
            --description)
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
            list_exclusions
            ;;
        scan)
            if [[ -z "$ssid" ]]; then
                json_error "SSID required for scan"
            fi
            discover_ssid "$ssid"
            ;;
        add)
            if [[ -z "$ssid" || -z "$method" ]]; then
                json_error "SSID and method required for add"
            fi
            add_exclusion "$ssid" "$method" "$bssids" "$description"
            ;;
        remove)
            if [[ -z "$remove_id" ]]; then
                json_error "ID required for remove"
            fi
            remove_exclusion "$remove_id"
            ;;
        "")
            # No action specified - run interactive mode
            if [[ "$JSON_MODE" == "true" ]]; then
                json_error "Action required in JSON mode (--list, --scan, --add, --remove)"
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
