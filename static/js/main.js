/* ==========================================================================
   Site interactions: theme, navigation, scroll reveal, charts, cite modal.
   Loaded with `defer`, so the DOM is parsed before this runs.
   ========================================================================== */
(function () {
    'use strict';

    var root = document.documentElement;

    // Mark the document as scripted so reveal animations can start from hidden.
    // Done here (not inline) so a failed script never hides the page content.
    root.classList.add('js');

    /* ---------------------------------------------------------------- Theme */
    function currentTheme() {
        return root.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
    }

    function isDark() {
        return currentTheme() === 'dark';
    }

    function syncThemeChrome(theme) {
        var meta = document.querySelector('meta[name="theme-color"]');
        if (meta) {
            meta.setAttribute('content', theme === 'dark' ? '#0a0f1c' : '#ffffff');
        }
        document.querySelectorAll('[data-theme-toggle]').forEach(function (btn) {
            btn.setAttribute('aria-label',
                theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme');
        });
    }

    function applyTheme(theme) {
        root.setAttribute('data-theme', theme);
        syncThemeChrome(theme);
        // Charts follow the theme.
        destroyCharts();
        renderCharts();
    }

    /* ------------------------------------------------------- Navigation */
    function closeNav() {
        document.body.classList.remove('nav-open');
        var toggle = document.querySelector('[data-nav-toggle]');
        if (toggle) { toggle.setAttribute('aria-expanded', 'false'); }
    }

    function closeDropdowns(except) {
        document.querySelectorAll('.dropdown.is-open').forEach(function (dd) {
            if (dd === except) { return; }
            dd.classList.remove('is-open');
            var btn = dd.querySelector('[data-dropdown-toggle]');
            if (btn) { btn.setAttribute('aria-expanded', 'false'); }
        });
    }

    // Event delegation keeps listeners valid for the whole document lifetime.
    document.addEventListener('click', function (e) {
        var themeBtn = e.target.closest('[data-theme-toggle]');
        if (themeBtn) {
            var next = isDark() ? 'light' : 'dark';
            try {
                localStorage.setItem('theme', next);
            } catch (err) { /* storage disabled */ }
            applyTheme(next);
            return;
        }

        var dropdownBtn = e.target.closest('[data-dropdown-toggle]');
        if (dropdownBtn) {
            var dropdown = dropdownBtn.closest('.dropdown');
            var willOpen = !dropdown.classList.contains('is-open');
            closeDropdowns(dropdown);
            dropdown.classList.toggle('is-open', willOpen);
            dropdownBtn.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
            return;
        }

        if (!e.target.closest('.dropdown')) {
            closeDropdowns();
        }

        var navBtn = e.target.closest('[data-nav-toggle]');
        if (navBtn) {
            var open = document.body.classList.toggle('nav-open');
            navBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
            return;
        }

        if (e.target.closest('nav a') && window.matchMedia('(max-width: 1100px)').matches) {
            closeNav();
        }
    });

    // Close an open dropdown once keyboard focus leaves it.
    document.addEventListener('focusin', function (e) {
        if (!e.target.closest('.dropdown')) {
            closeDropdowns();
        }
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            if (closeCiteModal()) { return; }
            var openDropdown = document.querySelector('.dropdown.is-open');
            if (openDropdown) {
                closeDropdowns();
                var trigger = openDropdown.querySelector('[data-dropdown-toggle]');
                if (trigger) { trigger.focus(); }
                return;
            }
            closeNav();
        }
    });

    /* ------------------------------------------------------------ Scroll UI */
    var observer = null;

    function observeReveals() {
        var els = document.querySelectorAll('.reveal:not(.is-visible)');
        if (!els.length) { return; }

        if (!('IntersectionObserver' in window)) {
            els.forEach(function (el) { el.classList.add('is-visible'); });
            return;
        }

        if (!observer) {
            observer = new IntersectionObserver(function (entries) {
                entries.forEach(function (entry) {
                    if (entry.isIntersecting) {
                        entry.target.classList.add('is-visible');
                        observer.unobserve(entry.target);
                    }
                });
            }, { rootMargin: '0px 0px -8% 0px', threshold: 0.05 });
        }

        els.forEach(function (el) { observer.observe(el); });
    }

    function stagger() {
        document.querySelectorAll('[data-stagger]').forEach(function (parent) {
            Array.prototype.forEach.call(parent.children, function (child, i) {
                if (child.classList.contains('reveal')) {
                    child.style.setProperty('--reveal-delay', Math.min(i, 10) * 55 + 'ms');
                }
            });
        });
    }

    /* --------------------------------------------------------------- Charts */
    var charts = {};

    function destroyCharts() {
        Object.keys(charts).forEach(function (id) {
            try { charts[id].destroy(); } catch (err) { /* noop */ }
            delete charts[id];
        });
        document.querySelectorAll('canvas[data-chart-canvas]').forEach(function (c) {
            delete c.dataset.done;
        });
    }

    function themedConfig(cfg) {
        var dark = isDark();
        var accent = dark ? '#82aaff' : '#1d4ed8';
        var accent2 = dark ? '#6ea0ff' : '#3b82f6';
        var grid = dark ? 'rgba(255,255,255,0.08)' : 'rgba(15,23,42,0.08)';
        var tick = dark ? '#9fb0ca' : '#56617a';

        cfg.options = cfg.options || {};
        cfg.options.responsive = true;
        cfg.options.maintainAspectRatio = false;
        cfg.options.plugins = cfg.options.plugins || {};
        cfg.options.plugins.legend = Object.assign({ display: cfg.data.datasets.length > 1 }, cfg.options.plugins.legend);
        cfg.options.plugins.tooltip = cfg.options.plugins.tooltip || {};
        cfg.options.plugins.tooltip.backgroundColor = dark ? '#182338' : '#0f172a';

        var scales = cfg.options.scales || {};
        ['x', 'y'].forEach(function (axis) {
            if (scales[axis] === false) { return; }
            var s = scales[axis] || {};
            s.grid = Object.assign({ color: grid, drawBorder: false }, s.grid);
            s.ticks = Object.assign({ color: tick, font: { family: "'Inter', sans-serif" } }, s.ticks);
            scales[axis] = s;
        });
        cfg.options.scales = scales;

        (cfg.data.datasets || []).forEach(function (ds, i) {
            var isLine = (cfg.type === 'line');
            var isPie = (cfg.type === 'doughnut' || cfg.type === 'pie');
            var base = i === 0 ? accent : accent2;

            if (isPie) {
                ds.backgroundColor = ['#3b82f6', '#8b5cf6', '#06b6d4', '#f59e0b', '#10b981', '#ef4444'];
                ds.borderColor = dark ? '#121a2b' : '#ffffff';
                ds.borderWidth = 2;
            } else if (isLine) {
                ds.borderColor = base;
                ds.backgroundColor = base;
                ds.tension = ds.tension === undefined ? 0.35 : ds.tension;
                ds.fill = ds.fill === undefined ? false : ds.fill;
            } else {
                ds.backgroundColor = ds.backgroundColor || base;
                ds.borderColor = ds.borderColor || base;
                ds.borderRadius = ds.borderRadius || 6;
                ds.maxBarThickness = ds.maxBarThickness || 42;
            }
        });

        return cfg;
    }

    function renderCharts() {
        if (typeof Chart === 'undefined') { return; }
        Chart.defaults.font.family = "'Inter', sans-serif";
        Chart.defaults.font.size = 12;

        document.querySelectorAll('script[type="application/json"][data-chart]').forEach(function (node) {
            var canvas = document.getElementById(node.getAttribute('data-chart'));
            if (!canvas || canvas.dataset.done || charts[canvas.id]) { return; }

            var cfg;
            try {
                cfg = JSON.parse(node.textContent);
            } catch (err) {
                return;
            }

            charts[canvas.id] = new Chart(canvas, themedConfig(cfg));
            canvas.dataset.done = '1';
        });
    }

    /* ------------------------------------------------------------ Cite modal */
    var citeTrigger = null;

    function formatApaAuthors(authorsStr) {
        var authors = authorsStr.split(',').map(function (a) { return a.trim(); }).filter(Boolean);
        var formatted = authors.map(function (author) {
            var parts = author.split(' ');
            var lastName = parts.pop();
            var initials = parts.map(function (p) { return p[0] + '.'; }).join(' ');
            return lastName + (initials ? ', ' + initials : '');
        });
        if (formatted.length === 1) { return formatted[0]; }
        if (formatted.length > 1) {
            var last = formatted.pop();
            return formatted.join(', ') + ', & ' + last;
        }
        return '';
    }

    function copyToClipboard(element, btn) {
        if (!element) { return; }
        element.select();
        var done = function () {
            var original = btn.innerText;
            btn.innerText = 'Copied!';
            setTimeout(function () { btn.innerText = original; }, 2000);
        };
        if (navigator.clipboard) {
            navigator.clipboard.writeText(element.value).then(done, done);
        } else {
            try { document.execCommand('copy'); } catch (err) { /* noop */ }
            done();
        }
    }

    function setPageInert(inert) {
        ['header', 'main', 'footer'].forEach(function (selector) {
            var el = document.querySelector(selector);
            if (!el) { return; }
            if (inert) {
                el.setAttribute('inert', '');
            } else {
                el.removeAttribute('inert');
            }
        });
    }

    function openCiteModal(trigger) {
        var modal = document.getElementById('citeModal');
        if (!modal) { return; }
        citeTrigger = trigger;
        modal.classList.add('is-open');
        document.body.classList.add('modal-open');
        setPageInert(true);
        var closeBtn = modal.querySelector('[data-cite-close]');
        if (closeBtn) { closeBtn.focus(); }
    }

    function closeCiteModal() {
        var modal = document.getElementById('citeModal');
        if (!modal || !modal.classList.contains('is-open')) { return false; }

        modal.classList.remove('is-open');
        document.body.classList.remove('modal-open');
        setPageInert(false);
        if (citeTrigger && typeof citeTrigger.focus === 'function') {
            citeTrigger.focus();
        }
        citeTrigger = null;
        return true;
    }

    // Keep keyboard focus inside the dialog while it is open.
    document.addEventListener('keydown', function (e) {
        if (e.key !== 'Tab') { return; }
        var modal = document.getElementById('citeModal');
        if (!modal || !modal.classList.contains('is-open')) { return; }

        var focusable = Array.prototype.filter.call(
            modal.querySelectorAll('button, textarea, input, select, a[href], [tabindex]:not([tabindex="-1"])'),
            function (el) { return el.offsetParent !== null; }
        );
        if (!focusable.length) { return; }

        var first = focusable[0];
        var last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
            e.preventDefault();
            last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
            e.preventDefault();
            first.focus();
        }
    });

    document.addEventListener('click', function (e) {
        var citeBtn = e.target.closest('.cite-btn');
        if (citeBtn) {
            var bibtexOutput = document.getElementById('bibtexOutput');
            var apaOutput = document.getElementById('apaOutput');
            if (!bibtexOutput || !apaOutput) { return; }

            var title = citeBtn.getAttribute('data-title') || '';
            var authors = citeBtn.getAttribute('data-authors') || '';
            var year = citeBtn.getAttribute('data-year') || '';
            var journal = citeBtn.getAttribute('data-journal') || '';

            var firstAuthor = (authors.split(',')[0] || '').split(' ').pop().toLowerCase().replace(/[^a-z]/g, '');
            var bibKey = firstAuthor + year;

            bibtexOutput.value = '@article{' + bibKey + ',\n  title = {' + title + '},\n  author = {' + authors +
                '},\n  journal = {' + journal + '},\n  year = {' + year + '}\n}';
            apaOutput.value = formatApaAuthors(authors) + ' (' + year + '). ' + title + '. ' + journal + '.';

            openCiteModal(citeBtn);
            return;
        }

        if (e.target.closest('[data-cite-close]')) {
            closeCiteModal();
            return;
        }

        // Click on the modal backdrop closes it.
        if (e.target.classList && e.target.classList.contains('modal')) {
            closeCiteModal();
            return;
        }

        if (e.target.closest('#copyBtn')) {
            copyToClipboard(document.getElementById('bibtexOutput'), e.target.closest('#copyBtn'));
            return;
        }
        if (e.target.closest('#copyApaBtn')) {
            copyToClipboard(document.getElementById('apaOutput'), e.target.closest('#copyApaBtn'));
            return;
        }
    });

    /* ----------------------------------------------------------- Bootstrap */
    function init() {
        syncThemeChrome(currentTheme());
        stagger();
        observeReveals();
        renderCharts();
    }

    if (document.readyState !== 'loading') {
        init();
    } else {
        document.addEventListener('DOMContentLoaded', init);
    }
})();
