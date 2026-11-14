#!/usr/bin/env python
"""Sync publications with ORCID and enrich metadata from Crossref.

* Matches data/publications/*.json to ORCID works by normalized title or DOI.
* Fills missing bibliographic fields for matched works using Crossref.
* Creates new JSON entries for journal articles that have a DOI and are not on
  the site yet.
* Writes preprints / software / DOI-less works to data/publications-review/ for
  manual approval (never published automatically).

Run manually, or via .github/workflows/update_publications.yml (monthly).
"""

import glob
import json
import os
import re
import sys
import unicodedata
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLICATIONS_DIR = os.path.join(ROOT, 'data', 'publications')
REVIEW_DIR = os.path.join(ROOT, 'data', 'publications-review')
ABOUT_FILE = os.path.join(ROOT, 'data', 'about.json')

EMAIL = 'marceloperlin@gmail.com'

# DOI prefixes that are preprints/software archives, never auto-published.
REVIEW_DOI_PREFIXES = ('10.2139/', '10.59350/', '10.31219/', '10.31234/', '10.20944/')


def norm(value):
    """Normalized title for fuzzy matching (lowercase, ascii, no punctuation)."""
    value = unicodedata.normalize('NFKD', value or '').encode('ascii', 'ignore').decode()
    value = value.replace('&amp;', '&')
    return re.sub(r'[^a-z0-9]+', '', value.lower())


def slugify(value):
    value = unicodedata.normalize('NFKD', value or '').encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')[:60]


def doi_from_link(link):
    if not link:
        return ''
    match = re.search(r'10\.\d{4,9}/[^\s\'"<>]+', link)
    return match.group(0).rstrip('.').rstrip(')') if match else ''


def bare_doi(value):
    value = (value or '').strip()
    value = re.sub(r'^https?://(dx\.)?doi\.org/', '', value)
    return value.rstrip('.').rstrip(')')


def get_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': f'msperlin-site/1.0 (mailto:{EMAIL})'})
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.loads(response.read().decode('utf-8'))


def fetch_orcid_works(orcid):
    url = f'https://pub.orcid.org/v3.0/{orcid}/works'
    req = urllib.request.Request(url, headers={
        'Accept': 'application/json',
        'User-Agent': f'msperlin-site/1.0 (mailto:{EMAIL})',
    })
    with urllib.request.urlopen(req, timeout=25) as response:
        data = json.loads(response.read().decode('utf-8'))
    return data.get('group', [])


def work_title(work):
    return work.get('title', {}).get('title', {}).get('value', '')


def work_doi(work):
    for ext in (work.get('external-ids') or {}).get('external-id', []):
        if ext.get('external-id-type') == 'doi':
            return bare_doi(ext.get('external-id-value'))
    return ''


def work_type(work):
    return (work.get('type') or '').strip().lower()


def work_year(work):
    date = work.get('publication-date') or {}
    year = date.get('year') or {}
    if isinstance(year, dict):
        return str(year.get('value') or '')
    return str(year or '')


def fetch_crossref(doi):
    url = 'https://api.crossref.org/works/' + urllib.parse.quote(doi)
    try:
        return (get_json(url) or {}).get('message') or {}
    except Exception as exc:  # noqa: BLE001
        print(f'    Crossref lookup failed for {doi}: {exc}')
        return None


def _jats_to_text(value):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', value or '')).strip()


def crossref_to_fields(message):
    fields = {}
    title = (message.get('title') or [''])
    if title and title[0]:
        fields['title'] = title[0]

    authors = message.get('author') or []
    names = []
    for author in authors:
        name = author.get('name') or f"{author.get('given', '')} {author.get('family', '')}".strip()
        if name:
            names.append(name)
    if names:
        fields['authors'] = ', '.join(names)

    container = message.get('container-title') or []
    if container and container[0]:
        fields['journal'] = container[0]
    for key, field in (('page', 'pages'), ('volume', 'volume'), ('issue', 'issue'),
                       ('publisher', 'publisher')):
        if message.get(key):
            fields[field] = str(message[key])
    issn = message.get('ISSN') or []
    if issn:
        fields['issn'] = issn[0]

    year = None
    for key in ('published-print', 'published-online', 'issued'):
        parts = (message.get(key) or {}).get('date-parts') or []
        if parts and parts[0] and parts[0][0]:
            year = str(parts[0][0])
            break
    if year:
        fields['year'] = year

    abstract = _jats_to_text(message.get('abstract'))
    if abstract:
        fields['abstract'] = abstract
    if message.get('is-referenced-by-count') is not None:
        fields['cited_by_count'] = int(message['is-referenced-by-count'])
    if message.get('URL'):
        fields['link'] = message['URL']
    return fields


def fetch_openalex(doi):
    """Fetch a work from OpenAlex by DOI (no key required)."""
    url = 'https://api.openalex.org/works/doi:' + urllib.parse.quote(doi)
    try:
        return get_json(url)
    except Exception as exc:  # noqa: BLE001
        print(f'    OpenAlex lookup failed for {doi}: {exc}')
        return None


def openalex_to_fields(message):
    """Map OpenAlex work metadata to optional publication fields."""
    if not message:
        return {}
    fields = {}
    if message.get('cited_by_count') is not None:
        fields['cited_by_count_openalex'] = int(message['cited_by_count'])
    open_access = message.get('open_access') or {}
    if open_access.get('is_oa'):
        fields['open_access'] = True
        if open_access.get('oa_url'):
            fields['open_access_url'] = open_access['oa_url']
    work_id = (message.get('id') or '').rsplit('/', 1)[-1]
    if work_id:
        fields['openalex_id'] = work_id
    topics = [topic.get('display_name') for topic in (message.get('topics') or [])[:3]
              if topic.get('display_name')]
    if topics:
        fields['topics'] = topics
    return fields


def load_publications():
    pubs = []
    for path in glob.glob(os.path.join(PUBLICATIONS_DIR, '*.json')):
        with open(path, encoding='utf-8') as handle:
            data = json.load(handle)
        data['_file'] = path
        data['_doi'] = data.get('doi') or doi_from_link(data.get('link', ''))
        data['_norm_title'] = norm(data.get('title', ''))
        pubs.append(data)
    return pubs


def fill_missing(target, fields):
    """Set fields on `target` only where the value is currently empty."""
    changed = False
    for key in ('doi', 'authors', 'journal', 'publication', 'year', 'abstract',
                'issn', 'volume', 'issue', 'pages', 'publisher', 'cited_by_count', 'link',
                'cited_by_count_openalex', 'open_access', 'open_access_url', 'openalex_id',
                'topics'):
        if key in fields and fields[key] in (None, ''):
            continue
        if key in fields and not target.get(key):
            target[key] = fields[key]
            changed = True
    return changed


def write_new_publication(fields):
    doi = fields.get('doi') or ''
    year = fields.get('year') or 'unknown'
    stem = slugify(fields.get('title', 'publication'))
    path = os.path.join(PUBLICATIONS_DIR, f'{year}_{stem}.json')
    entry = {
        'title': fields.get('title', ''),
        'authors': fields.get('authors', ''),
        'publication': fields.get('journal', ''),
        'journal': fields.get('journal', ''),
        'year': year,
        'abstract': fields.get('abstract', ''),
        'link': fields.get('link') or (f'https://doi.org/{doi}' if doi else ''),
        'doi': doi,
        'issn': fields.get('issn', ''),
        'impact_factor': '',
        'image': '',
        'volume': fields.get('volume', ''),
        'issue': fields.get('issue', ''),
        'pages': fields.get('pages', ''),
        'publisher': fields.get('publisher', ''),
    }
    if fields.get('cited_by_count') is not None:
        entry['cited_by_count'] = fields['cited_by_count']
    for extra in ('cited_by_count_openalex', 'open_access', 'open_access_url', 'openalex_id', 'topics'):
        if fields.get(extra) not in (None, ''):
            entry[extra] = fields[extra]
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(entry, handle, ensure_ascii=False, indent=4)
        handle.write('\n')
    return path


def write_review_draft(work, doi, title, year):
    os.makedirs(REVIEW_DIR, exist_ok=True)
    stem = slugify(title)
    short = re.sub(r'[^a-z0-9-]', '', (doi or '').split('/')[-1].lower())[:24] or 'x'
    path = os.path.join(REVIEW_DIR, f'{year or "noyear"}-{stem}-{short}.json')
    draft = {
        'needs_review': True,
        'type': work_type(work),
        'title': title,
        'year': year,
        'doi': doi,
        'link': f'https://doi.org/{doi}' if doi else '',
    }
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(draft, handle, ensure_ascii=False, indent=4)
        handle.write('\n')
    return path


def main():
    global EMAIL
    with open(ABOUT_FILE, encoding='utf-8') as handle:
        about = json.load(handle)
    orcid = about.get('orcid')
    if about.get('email'):
        EMAIL = about['email']
    if not orcid:
        print('No ORCID iD in data/about.json; nothing to do.')
        return

    publications = load_publications()
    by_norm = {p['_norm_title']: p for p in publications if p['_norm_title']}
    by_doi = {p['_doi']: p for p in publications if p['_doi']}

    works = fetch_orcid_works(orcid)
    print(f'ORCID works: {len(works)}')

    added = 0
    enriched = 0
    reviewed = 0

    for group in works:
        summaries = group.get('work-summary') or []
        if not summaries:
            continue
        work = summaries[0]
        title = work_title(work)
        doi = work_doi(work)
        wtype = work_type(work)
        year = work_year(work)
        norm_title = norm(title)

        target = by_norm.get(norm_title) or (by_doi.get(doi) if doi else None)

        if target:
            if not doi:
                continue
            message = fetch_crossref(doi)
            if message is None:
                continue
            fields = crossref_to_fields(message)
            fields.update(openalex_to_fields(fetch_openalex(doi)))
            if fill_missing(target, fields):
                # Preserve the original file's unicode-escaping and newline style
                # so the diff shows only the fields we actually added.
                try:
                    with open(target['_file'], encoding='utf-8') as handle:
                        raw = handle.read()
                except OSError:
                    raw = ''
                escaped = bool(re.search(r'\\u[0-9a-fA-F]{4}', raw))
                trailing_newline = raw.endswith('\n')
                with open(target['_file'], 'w', encoding='utf-8') as handle:
                    json.dump({k: v for k, v in target.items() if not k.startswith('_')},
                              handle, ensure_ascii=escaped, indent=4)
                    if trailing_newline:
                        handle.write('\n')
                enriched += 1
                print(f'  enriched: {title[:80]}')
            continue

        # Not on the site yet.
        if wtype == 'journal-article' and doi and not doi.startswith(REVIEW_DOI_PREFIXES):
            message = fetch_crossref(doi)
            if message is None:
                write_review_draft(work, doi, title, year)
                reviewed += 1
                continue
            fields = crossref_to_fields(message)
            fields.update(openalex_to_fields(fetch_openalex(doi)))
            fields['doi'] = doi
            if not fields.get('year'):
                fields['year'] = year
            path = write_new_publication(fields)
            added += 1
            print(f'  added: {fields.get("title", title)[:80]} -> {os.path.basename(path)}')
        else:
            write_review_draft(work, doi, title, year)
            reviewed += 1
            print(f'  review: {title[:80]}')

    print(f'\nDone. added={added} enriched={enriched} review={reviewed}')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f'update_publications failed: {exc}', file=sys.stderr)
        sys.exit(1)
