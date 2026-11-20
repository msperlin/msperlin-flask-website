"""Data integrity, referential integrity, asset existence, and schema tests.

Fast unit/integration checks against `data/`, `static/img/`, `books_rendered/`,
and `data/slides/` that catch broken cross-links, missing WebP derivatives,
dangling PDFs, or schema drift before deployment.
"""

import datetime
import glob
import json
import os
from urllib.parse import unquote

import pytest

import app as site

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope='module')
def client():
    site.app.config.update(TESTING=True)
    return site.app.test_client()


def _read_json(rel_path: str):
    with open(os.path.join(REPO_ROOT, rel_path), encoding='utf-8') as handle:
        return json.load(handle)


# ---------------------------------------------------------------------------
# 7. Referential integrity across data/*.json
# ---------------------------------------------------------------------------

def test_news_publication_slugs_exist():
    pub_slugs = {pub['slug'] for pub in site.get_publications()}
    for path in sorted(glob.glob(os.path.join(REPO_ROOT, 'data/news/*.json'))):
        item = _read_json(os.path.relpath(path, REPO_ROOT))
        for slug in item.get('publication_slugs') or []:
            assert slug in pub_slugs, (
                f"{os.path.basename(path)} references unknown publication slug '{slug}'"
            )


def test_package_counterparts_and_mcp_keys_exist():
    mcp_data = _read_json('data/mcp.json')
    mcp_server_slugs = {s['slug'] for s in mcp_data.get('servers', [])}
    mcp_keys_in_clients = set()
    for client_cfg in mcp_data.get('clients', []):
        snippet = client_cfg.get('snippet') or ''
        for key in ('bcb', 'cvm', 'tesourodireto'):
            if key in snippet:
                mcp_keys_in_clients.add(key)

    for ecosystem in ('r', 'python'):
        for pkg in site.get_packages(ecosystem):
            for other in pkg.get('counterparts') or []:
                other_eco = other.get('ecosystem')
                other_slug = other.get('slug')
                assert site.get_package(other_eco, other_slug) is not None, (
                    f"{ecosystem}/{pkg['slug']} references missing counterpart "
                    f"{other_eco}/{other_slug}"
                )
            mcp_key = pkg.get('mcp_server_key')
            if mcp_key:
                assert pkg['slug'] in mcp_server_slugs, (
                    f"python/{pkg['slug']} sets mcp_server_key='{mcp_key}' but is missing from data/mcp.json"
                )
                assert mcp_key in mcp_keys_in_clients, (
                    f"python/{pkg['slug']} mcp_server_key='{mcp_key}' not found in data/mcp.json client snippets"
                )


def test_mcp_hub_references_exist():
    mcp_data = _read_json('data/mcp.json')
    with site.app.test_request_context('/'):
        dataset_slugs = {ds['slug'] for ds in site.get_datasets()}

    for srv in mcp_data.get('servers', []):
        slug = srv['slug']
        assert site.get_package('python', slug) is not None, (
            f"data/mcp.json server '{slug}' does not match any Python package"
        )
        for r_slug in srv.get('r_counterparts') or []:
            assert site.get_package('r', r_slug) is not None, (
                f"data/mcp.json server '{slug}' references missing R package '{r_slug}'"
            )
        for ds_slug in srv.get('datasets') or []:
            assert ds_slug in dataset_slugs, (
                f"data/mcp.json server '{slug}' references missing dataset '{ds_slug}'"
            )

    for tool in mcp_data.get('ai_tools', []):
        assert site.get_package(tool['ecosystem'], tool['slug']) is not None, (
            f"data/mcp.json ai_tool {tool['ecosystem']}/{tool['slug']} does not exist"
        )


def test_research_theme_packages_exist():
    research = _read_json('data/research.json')
    all_pkg_names = {pkg['display_name'] for pkg in site.get_packages()}
    for theme in research.get('themes', []):
        for pkg_name in theme.get('packages') or []:
            assert pkg_name in all_pkg_names, (
                f"data/research.json theme '{theme['title']}' references unknown package '{pkg_name}'"
            )


# ---------------------------------------------------------------------------
# 8. Asset & file existence checks (images, WebP derivatives, PDFs, books, slides)
# ---------------------------------------------------------------------------

def test_all_referenced_images_and_webp_derivatives_exist():
    image_refs = []

    for path in sorted(glob.glob(os.path.join(REPO_ROOT, 'data/publications/*.json'))):
        item = _read_json(os.path.relpath(path, REPO_ROOT))
        if item.get('image'):
            image_refs.append((os.path.basename(path), item['image'], True))

    for path in sorted(glob.glob(os.path.join(REPO_ROOT, 'data/books/*.json'))):
        item = _read_json(os.path.relpath(path, REPO_ROOT))
        if item.get('cover_image'):
            image_refs.append((os.path.basename(path), item['cover_image'], True))

    press = _read_json('data/press.json')
    for shot in press.get('headshots', []):
        image_refs.append(('press.json', shot['path'], True))

    with site.app.test_request_context('/'):
        for source, img_path, require_opt in image_refs:
            rel = img_path.lstrip('/')
            full_path = os.path.join(REPO_ROOT, rel)
            assert os.path.isfile(full_path), f'{source} references missing image: {img_path}'
            if require_opt:
                opt = site.opt_url(img_path)
                opt_rel = unquote(opt.lstrip('/').split('?', 1)[0])
                assert '/opt/' in opt_rel and os.path.isfile(os.path.join(REPO_ROOT, opt_rel)), (
                    f'{source} image {img_path} is missing WebP derivative in static/img/opt/ '
                    f'(run `uv run python scripts/optimize_images.py`)'
                )


def test_news_pdfs_exist_and_serve_200(client):
    checked = 0
    for path in sorted(glob.glob(os.path.join(REPO_ROOT, 'data/news/*.json'))):
        item = _read_json(os.path.relpath(path, REPO_ROOT))
        pdf = item.get('pdf')
        if not pdf:
            continue
        full_path = os.path.join(REPO_ROOT, pdf.lstrip('/'))
        assert os.path.isfile(full_path), f'{os.path.basename(path)} references missing PDF: {pdf}'
        resp = client.get(f'/news/pdfs/{os.path.basename(pdf)}')
        assert resp.status_code == 200, f'/news/pdfs/{os.path.basename(pdf)} -> {resp.status_code}'
        assert 'pdf' in resp.headers.get('Content-Type', '').lower()
        checked += 1
    assert checked >= 5


def test_books_online_links_exist_and_serve_200(client):
    checked = 0
    for path in sorted(glob.glob(os.path.join(REPO_ROOT, 'data/books/*.json'))):
        book = _read_json(os.path.relpath(path, REPO_ROOT))
        online = book.get('link_online') or ''
        if not online.startswith('/books/'):
            continue
        folder = online.strip('/').split('/')[1]
        book_dir = os.path.join(REPO_ROOT, 'books_rendered', folder)
        assert os.path.isdir(book_dir), f'{os.path.basename(path)} missing books_rendered/{folder}'
        resp = client.get(online)
        assert resp.status_code == 200, f'{online} -> {resp.status_code}'
        checked += 1
    assert checked >= 5


def test_slides_local_links_and_pdfs_exist_and_serve_200(client):
    slides_data = site.load_data_from_folder('slides')
    assert slides_data
    for slide in slides_data:
        folder = slide.get('folder')
        if folder:
            slide_dir = os.path.join(REPO_ROOT, 'data', 'slides', folder)
            assert os.path.isdir(slide_dir), f"Slide folder missing: data/slides/{folder}"
        link = slide.get('link') or ''
        if link.startswith('/slides/'):
            resp = client.get(link)
            assert resp.status_code == 200, f'{link} -> {resp.status_code}'
        pdf_link = slide.get('pdf_link') or ''
        if pdf_link.startswith('/slides/'):
            resp = client.get(pdf_link)
            assert resp.status_code == 200, f'{pdf_link} -> {resp.status_code}'


# ---------------------------------------------------------------------------
# 9. JSON schema & slug uniqueness invariants
# ---------------------------------------------------------------------------

def test_publications_schema_invariants():
    pubs = site.get_publications()
    assert pubs
    slugs = []
    for pub in pubs:
        stem = pub['filename_stem']
        assert isinstance(pub.get('title'), str) and pub['title'].strip(), f'{stem}: missing title'
        year = pub.get('year')
        assert isinstance(year, str) and len(year) == 4 and year.isdigit(), (
            f'{stem}: publication year must be a 4-digit string, got {year!r}'
        )
        slugs.append(pub['slug'])
    assert len(slugs) == len(set(slugs)), 'Duplicate publication slugs found'


def test_books_schema_invariants():
    with site.app.test_request_context('/'):
        books = site.get_books()
    assert books
    slugs = []
    for book in books:
        stem = book['filename_stem']
        assert isinstance(book.get('title'), str) and book['title'].strip(), f'{stem}: missing title'
        year = book.get('year')
        assert isinstance(year, int) and 1990 <= year <= 2100, (
            f'{stem}: book year must be an int, got {year!r}'
        )
        slugs.append(book['slug'])
    assert len(slugs) == len(set(slugs)), 'Duplicate book slugs found'


def test_news_schema_invariants():
    news_items = site.load_data_from_folder('news')
    assert news_items
    for item in news_items:
        stem = item['filename_stem']
        assert isinstance(item.get('title'), str) and item['title'].strip(), f'{stem}: missing title'
        assert isinstance(item.get('source'), str) and item['source'].strip(), f'{stem}: missing source'
        assert isinstance(item.get('link'), str) and item['link'].strip(), f'{stem}: missing link'
        date_str = item.get('date')
        assert isinstance(date_str, str), f'{stem}: missing date'
        datetime.date.fromisoformat(date_str)


def test_awards_datasets_and_packages_schema_invariants():
    # Awards
    awards = site.load_data_from_folder('awards')
    assert awards
    for award in awards:
        stem = award['filename_stem']
        assert isinstance(award.get('title'), str) and award['title'].strip(), f'{stem}: missing title'
        assert isinstance(award.get('organization'), str) and award['organization'].strip(), f'{stem}: missing org'
        year = str(award.get('year', ''))
        assert len(year) == 4 and year.isdigit(), f'{stem}: invalid award year {award.get("year")!r}'

    # Datasets
    with site.app.test_request_context('/'):
        datasets = site.get_datasets()
    assert datasets
    ds_slugs = []
    for ds in datasets:
        stem = ds['filename_stem']
        assert isinstance(ds.get('name'), str) and ds['name'].strip(), f'{stem}: missing name'
        assert isinstance(ds.get('description'), str) and ds['description'].strip(), f'{stem}: missing description'
        assert isinstance(ds.get('link'), str) and ds['link'].strip(), f'{stem}: missing link'
        ds_slugs.append(ds['slug'])
    assert len(ds_slugs) == len(set(ds_slugs)), 'Duplicate dataset slugs found'

    # Packages (R & Python)
    for ecosystem in ('r', 'python'):
        pkgs = site.get_packages(ecosystem)
        assert pkgs
        pkg_slugs = []
        for pkg in pkgs:
            stem = pkg['filename_stem']
            assert isinstance(pkg.get('display_name'), str) and pkg['display_name'].strip(), (
                f'{ecosystem}/{stem}: missing name/title'
            )
            assert isinstance(pkg.get('description'), str) and pkg['description'].strip(), (
                f'{ecosystem}/{stem}: missing description'
            )
            pkg_slugs.append(pkg['slug'])
        assert len(pkg_slugs) == len(set(pkg_slugs)), f'Duplicate {ecosystem} package slugs found'
