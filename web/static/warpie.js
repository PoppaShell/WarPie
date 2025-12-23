/* WarPie Control Panel - Minimal UI Functions
 *
 * HTMX handles all server communication.
 * This file only handles local UI state (flyouts, toasts).
 */

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

function showRecentFilters() {
    document.getElementById('btn-recent').classList.add('active');
    document.getElementById('btn-all').classList.remove('active');
    // Load recent filters
    htmx.ajax('GET', '/api/filters/recent', '#static-exclusion-list');
}

function showAllFilters() {
    document.getElementById('btn-all').classList.add('active');
    document.getElementById('btn-recent').classList.remove('active');
    // Load all filters
    htmx.ajax('GET', '/api/filters', '#static-exclusion-list');
}

function scanSSID() {
    const ssid = document.getElementById('ssid-input').value.trim();
    if (!ssid) {
        showToast('Please enter an SSID', true);
        return;
    }
    htmx.ajax('GET', '/api/scan-ssid?ssid=' + encodeURIComponent(ssid), {
        target: '#found-networks',
        swap: 'innerHTML'
    }).then(() => {
        document.getElementById('scan-results').classList.remove('hidden');
    });
}

function addExclusion(matchType) {
    const ssid = document.getElementById('ssid-input').value.trim();
    const filterType = document.querySelector('input[name="exclusion-type"]:checked').value;

    fetch('/api/filters', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            ssid: ssid,
            filter_type: filterType,
            match_type: matchType
        })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showToast('Exclusion added');
            document.getElementById('ssid-input').value = '';
            document.getElementById('scan-results').classList.add('hidden');
            htmx.ajax('GET', '/api/filters', '#static-exclusion-list');
        } else {
            showToast(data.error || 'Failed to add', true);
        }
    });
}

function removeFilter(type, value) {
    if (!confirm('Remove this exclusion?')) return;

    fetch('/api/filters/' + type + '/' + encodeURIComponent(value), {method: 'DELETE'})
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                showToast('Removed');
                htmx.ajax('GET', '/api/filters', '#static-exclusion-list');
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
            htmx.ajax('GET', '/api/targets/lists', '#target-lists');
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
                htmx.ajax('GET', '/api/targets/lists', '#target-lists');
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

// === Filter Type Toggle ===

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('input[name="exclusion-type"]').forEach(radio => {
        radio.addEventListener('change', function() {
            const hint = document.getElementById('type-hint');
            if (this.value === 'static') {
                hint.textContent = 'Static: Block at capture time. Use for home networks, neighbors.';
                hint.classList.remove('dynamic');
            } else {
                hint.textContent = 'Dynamic: Post-process removal. Use for iPhone/Android hotspots with rotating MACs.';
                hint.classList.add('dynamic');
            }
        });
    });
});

// === HTMX Event Handlers ===

document.body.addEventListener('htmx:afterSwap', function(evt) {
    // Handle successful mode switch
    if (evt.detail.pathInfo && evt.detail.pathInfo.requestPath === '/api/mode') {
        showToast('Mode switched');
        hideTargetPicker();
    }
});

document.body.addEventListener('htmx:responseError', function(evt) {
    showToast('Request failed', true);
});
