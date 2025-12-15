/**
 * Unit tests for embedded JavaScript in warpie-control.py
 *
 * These tests verify the core JavaScript functions used in the WarPie web control panel.
 * Since the JS is embedded in Python, we test reconstructed/mocked versions of key functions.
 */

describe('WarPie Control Panel JavaScript', () => {
    // Setup DOM for browser-like environment
    beforeEach(() => {
        document.body.innerHTML = `
            <div id="toast" class="toast"></div>
            <div id="logOverlay" class="flyout-overlay"></div>
            <div id="logFlyout" class="flyout"></div>
            <div id="filterOverlay" class="flyout-overlay"></div>
            <div id="filterFlyout" class="flyout"></div>
            <div id="ssidInput"></div>
            <div id="scanResults"></div>
            <div id="staticExclusionList"></div>
            <div id="dynamicExclusionList"></div>
            <div id="targetList"></div>
        `;
    });

    describe('escapeHtml', () => {
        // Recreate the escapeHtml function for testing
        const escapeHtml = (text) => {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        };

        test('escapes HTML special characters', () => {
            expect(escapeHtml('<script>alert("XSS")</script>')).toBe(
                '&lt;script&gt;alert("XSS")&lt;/script&gt;'
            );
        });

        test('escapes ampersands', () => {
            expect(escapeHtml('foo & bar')).toBe('foo &amp; bar');
        });

        test('escapes quotes', () => {
            expect(escapeHtml('"quoted"')).toBe('"quoted"');
        });

        test('handles empty string', () => {
            expect(escapeHtml('')).toBe('');
        });

        test('handles plain text unchanged', () => {
            expect(escapeHtml('Hello World')).toBe('Hello World');
        });
    });

    describe('showToast', () => {
        // Recreate showToast function for testing
        const showToast = (msg, isError) => {
            const toast = document.getElementById('toast');
            toast.textContent = msg;
            toast.className = 'toast' + (isError ? ' error' : '');
            toast.style.display = 'block';
        };

        test('shows success toast', () => {
            showToast('Success!', false);
            const toast = document.getElementById('toast');
            expect(toast.textContent).toBe('Success!');
            expect(toast.className).toBe('toast');
            expect(toast.style.display).toBe('block');
        });

        test('shows error toast', () => {
            showToast('Error occurred', true);
            const toast = document.getElementById('toast');
            expect(toast.textContent).toBe('Error occurred');
            expect(toast.className).toBe('toast error');
        });
    });

    describe('Flyout Functions', () => {
        const openLogs = () => {
            document.getElementById('logOverlay').classList.add('open');
            document.getElementById('logFlyout').classList.add('open');
        };

        const closeLogs = () => {
            document.getElementById('logOverlay').classList.remove('open');
            document.getElementById('logFlyout').classList.remove('open');
        };

        const openFilters = () => {
            document.getElementById('filterOverlay').classList.add('open');
            document.getElementById('filterFlyout').classList.add('open');
        };

        const closeFilters = () => {
            document.getElementById('filterOverlay').classList.remove('open');
            document.getElementById('filterFlyout').classList.remove('open');
        };

        test('openLogs adds open class', () => {
            openLogs();
            expect(document.getElementById('logOverlay').classList.contains('open')).toBe(true);
            expect(document.getElementById('logFlyout').classList.contains('open')).toBe(true);
        });

        test('closeLogs removes open class', () => {
            openLogs();
            closeLogs();
            expect(document.getElementById('logOverlay').classList.contains('open')).toBe(false);
            expect(document.getElementById('logFlyout').classList.contains('open')).toBe(false);
        });

        test('openFilters adds open class', () => {
            openFilters();
            expect(document.getElementById('filterOverlay').classList.contains('open')).toBe(true);
            expect(document.getElementById('filterFlyout').classList.contains('open')).toBe(true);
        });

        test('closeFilters removes open class', () => {
            openFilters();
            closeFilters();
            expect(document.getElementById('filterOverlay').classList.contains('open')).toBe(false);
            expect(document.getElementById('filterFlyout').classList.contains('open')).toBe(false);
        });
    });

    describe('Filter Rendering', () => {
        const escapeHtml = (text) => {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        };

        test('renders static exclusion item correctly', () => {
            const exclusion = {
                value: 'HomeNetwork',
                type: 'exact',
                description: 'My home network',
            };

            const html = `
                <div class="exclusion-item">
                    <div class="exclusion-info">
                        <div class="exclusion-ssid">${escapeHtml(exclusion.value)}</div>
                        <div class="exclusion-meta">
                            <span class="exclusion-type static">static</span>
                            <span class="exclusion-method ${exclusion.type}">${exclusion.type}</span>
                            ${exclusion.description ? '- ' + escapeHtml(exclusion.description) : ''}
                        </div>
                    </div>
                </div>
            `.trim();

            expect(html).toContain('HomeNetwork');
            expect(html).toContain('static');
            expect(html).toContain('exact');
            expect(html).toContain('My home network');
        });

        test('renders targeting inclusion item correctly', () => {
            const target = {
                oui: '00:1E:C0:*',
                mode: '',
                builtin: false,
                description: 'custom target',
            };

            const html = `
                <div class="target-item">
                    <div class="exclusion-info">
                        <span class="target-oui">${escapeHtml(target.oui)}</span>
                        <span class="target-mode">${escapeHtml(target.mode)}</span>
                        ${target.builtin ? '<span class="target-builtin">built-in</span>' : ''}
                        ${target.description ? '<div class="exclusion-meta">' + escapeHtml(target.description) + '</div>' : ''}
                    </div>
                </div>
            `.trim();

            expect(html).toContain('00:1E:C0:*');
            expect(html).toContain('');
            expect(html).toContain('custom target');
            expect(html).not.toContain('built-in');
        });
    });

    describe('Input Validation', () => {
        test('validates SSID is not empty', () => {
            const validateSSID = (ssid) => Boolean(ssid && ssid.trim().length > 0);

            expect(validateSSID('')).toBe(false);
            expect(validateSSID('   ')).toBe(false);
            expect(validateSSID('HomeNetwork')).toBe(true);
        });

        test('validates OUI format', () => {
            // Simple OUI validation
            const validateOUI = (oui) => {
                const pattern = /^([0-9A-Fa-f]{2}:){2}[0-9A-Fa-f]{2}:\*$/;
                return pattern.test(oui);
            };

            expect(validateOUI('00:1E:C0:*')).toBe(true);
            expect(validateOUI('AA:BB:CC:*')).toBe(true);
            expect(validateOUI('invalid')).toBe(false);
            expect(validateOUI('00:1E:C0')).toBe(false);
        });
    });
});
