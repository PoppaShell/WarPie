#!/usr/bin/env bats
# Systemd Service File Validation Tests for WarPie
# Run with: bats tests/bash/test_systemd.bats

# Test script locations
SYSTEMD_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd)/systemd"

# =============================================================================
# Service File Existence Tests
# =============================================================================

@test "warpie-network.service exists" {
    [ -f "$SYSTEMD_DIR/warpie-network.service" ]
}

@test "warpie-control.service exists" {
    [ -f "$SYSTEMD_DIR/warpie-control.service" ]
}

@test "warpie-filter-processor.service exists" {
    [ -f "$SYSTEMD_DIR/warpie-filter-processor.service" ]
}

@test "gpsd-wardriver.service exists" {
    [ -f "$SYSTEMD_DIR/gpsd-wardriver.service" ]
}

# =============================================================================
# Required Section Tests
# =============================================================================

@test "warpie-network.service has [Unit] section" {
    grep -q "^\[Unit\]" "$SYSTEMD_DIR/warpie-network.service"
}

@test "warpie-network.service has [Service] section" {
    grep -q "^\[Service\]" "$SYSTEMD_DIR/warpie-network.service"
}

@test "warpie-network.service has [Install] section" {
    grep -q "^\[Install\]" "$SYSTEMD_DIR/warpie-network.service"
}

@test "warpie-control.service has [Unit] section" {
    grep -q "^\[Unit\]" "$SYSTEMD_DIR/warpie-control.service"
}

@test "warpie-control.service has [Service] section" {
    grep -q "^\[Service\]" "$SYSTEMD_DIR/warpie-control.service"
}

@test "warpie-control.service has [Install] section" {
    grep -q "^\[Install\]" "$SYSTEMD_DIR/warpie-control.service"
}

@test "warpie-filter-processor.service has [Unit] section" {
    grep -q "^\[Unit\]" "$SYSTEMD_DIR/warpie-filter-processor.service"
}

@test "warpie-filter-processor.service has [Service] section" {
    grep -q "^\[Service\]" "$SYSTEMD_DIR/warpie-filter-processor.service"
}

@test "warpie-filter-processor.service has [Install] section" {
    grep -q "^\[Install\]" "$SYSTEMD_DIR/warpie-filter-processor.service"
}

@test "gpsd-wardriver.service has [Unit] section" {
    grep -q "^\[Unit\]" "$SYSTEMD_DIR/gpsd-wardriver.service"
}

@test "gpsd-wardriver.service has [Service] section" {
    grep -q "^\[Service\]" "$SYSTEMD_DIR/gpsd-wardriver.service"
}

@test "gpsd-wardriver.service has [Install] section" {
    grep -q "^\[Install\]" "$SYSTEMD_DIR/gpsd-wardriver.service"
}

# =============================================================================
# Description Tests
# =============================================================================

@test "warpie-network.service has Description" {
    grep -q "^Description=" "$SYSTEMD_DIR/warpie-network.service"
}

@test "warpie-control.service has Description" {
    grep -q "^Description=" "$SYSTEMD_DIR/warpie-control.service"
}

@test "warpie-filter-processor.service has Description" {
    grep -q "^Description=" "$SYSTEMD_DIR/warpie-filter-processor.service"
}

@test "gpsd-wardriver.service has Description" {
    grep -q "^Description=" "$SYSTEMD_DIR/gpsd-wardriver.service"
}

# =============================================================================
# ExecStart Tests
# =============================================================================

@test "warpie-network.service has ExecStart" {
    grep -q "^ExecStart=" "$SYSTEMD_DIR/warpie-network.service"
}

@test "warpie-control.service has ExecStart" {
    grep -q "^ExecStart=" "$SYSTEMD_DIR/warpie-control.service"
}

@test "warpie-filter-processor.service has ExecStart" {
    grep -q "^ExecStart=" "$SYSTEMD_DIR/warpie-filter-processor.service"
}

@test "gpsd-wardriver.service has ExecStart" {
    grep -q "^ExecStart=" "$SYSTEMD_DIR/gpsd-wardriver.service"
}

# =============================================================================
# Service Type Tests
# =============================================================================

@test "warpie-network.service has Type=simple" {
    grep -q "^Type=simple" "$SYSTEMD_DIR/warpie-network.service"
}

@test "warpie-control.service has Type=simple" {
    grep -q "^Type=simple" "$SYSTEMD_DIR/warpie-control.service"
}

@test "warpie-filter-processor.service has Type=simple" {
    grep -q "^Type=simple" "$SYSTEMD_DIR/warpie-filter-processor.service"
}

@test "gpsd-wardriver.service has Type=simple" {
    grep -q "^Type=simple" "$SYSTEMD_DIR/gpsd-wardriver.service"
}

# =============================================================================
# Restart Policy Tests
# =============================================================================

@test "warpie-network.service has Restart policy" {
    grep -q "^Restart=" "$SYSTEMD_DIR/warpie-network.service"
}

@test "warpie-control.service has Restart policy" {
    grep -q "^Restart=" "$SYSTEMD_DIR/warpie-control.service"
}

@test "warpie-filter-processor.service has Restart policy" {
    grep -q "^Restart=" "$SYSTEMD_DIR/warpie-filter-processor.service"
}

@test "gpsd-wardriver.service has Restart policy" {
    grep -q "^Restart=" "$SYSTEMD_DIR/gpsd-wardriver.service"
}

# =============================================================================
# WantedBy Tests (Installation Target)
# =============================================================================

@test "warpie-network.service WantedBy multi-user.target" {
    grep -q "^WantedBy=multi-user.target" "$SYSTEMD_DIR/warpie-network.service"
}

@test "warpie-control.service WantedBy multi-user.target" {
    grep -q "^WantedBy=multi-user.target" "$SYSTEMD_DIR/warpie-control.service"
}

@test "warpie-filter-processor.service WantedBy multi-user.target" {
    grep -q "^WantedBy=multi-user.target" "$SYSTEMD_DIR/warpie-filter-processor.service"
}

@test "gpsd-wardriver.service WantedBy multi-user.target" {
    grep -q "^WantedBy=multi-user.target" "$SYSTEMD_DIR/gpsd-wardriver.service"
}

# =============================================================================
# Dependency Order Tests
# =============================================================================

@test "warpie-network.service After network-pre.target" {
    grep -q "^After=.*network" "$SYSTEMD_DIR/warpie-network.service"
}

@test "warpie-control.service After network.target" {
    grep -q "^After=network.target" "$SYSTEMD_DIR/warpie-control.service"
}

@test "warpie-filter-processor.service After network.target" {
    grep -q "^After=network.target" "$SYSTEMD_DIR/warpie-filter-processor.service"
}

@test "gpsd-wardriver.service After network.target" {
    grep -q "^After=network.target" "$SYSTEMD_DIR/gpsd-wardriver.service"
}

@test "gpsd-wardriver.service Before wardrive.service" {
    grep -q "^Before=wardrive.service" "$SYSTEMD_DIR/gpsd-wardriver.service"
}

# =============================================================================
# Security Hardening Tests
# =============================================================================

@test "warpie-filter-processor.service has NoNewPrivileges" {
    grep -q "^NoNewPrivileges=" "$SYSTEMD_DIR/warpie-filter-processor.service"
}

@test "warpie-filter-processor.service has PrivateTmp" {
    grep -q "^PrivateTmp=" "$SYSTEMD_DIR/warpie-filter-processor.service"
}

@test "warpie-filter-processor.service has ProtectSystem" {
    grep -q "^ProtectSystem=" "$SYSTEMD_DIR/warpie-filter-processor.service"
}

@test "warpie-network.service has PrivateTmp" {
    grep -q "^PrivateTmp=" "$SYSTEMD_DIR/warpie-network.service"
}

# =============================================================================
# Script Path Validation Tests
# =============================================================================

@test "warpie-network.service ExecStart uses /usr/local/bin" {
    grep -q "ExecStart=/usr/local/bin/warpie-network-manager.sh" "$SYSTEMD_DIR/warpie-network.service"
}

@test "warpie-control.service ExecStart uses /usr/local/bin" {
    grep -q "ExecStart=.*/usr/local/bin/warpie-control" "$SYSTEMD_DIR/warpie-control.service"
}

@test "warpie-filter-processor.service ExecStart uses /usr/local/bin" {
    grep -q "ExecStart=/usr/local/bin/warpie-filter-processor.py" "$SYSTEMD_DIR/warpie-filter-processor.service"
}

# =============================================================================
# No Dangerous Patterns Tests
# =============================================================================

@test "warpie-network.service has no KillMode=none" {
    run grep -q "^KillMode=none" "$SYSTEMD_DIR/warpie-network.service"
    [ "$status" -eq 1 ]
}

@test "warpie-control.service has no KillMode=none" {
    run grep -q "^KillMode=none" "$SYSTEMD_DIR/warpie-control.service"
    [ "$status" -eq 1 ]
}

@test "warpie-filter-processor.service has no KillMode=none" {
    run grep -q "^KillMode=none" "$SYSTEMD_DIR/warpie-filter-processor.service"
    [ "$status" -eq 1 ]
}

# =============================================================================
# Documentation Tests
# =============================================================================

@test "warpie-network.service has Documentation" {
    grep -q "^Documentation=" "$SYSTEMD_DIR/warpie-network.service"
}

@test "warpie-filter-processor.service has Documentation" {
    grep -q "^Documentation=" "$SYSTEMD_DIR/warpie-filter-processor.service"
}

@test "gpsd-wardriver.service has Documentation" {
    grep -q "^Documentation=" "$SYSTEMD_DIR/gpsd-wardriver.service"
}

# =============================================================================
# RestartSec Tests (Prevent restart loops)
# =============================================================================

@test "warpie-network.service has RestartSec" {
    grep -q "^RestartSec=" "$SYSTEMD_DIR/warpie-network.service"
}

@test "warpie-control.service has RestartSec" {
    grep -q "^RestartSec=" "$SYSTEMD_DIR/warpie-control.service"
}

@test "warpie-filter-processor.service has RestartSec" {
    grep -q "^RestartSec=" "$SYSTEMD_DIR/warpie-filter-processor.service"
}

@test "gpsd-wardriver.service has RestartSec" {
    grep -q "^RestartSec=" "$SYSTEMD_DIR/gpsd-wardriver.service"
}

# =============================================================================
# No Empty Values Tests
# =============================================================================

@test "warpie-network.service Description is not empty" {
    run grep "^Description=$" "$SYSTEMD_DIR/warpie-network.service"
    [ "$status" -eq 1 ]
}

@test "warpie-control.service Description is not empty" {
    run grep "^Description=$" "$SYSTEMD_DIR/warpie-control.service"
    [ "$status" -eq 1 ]
}

@test "warpie-filter-processor.service Description is not empty" {
    run grep "^Description=$" "$SYSTEMD_DIR/warpie-filter-processor.service"
    [ "$status" -eq 1 ]
}

@test "gpsd-wardriver.service Description is not empty" {
    run grep "^Description=$" "$SYSTEMD_DIR/gpsd-wardriver.service"
    [ "$status" -eq 1 ]
}

# =============================================================================
# Working Directory Tests (for services that need it)
# =============================================================================

@test "warpie-control.service has WorkingDirectory" {
    grep -q "^WorkingDirectory=" "$SYSTEMD_DIR/warpie-control.service"
}

# =============================================================================
# User/Group Tests
# =============================================================================

@test "warpie-control.service specifies User" {
    grep -q "^User=" "$SYSTEMD_DIR/warpie-control.service"
}

@test "warpie-filter-processor.service specifies User" {
    grep -q "^User=" "$SYSTEMD_DIR/warpie-filter-processor.service"
}

# =============================================================================
# Logging Tests
# =============================================================================

@test "warpie-network.service logs to journal" {
    grep -qE "^StandardOutput=(journal|append:)" "$SYSTEMD_DIR/warpie-network.service"
}

@test "warpie-filter-processor.service has log output configured" {
    grep -qE "^StandardOutput=(journal|append:)" "$SYSTEMD_DIR/warpie-filter-processor.service"
}
