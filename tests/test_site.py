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
            'publications_feed', 'site_log', 'json_feed', 'opensearch',
            'llms_txt', 'llms_full_txt', 'security_txt', 'healthz', 'press_kit',
            'publications_json', 'code_json', 'data_json', 'books_json'}
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


def test_static_slide_and_book_csp_allows_inline_scripts(client):
    slide_resp = client.get('/slides/20260826_cafe-com-pesquisa/')
    assert slide_resp.status_code == 200
    slide_csp = slide_resp.headers['Content-Security-Policy']
    assert "'unsafe-inline'" in slide_csp
    assert "object-src 'none'" in slide_csp
    assert "frame-ancestors 'none'" in slide_csp

    book_resp = client.get('/books/adfeR/')
    assert book_resp.status_code == 200
    book_csp = book_resp.headers['Content-Security-Policy']
    assert "'unsafe-inline'" in book_csp
    assert "object-src 'none'" in book_csp
    assert "frame-ancestors 'none'" in book_csp


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
            assert dates == list(dict.fromkeys(dates)), name
            for entry in history:
                datetime.date.fromisoformat(entry['date'] + '-01')


def test_home_page_shows_impact_and_recent_work(client):
    page = html(client.get('/'))
    assert 'Academic Impact at a Glance' in page
    assert 'Recent Publications' in page
    assert 'Recent Talks &amp; Slides' in page
    assert 'market microstructure' in page
    assert 'href="/cv">CV (html)</a>' in page
    nav_section = page.split('<nav aria-label="Primary">', 1)[1].split('</nav>', 1)[0]
    assert 'href="/site-log"' not in nav_section
    assert 'href="/site-log">Site Log</a>' in page.split('<footer>', 1)[1]


def test_all_publications_bibtex_export(client):
    response = client.get('/publications/all.bib')
    assert response.status_code == 200
    assert response.headers['Content-Type'].startswith('text/plain')
    assert 'msperlin-publications.bib' in response.headers['Content-Disposition']
    body = response.data.decode('utf-8')
    assert body.count('@article{') == len(site.get_publications())

    pubs_page = html(client.get('/publications'))
    assert 'pubYearChart' in pubs_page
    assert '/publications/all.bib' in pubs_page


def test_books_show_companion_links_and_language_badges(client):
    page = html(client.get('/books'))
    assert 'Online PDF' in page
    assert 'EPUB' in page
    assert 'Solutions' in page
    assert 'PT-BR' in page
    assert '>EN<' in page


def test_ecosystem_table_and_code_install_snippets(client):
    data_page = html(client.get('/data'))
    assert 'Brazilian Financial &amp; Public Data Ecosystem' in data_page
    assert 'cvm-mcp' in data_page
    assert 'bcb-mcp' in data_page

    r_page = html(client.get('/code/r'))
    assert "install.packages(&#39;BatchGetSymbols&#39;)" in r_page or "install.packages('BatchGetSymbols')" in r_page
    assert 'All-time downloads' in r_page

    py_page = html(client.get('/code/python'))
    assert 'MCP Server' in py_page
    assert 'pip install cvm-mcp' in py_page


def test_publication_detail_cross_links_software_and_related_papers(client):
    page = html(client.get('/publications/2019-rbfin-accessing-financial-repor'))
    assert 'Related Open-Source Software' in page
    assert 'GetDFPData2' in page
    assert 'Related Publications' in page


def test_search_renders_type_filter_buttons(client):
    page = html(client.get('/search', query_string={'q': 'R'}))
    assert 'data-search-type-filters' in page
    assert 'data-filter-type="all"' in page
    assert 'data-result-type=' in page


def test_slides_show_rich_metadata_and_paper_links(client):
    page = html(client.get('/slides'))
    assert 'An Empirical Analysis on Russell 1000 Constituent Companies' in page
    assert 'FinBERT' in page
    assert 'Paper Details' in page
    assert '/publications/2026-frl-ai-10ks' in page
    assert 'data-pkg-search' in page


def test_publication_detail_cross_links_slides_and_awards(client):
    ai_page = html(client.get('/publications/2026-frl-ai-10ks'))
    assert 'Related Talks &amp; Slides' in ai_page
    assert 'The Use of AI in 10-K Filings' in ai_page
    assert 'publications?q=Cristian' in ai_page

    pred_page = html(client.get('/publications/2018-scientometrics-is-predatory-publishing-a'))
    assert 'Awards &amp; Recognition' in pred_page
    assert 'Top 5% of Research Outputs' in pred_page

    rbfin_page = html(client.get('/publications/2013-rbfin-os-efeitos-da-introducao'))
    assert 'RBFIN Best Paper of 2013' in rbfin_page

    awards_page = html(client.get('/awards'))
    assert 'View Awarded Paper' in awards_page
    assert '/publications/2018-scientometrics-is-predatory-publishing-a' in awards_page


def test_publication_ris_export_and_sort_controls(client):
    pub = site.get_publications()[0]
    single = client.get(f"/publications/{pub['slug']}.ris")
    assert single.status_code == 200
    assert 'application/x-research-info-systems' in single.headers['Content-Type']
    body = single.data.decode('utf-8')
    assert body.startswith('TY  - JOUR\n')
    assert f"TI  - {pub['title']}" in body
    assert 'ER  - ' in body

    all_ris = client.get('/publications/all.ris')
    assert all_ris.status_code == 200
    assert all_ris.data.decode('utf-8').count('TY  - JOUR') == len(site.get_publications())
    assert client.get('/publications/does-not-exist.ris').status_code == 404

    pubs_page = html(client.get('/publications'))
    assert 'data-pub-sort' in pubs_page
    assert 'data-impact-factor=' in pubs_page


def test_search_matches_slide_descriptions(client):
    # Clear search cache in case previous tests populated it before reload
    site._SEARCH_CACHE['items'] = None
    response = client.get('/search', query_string={'q': 'Russell 1000'})
    page = html(response)
    assert 'The Use of AI in 10-K Filings' in page
    assert 'Slide' in page


def test_mcp_quickstart_and_expanded_cv(client):
    py_page = html(client.get('/code/python'))
    assert 'mcpServers' in py_page
    assert 'uvx' in py_page
    assert 'Last push:' in py_page

    r_page = html(client.get('/code/r'))
    assert 'Last push:' in r_page

    cv_page = html(client.get('/cv'))
    assert 'Invited Talks &amp; Seminars' in cv_page
    assert 'Selected Media Coverage' in cv_page


def test_navigation_structure_and_active_states(client):
    pubs_page = html(client.get('/publications'))
    assert 'id="menu-research"' in pubs_page
    assert 'aria-controls="menu-research"' in pubs_page
    assert 'id="menu-code-data"' in pubs_page
    assert 'id="menu-profile"' in pubs_page
    assert 'dropdown-submenu' not in pubs_page
    assert 'aria-haspopup' not in pubs_page
    assert 'href="/publications" aria-current="page">Research Articles</a>' in pubs_page

    with site.app.test_request_context('/'):
        book_slug = site.get_books()[0]['slug']
    book_page = html(client.get(f'/book/{book_slug}'))
    assert 'class="dropbtn active"' in book_page
    assert 'href="/books" aria-current="page">Books</a>' in book_page

    r_page = html(client.get('/code/r'))
    assert 'href="/code/r" aria-current="page">R Packages</a>' in r_page
    pkg_page = html(client.get('/code/python/cvm-mcp'))
    assert 'href="/code/python" aria-current="page">Python Packages</a>' in pkg_page

    cv_page = html(client.get('/cv'))
    assert 'href="/cv" aria-current="page">CV</a>' in cv_page
    press_page = html(client.get('/press'))
    assert 'href="/press" aria-current="page">Press Kit</a>' in press_page

    search_page = html(client.get('/search'))
    assert 'class="search-link active" href="/search" aria-current="page"' in search_page





# ---------------------------------------------------------------------------
# Press kit, feeds, security and polish
# ---------------------------------------------------------------------------

def test_press_page(client):
    page = html(client.get('/press'))
    assert 'Press Kit' in page
    assert 'ORCID' in page
    assert 'Biography' in page
    assert 'marceloperlin@gmail.com' in page
    assert 'Recent coverage' in page


def test_press_kit_zip(client):
    import zipfile
    import io as _io
    response = client.get('/press/kit.zip')
    assert response.status_code == 200
    assert response.headers['Content-Type'] == 'application/zip'
    assert 'attachment' in response.headers['Content-Disposition']
    archive = zipfile.ZipFile(_io.BytesIO(response.data))
    names = archive.namelist()
    assert 'bio-en.txt' in names
    assert 'bio-pt.txt' in names
    assert 'publications.bib' in names
    assert any(name.startswith('headshot-') for name in names)


def test_json_feed(client):
    response = client.get('/feed.json')
    assert response.status_code == 200
    assert response.headers['Content-Type'].startswith('application/feed+json')
    feed = json.loads(response.data)
    assert feed['version'].startswith('https://jsonfeed.org/version/1')
    assert feed['items']
    assert any('publication' in item.get('tags', []) for item in feed['items'])


def test_opensearch_description(client):
    response = client.get('/opensearch.xml')
    assert response.status_code == 200
    root = ET.fromstring(response.data)
    assert root.tag.endswith('OpenSearchDescription')
    assert root.find('.//{http://a9.com/-/spec/opensearch/1.1/}Url') is not None


def test_llms_txt(client):
    body = html(client.get('/llms.txt'))
    assert 'cvm-mcp' in body
    assert '/publications/' in body
    assert '# Marcelo S. Perlin' in body


def test_security_txt(client):
    response = client.get('/.well-known/security.txt')
    assert response.status_code == 200
    body = response.data.decode('utf-8')
    assert 'Contact: mailto:' in body
    assert 'Expires:' in body
    assert 'Canonical:' in body


def test_healthz(client):
    response = client.get('/healthz')
    assert response.status_code == 200
    payload = json.loads(response.data)
    assert payload['status'] == 'ok'


def test_404_page_has_search(client):
    response = client.get('/this-page-does-not-exist')
    assert response.status_code == 404
    page = html(response)
    assert 'name="q"' in page
    assert '>Publications</a>' in page


def test_search_highlights_terms(client):
    page = html(client.get('/search', query_string={'q': 'liquidity'}))
    assert '<mark>liquidity</mark>' in page


def test_highlight_escapes_html():
    result = str(site._highlight('<script>alert(1)</script>', ['script']))
    assert '<mark>' in result
    assert '<script>' not in result


def test_citation_history_chart():
    one_point = {'history': [{'date': '2026-01', 'citedby': 100}]}
    assert site._citation_history_chart(one_point) is None

    two_points = {'history': [
        {'date': '2026-01', 'citedby': 100},
        {'date': '2026-02', 'citedby': 120},
    ]}
    chart = json.loads(site._citation_history_chart(two_points))
    assert chart['type'] == 'line'
    assert chart['data']['labels'] == ['Jan 2026', 'Feb 2026']
    assert chart['data']['datasets'][0]['data'] == [100, 120]


def test_citation_chart_from_cites_per_year():
    chart = json.loads(site._citation_history_chart(
        {'cites_per_year': {'2018': 10, '2019': 25}}))
    assert chart['data']['labels'] == ['2018', '2019']
    assert chart['data']['datasets'][0]['data'] == [10, 25]


# ---------------------------------------------------------------------------
# Book/dataset detail pages, research, JSON API and citation formats
# ---------------------------------------------------------------------------

def test_book_detail_pages(client):
    with site.app.test_request_context('/'):
        books = site.get_books()
    assert books
    for book in books:
        response = client.get(f"/book/{book['slug']}")
        assert response.status_code == 200, book['slug']
        page = html(response)
        assert book['title'] in page
        assert 'Table of contents' in page
        assert 'Report an error' in page
        assert '"@type": "Book"' in page
        assert 'href="/books/' in page


def test_dataset_detail_pages(client):
    with site.app.test_request_context('/'):
        datasets = site.get_datasets()
    assert datasets
    for dataset in datasets:
        response = client.get(f"/data/{dataset['slug']}")
        assert response.status_code == 200, dataset['slug']
        page = html(response)
        assert dataset['name'] in page
        assert 'Cite this dataset' in page
        assert '@misc' in page
        assert '"@type": "Dataset"' in page


def test_research_page(client):
    response = client.get('/research')
    assert response.status_code == 200
    page = html(response)
    assert 'Market microstructure and liquidity' in page
    assert 'Selected papers' in page
    assert 'Software and data' in page
    assert 'href="/publications/' in page


def test_public_json_apis(client):
    for path, name in (('/publications.json', 'publications'), ('/code.json', 'code'),
                       ('/data.json', 'data'), ('/books.json', 'books')):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers['Content-Type'].startswith('application/json')
        payload = json.loads(response.data)
        assert payload['name'] == name
        assert payload['count'] == len(payload['items'])
        assert payload['items']
        assert all(item.get('url') for item in payload['items'])


def test_citation_formats():
    publication = site.get_publications()[0]
    strings = site.citation_strings(publication)
    assert {'bibtex', 'apa', 'abnt', 'chicago', 'doi', 'doi_url'} <= set(strings)
    assert publication['title'] in strings['apa']
    assert publication['title'] in strings['abnt']
    assert publication['title'] in strings['chicago']
    assert strings['bibtex'].startswith('@article{')


def test_publication_page_exposes_citation_formats(client):
    publication = site.get_publications()[0]
    page = html(client.get(f"/publications/{publication['slug']}"))
    assert 'id="abntOutput"' in page
    assert 'id="chicagoOutput"' in page
    assert 'data-abnt=' in page
    assert 'data-chicago=' in page


def test_publication_shows_linked_media_coverage(client):
    slug = '2018-scientometrics-is-predatory-publishing-a'
    page = html(client.get(f'/publications/{slug}'))
    assert 'Media coverage' in page
    assert 'Revista Pesquisa Fapesp' in page


def test_publication_shows_openalex_metrics(client):
    slug = '2018-scientometrics-is-predatory-publishing-a'
    publication = site.get_publication(slug)
    assert publication.get('cited_by_count_openalex')
    page = html(client.get(f'/publications/{slug}'))
    assert 'OpenAlex' in page
    assert 'openalex.org' in page


def test_sitemap_includes_new_detail_pages(client):
    body = html(client.get('/sitemap.xml'))
    with site.app.test_request_context('/'):
        book = site.get_books()[0]
        dataset = site.get_datasets()[0]
    assert f'/book/{book["slug"]}' in body
    assert f'/data/{dataset["slug"]}' in body
    assert '/research' in body


def test_new_detail_pages_have_valid_json_ld(client):
    import re
    with site.app.test_request_context('/'):
        book = site.get_books()[0]
        dataset = site.get_datasets()[0]
    for path in (f"/book/{book['slug']}", f"/data/{dataset['slug']}",
                 '/mcp', '/code/r/yfr', '/code/python/cvm-mcp'):
        page = html(client.get(path))
        blocks = re.findall(
            r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', page, re.S)
        assert blocks, path
        for block in blocks:
            json.loads(block)


# ---------------------------------------------------------------------------
# Software detail pages, MCP Hub, /llms-full.txt and Markdown mirrors
# ---------------------------------------------------------------------------

def test_every_software_package_has_a_detail_page(client):
    for ecosystem in ('r', 'python'):
        packages = site.get_packages(ecosystem)
        assert packages
        slugs = [pkg['slug'] for pkg in packages]
        assert len(slugs) == len(set(slugs)), f'duplicate {ecosystem} package slugs'
        for pkg in packages:
            response = client.get(f"/code/{ecosystem}/{pkg['slug']}")
            assert response.status_code == 200, f"{ecosystem}/{pkg['slug']}"
            page = html(response)
            assert pkg['display_name'] in page
            assert '"@type": "SoftwareSourceCode"' in page
            assert 'rel="canonical"' in page
            assert 'Cite this package' in page
            assert '@manual{' in page

    assert client.get('/code/r/does-not-exist').status_code == 404
    assert client.get('/code/rust/anything').status_code == 404


def test_package_bibtex_and_markdown_exports(client):
    bib = client.get('/code/r/getdfpdata2.bib')
    assert bib.status_code == 200
    assert bib.headers['Content-Type'].startswith('text/plain')
    assert 'attachment' in bib.headers['Content-Disposition']
    bib_text = bib.data.decode('utf-8')
    assert bib_text.startswith('@manual{')
    assert 'GetDFPData2' in bib_text

    md = client.get('/code/python/cvm-mcp.md')
    assert md.status_code == 200
    assert md.headers['Content-Type'].startswith('text/markdown')
    md_text = md.data.decode('utf-8')
    assert '# cvm-mcp' in md_text
    assert 'uvx cvm-mcp' in md_text
    assert 'mcpServers' in md_text
    assert '```bibtex' in md_text

    assert client.get('/code/r/does-not-exist.bib').status_code == 404
    assert client.get('/code/r/does-not-exist.md').status_code == 404


def test_package_detail_cross_links_and_trend_chart(client, monkeypatch):
    dfp_page = html(client.get('/code/r/getdfpdata2'))
    assert "citation(&#39;GetDFPData2&#39;)" in dfp_page or "citation('GetDFPData2')" in dfp_page
    assert 'Companion &amp; Counterpart Software' in dfp_page
    assert '/code/python/cvm-mcp' in dfp_page
    assert 'Related Datasets' in dfp_page
    assert '/data/getdfpdata2' in dfp_page
    assert 'Related Publications' in dfp_page

    cvm_page = html(client.get('/code/python/cvm-mcp'))
    assert 'MCP Client Configuration' in cvm_page
    assert 'What AI Agents Can Query' in cvm_page
    assert 'Example Prompts' in cvm_page
    assert '/code/r/getdfpdata2' in cvm_page

    original = site.load_data_from_folder

    def fake_loader(folder):
        if folder == 'code/r':
            return [{
                'filename_stem': 'fakepkg',
                'title': 'fakepkg',
                'description': 'test',
                'number_of_downloads': 15,
                'total_downloads': 120,
                'history': [
                    {'date': '2026-01', 'downloads_last_month': 10},
                    {'date': '2026-02', 'downloads_last_month': 15},
                ],
            }]
        return original(folder)

    monkeypatch.setattr(site, 'load_data_from_folder', fake_loader)
    trend_page = html(client.get('/code/r/fakepkg'))
    assert 'pkgTrendChart' in trend_page
    assert 'Jan 2026' in trend_page


def test_mcp_hub_page(client):
    response = client.get('/mcp')
    assert response.status_code == 200
    page = html(response)
    assert 'Brazilian Financial Data MCP Servers' in page
    assert 'cvm-mcp' in page
    assert 'bcb-mcp' in page
    assert 'tesourodireto-mcp' in page
    assert 'Claude Desktop' in page
    assert 'Cursor' in page
    assert 'Claude Code' in page
    assert 'Example Prompts to Try' in page
    assert '/code/python/cvm-mcp' in page
    assert '/code/r/getbcbdata' in page
    assert '/llms-full.txt' in page
    assert 'href="/mcp" aria-current="page"' in page


def test_publication_markdown_mirror(client):
    pub = site.get_publications()[0]
    response = client.get(f"/publications/{pub['slug']}.md")
    assert response.status_code == 200
    assert response.headers['Content-Type'].startswith('text/markdown')
    body = response.data.decode('utf-8')
    assert f"# {pub['title']}" in body
    assert '```bibtex' in body
    assert client.get('/publications/does-not-exist.md').status_code == 404


def test_llms_full_txt_and_sitemap_software(client):
    llms = html(client.get('/llms.txt'))
    assert '/mcp' in llms
    assert '/llms-full.txt' in llms
    assert '/code/r/yfr' in llms
    assert '/code/python/cvm-mcp' in llms

    full = client.get('/llms-full.txt')
    assert full.status_code == 200
    assert full.headers['Content-Type'].startswith('text/plain')
    full_text = full.data.decode('utf-8')
    assert 'Full Site Reference' in full_text
    assert '## Brazilian Financial Data MCP Servers' in full_text
    assert '## Peer-Reviewed Publications' in full_text
    assert 'cvm-mcp' in full_text
    assert 'GetDFPData2' in full_text

    sitemap_body = html(client.get('/sitemap.xml'))
    assert '/mcp' in sitemap_body
    assert '/code/r/yfr' in sitemap_body
    assert '/code/python/cvm-mcp' in sitemap_body
