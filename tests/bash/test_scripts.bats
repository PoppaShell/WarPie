#!/usr/bin/env bats
# Basic tests for WarPie Bash scripts
# Run with: bats tests/bash/

# Test script locations
SCRIPT_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd)/bin"

@test "wardrive.sh exists and is executable" {
    [ -f "$SCRIPT_DIR/wardrive.sh" ]
    [ -x "$SCRIPT_DIR/wardrive.sh" ]
}

@test "warpie-exclude-ssid.sh exists and is executable" {
    [ -f "$SCRIPT_DIR/warpie-exclude-ssid.sh" ]
    [ -x "$SCRIPT_DIR/warpie-exclude-ssid.sh" ]
}

@test "validate-warpie.sh exists and is executable" {
    [ -f "$SCRIPT_DIR/validate-warpie.sh" ]
    [ -x "$SCRIPT_DIR/validate-warpie.sh" ]
}

@test "fix-kismet-root.sh exists and is executable" {
    [ -f "$SCRIPT_DIR/fix-kismet-root.sh" ]
    [ -x "$SCRIPT_DIR/fix-kismet-root.sh" ]
}

@test "warpie-exclude-ssid.sh shows help with --help" {
    # Skip if script requires root
    run "$SCRIPT_DIR/warpie-exclude-ssid.sh" --help
    # Should exit 0 and show usage info
    [ "$status" -eq 0 ] || [ "$status" -eq 1 ]
    [[ "$output" == *"Usage"* ]] || [[ "$output" == *"usage"* ]] || [[ "$output" == *"SSID"* ]]
}

# TODO: Add more tests in Phase 4:
# - Test warpie-exclude-ssid.sh --json --list
# - Test wardrive.sh mode detection
# - Test install.sh --help
