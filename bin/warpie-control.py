#!/usr/bin/env python3
"""
WarPie Control Panel - Kismet Mode Switcher with Network Filter Management
Runs on port 1337
Version: 2.4.1
"""

import glob
import http.server
import json
import os
import re
import subprocess
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PORT = 1337
FILTER_MANAGER_SCRIPT = "/usr/local/bin/warpie-filter-manager.sh"
# Fallback to old script if new one doesn't exist yet
EXCLUDE_SCRIPT = "/usr/local/bin/warpie-exclude-ssid.sh"

MODES = {
    "normal": {
        "name": "Normal Mode",
        "desc": "Full capture, home networks excluded",
        "env": "normal",
    },
    "wardrive": {
        "name": "Wardrive Mode",
        "desc": "Optimized AP-only scanning, faster channel hopping",
        "env": "wardrive",
    },
}

# Common networks for quick-add buttons
QUICK_EXCLUDE_NETWORKS = [
    {"ssid": "xfinitywifi", "desc": "Xfinity Hotspots"},
    {"ssid": "attwifi", "desc": "AT&T Hotspots"},
    {"ssid": "Starbucks WiFi", "desc": "Starbucks"},
    {"ssid": "Google Starbucks", "desc": "Google Starbucks"},
    {"ssid": "McDonalds Free WiFi", "desc": "McDonald's"},
    {"ssid": "HPGuest", "desc": "HP Guest Networks"},
]

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
        .mode-btn.stop {{ background: #ff4757; color: white; }}
        .mode-btn.active {{ box-shadow: 0 0 0 3px #00ff88; }}
        .mode-desc {{ font-size: 12px; color: rgba(255,255,255,0.7); margin-top: 5px; font-weight: normal; }}
        .links {{ text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #0f3460; }}
        .links a, .links button {{ 
            color: #00ff88; 
            text-decoration: none; 
            margin: 0 10px; 
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
        .toast.error {{ background: #ff4757; color: white; }}
        .gps-info {{ display: flex; justify-content: space-between; margin-top: 10px; padding-top: 10px; border-top: 1px solid #0f3460; }}
        .gps-item {{ text-align: center; }}
        .gps-label {{ font-size: 10px; color: #888; }}
        .gps-value {{ font-size: 14px; color: #00ff88; }}
        
        /* Flyout Base Styles */
        .flyout-overlay {{
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
        .flyout-overlay.open {{ opacity: 1; visibility: visible; }}
        .flyout {{
            position: fixed;
            top: 0;
            right: -420px;
            width: 420px;
            max-width: 95vw;
            height: 100%;
            background: #16213e;
            border-left: 2px solid #00ff88;
            transition: right 0.3s ease;
            z-index: 1002;
            display: flex;
            flex-direction: column;
        }}
        .flyout.open {{ right: 0; }}
        .flyout-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 15px 20px;
            border-bottom: 1px solid #0f3460;
            background: #1a1a2e;
        }}
        .flyout-header h2 {{ margin: 0; color: #00ff88; font-size: 18px; }}
        .flyout-close {{
            background: none;
            border: none;
            color: #888;
            font-size: 28px;
            cursor: pointer;
            line-height: 1;
        }}
        .flyout-close:hover {{ color: #ff4757; }}
        .flyout-content {{
            flex: 1;
            overflow-y: auto;
            padding: 15px;
        }}
        
        /* Log Viewer Flyout */
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
        
        /* Exclusions Flyout Specific */
        .exclusion-section {{
            margin-bottom: 20px;
        }}
        .exclusion-section h3 {{
            color: #00ff88;
            font-size: 14px;
            margin: 0 0 10px 0;
            text-transform: uppercase;
        }}
        .scan-row {{
            display: flex;
            gap: 10px;
            margin-bottom: 15px;
        }}
        .scan-input {{
            flex: 1;
            padding: 12px;
            border-radius: 8px;
            border: 1px solid #0f3460;
            background: #0d1117;
            color: #eee;
            font-size: 16px;
        }}
        .scan-input:focus {{
            outline: none;
            border-color: #00ff88;
        }}
        .scan-btn {{
            padding: 12px 20px;
            border-radius: 8px;
            border: none;
            background: #00ff88;
            color: #1a1a2e;
            font-weight: bold;
            cursor: pointer;
            font-size: 14px;
        }}
        .scan-btn:hover {{ background: #00cc6a; }}
        .scan-btn:disabled {{ background: #555; color: #888; cursor: not-allowed; }}
        
        .quick-btns {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-bottom: 15px;
        }}
        .quick-btn {{
            padding: 8px 14px;
            border-radius: 20px;
            border: 1px solid #0f3460;
            background: #0d1117;
            color: #eee;
            font-size: 12px;
            cursor: pointer;
            transition: all 0.2s;
        }}
        .quick-btn:hover {{
            background: #00ff88;
            color: #1a1a2e;
            border-color: #00ff88;
        }}
        
        .exclusion-list {{
            background: #0d1117;
            border-radius: 8px;
            overflow: hidden;
        }}
        .exclusion-item {{
            padding: 12px 15px;
            border-bottom: 1px solid #1a1a2e;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .exclusion-item:last-child {{ border-bottom: none; }}
        .exclusion-info {{
            flex: 1;
        }}
        .exclusion-ssid {{
            font-weight: bold;
            color: #eee;
            margin-bottom: 3px;
        }}
        .exclusion-meta {{
            font-size: 11px;
            color: #888;
        }}
        .exclusion-method {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 10px;
            text-transform: uppercase;
            margin-right: 8px;
        }}
        .exclusion-method.bssid {{ background: #4834d4; color: white; }}
        .exclusion-method.ssid {{ background: #6c5ce7; color: white; }}
        .exclusion-method.hybrid {{ background: #e84393; color: white; }}
        .exclusion-remove {{
            background: none;
            border: none;
            color: #ff4757;
            font-size: 20px;
            cursor: pointer;
            padding: 5px 10px;
        }}
        .exclusion-remove:hover {{ color: #ff6b7a; }}
        
        .empty-state {{
            text-align: center;
            padding: 30px;
            color: #888;
        }}
        
        /* Scan Results Modal */
        .scan-results {{
            background: #0d1117;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 15px;
            display: none;
        }}
        .scan-results.show {{ display: block; }}
        .scan-results h4 {{
            color: #00ff88;
            margin: 0 0 10px 0;
            font-size: 14px;
        }}
        .found-network {{
            padding: 8px;
            background: #1a1a2e;
            border-radius: 5px;
            margin-bottom: 8px;
            font-size: 12px;
        }}
        .found-network .bssid {{ color: #58a6ff; font-family: monospace; }}
        .found-network .signal {{ color: #7ee787; }}
        
        .method-buttons {{
            display: flex;
            flex-direction: column;
            gap: 8px;
            margin-top: 15px;
        }}
        .method-btn {{
            padding: 12px;
            border-radius: 8px;
            border: none;
            cursor: pointer;
            font-size: 14px;
            text-align: left;
        }}
        .method-btn.bssid {{ background: #4834d4; color: white; }}
        .method-btn.ssid {{ background: #6c5ce7; color: white; }}
        .method-btn.hybrid {{ background: #e84393; color: white; }}
        .method-btn:hover {{ opacity: 0.9; }}
        .method-btn .method-title {{ font-weight: bold; display: block; }}
        .method-btn .method-desc {{ font-size: 11px; opacity: 0.8; }}
        
        .loading {{
            text-align: center;
            padding: 20px;
            color: #888;
        }}
        .loading::after {{
            content: '';
            animation: dots 1.5s infinite;
        }}
        @keyframes dots {{
            0%, 20% {{ content: '.'; }}
            40% {{ content: '..'; }}
            60%, 100% {{ content: '...'; }}
        }}

        /* Filter Tabs */
        .filter-tabs {{
            display: flex;
            border-bottom: 2px solid #0f3460;
            margin-bottom: 15px;
        }}
        .filter-tab {{
            flex: 1;
            padding: 12px;
            background: none;
            border: none;
            color: #888;
            font-size: 12px;
            font-weight: bold;
            cursor: pointer;
            text-transform: uppercase;
            transition: all 0.2s;
        }}
        .filter-tab:hover {{ color: #eee; }}
        .filter-tab.active {{
            color: #00ff88;
            border-bottom: 2px solid #00ff88;
            margin-bottom: -2px;
        }}
        .filter-panel {{ display: none; }}
        .filter-panel.active {{ display: block; }}

        /* Static/Dynamic Exclusion badges */
        .exclusion-type {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 10px;
            text-transform: uppercase;
            margin-right: 5px;
        }}
        .exclusion-type.static {{ background: #00ff88; color: #1a1a2e; }}
        .exclusion-type.dynamic {{ background: #ffa502; color: #1a1a2e; }}

        /* Targeting Inclusions */
        .target-section {{
            margin-bottom: 20px;
        }}
        .target-add-row {{
            display: flex;
            gap: 8px;
            margin-bottom: 15px;
            flex-wrap: wrap;
        }}
        .target-input {{
            flex: 1;
            min-width: 120px;
            padding: 10px;
            border-radius: 8px;
            border: 1px solid #0f3460;
            background: #0d1117;
            color: #eee;
            font-size: 14px;
            font-family: monospace;
        }}
        .target-input:focus {{ outline: none; border-color: #00ff88; }}
        .target-select {{
            padding: 10px;
            border-radius: 8px;
            border: 1px solid #0f3460;
            background: #0d1117;
            color: #eee;
            font-size: 14px;
        }}
        .target-item {{
            padding: 12px 15px;
            border-bottom: 1px solid #1a1a2e;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .target-item:last-child {{ border-bottom: none; }}
        .target-oui {{
            font-family: monospace;
            color: #58a6ff;
            font-weight: bold;
        }}
        .target-mode {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 10px;
            background: #e84393;
            color: white;
            margin-left: 10px;
        }}
        .target-builtin {{
            font-size: 10px;
            color: #888;
            background: #333;
            padding: 2px 6px;
            border-radius: 4px;
            margin-left: 8px;
        }}

        /* Filter type radio buttons */
        .filter-type-row {{
            display: flex;
            gap: 15px;
            margin: 10px 0 15px 0;
        }}
        .filter-type-option {{
            display: flex;
            align-items: center;
            gap: 6px;
            cursor: pointer;
            font-size: 13px;
        }}
        .filter-type-option input {{ cursor: pointer; }}
        .filter-type-info {{
            font-size: 11px;
            color: #888;
            margin-bottom: 15px;
            padding: 10px;
            background: #0d1117;
            border-radius: 8px;
            border-left: 3px solid #ffa502;
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
            <button type="submit" name="mode" value="stop" class="mode-btn stop">Stop Kismet<div class="mode-desc">Stop all capture</div></button>
        </form>
        <div class="links">
            <a href="http://{host}:2501" target="_blank">Kismet UI</a>
            <button onclick="openLogs()">View Logs</button>
            <button onclick="openFilters()">Filters</button>
            <a href="/api/status">API</a>
        </div>
    </div>
    
    <!-- Log Viewer Flyout -->
    <div class="flyout-overlay" id="logOverlay" onclick="closeLogs()"></div>
    <div class="flyout" id="logFlyout">
        <div class="flyout-header">
            <h2>Live Logs</h2>
            <button class="flyout-close" onclick="closeLogs()">&times;</button>
        </div>
        <div class="log-controls">
            <select id="logSource" onchange="refreshLogs()">
                <option value="wigle">WiGLE CSV</option>
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
    
    <!-- Filters Flyout -->
    <div class="flyout-overlay" id="filterOverlay" onclick="closeFilters()"></div>
    <div class="flyout" id="filterFlyout">
        <div class="flyout-header">
            <h2>Network Filters</h2>
            <button class="flyout-close" onclick="closeFilters()">&times;</button>
        </div>

        <!-- Tab Navigation -->
        <div class="filter-tabs">
            <button class="filter-tab active" onclick="switchFilterTab('exclusions')">Exclusions</button>
            <button class="filter-tab" onclick="switchFilterTab('targets')">Targeting</button>
        </div>

        <div class="flyout-content">
            <!-- EXCLUSIONS TAB -->
            <div class="filter-panel active" id="panel-exclusions">
                <!-- Add Exclusion Section -->
                <div class="exclusion-section">
                    <h3>Add Exclusion</h3>
                    <div class="scan-row">
                        <input type="text" class="scan-input" id="ssidInput" placeholder="Enter SSID name..." onkeypress="if(event.key==='Enter')scanSSID()">
                        <button class="scan-btn" id="scanBtn" onclick="scanSSID()">Scan</button>
                    </div>

                    <!-- Filter Type Selection -->
                    <div class="filter-type-row">
                        <label class="filter-type-option">
                            <input type="radio" name="filterType" value="static" checked>
                            <span style="color:#00ff88">Static</span>
                        </label>
                        <label class="filter-type-option">
                            <input type="radio" name="filterType" value="dynamic">
                            <span style="color:#ffa502">Dynamic</span>
                        </label>
                    </div>
                    <div class="filter-type-info" id="filterTypeInfo">
                        <strong>Static:</strong> Block at capture time. Use for home networks, neighbors, fixed infrastructure.
                    </div>

                    <!-- Scan Results -->
                    <div class="scan-results" id="scanResults">
                        <h4>Found Networks:</h4>
                        <div id="foundNetworks"></div>
                        <div class="method-buttons" id="methodButtons">
                            <button class="method-btn bssid" onclick="addExclusion('bssid')">
                                <span class="method-title">Add with BSSIDs</span>
                                <span class="method-desc">Block specific MAC addresses found</span>
                            </button>
                            <button class="method-btn ssid" onclick="addExclusion('exact')">
                                <span class="method-title">SSID Only</span>
                                <span class="method-desc">Block any network with this name</span>
                            </button>
                        </div>
                    </div>

                    <!-- Quick Add Buttons -->
                    <h3>Quick Add (Common Networks)</h3>
                    <div class="quick-btns">
                        {quick_buttons}
                    </div>
                </div>

                <!-- Current Exclusions List -->
                <div class="exclusion-section">
                    <h3>Static Exclusions</h3>
                    <div class="exclusion-list" id="staticExclusionList">
                        <div class="loading">Loading</div>
                    </div>

                    <h3 style="margin-top:20px">Dynamic Exclusions</h3>
                    <div class="exclusion-list" id="dynamicExclusionList">
                        <div class="loading">Loading</div>
                    </div>
                </div>
            </div>

            <!-- TARGETING TAB -->
            <div class="filter-panel" id="panel-targets">
                <div class="target-section">
                    <h3>Add OUI to Targeting Mode</h3>
                    <p style="color:#888;font-size:12px;margin-bottom:15px">
                        Add OUI prefixes to targeting modes. Use this when you discover new device variants in the field.
                    </p>
                    <div class="target-add-row">
                        <input type="text" class="target-input" id="ouiInput" placeholder="00:AA:BB:*" onkeypress="if(event.key==='Enter')addTargetOUI()">
                        <select class="target-select" id="targetModeSelect">
                            <option value="custom">Custom Target</option>
                        </select>
                        <button class="scan-btn" onclick="addTargetOUI()">Add</button>
                    </div>
                    <div class="filter-type-info">
                        <strong>Format:</strong> XX:XX:XX:* (OUI prefix with wildcard)<br>
                        Example: <code style="color:#58a6ff">00:1E:C0:*</code> for vendor-specific devices
                    </div>
                </div>

                <div class="target-section">
                    <h3>Targeting Inclusions</h3>
                    <div class="exclusion-list" id="targetList">
                        <div class="loading">Loading</div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <div class="toast" id="toast">Success!</div>
    
    <script>
        let logInterval = null;
        let currentScanData = null;
        
        // Toast notifications
        function showToast(msg, isError) {{
            const toast = document.getElementById('toast');
            toast.textContent = msg;
            toast.className = 'toast' + (isError ? ' error' : '');
            toast.style.display = 'block';
            setTimeout(() => toast.style.display = 'none', 3000);
        }}
        
        // ==================== LOG VIEWER ====================
        function openLogs() {{
            document.getElementById('logOverlay').classList.add('open');
            document.getElementById('logFlyout').classList.add('open');
            refreshLogs();
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
                    const html = data.logs.map(line => {{
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
        
        // ==================== FILTERS ====================
        function openFilters() {{
            document.getElementById('filterOverlay').classList.add('open');
            document.getElementById('filterFlyout').classList.add('open');
            loadFilters();
            loadTargets();
            // Reset scan state
            document.getElementById('scanResults').classList.remove('show');
            document.getElementById('ssidInput').value = '';
            currentScanData = null;
        }}

        function closeFilters() {{
            document.getElementById('filterOverlay').classList.remove('open');
            document.getElementById('filterFlyout').classList.remove('open');
        }}

        function switchFilterTab(tabName) {{
            // Update tab buttons
            document.querySelectorAll('.filter-tab').forEach(tab => tab.classList.remove('active'));
            event.target.classList.add('active');
            // Update panels
            document.querySelectorAll('.filter-panel').forEach(panel => panel.classList.remove('active'));
            document.getElementById('panel-' + tabName).classList.add('active');
        }}

        // Update filter type info when radio changes
        document.querySelectorAll('input[name="filterType"]').forEach(radio => {{
            radio.addEventListener('change', function() {{
                const info = document.getElementById('filterTypeInfo');
                if (this.value === 'static') {{
                    info.innerHTML = '<strong>Static:</strong> Block at capture time. Use for home networks, neighbors, fixed infrastructure.';
                    info.style.borderLeftColor = '#00ff88';
                }} else {{
                    info.innerHTML = '<strong>Dynamic:</strong> Post-processing removal. Use for iPhone/Android hotspots with rotating MACs. MACs are NEVER blocked.';
                    info.style.borderLeftColor = '#ffa502';
                }}
            }});
        }});

        function loadFilters() {{
            const staticList = document.getElementById('staticExclusionList');
            const dynamicList = document.getElementById('dynamicExclusionList');
            staticList.innerHTML = '<div class="loading">Loading</div>';
            dynamicList.innerHTML = '<div class="loading">Loading</div>';

            fetch('/api/filters')
                .then(r => r.json())
                .then(data => {{
                    // Static exclusions
                    if (data.static_exclusions && data.static_exclusions.length > 0) {{
                        staticList.innerHTML = data.static_exclusions.map(e => `
                            <div class="exclusion-item">
                                <div class="exclusion-info">
                                    <div class="exclusion-ssid">${{escapeHtml(e.value)}}</div>
                                    <div class="exclusion-meta">
                                        <span class="exclusion-type static">static</span>
                                        <span class="exclusion-method ${{e.type}}">${{e.type}}</span>
                                        ${{e.description ? '- ' + escapeHtml(e.description) : ''}}
                                    </div>
                                </div>
                                <button class="exclusion-remove" onclick="removeFilter('static', '${{escapeHtml(e.value)}}')" title="Remove">&times;</button>
                            </div>
                        `).join('');
                    }} else {{
                        staticList.innerHTML = '<div class="empty-state">No static exclusions</div>';
                    }}

                    // Dynamic exclusions
                    if (data.dynamic_exclusions && data.dynamic_exclusions.length > 0) {{
                        dynamicList.innerHTML = data.dynamic_exclusions.map(e => `
                            <div class="exclusion-item">
                                <div class="exclusion-info">
                                    <div class="exclusion-ssid">${{escapeHtml(e.value)}}</div>
                                    <div class="exclusion-meta">
                                        <span class="exclusion-type dynamic">dynamic</span>
                                        <span class="exclusion-method ${{e.type}}">${{e.type}}</span>
                                        ${{e.description ? '- ' + escapeHtml(e.description) : ''}}
                                    </div>
                                </div>
                                <button class="exclusion-remove" onclick="removeFilter('dynamic', '${{escapeHtml(e.value)}}')" title="Remove">&times;</button>
                            </div>
                        `).join('');
                    }} else {{
                        dynamicList.innerHTML = '<div class="empty-state">No dynamic exclusions</div>';
                    }}
                }})
                .catch(_err => {{
                    staticList.innerHTML = '<div class="empty-state">Failed to load</div>';
                    dynamicList.innerHTML = '<div class="empty-state">Failed to load</div>';
                }});
        }}

        function loadTargets() {{
            const list = document.getElementById('targetList');
            list.innerHTML = '<div class="loading">Loading</div>';

            fetch('/api/filters/targets')
                .then(r => r.json())
                .then(data => {{
                    if (data.targets && data.targets.length > 0) {{
                        list.innerHTML = data.targets.map(t => `
                            <div class="target-item">
                                <div class="exclusion-info">
                                    <span class="target-oui">${{escapeHtml(t.oui)}}</span>
                                    <span class="target-mode">${{escapeHtml(t.mode)}}</span>
                                    ${{t.builtin ? '<span class="target-builtin">built-in</span>' : ''}}
                                    ${{t.description ? '<div class="exclusion-meta">' + escapeHtml(t.description) + '</div>' : ''}}
                                </div>
                                ${{!t.builtin ? '<button class="exclusion-remove" onclick="removeTarget(\\\'' + escapeHtml(t.oui) + '\\\', \\\'' + escapeHtml(t.mode) + '\\\')" title="Remove">&times;</button>' : ''}}
                            </div>
                        `).join('');
                    }} else {{
                        list.innerHTML = '<div class="empty-state">No targeting inclusions configured</div>';
                    }}
                }})
                .catch(_err => {{
                    list.innerHTML = '<div class="empty-state">Failed to load targeting inclusions</div>';
                }});
        }}

        function scanSSID() {{
            const ssid = document.getElementById('ssidInput').value.trim();
            if (!ssid) {{
                showToast('Please enter an SSID', true);
                return;
            }}

            const btn = document.getElementById('scanBtn');
            btn.disabled = true;
            btn.textContent = 'Scanning...';

            const results = document.getElementById('scanResults');
            const networks = document.getElementById('foundNetworks');

            fetch('/api/scan-ssid?ssid=' + encodeURIComponent(ssid))
                .then(r => r.json())
                .then(data => {{
                    btn.disabled = false;
                    btn.textContent = 'Scan';

                    currentScanData = data;
                    results.classList.add('show');

                    let html = '';
                    if (data.live && data.live.length > 0) {{
                        data.live.forEach(n => {{
                            html += `<div class="found-network">
                                <span class="bssid">${{n.bssid}}</span>
                                <span class="signal">${{n.signal}}dBm</span> Ch${{n.channel}}
                            </div>`;
                        }});
                    }}

                    if (data.historical && data.historical.length > 0) {{
                        html += '<div style="font-size:11px;color:#888;margin:10px 0 5px;">From historical logs:</div>';
                        data.historical.forEach(bssid => {{
                            if (!data.live || !data.live.find(n => n.bssid === bssid)) {{
                                html += `<div class="found-network"><span class="bssid">${{bssid}}</span> (historical)</div>`;
                            }}
                        }});
                    }}

                    if (!html) {{
                        html = '<div style="color:#888;padding:10px;">No networks found. You can still add an SSID-only exclusion.</div>';
                    }}

                    networks.innerHTML = html;
                }})
                .catch(err => {{
                    btn.disabled = false;
                    btn.textContent = 'Scan';
                    showToast('Scan failed: ' + err.message, true);
                }});
        }}

        function addExclusion(matchType) {{
            const ssid = document.getElementById('ssidInput').value.trim();
            if (!ssid) {{
                showToast('Please enter an SSID', true);
                return;
            }}

            const filterType = document.querySelector('input[name="filterType"]:checked').value;
            let bssids = '';

            if (matchType === 'bssid' && currentScanData) {{
                const allBssids = [];
                if (currentScanData.live) {{
                    currentScanData.live.forEach(n => allBssids.push(n.bssid));
                }}
                if (currentScanData.historical) {{
                    currentScanData.historical.forEach(b => {{
                        if (!allBssids.includes(b)) allBssids.push(b);
                    }});
                }}
                bssids = allBssids.join(',');
            }}

            fetch('/api/filters', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ ssid, filter_type: filterType, match_type: matchType, bssids }})
            }})
            .then(r => r.json())
            .then(data => {{
                if (data.success) {{
                    showToast(filterType.charAt(0).toUpperCase() + filterType.slice(1) + ' exclusion added for ' + ssid);
                    document.getElementById('scanResults').classList.remove('show');
                    document.getElementById('ssidInput').value = '';
                    currentScanData = null;
                    loadFilters();
                }} else {{
                    showToast('Error: ' + data.error, true);
                }}
            }})
            .catch(err => showToast('Failed: ' + err.message, true));
        }}

        function quickExclude(ssid) {{
            document.getElementById('ssidInput').value = ssid;
            scanSSID();
        }}

        function removeFilter(filterType, value) {{
            if (!confirm('Remove this ' + filterType + ' exclusion?')) return;

            fetch('/api/filters/' + filterType + '/' + encodeURIComponent(value), {{ method: 'DELETE' }})
            .then(r => r.json())
            .then(data => {{
                if (data.success) {{
                    showToast('Exclusion removed');
                    loadFilters();
                }} else {{
                    showToast('Error: ' + data.error, true);
                }}
            }})
            .catch(err => showToast('Failed: ' + err.message, true));
        }}

        function addTargetOUI() {{
            const oui = document.getElementById('ouiInput').value.trim();
            const mode = document.getElementById('targetModeSelect').value;

            if (!oui) {{
                showToast('Please enter an OUI prefix', true);
                return;
            }}

            fetch('/api/filters/targets', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ oui, mode }})
            }})
            .then(r => r.json())
            .then(data => {{
                if (data.success) {{
                    showToast('Added ' + oui + ' to ' + mode + ' targeting');
                    document.getElementById('ouiInput').value = '';
                    loadTargets();
                }} else {{
                    showToast('Error: ' + data.error, true);
                }}
            }})
            .catch(err => showToast('Failed: ' + err.message, true));
        }}

        function removeTarget(oui, mode) {{
            if (!confirm('Remove ' + oui + ' from ' + mode + ' targeting?')) return;

            fetch('/api/filters/targets/' + encodeURIComponent(oui) + '?mode=' + encodeURIComponent(mode), {{ method: 'DELETE' }})
            .then(r => r.json())
            .then(data => {{
                if (data.success) {{
                    showToast('Targeting inclusion removed');
                    loadTargets();
                }} else {{
                    showToast('Error: ' + data.error, true);
                }}
            }})
            .catch(err => showToast('Failed: ' + err.message, true));
        }}
        
        // ==================== UTILITIES ====================
        function escapeHtml(text) {{
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }}
        
        // Close flyouts on Escape key
        document.addEventListener('keydown', e => {{
            if (e.key === 'Escape') {{
                closeLogs();
                closeFilters();
            }}
        }});
        
        // Auto-refresh status every 5 seconds (but not when flyouts are open)
        setInterval(() => {{
            if (!document.getElementById('logFlyout').classList.contains('open') &&
                !document.getElementById('filterFlyout').classList.contains('open')) {{
                location.reload();
            }}
        }}, 5000);
        
        // Show toast on mode switch
        if (window.location.search.includes('switched')) {{
            showToast('Mode switched!');
            if (window.history.replaceState) {{
                window.history.replaceState(null, null, window.location.pathname);
            }}
        }}
    </script>
</body>
</html>
"""


class WarPieHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def get_kismet_status(self):
        try:
            result = subprocess.run(
                ["pgrep", "-a", "kismet"], check=False, capture_output=True, text=True
            )
            if result.returncode == 0:
                cmdline = result.stdout
                if "--override " in cmdline:
                    return True, ""
                elif "--override wardrive" in cmdline:
                    return True, "Wardrive"
                else:
                    return True, "Normal"
            return False, "Stopped"
        except:
            return False, "Unknown"

    def get_gps_status(self):
        try:
            result = subprocess.run(
                ["gpspipe", "-w", "-n", "1"], check=False, capture_output=True, text=True, timeout=2
            )
            if '"mode":3' in result.stdout:
                return "3D Fix"
            elif '"mode":2' in result.stdout:
                return "2D Fix"
            elif '"mode":1' in result.stdout:
                return "No Fix"
            return "Active"
        except:
            return "N/A"

    def get_device_count(self):
        try:
            result = subprocess.run(
                [
                    "curl",
                    "-s",
                    "-u",
                    "kismet:kismet",
                    "--max-time",
                    "2",
                    "http://localhost:2501/devices/views/all/devices.json?fields=kismet.device.base.key",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=3,
            )
            return str(len(json.loads(result.stdout)))
        except:
            return "N/A"

    def get_uptime(self):
        try:
            with open("/proc/uptime") as f:
                secs = float(f.readline().split()[0])
            return f"{int(secs // 3600)}h {int((secs % 3600) // 60)}m"
        except:
            return "N/A"

    def get_logs(self, source="wardrive", lines=100):
        try:
            if source == "wigle":
                _, current_mode = self.get_kismet_status()
                mode_dir = current_mode.lower().replace(" ", "")
                if mode_dir == "stopped":
                    mode_dir = "normal"
                today = date.today().strftime("%Y-%m-%d")
                pattern = f"/home/pi/kismet/logs/{mode_dir}/{today}/*.wiglecsv"
                files = glob.glob(pattern)
                if not files:
                    pattern = f"/home/pi/kismet/logs/*/{today}/*.wiglecsv"
                    files = glob.glob(pattern)
                if not files:
                    return [f"No WiGLE CSV found for today ({today})", "Waiting for Kismet..."]
                latest = max(files, key=os.path.getmtime)
                result = subprocess.run(
                    ["tail", "-n", str(lines), latest],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    output = [f"=== {os.path.basename(latest)} ===", ""]
                    output.extend(
                        result.stdout.strip().split("\n") if result.stdout.strip() else ["(empty)"]
                    )
                    return output
                return ["Error reading WiGLE CSV"]
            elif source == "wardrive":
                result = subprocess.run(
                    ["journalctl", "-u", "wardrive", "-n", str(lines), "--no-pager", "-o", "short"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
            elif source == "kismet":
                result = subprocess.run(
                    ["journalctl", "-u", "wardrive", "-n", str(lines), "--no-pager", "-o", "cat"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
            elif source == "gps":
                result = subprocess.run(
                    [
                        "journalctl",
                        "-u",
                        "gpsd-wardriver",
                        "-n",
                        str(lines),
                        "--no-pager",
                        "-o",
                        "short",
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
            elif source == "network":
                result = subprocess.run(
                    [
                        "journalctl",
                        "-u",
                        "warpie-network",
                        "-n",
                        str(lines),
                        "--no-pager",
                        "-o",
                        "short",
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
            else:
                return ["Unknown log source"]
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip().split("\n")
            return ["No log entries found"]
        except Exception as e:
            return [f"Error: {e!s}"]

    def switch_mode(self, mode):
        subprocess.run(["sudo", "systemctl", "stop", "wardrive"], check=False, capture_output=True)
        subprocess.run(["sudo", "pkill", "-9", "kismet"], check=False, capture_output=True)
        subprocess.run(["sleep", "2"], check=False)
        if mode == "stop":
            return True
        if mode in MODES:
            env_dir = "/etc/systemd/system/wardrive.service.d"
            os.makedirs(env_dir, exist_ok=True)
            with open(f"{env_dir}/mode.conf", "w") as f:
                f.write(f"[Service]\nEnvironment=KISMET_MODE={mode}\n")
            subprocess.run(["sudo", "systemctl", "daemon-reload"], check=False, capture_output=True)
            subprocess.run(
                ["sudo", "systemctl", "start", "wardrive"], check=False, capture_output=True
            )
            return True
        return False

    # ==================== FILTER API ====================
    def call_filter_script(self, *args):
        """Call the filter manager script with arguments and return JSON result"""
        # Use new filter manager if available, otherwise fall back to old script
        script = FILTER_MANAGER_SCRIPT if Path(FILTER_MANAGER_SCRIPT).exists() else EXCLUDE_SCRIPT
        try:
            cmd = ["sudo", script, "--json"] + list(args)
            result = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=30)
            if result.stdout.strip():
                return json.loads(result.stdout)
            return {"success": False, "error": "No output"}
        except json.JSONDecodeError:
            return {"success": False, "error": "Invalid JSON response"}
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Script timeout"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def api_list_filters(self):
        """List all filters (static, dynamic, targeting)"""
        return self.call_filter_script("--list")

    def api_list_targets(self, mode="all"):
        """List targeting inclusions"""
        args = ["--list-targets"]
        if mode != "all":
            args.extend(["--mode", mode])
        return self.call_filter_script(*args)

    def api_scan_ssid(self, ssid):
        """Scan for SSID and discover BSSIDs"""
        return self.call_filter_script("--discover", ssid)

    def api_add_static(self, ssid, match_type="exact", bssids="", desc=""):
        """Add static exclusion"""
        args = ["--add-static", "--ssid", ssid, "--type", match_type]
        if desc:
            args.extend(["--desc", desc])
        result = self.call_filter_script(*args)
        # If BSSIDs provided, also add them
        if bssids and result.get("success"):
            for bssid_item in bssids.split(","):
                bssid_clean = bssid_item.strip()
                if bssid_clean:
                    self.call_filter_script("--add-static", "--bssid", bssid_clean)
        return result

    def api_add_dynamic(self, ssid, match_type="exact", desc=""):
        """Add dynamic exclusion"""
        args = ["--add-dynamic", "--ssid", ssid, "--type", match_type]
        if desc:
            args.extend(["--desc", desc])
        return self.call_filter_script(*args)

    def api_add_target(self, oui, mode, desc=""):
        """Add targeting inclusion (OUI prefix)"""
        args = ["--add-target", "--oui", oui, "--mode", mode]
        if desc:
            args.extend(["--desc", desc])
        return self.call_filter_script(*args)

    def api_remove_target(self, oui, mode):
        """Remove targeting inclusion"""
        return self.call_filter_script("--remove-target", "--oui", oui, "--mode", mode)

    # Legacy API compatibility
    def api_list_exclusions(self):
        return self.call_filter_script("--list")

    def api_add_exclusion(self, ssid, method, bssids=""):
        args = ["--add", "--ssid", ssid, "--method", method]
        if bssids:
            args.extend(["--bssids", bssids])
        return self.call_filter_script(*args)

    def api_remove_exclusion(self, exclusion_id):
        return self.call_filter_script("--remove", str(exclusion_id))

    # ==================== REQUEST HANDLERS ====================
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        # API: Status
        if path == "/api/status":
            self.send_json_response(self.get_status_json())
            return

        # API: Logs
        if path == "/api/logs":
            source = params.get("source", ["wardrive"])[0]
            logs = self.get_logs(source)
            self.send_json_response({"logs": logs, "lines": len(logs), "source": source})
            return

        # API: List all filters (new format)
        if path == "/api/filters":
            self.send_json_response(self.api_list_filters())
            return

        # API: List targeting inclusions
        if path == "/api/filters/targets":
            mode = params.get("mode", ["all"])[0]
            self.send_json_response(self.api_list_targets(mode))
            return

        # API: List exclusions (legacy)
        if path == "/api/exclusions":
            self.send_json_response(self.api_list_exclusions())
            return

        # API: Scan SSID
        if path == "/api/scan-ssid":
            ssid = params.get("ssid", [""])[0]
            if not ssid:
                self.send_json_response({"success": False, "error": "SSID required"})
                return
            self.send_json_response(self.api_scan_ssid(ssid))
            return

        # Main page
        self.send_html_response()

    def _handle_post_filter(self, body):
        """Handle POST /api/filters - add static or dynamic exclusion."""
        data = json.loads(body)
        ssid = data.get("ssid", "")
        filter_type = data.get("filter_type", "static")
        match_type = data.get("match_type", "exact")
        bssids = data.get("bssids", "")
        desc = data.get("description", "")

        if not ssid:
            return {"success": False, "error": "SSID required"}

        if filter_type == "dynamic":
            return self.api_add_dynamic(ssid, match_type, desc)
        return self.api_add_static(ssid, match_type, bssids, desc)

    def _handle_post_target(self, body):
        """Handle POST /api/filters/targets - add targeting inclusion."""
        data = json.loads(body)
        oui = data.get("oui", "")
        mode = data.get("mode", "")
        desc = data.get("description", "")

        if not oui:
            return {"success": False, "error": "OUI required"}

        return self.api_add_target(oui, mode, desc)

    def _handle_post_exclusion_legacy(self, body):
        """Handle POST /api/exclusions - legacy exclusion endpoint."""
        data = json.loads(body)
        ssid = data.get("ssid", "")
        method = data.get("method", "")
        bssids = data.get("bssids", "")

        if not ssid or not method:
            return {"success": False, "error": "SSID and method required"}

        return self.api_add_exclusion(ssid, method, bssids)

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode()

        # API: Add filter (static or dynamic exclusion)
        if self.path == "/api/filters":
            try:
                self.send_json_response(self._handle_post_filter(body))
            except Exception as e:
                self.send_json_response({"success": False, "error": str(e)})
            return

        # API: Add targeting inclusion (OUI prefix)
        if self.path == "/api/filters/targets":
            try:
                self.send_json_response(self._handle_post_target(body))
            except Exception as e:
                self.send_json_response({"success": False, "error": str(e)})
            return

        # API: Add exclusion (legacy endpoint)
        if self.path == "/api/exclusions":
            try:
                self.send_json_response(self._handle_post_exclusion_legacy(body))
            except Exception as e:
                self.send_json_response({"success": False, "error": str(e)})
            return

        # Mode switch (form POST)
        params = parse_qs(body)
        mode = params.get("mode", [""])[0]
        if mode:
            self.switch_mode(mode)
        self.send_response(303)
        self.send_header("Location", "/?switched=1")
        self.end_headers()

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        # API: Remove filter (static or dynamic exclusion)
        # DELETE /api/filters/{type}/{value}
        match = re.match(r"/api/filters/(static|dynamic)/(.+)", path)
        if match:
            filter_type = match.group(1)
            value = match.group(2)
            result = self.call_filter_script(f"--remove-{filter_type}", "--ssid", value)
            self.send_json_response(result)
            return

        # API: Remove targeting inclusion
        # DELETE /api/filters/targets/{oui}?mode=
        match = re.match(r"/api/filters/targets/(.+)", path)
        if match:
            oui = match.group(1)
            mode = params.get("mode", [""])[0]
            result = self.api_remove_target(oui, mode)
            self.send_json_response(result)
            return

        # API: Remove exclusion (legacy endpoint)
        match = re.match(r"/api/exclusions/(\d+)", path)
        if match:
            exclusion_id = match.group(1)
            result = self.api_remove_exclusion(exclusion_id)
            self.send_json_response(result)
            return

        self.send_response(404)
        self.end_headers()

    # ==================== RESPONSE HELPERS ====================
    def send_json_response(self, data):
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def get_status_json(self):
        running, mode = self.get_kismet_status()
        return {
            "running": running,
            "mode": mode,
            "gps": self.get_gps_status(),
            "devices": self.get_device_count(),
            "uptime": self.get_uptime(),
        }

    def send_html_response(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()

        running, current_mode = self.get_kismet_status()
        host = self.headers.get("Host", "localhost").split(":")[0]

        # Generate quick buttons
        quick_buttons = "".join(
            [
                f'<button class="quick-btn" onclick="quickExclude(\'{n["ssid"]}\')">{n["ssid"]}</button>'
                for n in QUICK_EXCLUDE_NETWORKS
            ]
        )

        html = HTML_TEMPLATE.format(
            status="Running" if running else "Stopped",
            status_class="status-running" if running else "status-stopped",
            current_mode=current_mode,
            gps_status=self.get_gps_status(),
            device_count=self.get_device_count() if running else "0",
            uptime=self.get_uptime(),
            host=host,
            active_normal="active" if current_mode == "Normal" else "",
            active_wardrive="active" if current_mode == "Wardrive" else "",
            active_="active" if current_mode == "" else "",
            quick_buttons=quick_buttons,
        )
        self.wfile.write(html.encode())


def main():
    server = http.server.HTTPServer(("0.0.0.0", PORT), WarPieHandler)
    print(f"WarPie Control Panel v2.4.1 running on port {PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
