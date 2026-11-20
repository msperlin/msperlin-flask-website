"""End-to-end browser tests that drive the live Flask site with real user clicks.

Runs a real Werkzeug server on an ephemeral localhost port and drives headless
Chromium via Playwright across every section, dropdown, hover/pin interaction,
filter, sort, modal, accordion, copy button, download, keyboard shortcut, and
mobile drawer.

Usage:
    uv run pytest tests/test_e2e.py
    uv run pytest -m e2e
    uv run pytest tests/test_e2e.py --headed --slowmo 250   # watch it click!
"""

import logging
import re
import shutil
import threading
import zipfile
from urllib.parse import urlparse

import pytest
from playwright.sync_api import expect, sync_playwright
from werkzeug.serving import make_server

import app as site

pytestmark = pytest.mark.e2e


# ---------------------------------------------------------------------------
# Infrastructure fixtures: live Flask server + Chromium browser + monitored page
# ---------------------------------------------------------------------------

def _launch_chromium(playwright, *, headless: bool, slow_mo: int):
    """Launch Playwright's managed Chromium, falling back to system Chromium."""
    args = [
        '--disable-dev-shm-usage',
        '--disable-extensions',
        '--disable-background-networking',
        '--disable-sync',
        '--metrics-recording-only',
        '--no-first-run',
    ]
    if headless:
        args.append('--disable-gpu')
    kwargs = {'headless': headless, 'slow_mo': slow_mo, 'args': args}
    try:
        return playwright.chromium.launch(**kwargs)
    except Exception as first_err:
        for candidate in ('chromium', 'chromium-browser', 'google-chrome', 'google-chrome-stable'):
            path = shutil.which(candidate)
            if path:
                return playwright.chromium.launch(executable_path=path, **kwargs)
        raise first_err


@pytest.fixture(scope='module')
def live_server():
    """Start the Flask app on a free localhost port in a background thread."""
    orig_commits = site.get_recent_commits
    orig_actions = site.get_recent_actions
    site.get_recent_commits = lambda limit=3: [{
        'hash': 'abc1234',
        'message': 'Test commit entry',
        'date': '2026-11-20',
        'iso_date': '2026-11-20T12:00:00Z',
        'url': 'https://github.com/msperlin/msperlin-flask-website/commit/abc1234',
    }]
    site.get_recent_actions = lambda limit=15: [{
        'name': 'Tests',
        'status': 'completed',
        'conclusion': 'success',
        'created_at': '2026-11-20T12:00:00Z',
        'html_url': 'https://github.com/msperlin/msperlin-flask-website/actions',
    }]

    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    server = make_server('127.0.0.1', 0, site.app, threaded=True)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{port}'
    finally:
        server.shutdown()
        thread.join(timeout=5)
        site.get_recent_commits = orig_commits
        site.get_recent_actions = orig_actions


@pytest.fixture(scope='module')
def browser(request):
    headed = bool(request.config.getoption('--headed'))
    slowmo = int(request.config.getoption('--slowmo') or 0)
    with sync_playwright() as pw:
        br = _launch_chromium(pw, headless=not headed, slow_mo=slowmo)
        yield br
        br.close()


def _attach_monitors(page, base_url: str):
    """Attach JS/console/HTTP error monitors to a page and return the collectors."""
    page.set_default_timeout(10000)

    page_errors = []
    console_errors = []
    bad_responses = []
    allowed_error_paths = set()

    parsed_base = urlparse(base_url)

    def _is_expected_404(path: str) -> bool:
        if path in allowed_error_paths:
            return True
        # Chromium automatically probes /favicon.ico on raw non-HTML responses (.md, etc.).
        if path == '/favicon.ico' and page.url.endswith('.md'):
            return True
        return False

    def _is_static_bundle(url: str) -> bool:
        path = urlparse(url).path
        return path.startswith(('/books/', '/slides/'))

    def on_pageerror(err):
        # Pre-rendered bookdown/reveal static bundles under /books/<name>/ and
        # /slides/<folder>/ carry their own third-party scripts blocked by site CSP.
        if _is_static_bundle(page.url):
            return
        page_errors.append(f'{page.url}: {err}')

    def on_console(msg):
        if msg.type == 'error':
            if _is_static_bundle(page.url):
                return
            text = msg.text
            if '404 (NOT FOUND)' in text:
                if allowed_error_paths or page.url.endswith('.md'):
                    return
            console_errors.append(f'{page.url}: {text}')

    def on_response(resp):
        parsed = urlparse(resp.url)
        if parsed.netloc == parsed_base.netloc and resp.status >= 400:
            if not _is_expected_404(parsed.path):
                bad_responses.append(f'{resp.status} {parsed.path} (from {page.url})')

    page.on('pageerror', on_pageerror)
    page.on('console', on_console)
    page.on('response', on_response)
    page._allowed_error_paths = allowed_error_paths

    return page_errors, console_errors, bad_responses


def _new_context(browser, base_url: str, *, viewport: dict, color_scheme: str = 'light',
                 reduced_motion: str = 'reduce', java_script_enabled: bool = True):
    context = browser.new_context(
        viewport=viewport,
        color_scheme=color_scheme,
        reduced_motion=reduced_motion,
        java_script_enabled=java_script_enabled,
        accept_downloads=True,
    )
    if java_script_enabled:
        context.grant_permissions(['clipboard-read', 'clipboard-write'], origin=base_url)
    return context


@pytest.fixture(scope='module')
def desktop_context(request, browser, live_server):
    motion = 'no-preference' if request.config.getoption('--headed') else 'reduce'
    ctx = _new_context(
        browser, live_server,
        viewport={'width': 1280, 'height': 850},
        reduced_motion=motion,
    )
    yield ctx
    ctx.close()


@pytest.fixture(scope='module')
def mobile_context(request, browser, live_server):
    motion = 'no-preference' if request.config.getoption('--headed') else 'reduce'
    ctx = _new_context(
        browser, live_server,
        viewport={'width': 390, 'height': 844},
        reduced_motion=motion,
    )
    yield ctx
    ctx.close()


def _reset_page_state(context, pg):
    """Clear storage and cookies between tests while keeping Chromium's HTTP cache warm."""
    try:
        if pg.url.startswith('http'):
            pg.evaluate('() => { try { localStorage.clear(); sessionStorage.clear(); } catch (e) {} }')
    except Exception:
        pass
    context.clear_cookies()


@pytest.fixture
def page(desktop_context, live_server):
    pg = desktop_context.new_page()
    page_errors, console_errors, bad_responses = _attach_monitors(pg, live_server)
    try:
        yield pg
    finally:
        _reset_page_state(desktop_context, pg)
        pg.close()
    assert not page_errors, f'Uncaught page errors: {page_errors}'
    assert not console_errors, f'Console errors: {console_errors}'
    assert not bad_responses, f'Failed same-origin HTTP responses: {bad_responses}'


@pytest.fixture
def mobile_page(mobile_context, live_server):
    pg = mobile_context.new_page()
    page_errors, console_errors, bad_responses = _attach_monitors(pg, live_server)
    try:
        yield pg
    finally:
        _reset_page_state(mobile_context, pg)
        pg.close()
    assert not page_errors, f'Uncaught mobile page errors: {page_errors}'
    assert not console_errors, f'Console mobile errors: {console_errors}'
    assert not bad_responses, f'Failed mobile HTTP responses: {bad_responses}'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _assert_chart_rendered(page, canvas_id: str):
    canvas = page.locator(f'#{canvas_id}')
    expect(canvas).to_be_visible()
    expect(canvas).to_have_attribute('data-done', '1')
    box = canvas.bounding_box()
    assert box is not None and box['width'] > 100 and box['height'] > 50, (
        f'Chart #{canvas_id} has unexpected dimensions: {box}'
    )


def _assert_images_loaded(page):
    """Scroll images into view and verify every visible image decoded cleanly."""
    broken = page.evaluate(
        """async () => {
            const imgs = Array.from(document.querySelectorAll('img'));
            for (const img of imgs) {
                if (img.loading === 'lazy') {
                    img.scrollIntoView({ behavior: 'instant', block: 'center' });
                }
            }
            await Promise.all(imgs.map(img => {
                if (img.complete) return Promise.resolve();
                return new Promise(resolve => {
                    img.addEventListener('load', resolve, { once: true });
                    img.addEventListener('error', resolve, { once: true });
                    setTimeout(resolve, 3000);
                });
            }));
            return imgs
                .filter(img => img.offsetParent !== null && (!img.complete || img.naturalWidth === 0))
                .map(img => img.getAttribute('src'));
        }"""
    )
    assert not broken, f'Broken images on {page.url}: {broken}'


def _open_dropdown(page, label: str):
    btn = page.locator('header nav button[data-dropdown-toggle]', has_text=label).first
    expect(btn).to_be_visible()
    btn.click()
    expect(btn).to_have_attribute('aria-expanded', 'true')
    return btn


def _read_clipboard(page) -> str:
    return page.evaluate('() => navigator.clipboard.readText()')


# ---------------------------------------------------------------------------
# 1. Header navigation, dropdowns, hover-preview/pin, footer & dismissal
# ---------------------------------------------------------------------------

def test_desktop_header_dropdowns_and_every_nav_link(page, live_server):
    page.goto(live_server + '/')
    expect(page.locator('h1')).to_have_text('Welcome')

    # Research dropdown -> click every item
    research_items = [
        ('Research Themes', '/research', 'Research'),
        ('Research Articles', '/publications', 'Publications'),
        ('Books', '/books', 'Books'),
        ('Talk Slides', '/slides', 'Slides'),
    ]
    for link_text, expected_path, expected_h1 in research_items:
        _open_dropdown(page, 'Research')
        link = page.locator('#menu-research a', has_text=link_text)
        expect(link).to_be_visible()
        link.click()
        expect(page).to_have_url(live_server + expected_path)
        expect(page.locator('h1')).to_have_text(expected_h1)

    # Code & Data dropdown -> click every item
    code_data_items = [
        ('R Packages', '/code/r', 'Code (R)'),
        ('Python Packages', '/code/python', 'Code (Python)'),
        ('MCP Servers', '/mcp', 'Brazilian Financial Data MCP Servers'),
        ('Datasets', '/data', 'Data'),
    ]
    for link_text, expected_path, expected_h1 in code_data_items:
        _open_dropdown(page, 'Code & Data')
        link = page.locator('#menu-code-data a', has_text=link_text)
        expect(link).to_be_visible()
        link.click()
        expect(page).to_have_url(live_server + expected_path)
        expect(page.locator('h1')).to_have_text(expected_h1)

    # Profile dropdown -> click every item
    profile_items = [
        ('CV', '/cv', 'Marcelo'),
        ('Awards', '/awards', 'Awards'),
        ('Media Coverage', '/news', 'Interviews, lectures and News'),
        ('Press Kit', '/press', 'Press Kit'),
    ]
    for link_text, expected_path, expected_h1_part in profile_items:
        _open_dropdown(page, 'Profile')
        link = page.locator('#menu-profile a', has_text=link_text)
        expect(link).to_be_visible()
        link.click()
        expect(page).to_have_url(live_server + expected_path)
        expect(page.locator('h1')).to_contain_text(expected_h1_part)

    # Top-level Consulting, Search icon, Logo back to Home
    page.locator('#primary-nav > li > a', has_text='Consulting').click()
    expect(page).to_have_url(live_server + '/consulting')
    expect(page.locator('h1')).to_be_visible()

    page.locator('header a.search-link').click()
    expect(page).to_have_url(live_server + '/search')
    expect(page.locator('h1')).to_have_text('Search')

    page.locator('header a.logo').click()
    expect(page).to_have_url(live_server + '/')
    expect(page.locator('h1')).to_have_text('Welcome')

    # Footer links: CV, Press, Site Log, Search
    page.locator('footer a', has_text='CV').click()
    expect(page).to_have_url(live_server + '/cv')
    expect(page.locator('h1')).to_contain_text('Marcelo')

    page.locator('footer a', has_text='Press').click()
    expect(page).to_have_url(live_server + '/press')
    expect(page.locator('h1')).to_have_text('Press Kit')

    page.locator('footer a', has_text='Site Log').click()
    expect(page).to_have_url(live_server + '/site-log')
    expect(page.locator('h1')).to_have_text('Site Log')

    page.locator('footer a', has_text='Search').click()
    expect(page).to_have_url(live_server + '/search')
    expect(page.locator('h1')).to_have_text('Search')


def test_dropdown_hover_preview_pin_outside_click_and_escape(page, live_server):
    page.goto(live_server + '/')

    # Hover preview opens dropdown, moving away closes it
    research_dd = page.locator('header nav li.dropdown').first
    research_btn = research_dd.locator('button[data-dropdown-toggle]')
    research_dd.hover()
    expect(research_btn).to_have_attribute('aria-expanded', 'true')
    expect(research_dd).to_have_attribute('data-hover-preview', 'true')

    page.locator('main h1').hover()
    expect(research_btn).to_have_attribute('aria-expanded', 'false')

    # Hover then click pins it open even after moving pointer away
    research_dd.hover()
    research_btn.click()
    expect(research_btn).to_have_attribute('aria-expanded', 'true')
    page.locator('main h1').hover()
    expect(research_btn).to_have_attribute('aria-expanded', 'true')

    # Clicking outside closes pinned dropdown
    page.locator('main h1').click()
    expect(research_btn).to_have_attribute('aria-expanded', 'false')

    # Pressing Escape closes an open dropdown and focuses trigger
    code_btn = _open_dropdown(page, 'Code & Data')
    page.keyboard.press('Escape')
    expect(code_btn).to_have_attribute('aria-expanded', 'false')
    expect(code_btn).to_be_focused()


# ---------------------------------------------------------------------------
# 2. Mobile navigation drawer
# ---------------------------------------------------------------------------

def test_mobile_nav_drawer_and_dropdown_navigation(mobile_page, live_server):
    mobile_page.goto(live_server + '/')
    nav_toggle = mobile_page.locator('[data-nav-toggle]')
    expect(nav_toggle).to_be_visible()
    expect(nav_toggle).to_have_attribute('aria-expanded', 'false')

    # Open drawer
    nav_toggle.click()
    expect(nav_toggle).to_have_attribute('aria-expanded', 'true')
    expect(mobile_page.locator('body')).to_have_class('nav-open')

    # Open Code & Data -> click MCP Servers inside mobile drawer
    mobile_page.locator('nav button[data-dropdown-toggle]', has_text='Code & Data').click()
    mobile_page.locator('#menu-code-data a', has_text='MCP Servers').click()

    expect(mobile_page).to_have_url(live_server + '/mcp')
    expect(mobile_page.locator('h1')).to_have_text('Brazilian Financial Data MCP Servers')

    # Re-open mobile drawer and close with Escape (restores focus to toggle)
    mobile_page.locator('[data-nav-toggle]').click()
    expect(mobile_page.locator('body')).to_have_class('nav-open')
    mobile_page.keyboard.press('Escape')
    expect(mobile_page.locator('[data-nav-toggle]')).to_have_attribute('aria-expanded', 'false')
    assert 'nav-open' not in (mobile_page.locator('body').get_attribute('class') or '')


# ---------------------------------------------------------------------------
# 3. Theme toggle (light/dark persistence + Chart.js re-render)
# ---------------------------------------------------------------------------

def test_theme_toggle_persists_and_rerenders_charts(page, live_server):
    page.goto(live_server + '/')
    html_el = page.locator('html')
    theme_btn = page.locator('[data-theme-toggle]')

    expect(html_el).to_have_attribute('data-theme', 'light')
    expect(theme_btn).to_have_attribute('aria-label', 'Switch to dark theme')

    # Switch to dark mode
    theme_btn.click()
    expect(html_el).to_have_attribute('data-theme', 'dark')
    expect(theme_btn).to_have_attribute('aria-label', 'Switch to light theme')
    assert page.evaluate("localStorage.getItem('theme')") == 'dark'
    expect(page.locator('meta[name="theme-color"]')).to_have_attribute('content', '#0a0f1c')

    # Navigate to /publications — dark theme persists and charts render
    _open_dropdown(page, 'Research')
    page.locator('#menu-research a', has_text='Research Articles').click()
    expect(page).to_have_url(live_server + '/publications')
    expect(html_el).to_have_attribute('data-theme', 'dark')
    _assert_chart_rendered(page, 'pubYearChart')

    # Toggle back to light mode on chart page — charts cleanly destroy & re-render
    page.locator('[data-theme-toggle]').click()
    expect(html_el).to_have_attribute('data-theme', 'light')
    expect(page.locator('meta[name="theme-color"]')).to_have_attribute('content', '#ffffff')
    _assert_chart_rendered(page, 'pubYearChart')


# ---------------------------------------------------------------------------
# 4. Home page clicks
# ---------------------------------------------------------------------------

def test_home_page_clicks_and_images(page, live_server):
    page.goto(live_server + '/')
    _assert_images_loaded(page)

    # Click a research interest pill -> jumps to /search?q=... with results
    first_pill = page.locator('.interest-pills a.tag-pill').first
    pill_text = first_pill.inner_text().strip()
    first_pill.click()
    expect(page).to_have_url(re.compile(r'/search\?q='))
    expect(page.locator('#site-search')).to_have_value(pill_text)
    expect(page.locator('[data-search-summary]')).to_be_visible()

    # Back to home -> click CV (html) link
    page.goto(live_server + '/')
    page.locator('.hero .links a', has_text='CV (html)').click()
    expect(page).to_have_url(live_server + '/cv')

    # Back to home -> click stat card links
    page.goto(live_server + '/')
    page.locator('.stat-card a', has_text='Browse peer-reviewed articles').click()
    expect(page).to_have_url(live_server + '/publications')

    page.goto(live_server + '/')
    page.locator('.stat-card a', has_text='Read online or on Amazon').click()
    expect(page).to_have_url(live_server + '/books')

    page.goto(live_server + '/')
    page.locator('.stat-card').get_by_role('link', name='R', exact=True).click()
    expect(page).to_have_url(live_server + '/code/r')

    page.goto(live_server + '/')
    page.locator('.stat-card').get_by_role('link', name='Python', exact=True).click()
    expect(page).to_have_url(live_server + '/code/python')

    # Back to home -> click a recent publication card -> detail page
    page.goto(live_server + '/')
    recent_pub = page.locator('.home-column').first.locator('.item-card h3 a').first
    pub_title = recent_pub.inner_text().strip()
    recent_pub.click()
    expect(page).to_have_url(re.compile(r'/publications/'))
    expect(page.locator('h1')).to_have_text(pub_title)

    # Home -> View all slides / media / press kit links
    page.goto(live_server + '/')
    page.locator('a.read-more', has_text='View all presentation slides').click()
    expect(page).to_have_url(live_server + '/slides')

    page.goto(live_server + '/')
    page.locator('a.read-more', has_text='All media coverage').click()
    expect(page).to_have_url(live_server + '/news')

    page.goto(live_server + '/')
    page.locator('a.read-more', has_text='Press kit').click()
    expect(page).to_have_url(live_server + '/press')


# ---------------------------------------------------------------------------
# 5. Publications: filtering, sorting, URL sync, cite modal, downloads
# ---------------------------------------------------------------------------

def test_publications_filter_sort_and_clear(page, live_server):
    page.goto(live_server + '/publications')
    _assert_chart_rendered(page, 'pubYearChart')
    if page.locator('#citationHistoryChart').count():
        _assert_chart_rendered(page, 'citationHistoryChart')

    items = page.locator('#pubList .publication-item')
    total = items.count()
    assert total > 10
    expect(page.locator('[data-pub-count]')).to_have_text(f'{total} of {total} shown')

    # Search filter
    search_input = page.locator('[data-pub-search]')
    search_input.fill('liquidity')
    visible_after_search = page.locator('#pubList .publication-item:not([hidden])').count()
    assert 0 < visible_after_search < total
    expect(page.locator('[data-pub-count]')).to_have_text(f'{visible_after_search} of {total} shown')
    assert 'q=liquidity' in page.url

    # Year filter
    year_select = page.locator('[data-pub-year]')
    first_visible_year = page.locator('#pubList .publication-item:not([hidden])').first.get_attribute('data-year')
    year_select.select_option(first_visible_year)
    assert f'year={first_visible_year}' in page.url
    visible_years = page.locator('#pubList .publication-item:not([hidden])').evaluate_all(
        'els => els.map(el => el.dataset.year)'
    )
    assert visible_years and all(y == first_visible_year for y in visible_years)

    # Empty state when nothing matches
    search_input.fill('zzzznonexistentpaperquery')
    expect(page.locator('[data-pub-empty]')).to_be_visible()
    expect(page.locator('[data-pub-count]')).to_have_text(f'0 of {total} shown')

    # Clear button restores everything and clears URL params
    page.locator('[data-pub-clear]').click()
    expect(search_input).to_have_value('')
    expect(year_select).to_have_value('all')
    expect(page.locator('[data-pub-empty]')).to_be_hidden()
    expect(page.locator('[data-pub-count]')).to_have_text(f'{total} of {total} shown')
    assert '?' not in page.url

    # Sort oldest first -> years should be non-decreasing
    sort_select = page.locator('[data-pub-sort]')
    sort_select.select_option('oldest')
    assert 'sort=oldest' in page.url
    years_oldest = page.locator('#pubList .publication-item').evaluate_all(
        'els => els.map(el => parseInt(el.dataset.year || "0", 10))'
    )
    assert years_oldest == sorted(years_oldest)

    # Sort by Impact Factor -> IF should be non-increasing
    sort_select.select_option('if')
    assert 'sort=if' in page.url
    ifs = page.locator('#pubList .publication-item').evaluate_all(
        'els => els.map(el => parseFloat(el.dataset.impactFactor || "0"))'
    )
    assert ifs == sorted(ifs, reverse=True)


def test_publications_cite_modal_and_downloads(page, live_server):
    page.goto(live_server + '/publications')

    # Open Cite modal on first publication that has a DOI
    cite_btn = page.locator('.cite-btn[data-doi]:not([data-doi=""])').first
    cite_btn.click()

    modal = page.locator('#citeModal')
    expect(modal).to_be_visible()
    expect(modal).to_have_class('modal is-open')
    expect(page.locator('main')).to_have_attribute('inert', '')

    # Citation fields populated
    bibtex_val = page.locator('#bibtexOutput').input_value()
    apa_val = page.locator('#apaOutput').input_value()
    abnt_val = page.locator('#abntOutput').input_value()
    chicago_val = page.locator('#chicagoOutput').input_value()
    assert bibtex_val.startswith('@article{')
    assert len(apa_val) > 20
    assert len(abnt_val) > 20
    assert len(chicago_val) > 20

    # Copy BibTeX / APA / ABNT / Chicago buttons
    for btn_id, expected_snippet in (
        ('#copyBtn', '@article{'),
        ('#copyApaBtn', apa_val[:20]),
        ('#copyAbntBtn', abnt_val[:20]),
        ('#copyChicagoBtn', chicago_val[:20]),
    ):
        btn = page.locator(btn_id)
        btn.click()
        expect(btn).to_have_text('Copied!')
        assert expected_snippet in _read_clipboard(page)

    # Copy DOI button
    expect(page.locator('#citeDoiRow')).to_be_visible()
    doi_text = page.locator('#citeDoi').inner_text().strip()
    assert doi_text
    copy_doi = page.locator('#copyDoiBtn')
    copy_doi.click()
    expect(copy_doi).to_have_class('install-btn is-copied')
    assert _read_clipboard(page) == doi_text

    # Share links populated
    expect(page.locator('#citeShare')).to_be_visible()
    for network in ('linkedin', 'bluesky', 'mastodon', 'email'):
        href = page.locator(f'#citeShare a[data-share="{network}"]').get_attribute('href')
        assert href and href != '#'

    # Close via close button -> inert removed
    page.locator('[data-cite-close]').click()
    expect(modal).to_be_hidden()
    expect(page.locator('main')).not_to_have_attribute('inert', '')

    # Re-open and close via Escape
    cite_btn.click()
    expect(modal).to_be_visible()
    page.keyboard.press('Escape')
    expect(modal).to_be_hidden()

    # Re-open and close via backdrop click
    cite_btn.click()
    expect(modal).to_be_visible()
    modal.click(position={'x': 5, 'y': 5})
    expect(modal).to_be_hidden()

    # Download all (.bib) and (.ris) via real clicks
    with page.expect_download() as dl_bib:
        page.locator('a', has_text='Download all (.bib)').click()
    bib_path = dl_bib.value.path()
    assert dl_bib.value.suggested_filename.endswith('.bib')
    with open(bib_path, encoding='utf-8') as f:
        assert '@article{' in f.read()

    with page.expect_download() as dl_ris:
        page.locator('a', has_text='Download all (.ris)').click()
    ris_path = dl_ris.value.path()
    assert dl_ris.value.suggested_filename.endswith('.ris')
    with open(ris_path, encoding='utf-8') as f:
        assert 'TY  - JOUR' in f.read()


# ---------------------------------------------------------------------------
# 6. Publication detail page: cross-links, author filter, cite modal, exports
# ---------------------------------------------------------------------------

def test_publication_detail_interactions_and_cross_links(page, live_server):
    page.goto(live_server + '/publications/2019-rbfin-accessing-financial-repor')
    expect(page.locator('h1')).to_be_visible()

    # Cite modal on detail page
    page.locator('.pub-links .cite-btn').click()
    expect(page.locator('#citeModal')).to_be_visible()
    page.locator('#copyBtn').click()
    expect(page.locator('#copyBtn')).to_have_text('Copied!')
    page.locator('[data-cite-close]').click()
    expect(page.locator('#citeModal')).to_be_hidden()

    # Download .bib and .ris
    with page.expect_download() as dl_bib:
        page.locator('.pub-links a', has_text='Download .bib').click()
    assert dl_bib.value.suggested_filename.endswith('.bib')

    with page.expect_download() as dl_ris:
        page.locator('.pub-links a', has_text='Download .ris').click()
    assert dl_ris.value.suggested_filename.endswith('.ris')

    # Click Markdown (.md) link
    page.locator('.pub-links a', has_text='Markdown (.md)').click()
    expect(page).to_have_url(live_server + '/publications/2019-rbfin-accessing-financial-repor.md')
    assert page.locator('body').inner_text().startswith('# ')
    page.go_back()

    # Click Related Open-Source Software -> navigates to package detail
    page.locator('h2:has-text("Related Open-Source Software") + ul a').first.click()
    expect(page).to_have_url(re.compile(r'/code/'))
    expect(page.locator('h1')).to_be_visible()
    page.go_back()

    # Click Related Publication -> navigates to another publication detail
    page.locator('h2:has-text("Related Publications") + ul a').first.click()
    expect(page).to_have_url(re.compile(r'/publications/'))
    expect(page.locator('h1')).to_be_visible()
    page.go_back()

    # Click an author link -> filters /publications?q=<author> automatically
    author_link = page.locator('.pub-authors a.author-link').first
    author_name = author_link.inner_text().strip()
    author_link.click()
    expect(page).to_have_url(re.compile(r'/publications\?q='))
    expect(page.locator('[data-pub-search]')).to_have_value(author_name)
    assert page.locator('#pubList .publication-item:not([hidden])').count() >= 1

    # Click back link from a detail page
    page.goto(live_server + '/publications/2018-scientometrics-is-predatory-publishing-a')
    expect(page.locator('h2', has_text='Awards & Recognition')).to_be_visible()
    expect(page.locator('h2', has_text='Media coverage')).to_be_visible()
    page.locator('a.back-link', has_text='All publications').click()
    expect(page).to_have_url(live_server + '/publications')


# ---------------------------------------------------------------------------
# 7. Books, Book detail, and rendered bookdown HTML book
# ---------------------------------------------------------------------------

def test_books_detail_and_rendered_online_book(page, live_server):
    page.goto(live_server + '/books')
    _assert_images_loaded(page)

    # Click first book title -> book detail page
    first_book_link = page.locator('.item-list .item-card h2 a').first
    book_title = first_book_link.inner_text().strip()
    first_book_link.click()
    expect(page).to_have_url(re.compile(r'/book/'))
    expect(page.locator('h1')).to_have_text(book_title)
    _assert_images_loaded(page)
    expect(page.locator('pre.pub-bibtex')).to_be_visible()

    # Click a rendered online book chapter link (points to /books/<name>/...)
    toc_link = page.locator('ol.book-toc a').first
    if toc_link.count():
        toc_link.click()
        expect(page).to_have_url(re.compile(r'/books/'))
        page.wait_for_load_state('domcontentloaded')
        expect(page.locator('h1').first).to_be_visible()
        assert len(page.locator('body').inner_text().strip()) > 50
        page.go_back()

    # Back to /books
    page.locator('a.back-link', has_text='All books').click()
    expect(page).to_have_url(live_server + '/books')


# ---------------------------------------------------------------------------
# 8. Code (R), Code (Python), Package details, and MCP Hub
# ---------------------------------------------------------------------------

def test_code_r_filter_copy_chart_and_package_detail(page, live_server):
    page.goto(live_server + '/code/r')
    _assert_chart_rendered(page, 'rDownloadsChart')

    total = page.locator('[data-pkg-list] .pkg-item').count()
    assert total > 5
    expect(page.locator('[data-pkg-count]')).to_have_text(f'{total} of {total} shown')

    # Filter R packages
    search = page.locator('[data-pkg-search]')
    search.fill('GetDFPData2')
    expect(page.locator('[data-pkg-list] .pkg-item:not([hidden])')).to_have_count(1)
    expect(page.locator('[data-pkg-count]')).to_have_text(f'1 of {total} shown')

    # Empty state
    search.fill('zzzznonexistentpkg')
    expect(page.locator('[data-pkg-empty]')).to_be_visible()

    # Clear
    page.locator('[data-pkg-clear]').click()
    expect(page.locator('[data-pkg-empty]')).to_be_hidden()
    expect(page.locator('[data-pkg-count]')).to_have_text(f'{total} of {total} shown')

    # Click install command copy button
    install_btn = page.locator('[data-pkg-list] button.install-btn').first
    expected_cmd = install_btn.get_attribute('data-copy-text')
    install_btn.click()
    expect(install_btn).to_have_class('install-btn is-copied')
    assert _read_clipboard(page) == expected_cmd

    # Navigate to GetDFPData2 package detail page
    page.locator('[data-pkg-list] a', has_text='GetDFPData2').first.click()
    expect(page).to_have_url(live_server + '/code/r/getdfpdata2')
    expect(page.locator('h1')).to_have_text('GetDFPData2')

    # Click every copy button on the package detail page
    for btn in page.locator('article button[data-copy-text]').all():
        expected = btn.get_attribute('data-copy-text')
        btn.click()
        expect(btn).to_have_class('install-btn is-copied')
        assert _read_clipboard(page) == expected

    # Download .bib and open .md
    with page.expect_download() as dl_bib:
        page.locator('.pub-links a', has_text='Download .bib').click()
    assert dl_bib.value.suggested_filename.endswith('.bib')

    page.locator('.pub-links a', has_text='Markdown (.md)').click()
    expect(page).to_have_url(live_server + '/code/r/getdfpdata2.md')
    assert '# GetDFPData2' in page.locator('body').inner_text()
    page.go_back()

    # Follow cross-links: Companion software (cvm-mcp), Related Datasets, Back link
    page.locator('h2:has-text("Companion") + ul a', has_text='cvm-mcp').click()
    expect(page).to_have_url(live_server + '/code/python/cvm-mcp')
    expect(page.locator('h1')).to_have_text('cvm-mcp')
    page.go_back()

    page.locator('h2:has-text("Related Datasets") + ul a').first.click()
    expect(page).to_have_url(re.compile(r'/data/'))
    page.go_back()

    page.locator('a.back-link', has_text='All R code').click()
    expect(page).to_have_url(live_server + '/code/r')


def test_code_python_and_mcp_hub_interactions(page, live_server):
    page.goto(live_server + '/code/python')
    _assert_chart_rendered(page, 'pythonDownloadsChart')

    # Filter Python packages
    total = page.locator('[data-pkg-list] .pkg-item').count()
    assert total >= 3
    page.locator('[data-pkg-search]').fill('cvm-mcp')
    expect(page.locator('[data-pkg-list] .pkg-item:not([hidden])')).to_have_count(1)
    page.locator('[data-pkg-clear]').click()
    expect(page.locator('[data-pkg-count]')).to_have_text(f'{total} of {total} shown')

    # Copy pip install command
    pip_btn = page.locator('[data-pkg-list] button.install-btn').first
    pip_btn.click()
    expect(pip_btn).to_have_class('install-btn is-copied')
    assert _read_clipboard(page).startswith('pip install ')

    # Expand MCP Quickstart <details> accordion and click Copy MCP JSON Config
    quickstart = page.locator('details.mcp-config-card')
    assert quickstart.get_attribute('open') is None
    quickstart.locator('summary').click()
    expect(quickstart).to_have_attribute('open', '')
    copy_mcp = quickstart.locator('button[data-copy-text]')
    copy_mcp.click()
    expect(copy_mcp).to_have_class('install-btn is-copied')
    assert 'mcpServers' in _read_clipboard(page)

    # Navigate to MCP Hub via link inside quickstart
    quickstart.locator('a', has_text='Explore all MCP servers').click()
    expect(page).to_have_url(live_server + '/mcp')
    expect(page.locator('h1')).to_have_text('Brazilian Financial Data MCP Servers')

    # Copy uvx command on MCP server card
    uvx_btn = page.locator('.mcp-server-card button.install-btn').first
    uvx_btn.click()
    expect(uvx_btn).to_have_class('install-btn is-copied')
    assert _read_clipboard(page).startswith('uvx ')

    # Toggle Client Setup Guides <details> accordions and copy config
    details_cards = page.locator('.mcp-accordion details.mcp-config-card')
    assert details_cards.count() >= 3
    expect(details_cards.first).to_have_attribute('open', '')

    # Click second client summary to open it and copy its config
    second_client = details_cards.nth(1)
    second_client.locator('summary').click()
    expect(second_client).to_have_attribute('open', '')
    second_copy = second_client.locator('button[data-copy-text]')
    second_copy.click()
    expect(second_copy).to_have_class('install-btn is-copied')
    assert _read_clipboard(page) == second_copy.get_attribute('data-copy-text')

    # Copy an example prompt
    prompt_btn = page.locator('.prompt-card button[data-copy-text]').first
    prompt_btn.click()
    expect(prompt_btn).to_have_class('install-btn is-copied')
    assert _read_clipboard(page) == prompt_btn.get_attribute('data-copy-text')

    # Click through to MCP package detail page and test its MCP copy buttons
    page.locator('.mcp-server-card a', has_text='Package Details').first.click()
    expect(page).to_have_url(re.compile(r'/code/python/'))
    expect(page.locator('h2', has_text='MCP Client Configuration')).to_be_visible()
    mcp_json_btn = page.locator('button', has_text='Copy MCP JSON')
    mcp_json_btn.click()
    expect(mcp_json_btn).to_have_class('install-btn is-copied')
    assert 'mcpServers' in _read_clipboard(page)


# ---------------------------------------------------------------------------
# 9. Data, Dataset detail, Research themes, News, Awards, Slides
# ---------------------------------------------------------------------------

def test_data_and_dataset_detail_clicks(page, live_server):
    page.goto(live_server + '/data')

    # Click Details on first dataset
    page.locator('ul.item-list li a', has_text='Details').first.click()
    expect(page).to_have_url(re.compile(r'/data/'))
    expect(page.locator('h1')).to_be_visible()
    expect(page.locator('pre.pub-bibtex')).to_be_visible()

    # Back to /data
    page.locator('a.back-link', has_text='All data').click()
    expect(page).to_have_url(live_server + '/data')

    # Click links inside the Ecosystem table
    page.locator('.ecosystem-table a', has_text='GetDFPData2').click()
    expect(page).to_have_url(live_server + '/code/r/getdfpdata2')
    page.go_back()

    page.locator('.ecosystem-table a', has_text='cvm-mcp').click()
    expect(page).to_have_url(live_server + '/code/python/cvm-mcp')
    page.go_back()

    page.locator('.ecosystem-table a', has_text='DFP Dataverse').click()
    expect(page).to_have_url(live_server + '/data/getdfpdata2')


def test_research_news_awards_and_slides_interactions(page, live_server):
    # Research themes -> click paper & software links
    page.goto(live_server + '/research')
    page.locator('.research-theme h4 a').first.click()
    expect(page).to_have_url(re.compile(r'/publications/'))

    page.goto(live_server + '/research')
    page.locator('.research-theme h3:has-text("Software and data") + ul a').first.click()
    expect(page).to_have_url(re.compile(r'/(code|data)/'))

    # Media Coverage (/news) -> filter hides non-matching year groups, clear restores
    page.goto(live_server + '/news')
    total_news = page.locator('[data-pkg-list] .pkg-item').count()
    total_groups = page.locator('[data-year-group]').count()
    assert total_news > 5 and total_groups >= 2

    page.locator('[data-pkg-search]').fill('Fapesp')
    visible_news = page.locator('[data-pkg-list] .pkg-item:not([hidden])').count()
    visible_groups = page.locator('[data-year-group]:not([hidden])').count()
    assert 0 < visible_news < total_news
    assert 0 < visible_groups < total_groups

    page.locator('[data-pkg-search]').fill('zzzznomatchingnews')
    expect(page.locator('[data-pkg-empty]')).to_be_visible()

    page.locator('[data-pkg-clear]').click()
    expect(page.locator('[data-pkg-empty]')).to_be_hidden()
    expect(page.locator('[data-year-group]:not([hidden])')).to_have_count(total_groups)

    # Awards -> click View Awarded Paper
    page.goto(live_server + '/awards')
    page.locator('a', has_text='View Awarded Paper').first.click()
    expect(page).to_have_url(re.compile(r'/publications/'))
    expect(page.locator('h1')).to_be_visible()

    # Slides -> filter, clear, Paper Details link, and local slide deck opens cleanly
    page.goto(live_server + '/slides')
    total_slides = page.locator('[data-pkg-list] .pkg-item').count()
    assert total_slides > 5

    page.locator('[data-pkg-search]').fill('FinBERT')
    assert 0 < page.locator('[data-pkg-list] .pkg-item:not([hidden])').count() < total_slides
    page.locator('[data-pkg-clear]').click()
    expect(page.locator('[data-pkg-count]')).to_have_text(f'{total_slides} of {total_slides} shown')

    page.locator('.slide-card a', has_text='Paper Details').first.click()
    expect(page).to_have_url(re.compile(r'/publications/'))
    page.go_back()

    # Open a local rendered slide deck (same-origin /slides/...) in its popup tab
    local_slide = page.locator('.slide-card a[href^="/slides/"]').first
    if local_slide.count():
        with page.expect_popup() as popup_info:
            local_slide.click()
        popup = popup_info.value
        popup.wait_for_load_state('domcontentloaded')
        assert '/slides/' in popup.url
        popup.wait_for_function(
            '() => Boolean(window.Reveal && window.Reveal.isReady && window.Reveal.isReady())',
            timeout=10000,
        )
        assert popup.evaluate('() => window.Reveal.getTotalSlides()') > 0
        popup.close()


def _local_slide_hrefs():
    """Return all local /slides/<folder>/ links from data/slides/ for parametrization."""
    hrefs = []
    for item in site.load_data_from_folder('slides'):
        link = item.get('link') or ''
        if link.startswith('/slides/'):
            hrefs.append(link)
    return sorted(set(hrefs))


@pytest.mark.parametrize('href', _local_slide_hrefs())
def test_every_local_slide_deck_initializes_cleanly(desktop_context, live_server, href):
    """Every local talk slide deck must initialize Reveal.js with zero broken assets or CSP errors."""
    parsed_base = urlparse(live_server)
    deck = desktop_context.new_page()
    # Self-contained Quarto decks can be 8-12 MB of embedded base64 assets, so allow
    # extra time to compress/parse when xdist runs many Chromium workers in parallel.
    deck.set_default_timeout(30000)
    page_errors = []
    csp_errors = []
    bad_responses = []

    deck.on('pageerror', lambda err: page_errors.append(f'{href}: {err}'))

    def on_console(msg):
        if msg.type == 'error' and 'Content Security Policy' in msg.text:
            csp_errors.append(f'{href}: {msg.text}')

    def on_response(resp):
        parsed = urlparse(resp.url)
        if parsed.netloc == parsed_base.netloc and resp.status >= 400 and parsed.path != '/favicon.ico':
            bad_responses.append(f'{href}: {resp.status} {parsed.path}')

    deck.on('console', on_console)
    deck.on('response', on_response)

    try:
        resp = deck.goto(live_server + href, wait_until='domcontentloaded', timeout=30000)
        assert resp.status == 200, f'{href} returned {resp.status}'
        deck.wait_for_function(
            '() => Boolean(window.Reveal && window.Reveal.isReady && window.Reveal.isReady())',
            timeout=30000,
        )
        assert deck.evaluate('() => window.Reveal.getTotalSlides()') > 0, f'{href} has 0 slides'
    finally:
        deck.close()

    assert not page_errors, f'Uncaught JS errors in {href}: {page_errors}'
    assert not csp_errors, f'CSP violations in {href}: {csp_errors}'
    assert not bad_responses, f'Broken local assets in {href}: {bad_responses}'


# ---------------------------------------------------------------------------
# 10. Search, type filter toolbar, keyboard shortcuts (Ctrl+K, /), and 404
# ---------------------------------------------------------------------------

def test_search_type_filters_shortcuts_and_404(page, live_server):
    page.goto(live_server + '/')

    # Ctrl+K navigates to /search
    page.keyboard.press('Control+k')
    expect(page).to_have_url(live_server + '/search')

    # Submit a search query using real typing and button click
    page.locator('#site-search').fill('Brazil')
    page.locator('form.search-form button[type="submit"]').click()
    expect(page).to_have_url(live_server + '/search?q=Brazil')
    expect(page.locator('[data-search-summary]')).to_be_visible()
    expect(page.locator('.search-result mark').first).to_be_visible()

    # Click type filter toolbar buttons
    toolbar = page.locator('[data-search-type-filters]')
    expect(toolbar).to_be_visible()
    total_results = page.locator('[data-search-results] [data-result-type]').count()
    assert total_results > 3

    pub_filter = toolbar.locator('button[data-filter-type="Publication"]')
    pub_filter.click()
    expect(pub_filter).to_have_attribute('aria-pressed', 'true')
    expect(pub_filter).to_have_class('type-filter-btn is-active')
    visible_types = page.locator('[data-search-results] [data-result-type]:not([hidden])').evaluate_all(
        'els => els.map(el => el.getAttribute("data-result-type"))'
    )
    assert visible_types and all(t == 'Publication' for t in visible_types)

    # Click All to restore
    all_filter = toolbar.locator('button[data-filter-type="all"]')
    all_filter.click()
    expect(page.locator('[data-search-results] [data-result-type]:not([hidden])')).to_have_count(total_results)

    # Click a search result card -> navigates cleanly
    first_internal_result = page.locator('[data-search-results] a.search-result[href^="/"]').first
    first_internal_result.click()
    expect(page.locator('h1')).to_be_visible()

    # '/' shortcut focuses the page filter on /publications
    page.goto(live_server + '/publications')
    page.locator('h1').click()
    page.keyboard.press('/')
    expect(page.locator('[data-pub-search]')).to_be_focused()

    # 404 page search form & browse links
    not_found_path = '/this-page-definitely-does-not-exist'
    page._allowed_error_paths.add(not_found_path)
    resp = page.goto(live_server + not_found_path)
    assert resp.status == 404
    expect(page.locator('h1')).to_have_text('Page not found')

    page.locator('#not-found-search').fill('liquidity')
    page.locator('form.search-form button[type="submit"]').click()
    expect(page).to_have_url(live_server + '/search?q=liquidity')
    assert page.locator('[data-search-results] .search-result').count() >= 1


# ---------------------------------------------------------------------------
# 11. CV print button, Press Kit bio copy + zip download, Consulting, Site Log
# ---------------------------------------------------------------------------

def test_cv_press_consulting_and_site_log(page, live_server):
    # CV page print button
    page.goto(live_server + '/cv')
    page.evaluate('() => { window.__printCalls = 0; window.print = () => { window.__printCalls += 1; }; }')
    page.locator('[data-print]').click()
    assert page.evaluate('() => window.__printCalls') == 1

    # Press Kit: click all 4 bio copy buttons & download press kit .zip
    page.goto(live_server + '/press')
    bio_buttons = page.locator('button[data-copy-text]')
    assert bio_buttons.count() == 4
    for i in range(4):
        btn = bio_buttons.nth(i)
        expected = btn.get_attribute('data-copy-text')
        btn.click()
        expect(btn).to_have_class('install-btn is-copied')
        assert _read_clipboard(page) == expected

    with page.expect_download() as dl_zip:
        page.locator('a', has_text='Download press kit (.zip)').click()
    zip_path = dl_zip.value.path()
    assert dl_zip.value.suggested_filename.endswith('.zip')
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        assert 'bio-en.txt' in names and 'bio-pt.txt' in names and 'publications.bib' in names

    # Consulting & Site Log
    page.goto(live_server + '/consulting')
    expect(page.locator('.service-card').first).to_be_visible()

    page.goto(live_server + '/site-log')
    expect(page.locator('h1')).to_have_text('Site Log')
    expect(page.locator('.action-list li').first).to_be_visible()
    expect(page.locator('.commit-list li').first).to_be_visible()


# ---------------------------------------------------------------------------
# 12. Full site internal link crawl (zero broken pages, zero JS/asset errors)
# ---------------------------------------------------------------------------

def _all_detail_paths():
    """Return every publication, book, package, and dataset detail URL."""
    paths = [f"/publications/{pub['slug']}" for pub in site.get_publications()]
    with site.app.test_request_context('/'):
        paths.extend(f"/book/{book['slug']}" for book in site.get_books())
        paths.extend(f"/data/{ds['slug']}" for ds in site.get_datasets())
    for ecosystem in ('r', 'python'):
        paths.extend(f"/code/{ecosystem}/{pkg['slug']}" for pkg in site.get_packages(ecosystem))
    return sorted(set(paths))


_DETAIL_PATHS = _all_detail_paths()


def test_all_primary_pages_and_internal_links_load_cleanly(page, live_server):
    """Visit every top-level section and verify all internal page links resolve."""
    seed_paths = [
        '/', '/publications', '/books', '/news', '/awards', '/slides',
        '/research', '/code/r', '/code/python', '/mcp', '/data',
        '/consulting', '/site-log', '/cv', '/press', '/search',
    ]
    skip_suffixes = ('.bib', '.ris', '.md', '.zip', '.pdf', '.xml', '.json', '.txt')
    known = set(seed_paths) | set(_DETAIL_PATHS)
    extra = []

    for path in seed_paths:
        resp = page.goto(live_server + path, wait_until='domcontentloaded')
        assert resp.status == 200, f'{path} returned {resp.status}'
        expect(page.locator('h1')).to_be_visible()

        hrefs = page.locator('main a[href^="/"]').evaluate_all(
            'els => els.map(el => el.getAttribute("href"))'
        )
        for href in hrefs:
            clean = href.split('#', 1)[0].split('?', 1)[0]
            if not clean or clean in known or clean.endswith(skip_suffixes):
                continue
            if clean.startswith(('/books/', '/slides/', '/static/', '/news/pdfs/')):
                continue
            known.add(clean)
            extra.append(clean)

    for path in extra:
        resp = page.goto(live_server + path, wait_until='domcontentloaded')
        assert resp.status == 200, f'{path} returned {resp.status}'
        expect(page.locator('h1')).to_be_visible()


@pytest.mark.parametrize('shard', range(4), ids=[f'shard-{i}' for i in range(4)])
def test_all_detail_pages_load_cleanly(page, live_server, shard):
    """Visit every publication, book, package, and dataset detail page (sharded for parallel runs)."""
    chunk = _DETAIL_PATHS[shard::4]
    assert chunk
    for path in chunk:
        resp = page.goto(live_server + path, wait_until='domcontentloaded')
        assert resp.status == 200, f'{path} returned {resp.status}'
        expect(page.locator('h1')).to_be_visible()


# ---------------------------------------------------------------------------
# 13. No-JS progressive enhancement (content, dropdowns & search work without JS)
# ---------------------------------------------------------------------------

def test_no_js_progressive_enhancement(browser, live_server):
    context = _new_context(
        browser, live_server,
        viewport={'width': 1280, 'height': 850},
        java_script_enabled=False,
    )
    pg = context.new_page()
    pg.set_default_timeout(10000)
    try:
        # Home, publications, code, news, slides, MCP, CV, Press must show all content without JS
        pages_to_check = [
            ('/', 'Welcome'),
            ('/publications', 'Publications'),
            ('/books', 'Books'),
            ('/code/r', 'Code (R)'),
            ('/code/python', 'Code (Python)'),
            ('/mcp', 'Brazilian Financial Data MCP Servers'),
            ('/data', 'Data'),
            ('/news', 'Interviews, lectures and News'),
            ('/slides', 'Slides'),
            ('/cv', 'Marcelo'),
            ('/press', 'Press Kit'),
        ]
        for path, expected_h1 in pages_to_check:
            resp = pg.goto(live_server + path, wait_until='domcontentloaded')
            assert resp.status == 200, f'No-JS {path} returned {resp.status}'
            expect(pg.locator('h1')).to_contain_text(expected_h1)
            # Confirm scripts did not run
            assert 'js' not in (pg.locator('html').get_attribute('class') or '').split()
            # No .reveal element may be stuck invisible (opacity: 0) when JS is disabled
            hidden_reveals = pg.locator('.reveal').evaluate_all(
                'els => els.filter(el => parseFloat(getComputedStyle(el).opacity) < 0.99).length'
            )
            assert hidden_reveals == 0, f'{hidden_reveals} .reveal elements stuck hidden without JS on {path}'

        # Publications list is fully visible without JS
        pg.goto(live_server + '/publications', wait_until='domcontentloaded')
        assert pg.locator('#pubList .publication-item').count() > 10
        expect(pg.locator('#pubList .publication-item').first).to_be_visible()

        # CSS-only dropdown opens on hover without JS (:root:not(.js) .dropdown:hover)
        pg.goto(live_server + '/', wait_until='domcontentloaded')
        pg.locator('header nav li.dropdown').first.hover()
        expect(pg.locator('#menu-research a', has_text='Research Articles')).to_be_visible()
        pg.locator('#menu-research a', has_text='Research Articles').click()
        expect(pg).to_have_url(live_server + '/publications')

        # Server-side /search form works end-to-end without JS
        pg.goto(live_server + '/search', wait_until='domcontentloaded')
        pg.locator('#site-search').fill('liquidity')
        pg.locator('form.search-form button[type="submit"]').click()
        expect(pg).to_have_url(live_server + '/search?q=liquidity')
        expect(pg.locator('.search-result').first).to_be_visible()
    finally:
        context.close()


# ---------------------------------------------------------------------------
# 14. Mobile & tablet horizontal-overflow checks across all site layouts
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('viewport_name,viewport', [
    ('mobile', {'width': 390, 'height': 844}),
    ('tablet', {'width': 768, 'height': 1024}),
])
def test_responsive_no_horizontal_overflow(browser, live_server, viewport_name, viewport):
    context = _new_context(browser, live_server, viewport=viewport)
    pg = context.new_page()
    page_errors, console_errors, bad_responses = _attach_monitors(pg, live_server)
    paths = [
        '/',
        '/publications',
        '/publications/2019-rbfin-accessing-financial-repor',
        '/books',
        '/book/2019-pirf',
        '/code/r',
        '/code/r/getdfpdata2',
        '/code/python',
        '/code/python/cvm-mcp',
        '/mcp',
        '/data',
        '/data/getdfpdata2',
        '/research',
        '/news',
        '/awards',
        '/slides',
        '/consulting',
        '/cv',
        '/press',
        '/search?q=Brazil',
        '/site-log',
    ]
    overflows = []
    try:
        for path in paths:
            resp = pg.goto(live_server + path, wait_until='domcontentloaded')
            assert resp.status == 200, f'{viewport_name} {path} -> {resp.status}'
            metrics = pg.evaluate(
                """() => ({
                    scrollWidth: document.documentElement.scrollWidth,
                    clientWidth: document.documentElement.clientWidth,
                })"""
            )
            if metrics['scrollWidth'] > metrics['clientWidth'] + 1:
                overflows.append(
                    f"{path}: scrollWidth={metrics['scrollWidth']} > clientWidth={metrics['clientWidth']}"
                )
    finally:
        context.close()

    assert not page_errors, f'{viewport_name} page errors: {page_errors}'
    assert not console_errors, f'{viewport_name} console errors: {console_errors}'
    assert not bad_responses, f'{viewport_name} bad HTTP responses: {bad_responses}'
    assert not overflows, f'Horizontal overflow on {viewport_name} ({viewport["width"]}px): {overflows}'
