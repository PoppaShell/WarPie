#!/bin/bash
# =============================================================================
# WarPie Security Fix - Run Kismet as Non-Root User
# =============================================================================
# This script fixes the "Kismet is running as root" warning by:
#   1. Adding the user to the kismet group
#   2. Updating the wardrive service to run as the user
#   3. Fixing directory permissions
# =============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

if [[ $EUID -ne 0 ]]; then
    log_error "This script must be run as root (use sudo)"
    exit 1
fi

# Detect the user who ran sudo
WARPIE_USER="${SUDO_USER:-pi}"

echo "============================================================================="
echo "WarPie Security Fix - Non-Root Kismet Configuration"
echo "============================================================================="
echo ""
log_info "Configuring Kismet to run as user: ${WARPIE_USER}"
echo ""

# Step 1: Check/create kismet group
log_info "Step 1: Checking kismet group..."
if getent group kismet > /dev/null 2>&1; then
    log_success "kismet group exists"
else
    log_warn "kismet group not found - creating it"
    groupadd -r kismet
    log_success "kismet group created"
fi

# Step 2: Add user to kismet group
log_info "Step 2: Adding ${WARPIE_USER} to kismet group..."
if id -nG "${WARPIE_USER}" | grep -qw "kismet"; then
    log_success "User ${WARPIE_USER} already in kismet group"
else
    usermod -aG kismet "${WARPIE_USER}"
    log_success "User ${WARPIE_USER} added to kismet group"
fi

# Step 3: Update wardrive.service to run as user
log_info "Step 3: Updating wardrive.service..."
if [[ -f /etc/systemd/system/wardrive.service ]]; then
    # Check if already configured
    if grep -q "^User=" /etc/systemd/system/wardrive.service; then
        log_info "wardrive.service already has User= directive"
        # Update the user if different
        sed -i "s/^User=.*/User=${WARPIE_USER}/" /etc/systemd/system/wardrive.service
        sed -i "s/^Group=.*/Group=kismet/" /etc/systemd/system/wardrive.service
    else
        # Add User= and Group= after [Service]
        sed -i '/^\[Service\]/a User='"${WARPIE_USER}"'\nGroup=kismet' /etc/systemd/system/wardrive.service
    fi
    log_success "wardrive.service updated to run as ${WARPIE_USER}"
else
    log_warn "wardrive.service not found - skipping"
fi

# Step 4: Fix directory permissions
log_info "Step 4: Fixing directory permissions..."

# Log directory
if [[ -d /var/log/warpie ]]; then
    chown -R "${WARPIE_USER}:kismet" /var/log/warpie
    chmod 775 /var/log/warpie
    log_success "/var/log/warpie permissions fixed"
fi

# Kismet data directory
if [[ -d "/home/${WARPIE_USER}/kismet" ]]; then
    chown -R "${WARPIE_USER}:kismet" "/home/${WARPIE_USER}/kismet"
    chmod 775 "/home/${WARPIE_USER}/kismet"
    log_success "/home/${WARPIE_USER}/kismet permissions fixed"
fi

# Step 5: Check Kismet capture binary
log_info "Step 5: Checking Kismet capture binary..."
KISMET_CAP=""
if [[ -f /usr/bin/kismet_cap_linux_wifi ]]; then
    KISMET_CAP="/usr/bin/kismet_cap_linux_wifi"
elif [[ -f /usr/local/bin/kismet_cap_linux_wifi ]]; then
    KISMET_CAP="/usr/local/bin/kismet_cap_linux_wifi"
fi

if [[ -n "$KISMET_CAP" ]]; then
    if [[ -u "$KISMET_CAP" ]]; then
        log_success "Kismet capture binary is suid-root (good!)"
    else
        log_warn "Kismet capture binary is NOT suid-root"
        echo ""
        echo "  The capture binary needs suid-root to control WiFi interfaces."
        echo "  If you compiled Kismet from source, run:"
        echo "    cd /path/to/kismet-source && sudo make suidinstall"
        echo ""
        echo "  Or manually fix with:"
        echo "    sudo chown root:kismet ${KISMET_CAP}"
        echo "    sudo chmod 4750 ${KISMET_CAP}"
        echo ""
    fi
else
    log_warn "Kismet capture binary not found"
fi

# Step 6: Reload systemd and restart services
log_info "Step 6: Reloading systemd..."
systemctl daemon-reload
log_success "systemd reloaded"

# Restart wardrive if running
if systemctl is-active --quiet wardrive; then
    log_info "Restarting wardrive service..."
    systemctl restart wardrive
    sleep 3
    if systemctl is-active --quiet wardrive; then
        log_success "wardrive service restarted successfully"
    else
        log_warn "wardrive service failed to restart - check: journalctl -u wardrive -n 20"
    fi
fi

echo ""
echo "============================================================================="
echo -e "${GREEN}Security Fix Complete!${NC}"
echo "============================================================================="
echo ""
echo "Changes made:"
echo "  - User '${WARPIE_USER}' is in the 'kismet' group"
echo "  - wardrive.service now runs as '${WARPIE_USER}'"
echo "  - Directory permissions updated"
echo ""
echo -e "${YELLOW}IMPORTANT: You must log out and back in (or reboot) for${NC}"
echo -e "${YELLOW}group membership changes to take effect for interactive use.${NC}"
echo ""
echo "The wardrive service should already be running as non-root."
echo "Verify with: ps aux | grep kismet"
echo ""
echo "The ROOTUSER warning should no longer appear in Kismet logs."
echo "============================================================================="
