"""Smoke tests for every public route plus the SEO/citation features."""

import datetime
import json
import os
import xml.etree.ElementTree as ET

import pytest

import app as site


@pytest.fixture(scope='session')
def client():
    site.app.config.update(TESTING=True)
    # Never hit GitHub from the test suite.
    site.get_recent_commits = lambda limit=3: []
    site.get_recent_actions = lambda limit=15: []
    return site.app.test_client()


def html(response):
    return response.data.decode('utf-8')


def test_all_static_routes_render(client):
    skip = {'static', 'sitemap', 'robots', 'indexnow_key', 'news_feed',
            'publications_feed', 'site_log'}
    checked = 0
    for rule in site.app.url_map.iter_rules():
        if 'GET' not in rule.methods or rule.arguments or rule.endpoint in skip:
            continue
        response = client.get(rule.rule)
        assert response.status_code == 200, f'{rule.rule} -> {response.status_code}'
        assert '<h1' in html(response), f'{rule.rule} has no h1'
        checked += 1
    assert checked >= 8


def test_site_log_renders(client):
    assert client.get('/site-log').status_code == 200


def test_every_publication_has_a_detail_page(client):
    publications = site.get_publications()
    assert publications
    slugs = [pub['slug'] for pub in publications]
    assert len(slugs) == len(set(slugs)), 'duplicate publication slugs'

    for publication in publications:
        response = client.get(f"/publications/{publication['slug']}")
        assert response.status_code == 200
        page = html(response)
        assert 'name="citation_title"' in page
        assert 'application/ld+json' in page
        assert 'rel="canonical"' in page


def test_publication_bibtex_download(client):
    publication = site.get_publications()[0]
    response = client.get(f"/publications/{publication['slug']}.bib")
    assert response.status_code == 200
    assert response.headers['Content-Type'].startswith('text/plain')
    assert 'attachment' in response.headers['Content-Disposition']
    body = response.data.decode('utf-8')
    assert body.startswith('@article{')
    assert publication['title'].replace('{', '(') .replace('}', ')') in body


def test_unknown_publication_returns_404(client):
    assert client.get('/publications/does-not-exist').status_code == 404
    assert client.get('/publications/does-not-exist.bib').status_code == 404


def test_news_feed_is_valid_rss(client):
    response = client.get('/feed.xml')
    assert response.status_code == 200
    assert response.headers['Content-Type'].startswith('application/rss+xml')
    assert 'max-age=600' in response.headers['Cache-Control']
    root = ET.fromstring(response.data)
    assert root.tag == 'rss'
    items = root.findall('./channel/item')
    assert items
    assert items[0].findtext('title')


def test_publications_feed_is_valid_rss(client):
    response = client.get('/publications/feed.xml')
    root = ET.fromstring(response.data)
    items = root.findall('./channel/item')
    assert len(items) == len(site.get_publications())
    assert all(item.findtext('link').startswith('http') for item in items)


def test_search_finds_publications_books_and_news(client):
    for query, expected_type in (('liquidity', 'Publication'),
                                 ('Amazon', 'Book'),
                                 ('Perlin', 'News')):
        response = client.get('/search', query_string={'q': query})
        assert response.status_code == 200
        page = html(response)
        assert expected_type in page
        assert 'No results' not in page


def test_search_without_query_shows_form(client):
    response = client.get('/search')
    assert response.status_code == 200
    assert 'name="q"' in html(response)


def test_sitemap_has_lastmod_and_detail_pages(client):
    response = client.get('/sitemap.xml')
    assert response.status_code == 200
    root = ET.fromstring(response.data)
    namespace = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    urls = root.findall('sm:url', namespace)
    assert len(urls) > 20
    assert all(url.find('sm:lastmod', namespace) is not None for url in urls)

    locs = [url.findtext('sm:loc', namespaces=namespace) for url in urls]
    publication = site.get_publications()[0]
    assert any(loc.endswith(f"/publications/{publication['slug']}") for loc in locs)


def test_html_security_headers(client):
    response = client.get('/')
    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert response.headers['Referrer-Policy'] == 'strict-origin-when-cross-origin'
    csp = response.headers['Content-Security-Policy']
    assert "default-src 'self'" in csp
    assert 'frame-ancestors' in csp
    # No third-party script/style origins should be needed any more.
    assert 'fonts.googleapis.com' not in csp
    assert 'cdn.jsdelivr.net' not in csp
    # The inline theme script must carry the per-request nonce.
    nonce = csp.split("'nonce-", 1)[1].split("'", 1)[0]
    assert f'nonce="{nonce}"' in html(response)
    assert response.headers['Cache-Control'] == 'no-cache'


def test_static_assets_are_cacheable(client):
    response = client.get('/static/css/style.css')
    assert response.status_code == 200
    assert 'max-age=31536000' in response.headers['Cache-Control']


def test_html_is_compressed(client):
    response = client.get('/publications', headers={'Accept-Encoding': 'gzip'})
    assert response.headers.get('Content-Encoding') == 'gzip'
    assert len(response.data) < 60000


def test_templates_do_not_load_third_party_assets():
    templates = os.path.join(os.path.dirname(site.__file__), 'templates')
    for name in os.listdir(templates):
        if not name.endswith('.html'):
            continue
        with open(os.path.join(templates, name), encoding='utf-8') as handle:
            source = handle.read()
        assert 'fonts.googleapis.com' not in source, name
        assert 'cdn.jsdelivr.net' not in source, name


def test_cv_page(client):
    page = html(client.get('/cv'))
    assert 'Print / Save as PDF' in page
    assert 'Publications' in page
    assert 'Awards and Honors' in page


def test_publication_detail_shows_the_full_abstract(client):
    publication = site.get_publications()[0]
    page = html(client.get(f"/publications/{publication['slug']}"))
    assert publication['abstract'] in page


def test_download_trend_chart_needs_two_months():
    one_month = [{'name': 'pkg', 'history': [{'date': '2026-01', 'downloads_last_month': 10}]}]
    assert site.download_trend_chart(one_month, 'name') is None

    two_months = [{
        'name': 'pkg',
        'number_of_downloads': 12,
        'history': [
            {'date': '2026-01', 'downloads_last_month': 10},
            {'date': '2026-02', 'downloads_last_month': 12},
        ],
    }]
    chart = json.loads(site.download_trend_chart(two_months, 'name'))
    assert chart['type'] == 'line'
    assert chart['data']['labels'] == ['Jan 2026', 'Feb 2026']
    assert chart['data']['datasets'][0]['data'] == [10, 12]


def test_json_ld_blocks_are_valid_json(client):
    import re

    paths = ['/', '/books', '/publications', '/cv',
             f"/publications/{site.get_publications()[0]['slug']}"]
    found = 0
    for path in paths:
        page = html(client.get(path))
        for block in re.findall(
                r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', page, re.S):
            json.loads(block)
            found += 1
    assert found >= 3


def test_trend_chart_card_renders_with_history(client, monkeypatch):
    original = site.load_data_from_folder

    def fake_loader(folder):
        if folder == 'code/r':
            return [{
                'title': 'fakepkg',
                'description': 'test',
                'number_of_downloads': 12,
                'total_downloads': 100,
                'history': [
                    {'date': '2026-01', 'downloads_last_month': 10},
                    {'date': '2026-02', 'downloads_last_month': 12},
                ],
            }]
        return original(folder)

    monkeypatch.setattr(site, 'load_data_from_folder', fake_loader)
    page = html(client.get('/code/r'))
    assert 'rTrendChart' in page
    assert 'Jan 2026' in page


@pytest.mark.parametrize('path', [
    '/books/../app.py',
    '/books/../requirements.txt',
    '/books/../.git/config',
    '/books/../data/about.json',
    '/slides/../about.json',
    '/slides/../stats/gscholar.json',
])
def test_directory_traversal_is_blocked(client, path):
    assert client.get(path).status_code == 404


def test_code_pages_show_when_stats_were_updated(client):
    assert 'Package statistics updated at' in html(client.get('/code/r'))
    assert 'Download statistics updated at' in html(client.get('/code/python'))


def test_https_proxy_headers_are_honoured(client):
    headers = {'X-Forwarded-Proto': 'https'}
    sitemap = html(client.get('/sitemap.xml', headers=headers))
    assert '<loc>http://' not in sitemap
    assert '<loc>https://' in sitemap

    home = client.get('/', headers=headers)
    assert home.headers.get('Strict-Transport-Security')
    assert 'href="https://' in html(home)


def test_news_feed_uses_rss_categories(client):
    body = client.get('/feed.xml').data.decode('utf-8')
    assert '<category>' in body
    assert '<source>' not in body


def test_publications_have_unique_abstracts():
    """Guards against copy-paste mistakes between JSON files."""
    seen = {}
    for publication in site.get_publications():
        abstract = (publication.get('abstract') or '').strip()
        if len(abstract) < 80:
            continue
        assert abstract not in seen, (
            f"{publication['filename_stem']} reuses the abstract of {seen[abstract]}")
        seen[abstract] = publication['filename_stem']


def test_download_history_is_well_formed():
    for folder in ('data/code/r', 'data/code/python'):
        path = os.path.join(os.path.dirname(site.__file__), folder)
        for name in os.listdir(path):
            if not name.endswith('.json'):
                continue
            with open(os.path.join(path, name), encoding='utf-8') as handle:
                package = json.load(handle)
            history = package.get('history') or []
            dates = [entry.get('date') for entry in history]
            assert dates == sorted(dates), name
            assert len(dates) == len(set(dates)), name
            for entry in history:
                datetime.date.fromisoformat(entry['date'] + '-01')
