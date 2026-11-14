# msperlin-flask-website

This is the source code for the personal academic website of msperlin, built with **Flask** and **Python**. The site is designed to be easily maintainable by separating content (data) from the presentation (code/templates).

## 🚀 Quick Start (Local Development)

Follow these steps to run the website on your local machine.

### Prerequisites
*   [uv](https://docs.astral.sh/uv/) — the project is managed with uv, which
    can also install the correct Python version for you.

### 1. Clone & Setup
```bash
# Clone the repository (if not already done)
git clone https://github.com/msperlin/msperlin-flask-website.git
cd msperlin-flask-website

# Install uv (if you don't have it yet)
# On Linux/MacOS:
curl -LsSf https://astral.sh/uv/install.sh | sh
# On Windows (PowerShell):
# powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Create the virtual environment (.venv) and install dependencies from uv.lock
uv sync
```

### 2. Run the Application
```bash
uv run python app.py
```
The website will be available at **http://127.0.0.1:5000**.
Debug mode is enabled by default, so changes to code or templates will auto-reload the server.

> **Prefer plain `pip`?** The dependencies are also listed in `requirements.txt`
> and you can still use `python3 -m venv .venv && pip install -r requirements.txt`.
> Note that `pyproject.toml` / `uv.lock` are the source of truth for uv.

---

## 📝 How to Edit and Maintain

Most of the content on this website is data-driven, meaning you don't need to edit HTML `templates` for routine updates. Instead, you modify JSON files in the `data/` directory.

### Project Structure
*   **`app.py`**: The main Flask application logic and routing.
*   **`data/`**: JSON files containing the site's content.
*   **`templates/`**: HTML templates (using Jinja2).
*   **`static/`**: CSS, JavaScript, fonts, images, and other static assets.
*   **`scripts/`**: Maintenance scripts.
*   **`tests/`**: Pytest smoke tests (`uv run pytest`).
*   **`books_rendered/`**: Contains static HTML files for the online books.

### Pages and feeds
Besides the browsable sections, the app exposes stable and machine-readable URLs:

| URL | What it is |
| --- | --- |
| `/publications/<slug>` | One permanent page per paper, with the full abstract, Highwire `citation_*` tags (Google Scholar), `ScholarlyArticle` JSON-LD and a canonical URL. |
| `/publications/<slug>.bib` | The paper as a downloadable BibTeX file. |
| `/feed.xml` | RSS feed for news/media coverage. |
| `/publications/feed.xml` | RSS feed for new publications. |
| `/search` | Site-wide search over publications, books, news, slides, awards, datasets and code (server-side, works without JS). |
| `/cv` | A print-friendly CV generated from the JSON files. |
| `/press` | Press kit: EN/PT bios, topics, headshot and contact. |
| `/press/kit.zip` | Downloadable press kit (bios, topics, headshot, `.bib`). |
| `/feed.json` | JSON Feed 1.1 combining news and publications. |
| `/opensearch.xml` | OpenSearch description for browser site-search. |
| `/llms.txt` | Curated, machine-readable site map for AI assistants. |
| `/.well-known/security.txt` | Security contact information. |
| `/healthz` | Health-check endpoint for Cloud Run. |
| `/sitemap.xml` | Sitemap with per-page `lastmod` dates. |

### Frontend & UI
The site is server-rendered HTML (great for SEO) with a thin layer of progressive
enhancement on top. Everything still works if JavaScript is disabled.

*   **Design tokens & dark mode**: colors, radii, and fonts are CSS variables in
    `static/css/style.css`. The theme toggle switches `[data-theme="dark"]`;
    the choice is stored in `localStorage` and defaults to the OS preference.
*   **Navigation**: plain server-rendered links (no client-side routing), so
    browser history, focus and screen-reader behaviour stay native.
*   **Publications search/filter**: `static/js/main.js` filters the
    server-rendered list client-side (title/author/journal + year). The controls
    are hidden without JavaScript, and the full list always remains visible.
*   **Charts**: [Chart.js](https://www.chartjs.org) renders package download
    charts. It is self-hosted in `static/js/vendor/`, loaded only by the two code
    pages, and reads its data from
    `<script type="application/json" data-chart="…">` blocks. The update scripts
    also record a monthly `history`, which feeds a downloads-over-time chart once
    two months are available.
*   **Fonts**: Inter and Source Serif 4 are self-hosted from `static/fonts/`
    (SIL Open Font License), so there are no third-party font requests.
*   **Site JS**: all interaction logic lives in `static/js/main.js` (theme,
    mobile nav, scroll-reveal animations, charts, citation modal, print button)
    and uses event delegation. Content is never hidden behind a failed script.
*   **Images**: originals live in `static/img/`; the site serves resized WebP
    derivatives from `static/img/opt/` (with the original as fallback). Run
    `python scripts/optimize_images.py` after adding or replacing a cover or
    portrait image.
*   **No build step and no third-party CDNs**: all CSS, JS and fonts are served
    from this origin, which lets the Content-Security-Policy stay strict.
*   **Delivery**: responses are gzip-compressed (`flask-compress`), static files
    are cached for a year behind `?v=<mtime>` URLs (`static_url`), and HTML gets
    security headers plus a per-request CSP nonce (`add_security_headers`).

### Common Tasks

#### 1. Adding a Publication
1.  Navigate to `data/publications/`.
2.  Create a new JSON file (e.g., `2024_new_paper.json`) or duplicate an existing one.
3.  Fill in the details (title, authors, year, abstract, link, etc.).
4.  The site will automatically pick up the new file and sort it by year.

#### 2. Adding a News Item
1.  Navigate to `data/news/`.
2.  Create or duplicate a JSON file.
3.  Ensure the `date` field is correct (format: `YYYY-MM-DD`).

#### 3. Updating "About Me"
*   Edit `data/about.json`.

#### 4. Updating Google Scholar Stats
The site displays your Google Scholar statistics. These are fetched using a script.
To update them, run it from the repository root:
```bash
uv run --group stats python scripts/run_scholarly.py
```
This will update `data/stats/gscholar.json`. It also appends a monthly
`history` snapshot of `citedby` / `hindex` / `i10index`, which powers the
"Citations over time" chart on the publications page once two months are
available. The `stats` dependency group is only needed for this script, so the
production image does not install it.

#### 5. Updating Download and GitHub Stats
Three scripts keep the code pages current (all run weekly by GitHub Actions):
```bash
uv run python scripts/update_cran_downloads.py   # CRAN downloads + monthly history
uv run python scripts/update_pypi_downloads.py   # PyPI downloads + monthly history
uv run python scripts/update_github_stats.py     # stars, forks, last push
```
They fill `history` with one entry per month (capped at 24), which powers the
“Downloads over time” chart once there are at least two months. Set
`GITHUB_TOKEN` when running the GitHub script locally to avoid the 60 req/hour
anonymous limit.

#### 6. Running the Tests
```bash
uv run pytest
```
The suite renders every public route, checks the per-publication pages and
`.bib` downloads, validates both RSS feeds and the sitemap, and asserts the
security/caching headers. It runs in CI on every push and pull request.

#### 7. Adding or Replacing Images
1.  Put the original image in `static/img/` and reference it from the JSON file
    (e.g. `static/img/2027_cover_Journal.jpg`).
2.  Regenerate the optimized WebP derivatives and size manifest:
    ```bash
    uv run python scripts/optimize_images.py
    ```
    This requires [ImageMagick](https://imagemagick.org) (`magick` on the PATH).

The templates use the `opt_url` filter and `img_dims()` helper (see `app.py`),
so new images automatically get the resized file, lazy loading and intrinsic
dimensions.

#### 8. Adding a Python Project
1.  Navigate to `data/code/python/`.
2.  Create a JSON file with the same fields as the existing ones:
    ```json
    {
        "name": "package-name",
        "description": "What the project does.",
        "link": "https://github.com/msperlin/package-name",
        "github_link": "https://github.com/msperlin/package-name",
        "pypi_link": "https://pypi.org/project/package-name/",
        "number_of_downloads": null,
        "downloads_last_month": null,
        "total_downloads": null,
        "updated_at": null
    }
    ```
3.  `link` is where the project name points to (normally the GitHub repo);
    `github_link` and `pypi_link` feed the standard `GitHub | PyPI` line.
    Use `null` when the project is not published on PyPI yet.
4.  Download stats are filled in by `uv run python scripts/update_pypi_downloads.py`,
    which skips projects with `"pypi_link": null`. Stars and forks are added by
    `scripts/update_github_stats.py`.

#### 9. Updating the Press Kit
*   Edit `data/press.json` (bios in English and Portuguese, topics, contact,
    headshots).
*   The downloadable archive is generated on the fly at `/press/kit.zip`.

#### 10. Syncing Publications from ORCID & Crossref
```bash
uv run python scripts/update_publications.py
```
This runs monthly via GitHub Actions. It matches `data/publications/*.json`
to your ORCID works, fills missing bibliographic fields (volume, issue, pages,
publisher, citation counts) from Crossref, adds new journal articles that have
a DOI, and writes preprints / software / DOI-less works to
`data/publications-review/` for manual approval (never published automatically).
Move a reviewed file into `data/publications/` to publish it.

---

## ☁️ Hosting on Google Cloud

This project includes a `Dockerfile` configured for **Google Cloud Run**, a serverless platform that scales your container automatically.

### Prerequisites
1.  **Google Cloud Project**: Create one at [console.cloud.google.com](https://console.cloud.google.com/).
2.  **Google Cloud SDK (`gcloud`)**: [Install the CLI tool](https://cloud.google.com/sdk/docs/install).

### Deployment Steps

#### 1. Login to Google Cloud
Open your terminal and authenticate:
```bash
gcloud auth login
```

#### 2. Set your Project
```bash
gcloud config set project YOUR_PROJECT_ID
```
*(Replace `YOUR_PROJECT_ID` with your actual GCP project ID)*

#### 3. Deploy to Cloud Run
Run the following command from the root of the repository:
```bash
gcloud run deploy msperlin-website --source . --region us-central1 --allow-unauthenticated
```
*   `--source .`: Tells Google Cloud to build the container image from the current directory (using the Dockerfile).
*   `--region us-central1`: Sets the server location (change if needed).
*   `--allow-unauthenticated`: Makes the website public (accessible to anyone on the internet).

#### 4. Verify
After the command finishes, it will output a **Service URL** (e.g., `https://msperlin-website-xyz-uc.a.run.app`). Click it to view your live site.

### Updating the Live Site
To deploy changes (content updates or code fixes):
1.  Make your edits locally.
2.  Run the deploy command again:
    ```bash
    gcloud run deploy msperlin-website --source .
    ```
