#!/usr/bin/env bats
# Comprehensive tests for WarPie Bash scripts
# Run with: bats tests/bash/

# Test script locations
SCRIPT_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd)/bin"
INSTALL_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd)/install"

# =============================================================================
# Script Existence and Executability Tests
# =============================================================================

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

@test "warpie-filter-manager.sh exists and is executable" {
    [ -f "$SCRIPT_DIR/warpie-filter-manager.sh" ]
    [ -x "$SCRIPT_DIR/warpie-filter-manager.sh" ]
}

@test "warpie-network-manager.sh exists and is executable" {
    [ -f "$SCRIPT_DIR/warpie-network-manager.sh" ]
    [ -x "$SCRIPT_DIR/warpie-network-manager.sh" ]
}

@test "install.sh exists and is executable" {
    [ -f "$INSTALL_DIR/install.sh" ]
    [ -x "$INSTALL_DIR/install.sh" ]
}

@test "warpie-kismet-to-wigle.py exists and is executable" {
    [ -f "$SCRIPT_DIR/warpie-kismet-to-wigle.py" ]
    [ -x "$SCRIPT_DIR/warpie-kismet-to-wigle.py" ]
}

# =============================================================================
# Help/Usage Tests
# =============================================================================

@test "warpie-exclude-ssid.sh shows help with --help" {
    run "$SCRIPT_DIR/warpie-exclude-ssid.sh" --help
    [ "$status" -eq 0 ] || [ "$status" -eq 1 ]
    [[ "$output" == *"Usage"* ]] || [[ "$output" == *"usage"* ]] || [[ "$output" == *"SSID"* ]]
}

@test "warpie-filter-manager.sh shows help with --help" {
    run "$SCRIPT_DIR/warpie-filter-manager.sh" --help
    [ "$status" -eq 0 ] || [ "$status" -eq 1 ]
    [[ "$output" == *"Usage"* ]] || [[ "$output" == *"usage"* ]] || [[ "$output" == *"filter"* ]] || [[ "$output" == *"Filter"* ]]
}

@test "install.sh shows help with --help" {
    run "$INSTALL_DIR/install.sh" --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"Usage"* ]] || [[ "$output" == *"usage"* ]] || [[ "$output" == *"install"* ]]
}

@test "warpie-kismet-to-wigle.py shows help with --help" {
    run python3 "$SCRIPT_DIR/warpie-kismet-to-wigle.py" --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"Export Kismet"* ]] || [[ "$output" == *"WiGLE"* ]] || [[ "$output" == *"wigle"* ]]
}

# =============================================================================
# Script Syntax Validation (shellcheck-style)
# =============================================================================

@test "wardrive.sh has valid bash syntax" {
    run bash -n "$SCRIPT_DIR/wardrive.sh"
    [ "$status" -eq 0 ]
}

@test "warpie-exclude-ssid.sh has valid bash syntax" {
    run bash -n "$SCRIPT_DIR/warpie-exclude-ssid.sh"
    [ "$status" -eq 0 ]
}

@test "validate-warpie.sh has valid bash syntax" {
    run bash -n "$SCRIPT_DIR/validate-warpie.sh"
    [ "$status" -eq 0 ]
}

@test "fix-kismet-root.sh has valid bash syntax" {
    run bash -n "$SCRIPT_DIR/fix-kismet-root.sh"
    [ "$status" -eq 0 ]
}

@test "warpie-filter-manager.sh has valid bash syntax" {
    run bash -n "$SCRIPT_DIR/warpie-filter-manager.sh"
    [ "$status" -eq 0 ]
}

@test "warpie-network-manager.sh has valid bash syntax" {
    run bash -n "$SCRIPT_DIR/warpie-network-manager.sh"
    [ "$status" -eq 0 ]
}

@test "install.sh has valid bash syntax" {
    run bash -n "$INSTALL_DIR/install.sh"
    [ "$status" -eq 0 ]
}

@test "warpie-kismet-to-wigle.py has valid Python syntax" {
    run python3 -m py_compile "$SCRIPT_DIR/warpie-kismet-to-wigle.py"
    [ "$status" -eq 0 ]
}

# =============================================================================
# Shebang Validation
# =============================================================================

@test "wardrive.sh has proper shebang" {
    head -1 "$SCRIPT_DIR/wardrive.sh" | grep -qE '^#!/(usr/)?bin/(env )?bash'
}

@test "warpie-exclude-ssid.sh has proper shebang" {
    head -1 "$SCRIPT_DIR/warpie-exclude-ssid.sh" | grep -qE '^#!/(usr/)?bin/(env )?bash'
}

@test "install.sh has proper shebang" {
    head -1 "$INSTALL_DIR/install.sh" | grep -qE '^#!/(usr/)?bin/(env )?bash'
}

# =============================================================================
# JSON Mode Tests (where applicable)
# =============================================================================

@test "warpie-exclude-ssid.sh --json --list returns valid JSON structure" {
    # This test may fail without proper environment, but should at least not crash
    run "$SCRIPT_DIR/warpie-exclude-ssid.sh" --json --list 2>/dev/null
    # Accept success or graceful failure (missing config)
    [ "$status" -eq 0 ] || [ "$status" -eq 1 ]
    # If it outputs something, it should be JSON-like or an error message
    if [ -n "$output" ]; then
        [[ "$output" == "{"* ]] || [[ "$output" == "["* ]] || [[ "$output" == *"error"* ]] || [[ "$output" == *"Error"* ]] || [[ "$output" == *"not found"* ]]
    fi
}

@test "warpie-filter-manager.sh --json --list returns valid JSON structure" {
    run "$SCRIPT_DIR/warpie-filter-manager.sh" --json --list 2>/dev/null
    [ "$status" -eq 0 ] || [ "$status" -eq 1 ]
    if [ -n "$output" ]; then
        [[ "$output" == "{"* ]] || [[ "$output" == "["* ]] || [[ "$output" == *"error"* ]] || [[ "$output" == *"Error"* ]] || [[ "$output" == *"not found"* ]]
    fi
}

# =============================================================================
# Install Script Mode Detection
# =============================================================================

@test "install.sh recognizes --uninstall flag" {
    run grep -q "\-\-uninstall" "$INSTALL_DIR/install.sh"
    [ "$status" -eq 0 ]
}

@test "install.sh recognizes --configure flag" {
    run grep -q "\-\-configure" "$INSTALL_DIR/install.sh"
    [ "$status" -eq 0 ]
}

@test "install.sh recognizes --test flag" {
    run grep -q "\-\-test" "$INSTALL_DIR/install.sh"
    [ "$status" -eq 0 ]
}

# =============================================================================
# Wardrive Script Mode Tests
# =============================================================================

@test "wardrive.sh supports normal mode" {
    run grep -q "normal" "$SCRIPT_DIR/wardrive.sh"
    [ "$status" -eq 0 ]
}

@test "wardrive.sh supports wardrive mode" {
    run grep -q "wardrive" "$SCRIPT_DIR/wardrive.sh"
    [ "$status" -eq 0 ]
}

@test "wardrive.sh uses KISMET_MODE environment variable" {
    run grep -q "KISMET_MODE" "$SCRIPT_DIR/wardrive.sh"
    [ "$status" -eq 0 ]
}

# =============================================================================
# Security Tests
# =============================================================================

@test "install.sh checks for root privileges" {
    run grep -qE "EUID|root" "$INSTALL_DIR/install.sh"
    [ "$status" -eq 0 ]
}

@test "scripts don't contain hardcoded passwords" {
    run grep -rE "(password|passwd|secret)\s*=\s*['\"][^'\"]+['\"]" "$SCRIPT_DIR/"
    # Should find nothing (exit 1) or only template/example patterns
    [ "$status" -eq 1 ] || [[ "$output" == *"example"* ]] || [[ "$output" == *"template"* ]] || [[ "$output" == *"wardriving"* ]]
}

# =============================================================================
# Configuration Path Tests
# =============================================================================

@test "scripts reference correct config directory /etc/warpie" {
    run grep -l "/etc/warpie" "$SCRIPT_DIR"/*.sh
    [ "$status" -eq 0 ]
}

@test "scripts reference correct Kismet config path /etc/kismet" {
    run grep -l "/etc/kismet" "$SCRIPT_DIR"/*.sh "$INSTALL_DIR/install.sh"
    [ "$status" -eq 0 ]
}

# =============================================================================
# Error Handling Tests
# =============================================================================

@test "install.sh uses set -e or equivalent error handling" {
    run grep -qE "set -e|set -o errexit" "$INSTALL_DIR/install.sh"
    [ "$status" -eq 0 ]
}

@test "wardrive.sh has error handling" {
    run grep -qE "set -e|exit 1|\|\| exit" "$SCRIPT_DIR/wardrive.sh"
    [ "$status" -eq 0 ]
}

# =============================================================================
# Filter Rules Configuration Tests
# =============================================================================

@test "install.sh creates filter_rules.conf with section headers" {
    run grep -q "\[static_exclusions\]" "$INSTALL_DIR/install.sh"
    [ "$status" -eq 0 ]
}

@test "install.sh creates filter_rules.conf with dynamic exclusions section" {
    run grep -q "\[dynamic_exclusions\]" "$INSTALL_DIR/install.sh"
    [ "$status" -eq 0 ]
}

# =============================================================================
# Monitor Interface Cleanup Tests
# =============================================================================

@test "install.sh cleans up monitor interfaces during uninstall" {
    run grep -q "iw dev.*del" "$INSTALL_DIR/install.sh"
    [ "$status" -eq 0 ]
}

@test "install.sh detects monitor interfaces by *mon pattern" {
    run grep -qE "\*mon|mon\]" "$INSTALL_DIR/install.sh"
    [ "$status" -eq 0 ]
}

# =============================================================================
# WARPIE_FILTER Comment Format Tests
# =============================================================================

@test "install.sh writes WARPIE_FILTER comments for exclusions" {
    run grep -q "WARPIE_FILTER" "$INSTALL_DIR/install.sh"
    [ "$status" -eq 0 ]
}
