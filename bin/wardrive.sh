#!/bin/bash
# WarPie Wardrive Launcher
# Organizes logs by mode and date

set -e

LOG_FILE="/var/log/warpie/wardrive.log"
ADAPTERS_CONF="/etc/warpie/adapters.conf"
KISMET_BASE="${HOME}/kismet"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [INFO] $1" | tee -a "$LOG_FILE"; }

# Load adapter configuration
if [[ -f "${ADAPTERS_CONF}" ]]; then
    # shellcheck source=/dev/null
    source "${ADAPTERS_CONF}"
    # Convert space-separated strings to arrays
    read -ra WIFI_CAPTURE_INTERFACES <<< "${WIFI_CAPTURE_INTERFACES}"
    read -ra WIFI_CAPTURE_NAMES <<< "${WIFI_CAPTURE_NAMES}"
else
    log "ERROR: Adapter configuration not found at ${ADAPTERS_CONF}"
    log "Please run: sudo /path/to/install.sh --configure"
    exit 1
fi

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

# Build capture interface arguments dynamically
CAPTURE_ARGS=""
for i in "${!WIFI_CAPTURE_INTERFACES[@]}"; do
    iface="${WIFI_CAPTURE_INTERFACES[$i]}"
    name="${WIFI_CAPTURE_NAMES[$i]}"
    # Use persistent name if available, otherwise use original interface name
    if [[ -e "/sys/class/net/warpie_cap${i}" ]]; then
        CAPTURE_ARGS="${CAPTURE_ARGS} -c warpie_cap${i}:name=${name}"
    else
        CAPTURE_ARGS="${CAPTURE_ARGS} -c ${iface}:name=${name}"
    fi
done

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
