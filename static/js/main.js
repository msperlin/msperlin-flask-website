/* ==========================================================================
   Site interactions: theme, mobile nav, scroll reveal, charts, HTMX hooks.
   Loaded with `defer`, so the DOM is parsed before this runs.
   ========================================================================== */
(function () {
    'use strict';

    var root = document.documentElement;

    /* ---------------------------------------------------------------- Theme */
    function currentTheme() {
        return root.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
    }

    function isDark() {
        return currentTheme() === 'dark';
    }

    function applyTheme(theme) {
        root.setAttribute('data-theme', theme);
        var meta = document.querySelector('meta[name="theme-color"]');
        if (meta) {
            meta.setAttribute('content', theme === 'dark' ? '#0a0f1c' : '#ffffff');
        }
        // Charts follow the theme.
        destroyCharts();
        renderCharts();
    }

    /* ------------------------------------------------------------- Elements */
    // Event delegation so listeners survive HTMX body swaps.
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

        var navBtn = e.target.closest('[data-nav-toggle]');
        if (navBtn) {
            var open = document.body.classList.toggle('nav-open');
            navBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
            return;
        }

        if (e.target.closest('nav a') && window.matchMedia('(max-width: 820px)').matches) {
            document.body.classList.remove('nav-open');
            var toggle = document.querySelector('[data-nav-toggle]');
            if (toggle) { toggle.setAttribute('aria-expanded', 'false'); }
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

    function hexA(hex, alpha) {
        var h = hex.replace('#', '');
        if (h.length === 3) {
            h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
        }
        var n = parseInt(h, 16);
        var r = (n >> 16) & 255;
        var g = (n >> 8) & 255;
        var b = n & 255;
        return 'rgba(' + r + ',' + g + ',' + b + ',' + alpha + ')';
    }

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
            var isBox = (cfg.type === 'boxplot' || cfg.type === 'violin');
            var base = i === 0 ? accent : accent2;

            if (isBox) {
                ds.backgroundColor = hexA(base, 0.28);
                ds.borderColor = base;
                ds.medianColor = base;
                ds.outlierBackgroundColor = base;
                ds.outlierBorderColor = base;
                ds.outlierRadius = 3;
                ds.itemRadius = 2;
                ds.borderWidth = ds.borderWidth || 1.5;
            } else if (isPie) {
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

    document.addEventListener('click', function (e) {
        var citeBtn = e.target.closest('.cite-btn');
        if (citeBtn) {
            var modal = document.getElementById('citeModal');
            var bibtexOutput = document.getElementById('bibtexOutput');
            var apaOutput = document.getElementById('apaOutput');
            if (!modal || !bibtexOutput || !apaOutput) { return; }

            var title = citeBtn.getAttribute('data-title') || '';
            var authors = citeBtn.getAttribute('data-authors') || '';
            var year = citeBtn.getAttribute('data-year') || '';
            var journal = citeBtn.getAttribute('data-journal') || '';

            var firstAuthor = (authors.split(',')[0] || '').split(' ').pop().toLowerCase().replace(/[^a-z]/g, '');
            var bibKey = firstAuthor + year;

            bibtexOutput.value = '@article{' + bibKey + ',\n  title = {' + title + '},\n  author = {' + authors +
                '},\n  journal = {' + journal + '},\n  year = {' + year + '}\n}';
            apaOutput.value = formatApaAuthors(authors) + ' (' + year + '). ' + title + '. ' + journal + '.';

            modal.classList.add('is-open');
            return;
        }

        if (e.target.closest('[data-cite-close]')) {
            var openModal = document.getElementById('citeModal');
            if (openModal) { openModal.classList.remove('is-open'); }
            return;
        }

        // Click on the modal backdrop closes it.
        if (e.target.classList && e.target.classList.contains('modal')) {
            e.target.classList.remove('is-open');
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

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            var modal = document.getElementById('citeModal');
            if (modal) { modal.classList.remove('is-open'); }
        }
    });

    /* ----------------------------------------------------------- Bootstrap */
    function init() {
        stagger();
        observeReveals();
        renderCharts();
    }

    document.addEventListener('DOMContentLoaded', init);

    // HTMX: tear down charts before the body is replaced to avoid leaks.
    document.addEventListener('htmx:beforeSwap', function () {
        destroyCharts();
    });

    // HTMX: re-run enhancements after swapped content settles.
    document.addEventListener('htmx:afterSwap', function (event) {
        // Keep the document title in sync with the boosted page.
        try {
            var html = event.detail.xhr.responseText;
            var match = html && html.match(/<title[^>]*>([\s\S]*?)<\/title>/i);
            if (match) { document.title = match[1].trim(); }
        } catch (err) { /* noop */ }

        stagger();
        observeReveals();
        renderCharts();
    });

    document.addEventListener('htmx:afterSettle', function () {
        window.scrollTo({ top: 0, behavior: 'auto' });
    });

    // If the document is already parsed (e.g. script loaded late), run now.
    if (document.readyState !== 'loading') {
        init();
    }
})();
