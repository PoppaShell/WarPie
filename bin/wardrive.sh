#!/bin/bash
# WarPie Wardrive Launcher
# Organizes logs by mode and date

set -e

LOG_FILE="/var/log/warpie/wardrive.log"
ADAPTERS_CONF="/etc/warpie/adapters.conf"
KISMET_BASE="${HOME}/kismet"

# Standard WiFi Channel Lists (for expanding "all")
readonly CHANNELS_5_ALL="36,40,44,48,52,56,60,64,100,104,108,112,116,120,124,128,132,136,140,144,149,153,157,161,165"
readonly CHANNELS_6_PSC="5,21,37,53,69,85,101,117,133,149,165,181,197,213,229"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [INFO] $1" | tee -a "$LOG_FILE"; }

# Load adapter configuration
if [[ -f "${ADAPTERS_CONF}" ]]; then
    # shellcheck source=/dev/null
    source "${ADAPTERS_CONF}"
else
    log "ERROR: Adapter configuration not found at ${ADAPTERS_CONF}"
    log "Please run: sudo /path/to/install.sh --configure"
    exit 1
fi

# Build Kismet capture arguments with channel specifications
build_capture_args() {
    local args=""

    for ((i=0; i<WIFI_CAPTURE_COUNT; i++)); do
        local iface_var="ADAPTER_${i}_IFACE"
        local name_var="ADAPTER_${i}_NAME"
        local ch24_var="ADAPTER_${i}_CHANNELS_24"
        local ch5_var="ADAPTER_${i}_CHANNELS_5"
        local ch6_var="ADAPTER_${i}_CHANNELS_6"

        local iface="${!iface_var}"
        local name="${!name_var}"
        local ch24="${!ch24_var}"
        local ch5="${!ch5_var}"
        local ch6="${!ch6_var}"

        # Use the configured interface name directly
        local actual_iface="$iface"

        # Build combined channel list from all configured bands
        local all_channels=""

        # Add 2.4GHz channels
        if [[ -n "$ch24" ]]; then
            all_channels="$ch24"
        fi

        # Add 5GHz channels
        if [[ -n "$ch5" ]]; then
            local ch5_expanded="$ch5"
            [[ "$ch5" == "all" ]] && ch5_expanded="$CHANNELS_5_ALL"
            if [[ -n "$all_channels" ]]; then
                all_channels="${all_channels},${ch5_expanded}"
            else
                all_channels="$ch5_expanded"
            fi
        fi

        # Add 6GHz channels (append -6e suffix for Kismet)
        if [[ -n "$ch6" ]]; then
            local ch6_expanded="$ch6"
            [[ "$ch6" == "all" ]] && ch6_expanded="$CHANNELS_6_PSC"
            # Convert 6GHz channels to Kismet format (append -6e)
            local ch6_formatted=""
            IFS=',' read -ra ch6_array <<< "$ch6_expanded"
            for ch in "${ch6_array[@]}"; do
                [[ -n "$ch6_formatted" ]] && ch6_formatted="${ch6_formatted},"
                ch6_formatted="${ch6_formatted}${ch}-6e"
            done
            if [[ -n "$all_channels" ]]; then
                all_channels="${all_channels},${ch6_formatted}"
            else
                all_channels="$ch6_formatted"
            fi
        fi

        # Build source argument
        if [[ -n "$all_channels" ]]; then
            args="${args} -c ${actual_iface}:name=${name},channels=\"${all_channels}\""
        else
            # Fallback to just interface name if no channels specified
            args="${args} -c ${actual_iface}:name=${name}"
        fi
    done

    echo "$args"
}

# Determine mode from environment or default
MODE="${KISMET_MODE:-normal}"

# Create organized log directory structure: ~/kismet/logs/<mode>/<date>/
TODAY=$(date '+%Y-%m-%d')
KISMET_DIR="${KISMET_BASE}/logs/${MODE}/${TODAY}"
mkdir -p "$KISMET_DIR"

log "Log directory: $KISMET_DIR"

cd "$KISMET_DIR" || exit 1

# Check GPS status
log "Checking GPS status..."
GPS_STATUS=$(gpspipe -w -n 1 2>/dev/null | grep -o '"mode":[0-9]' | head -1 || true)
if [[ "$GPS_STATUS" == *"3"* ]]; then
    log "GPS status: 3D Fix"
elif [[ "$GPS_STATUS" == *"2"* ]]; then
    log "GPS status: 2D Fix"
else
    log "GPS status: No fix (searching for satellites)"
fi

# Try to sync time from GPS
log "Attempting GPS time synchronization..."
GPS_TIME=$(gpspipe -w -n 5 2>/dev/null | grep -o '"time":"[^"]*"' | head -1 | cut -d'"' -f4 || true)
if [[ -n "$GPS_TIME" ]]; then
    log "GPS time received: $GPS_TIME"
    date -s "$GPS_TIME" 2>/dev/null && log "System time synchronized from GPS" || log "Could not set system time"
fi

log "Starting Kismet in $MODE mode..."

# Build capture interface arguments with channel configuration
CAPTURE_ARGS=$(build_capture_args)

log "Capture interfaces:${CAPTURE_ARGS}"

case "$MODE" in
    wardrive)
        # shellcheck disable=SC2086
        exec kismet --no-ncurses --override wardrive ${CAPTURE_ARGS}
        ;;
    *)
        # shellcheck disable=SC2086
        exec kismet --no-ncurses ${CAPTURE_ARGS}
        ;;
esac
