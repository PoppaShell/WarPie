/* WarPie Control Panel - Minimal UI Functions
 *
 * HTMX handles all server communication.
 * This file only handles local UI state (flyouts, toasts).
 */

// === Unsaved Changes State ===

let hasUnsavedChanges = false;

function markUnsavedChanges() {
    hasUnsavedChanges = true;
    updateUnsavedUI();
}

function clearUnsavedChanges() {
    hasUnsavedChanges = false;
    updateUnsavedUI();
}

function updateUnsavedUI() {
    const banner = document.getElementById('unsaved-changes-banner');
    if (hasUnsavedChanges) {
        if (banner) banner.classList.remove('hidden');
    } else {
        if (banner) banner.classList.add('hidden');
    }
}

function applyChanges() {
    // Changes are already saved to config - just clear state and show confirmation
    showToast('Changes saved');
    clearUnsavedChanges();
}

function discardChanges() {
    // Reload filter lists from server to discard local view
    clearUnsavedChanges();
    htmx.ajax('GET', '/api/filters/static?limit=5', '#static-exclusion-list');
    htmx.ajax('GET', '/api/filters/dynamic?limit=5', '#dynamic-exclusion-list');
    showToast('Changes discarded');
}

// Warn on page unload if unsaved changes
window.addEventListener('beforeunload', function(e) {
    if (hasUnsavedChanges) {
        e.preventDefault();
        e.returnValue = 'You have unsaved filter changes. Are you sure you want to leave?';
        return e.returnValue;
    }
});

// === Font Size Controls ===

const FONT_SCALE_MIN = 0.8;
const FONT_SCALE_MAX = 1.4;
const FONT_SCALE_STEP = 0.1;

function getFontScale() {
    const saved = localStorage.getItem('warpie-font-scale');
    return saved ? parseFloat(saved) : 1;
}

function setFontScale(scale) {
    scale = Math.max(FONT_SCALE_MIN, Math.min(FONT_SCALE_MAX, scale));
    document.documentElement.style.setProperty('--font-scale', scale);
    localStorage.setItem('warpie-font-scale', scale);
}

function increaseFontSize() {
    setFontScale(getFontScale() + FONT_SCALE_STEP);
}

function decreaseFontSize() {
    setFontScale(getFontScale() - FONT_SCALE_STEP);
}

// Apply saved font scale on load
document.addEventListener('DOMContentLoaded', () => {
    setFontScale(getFontScale());
});

// === Flyout Management ===

function openLogs() {
    document.getElementById('flyout-overlay').classList.add('open');
    document.getElementById('log-flyout').classList.add('open');
}

function closeLogs() {
    document.getElementById('flyout-overlay').classList.remove('open');
    document.getElementById('log-flyout').classList.remove('open');
}

function openFilters() {
    document.getElementById('flyout-overlay').classList.add('open');
    document.getElementById('filters-flyout').classList.add('open');
}

function closeFilters() {
    document.getElementById('flyout-overlay').classList.remove('open');
    document.getElementById('filters-flyout').classList.remove('open');
}

function closeAllFlyouts() {
    document.getElementById('flyout-overlay').classList.remove('open');
    document.querySelectorAll('.flyout').forEach(f => f.classList.remove('open'));
}

// Target List Editor
function openTargetEditor(listId, listName) {
    document.getElementById('target-editor-flyout').classList.add('open');
    document.getElementById('target-editor-title').textContent = 'Edit: ' + listName;
    document.getElementById('target-editor-flyout').dataset.listId = listId;
    // Trigger HTMX to load OUI list
    htmx.ajax('GET', '/api/targets/lists/' + listId, '#oui-list');
}

function closeTargetEditor() {
    document.getElementById('target-editor-flyout').classList.remove('open');
    // Refresh target lists to update OUI counts
    htmx.ajax('GET', '/api/targets/lists?view=manage', '#target-lists');
}

// Static Exclusions Manager
function openStaticManager() {
    document.getElementById('static-manager-flyout').classList.add('open');
    htmx.ajax('GET', '/api/filters/static', '#static-manager-list');
}

function closeStaticManager() {
    document.getElementById('static-manager-flyout').classList.remove('open');
}

// Dynamic Exclusions Manager
function openDynamicManager() {
    document.getElementById('dynamic-manager-flyout').classList.add('open');
    htmx.ajax('GET', '/api/filters/dynamic', '#dynamic-manager-list');
}

function closeDynamicManager() {
    document.getElementById('dynamic-manager-flyout').classList.remove('open');
}

// === Target Mode ===

function showTargetPicker() {
    document.getElementById('target-picker').classList.remove('hidden');
    // Refresh target lists
    htmx.ajax('GET', '/api/targets/lists', '#target-list-checkboxes');
}

function hideTargetPicker() {
    document.getElementById('target-picker').classList.add('hidden');
}

function collectSelectedLists(btn) {
    const checkboxes = document.querySelectorAll('#target-list-checkboxes input:checked');
    const lists = Array.from(checkboxes).map(cb => cb.value);
    // Update the hx-vals with selected lists
    btn.setAttribute('hx-vals', JSON.stringify({mode: 'targeted', target_lists: lists}));
}

// === Log Viewer ===

function isLogFlyoutOpen() {
    return document.getElementById('log-flyout').classList.contains('open');
}

function refreshLogs() {
    const source = document.getElementById('log-source').value;
    htmx.ajax('GET', '/api/logs/html?source=' + source, '#log-content');
    document.getElementById('log-status').textContent = 'Last updated: ' + new Date().toLocaleTimeString();
}

// === Filter UI ===

// PHY type state
let currentStaticPhy = 'wifi';
let currentDynamicPhy = 'wifi';
let currentWifiInputMode = 'scan';  // 'scan' or 'direct'

function setStaticPhy(phy) {
    currentStaticPhy = phy;
    // Update button states
    document.querySelectorAll('#static-phy-selector .phy-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.phy === phy);
    });

    const wifiModeToggle = document.getElementById('wifi-input-mode');
    const scanForm = document.getElementById('static-scan-form');
    const directMacForm = document.getElementById('static-direct-mac-form');

    if (phy === 'wifi') {
        // Show WiFi input mode toggle
        wifiModeToggle.classList.remove('hidden');
        // Apply current WiFi input mode
        if (currentWifiInputMode === 'scan') {
            scanForm.classList.remove('hidden');
            directMacForm.classList.add('hidden');
        } else {
            scanForm.classList.add('hidden');
            directMacForm.classList.remove('hidden');
        }
    } else {
        // BTLE/BT: hide mode toggle, show direct MAC form only
        wifiModeToggle.classList.add('hidden');
        scanForm.classList.add('hidden');
        directMacForm.classList.remove('hidden');
    }

    // Refresh list with PHY filter (use fetch to avoid loading indicator flash)
    fetch('/api/filters/static?limit=5&phy=' + phy, {
        headers: {'HX-Request': 'true'}
    })
    .then(response => response.text())
    .then(html => {
        document.getElementById('static-exclusion-list').innerHTML = html;
    });
}

function setWifiInputMode(mode) {
    currentWifiInputMode = mode;
    // Update toggle button states
    document.querySelectorAll('#wifi-input-mode .toggle-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.mode === mode);
    });

    const scanForm = document.getElementById('static-scan-form');
    const directMacForm = document.getElementById('static-direct-mac-form');

    if (mode === 'scan') {
        scanForm.classList.remove('hidden');
        directMacForm.classList.add('hidden');
    } else {
        scanForm.classList.add('hidden');
        directMacForm.classList.remove('hidden');
    }
}

function setDynamicPhy(phy) {
    currentDynamicPhy = phy;
    // Update button states
    document.querySelectorAll('#dynamic-phy-selector .phy-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.phy === phy);
    });
    // Update placeholder based on PHY type
    const input = document.getElementById('dynamic-ssid-input');
    if (phy === 'wifi') {
        input.placeholder = 'SSID or pattern (* = wildcard)';
    } else if (phy === 'btle') {
        input.placeholder = 'Device name or pattern (* = wildcard)';
    } else {
        input.placeholder = 'Bluetooth name or pattern (* = wildcard)';
    }
    // Refresh list with PHY filter (use fetch to avoid loading indicator flash)
    fetch('/api/filters/dynamic?limit=5&phy=' + phy, {
        headers: {'HX-Request': 'true'}
    })
    .then(response => response.text())
    .then(html => {
        document.getElementById('dynamic-exclusion-list').innerHTML = html;
    });
}

function addDirectMAC() {
    const mac = document.getElementById('static-mac-input').value.trim();
    const desc = document.getElementById('static-desc-input').value.trim();

    if (!mac) {
        showToast('Please enter a MAC address', true);
        return;
    }

    // Basic MAC format validation
    const macRegex = /^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$/;
    if (!macRegex.test(mac)) {
        showToast('Invalid MAC format. Use AA:BB:CC:11:22:33', true);
        return;
    }

    fetch('/api/filters/static', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            ssid: mac,
            match_type: 'bssid',
            description: desc,
            phy: currentStaticPhy
        })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showToast('Added ' + mac + (desc ? ' (' + desc + ')' : ''));
            markUnsavedChanges();
            document.getElementById('static-mac-input').value = '';
            document.getElementById('static-desc-input').value = '';
            htmx.ajax('GET', '/api/filters/static?limit=5&phy=' + currentStaticPhy, '#static-exclusion-list');
        } else {
            showToast(data.error || 'Failed to add', true);
        }
    });
}

// --- Static Exclusions (scan-based, BSSID blocking) ---

function scanForStatic() {
    const ssid = document.getElementById('static-ssid-input').value.trim();
    if (!ssid) {
        showToast('Please enter an SSID', true);
        return;
    }
    // Show scanning state
    document.getElementById('static-found-networks').innerHTML = '<div class="loading"><span class="spinner"></span> Scanning...</div>';
    document.getElementById('static-scan-results').classList.remove('hidden');

    // Use fetch instead of htmx.ajax to avoid global indicator triggering
    fetch('/api/scan-ssid?ssid=' + encodeURIComponent(ssid), {
        headers: {'HX-Request': 'true'}
    })
    .then(response => response.text())
    .then(html => {
        document.getElementById('static-found-networks').innerHTML = html;
    })
    .catch(err => {
        document.getElementById('static-found-networks').innerHTML = '<div class="error-message">Scan failed: ' + err.message + '</div>';
    });
}

function addSingleBSSID(bssid, ssid) {
    fetch('/api/filters/static', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            ssid: bssid,
            match_type: 'bssid',
            description: 'SSID: ' + ssid,
            phy: currentStaticPhy
        })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showToast('Added ' + bssid);
            markUnsavedChanges();
            htmx.ajax('GET', '/api/filters/static?limit=5&phy=' + currentStaticPhy, '#static-exclusion-list');
        } else {
            showToast(data.error || 'Failed to add', true);
        }
    });
}

function addAllBSSIDs() {
    const ssid = document.getElementById('static-ssid-input').value.trim();
    const bssidElements = document.querySelectorAll('#static-found-networks .network-bssid');
    const bssids = Array.from(bssidElements).map(el => el.textContent.trim());

    if (bssids.length === 0) {
        showToast('No BSSIDs to add', true);
        return;
    }

    fetch('/api/filters/static', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            ssid: ssid,
            match_type: 'bssid',
            bssids: bssids.join(','),
            description: 'SSID: ' + ssid,
            phy: currentStaticPhy
        })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showToast('Added ' + bssids.length + ' BSSIDs');
            markUnsavedChanges();
            document.getElementById('static-ssid-input').value = '';
            document.getElementById('static-scan-results').classList.add('hidden');
            htmx.ajax('GET', '/api/filters/static?limit=5&phy=' + currentStaticPhy, '#static-exclusion-list');
        } else {
            showToast(data.error || 'Failed to add', true);
        }
    });
}

// --- Dynamic Exclusions (SSID-only, post-processing) ---

function addDynamicExclusion() {
    const ssid = document.getElementById('dynamic-ssid-input').value.trim();
    const desc = document.getElementById('dynamic-desc-input').value.trim();
    if (!ssid) {
        showToast('Please enter an SSID', true);
        return;
    }

    // Determine if pattern (contains wildcards) or exact
    const matchType = (ssid.includes('*') || ssid.includes('?')) ? 'pattern' : 'exact';

    fetch('/api/filters/dynamic', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            ssid: ssid,
            match_type: matchType,
            description: desc,
            phy: currentDynamicPhy
        })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showToast('Dynamic exclusion added');
            markUnsavedChanges();
            document.getElementById('dynamic-ssid-input').value = '';
            document.getElementById('dynamic-desc-input').value = '';
            htmx.ajax('GET', '/api/filters/dynamic?limit=5&phy=' + currentDynamicPhy, '#dynamic-exclusion-list');
        } else {
            showToast(data.error || 'Failed to add', true);
        }
    });
}

// --- Remove Filters ---

function removeFilter(type, value, phy) {
    if (!confirm('Remove this exclusion?')) return;

    const phyParam = phy ? '?phy=' + phy : '';
    fetch('/api/filters/' + type + '/' + encodeURIComponent(value) + phyParam, {method: 'DELETE'})
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                showToast('Removed');
                markUnsavedChanges();
                // Refresh the appropriate list
                const currentPhy = type === 'static' ? currentStaticPhy : currentDynamicPhy;
                if (type === 'static') {
                    htmx.ajax('GET', '/api/filters/static?limit=5&phy=' + currentPhy, '#static-exclusion-list');
                } else {
                    htmx.ajax('GET', '/api/filters/dynamic?limit=5&phy=' + currentPhy, '#dynamic-exclusion-list');
                }
            } else {
                showToast(data.error || 'Failed', true);
            }
        });
}

// === Target Lists ===

function openCreateTargetList() {
    const name = prompt('Enter name for new Target List:');
    if (!name) return;

    fetch('/api/targets/lists', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: name})
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showToast('Created: ' + name);
            htmx.ajax('GET', '/api/targets/lists?view=manage', '#target-lists');
        } else {
            showToast(data.error || 'Failed', true);
        }
    });
}

function editTargetList(listId, listName) {
    openTargetEditor(listId, listName);
}

function deleteTargetList(listId) {
    if (!confirm('Delete this Target List?')) return;

    fetch('/api/targets/lists/' + listId, {method: 'DELETE'})
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                showToast('Deleted');
                htmx.ajax('GET', '/api/targets/lists?view=manage', '#target-lists');
            } else {
                showToast(data.error || 'Failed', true);
            }
        });
}

function addOUIToList() {
    const listId = document.getElementById('target-editor-flyout').dataset.listId;
    const oui = document.getElementById('oui-input').value.trim();
    const desc = document.getElementById('oui-desc-input').value.trim();

    if (!oui) {
        showToast('Enter an OUI prefix', true);
        return;
    }

    fetch('/api/targets/lists/' + listId + '/ouis', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({oui: oui, description: desc})
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showToast('Added ' + oui);
            document.getElementById('oui-input').value = '';
            document.getElementById('oui-desc-input').value = '';
            htmx.ajax('GET', '/api/targets/lists/' + listId, '#oui-list');
        } else {
            showToast(data.error || 'Failed', true);
        }
    });
}

function removeOUI(listId, oui) {
    if (!confirm('Remove ' + oui + '?')) return;

    fetch('/api/targets/lists/' + listId + '/ouis/' + encodeURIComponent(oui), {method: 'DELETE'})
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                showToast('Removed');
                htmx.ajax('GET', '/api/targets/lists/' + listId, '#oui-list');
            } else {
                showToast(data.error || 'Failed', true);
            }
        });
}

function removeOUIFromList(oui) {
    const listId = document.getElementById('target-editor-flyout').dataset.listId;
    removeOUI(listId, oui);
}

// === Toast Notifications ===

function showToast(message, isError) {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = 'toast ' + (isError ? 'error' : 'success');
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// === Keyboard Shortcuts ===

document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
        closeAllFlyouts();
    }
});

// === Enter Key Submission ===

document.addEventListener('DOMContentLoaded', () => {
    // Static SSID input - Enter triggers scan
    const staticInput = document.getElementById('static-ssid-input');
    if (staticInput) {
        staticInput.addEventListener('keydown', e => {
            if (e.key === 'Enter') {
                e.preventDefault();
                scanForStatic();
            }
        });
    }

    // Dynamic SSID input - Enter triggers add
    const dynamicInput = document.getElementById('dynamic-ssid-input');
    if (dynamicInput) {
        dynamicInput.addEventListener('keydown', e => {
            if (e.key === 'Enter') {
                e.preventDefault();
                addDynamicExclusion();
            }
        });
    }

    // OUI input in target editor - Enter triggers add
    const ouiInput = document.getElementById('oui-input');
    if (ouiInput) {
        ouiInput.addEventListener('keydown', e => {
            if (e.key === 'Enter') {
                e.preventDefault();
                addOUIToList();
            }
        });
    }
});


// === Mode Button Instant Highlight ===

// Use mousedown for immediate visual feedback (fires before click/htmx processing)
document.addEventListener('mousedown', function(evt) {
    // Find if click was on or inside a mode button
    const modeBtn = evt.target.closest('.mode-btn');
    if (modeBtn) {
        // Remove active from all mode buttons, add to clicked one
        document.querySelectorAll('.mode-btn').forEach(btn => btn.classList.remove('active'));
        modeBtn.classList.add('active');
    }
});

// Also handle touch events for mobile
document.addEventListener('touchstart', function(evt) {
    const modeBtn = evt.target.closest('.mode-btn');
    if (modeBtn) {
        document.querySelectorAll('.mode-btn').forEach(btn => btn.classList.remove('active'));
        modeBtn.classList.add('active');
    }
}, {passive: true});

// === HTMX Event Handlers ===

// Track if we've already shown the mode switch toast for this request
let modeToastShown = false;

document.body.addEventListener('htmx:beforeRequest', function(evt) {
    // Reset toast flag before each mode switch request
    if (evt.detail.pathInfo && evt.detail.pathInfo.requestPath === '/api/mode') {
        modeToastShown = false;
    }
});

document.body.addEventListener('htmx:afterSwap', function(evt) {
    // Handle successful mode switch - only show toast once per request
    if (evt.detail.pathInfo && evt.detail.pathInfo.requestPath === '/api/mode') {
        if (!modeToastShown) {
            modeToastShown = true;
            showToast('Mode switched');
            hideTargetPicker();
        }
    }
});

document.body.addEventListener('htmx:responseError', function(evt) {
    showToast('Request failed', true);
});

// === Reboot/Shutdown Recovery ===

let rebootCheckInterval = null;

function startRebootCheck() {
    // After reboot/shutdown initiated, poll until server responds, then reload
    if (rebootCheckInterval) return;

    rebootCheckInterval = setInterval(() => {
        fetch('/api/status', { method: 'GET' })
            .then(response => {
                if (response.ok) {
                    clearInterval(rebootCheckInterval);
                    rebootCheckInterval = null;
                    location.reload();
                }
            })
            .catch(() => {
                // Server still down, keep polling
            });
    }, 3000);
}

// Listen for reboot/shutdown button clicks
document.body.addEventListener('htmx:afterRequest', function(evt) {
    const path = evt.detail.pathInfo?.requestPath;
    if (path === '/api/reboot' || path === '/api/shutdown') {
        if (evt.detail.successful) {
            startRebootCheck();
        }
    }
});

// === Performance Flyout ===

function openPerformance() {
    document.getElementById('flyout-overlay').classList.add('open');
    document.getElementById('performance-flyout').classList.add('open');
}

function closePerformance() {
    document.getElementById('flyout-overlay').classList.remove('open');
    document.getElementById('performance-flyout').classList.remove('open');
}

function isPerformanceFlyoutOpen() {
    return document.getElementById('performance-flyout').classList.contains('open');
}

// === Threshold Configuration ===

let currentConfig = null;

async function loadThresholdConfig() {
    try {
        const response = await fetch('/api/performance/config');
        if (!response.ok) {
            console.error('Failed to load threshold config');
            return;
        }
        currentConfig = await response.json();
        updateThresholdUI();
    } catch (error) {
        console.error('Error loading threshold config:', error);
    }
}

function updateThresholdUI() {
    if (!currentConfig) return;

    // Update all sliders and dropdowns with current config
    for (const [metric, settings] of Object.entries(currentConfig)) {
        if (metric === 'global_settings') continue;

        const warningSlider = document.getElementById(`${metric}-warning`);
        const criticalSlider = document.getElementById(`${metric}-critical`);
        const actionSlider = document.getElementById(`${metric}-action`);
        const responseSelect = document.getElementById(`${metric}-response`);

        if (warningSlider) {
            warningSlider.value = settings.warning_threshold;
            document.getElementById(`${metric}-warning-value`).textContent = settings.warning_threshold;
        }
        if (criticalSlider) {
            criticalSlider.value = settings.critical_threshold;
            document.getElementById(`${metric}-critical-value`).textContent = settings.critical_threshold;
        }
        if (actionSlider) {
            actionSlider.value = settings.action_threshold;
            document.getElementById(`${metric}-action-value`).textContent = settings.action_threshold;
        }
        if (responseSelect) {
            responseSelect.value = settings.response_action;
        }
    }
}

async function saveThresholdConfig() {
    if (!currentConfig) {
        showToast('No configuration to save', true);
        return;
    }

    try {
        const response = await fetch('/api/performance/config', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(currentConfig)
        });

        if (response.ok) {
            showToast('Thresholds saved successfully');
        } else {
            const error = await response.json();
            showToast(`Failed to save: ${error.error}`, true);
        }
    } catch (error) {
        showToast('Failed to save thresholds', true);
        console.error('Error saving config:', error);
    }
}

function updateThreshold(metric, level, value) {
    if (!currentConfig || !currentConfig[metric]) return;

    const thresholdKey = `${level}_threshold`;
    currentConfig[metric][thresholdKey] = parseFloat(value);

    // Update display value
    const displayElement = document.getElementById(`${metric}-${level}-value`);
    if (displayElement) {
        displayElement.textContent = value;
    }
}

function updateResponseAction(metric, action) {
    if (!currentConfig || !currentConfig[metric]) return;
    currentConfig[metric].response_action = action;
}

function dismissAlert(metric) {
    fetch('/api/performance/dismiss', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({metric: metric})
    }).catch(error => {
        console.error('Error dismissing alert:', error);
    });

    // Remove alert banner immediately
    const alertBanner = document.getElementById('perf-alert-banner');
    if (alertBanner) {
        alertBanner.innerHTML = '';
    }
}

function toggleSettings() {
    const content = document.getElementById('threshold-settings');
    const button = event.target;

    if (!content || !button) return;

    if (content.classList.contains('hidden')) {
        content.classList.remove('hidden');
        button.textContent = 'CONFIGURE THRESHOLDS [-]';
        if (!currentConfig) {
            loadThresholdConfig();  // Load on first open
        }
    } else {
        content.classList.add('hidden');
        button.textContent = 'CONFIGURE THRESHOLDS [+]';
    }
}

// Load config when flyout opens
document.addEventListener('DOMContentLoaded', () => {
    const perfFlyout = document.getElementById('performance-flyout');
    if (perfFlyout) {
        const observer = new MutationObserver((mutations) => {
            for (const mutation of mutations) {
                if (mutation.attributeName === 'class') {
                    if (perfFlyout.classList.contains('open') && !currentConfig) {
                        loadThresholdConfig();
                    }
                }
            }
        });
        observer.observe(perfFlyout, {attributes: true, attributeFilter: ['class']});
    }
});
