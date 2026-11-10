#!/usr/bin/env python3
"""Record GitHub stars/forks for every package that has a repository.

Writes `github_repo`, `github_stars`, `github_forks` and `github_last_push`
into data/code/{r,python}/*.json. Run from the repository root:

    python scripts/update_github_stats.py

Set GITHUB_TOKEN to raise the API rate limit (the CI workflow provides it).
"""

import glob
import json
import os
import re
import sys
import urllib.error
import urllib.request

GITHUB_URL = re.compile(r'https?://(?:www\.)?github\.com/([^/\s]+)/([^/\s#?]+)')


def repo_slug(*urls):
    """owner/repo from any GitHub URL among the arguments."""
    for url in urls:
        if not url:
            continue
        match = GITHUB_URL.search(url)
        if match:
            return f'{match.group(1)}/{match.group(2).removesuffix(".git")}'
    return None


def github_get(path, token, headers):
    url = f'https://api.github.com{path}'
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode()), response.headers
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None, error.headers
        if error.code in (403, 429):
            print(f'GitHub API rate limit reached while fetching {path}.', file=sys.stderr)
            raise
        print(f'HTTP {error.code} for {path}', file=sys.stderr)
        return None, error.headers


def main():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    token = os.environ.get('GITHUB_TOKEN')
    headers = {
        'User-Agent': 'msperlin-website-stats',
        'Accept': 'application/vnd.github+json',
    }
    if token:
        headers['Authorization'] = f'Bearer {token}'

    targets = (
        (os.path.join(project_root, 'data', 'code', 'r'), 'title', True),
        (os.path.join(project_root, 'data', 'code', 'python'), 'name', False),
    )

    updated = 0
    for target_dir, name_field, guess_repo in targets:
        for filepath in sorted(glob.glob(os.path.join(target_dir, '*.json'))):
            with open(filepath, encoding='utf-8') as handle:
                package = json.load(handle)

            name = package.get(name_field)
            slug = repo_slug(package.get('github_link'), package.get('link'))
            if not slug and guess_repo and name:
                # R package sites point at r-universe; the source usually lives
                # under the same owner as the package name.
                slug = f'msperlin/{name}'
            if not slug:
                continue

            try:
                repo, response_headers = github_get(f'/repos/{slug}', token, headers)
            except (urllib.error.URLError, urllib.error.HTTPError) as error:
                print(f'Stopping: {error}', file=sys.stderr)
                break
            if repo is None:
                continue

            new_values = {
                'github_repo': repo.get('full_name'),
                'github_stars': repo.get('stargazers_count'),
                'github_forks': repo.get('forks_count'),
                'github_last_push': (repo.get('pushed_at') or '')[:10] or None,
            }
            if any(package.get(key) != value for key, value in new_values.items()):
                package.update(new_values)
                with open(filepath, 'w', encoding='utf-8') as handle:
                    json.dump(package, handle, indent=4)
                    handle.write('\n')
                updated += 1
                print(f'{name}: {new_values["github_stars"]} stars, '
                      f'{new_values["github_forks"]} forks')

            remaining = response_headers.get('X-RateLimit-Remaining') if response_headers else None
            if remaining is not None and int(remaining) <= 1:
                print('GitHub API quota nearly exhausted; stopping.', file=sys.stderr)
                print(f'Updated {updated} packages.')
                return

    print(f'Updated {updated} packages.')


if __name__ == '__main__':
    main()
