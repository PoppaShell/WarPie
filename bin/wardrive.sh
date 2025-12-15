#!/bin/bash
# WarPie Wardrive Launcher
# Organizes logs by mode and date

LOG_FILE="/var/log/warpie/wardrive.log"
KISMET_BASE="/home/pi/kismet"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [INFO] $1" | tee -a "$LOG_FILE"; }

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
GPS_STATUS=$(gpspipe -w -n 1 2>/dev/null | grep -o '"mode":[0-9]' | head -1)
if [[ "$GPS_STATUS" == *"3"* ]]; then
    log "GPS status: 3D Fix"
elif [[ "$GPS_STATUS" == *"2"* ]]; then
    log "GPS status: 2D Fix"
else
    log "GPS status: No fix (searching for satellites)"
fi

# Try to sync time from GPS
log "Attempting GPS time synchronization..."
GPS_TIME=$(gpspipe -w -n 5 2>/dev/null | grep -o '"time":"[^"]*"' | head -1 | cut -d'"' -f4)
if [[ -n "$GPS_TIME" ]]; then
    log "GPS time received: $GPS_TIME"
    date -s "$GPS_TIME" 2>/dev/null && log "System time synchronized from GPS" || log "Could not set system time"
fi

log "Starting Kismet in $MODE mode..."

case "$MODE" in
    wardrive)
        exec kismet --no-ncurses --override wardrive \
            -c wlan1:name=AWUS036AXML_5GHz \
            -c wlan2:name=RT3070_24GHz
        ;;
    *)
        exec kismet --no-ncurses \
            -c wlan1:name=AWUS036AXML_5GHz \
            -c wlan2:name=RT3070_24GHz
        ;;
esac
