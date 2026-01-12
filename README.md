# msperlin-flask-website

This is the source code for the personal academic website of msperlin, built with **Flask** and **Python**. The site is designed to be easily maintainable by separating content (data) from the presentation (code/templates).

## 🚀 Quick Start (Local Development)

Follow these steps to run the website on your local machine.

### Prerequisites
*   Python 3.10+ installed.

### 1. Clone & Setup
```bash
# Clone the repository (if not already done)
git clone https://github.com/msperlin/msperlin-flask-website.git
cd msperlin-flask-website

# Create a virtual environment
python3 -m venv .venv

# Activate the virtual environment
# On Linux/MacOS:
source .venv/bin/activate
# On Windows:
# .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Run the Application
```bash
python app.py
```
The website will be available at **http://127.0.0.1:5000**.
Debug mode is enabled by default, so changes to code or templates will auto-reload the server.

---

## 📝 How to Edit and Maintain

Most of the content on this website is data-driven, meaning you don't need to edit HTML `templates` for routine updates. Instead, you modify JSON files in the `data/` directory.

### Project Structure
*   **`app.py`**: The main Flask application logic and routing.
*   **`data/`**: JSON files containing the site's content.
*   **`templates/`**: HTML templates (using Jinja2).
*   **`static/`**: CSS, JavaScript, images, and other static assets.
*   **`scripts/`**: Maintenance scripts.
*   **`books_rendered/`**: Contains static HTML files for the online books.

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
To update them:
```bash
# Ensure your virtual environment is active
cd scripts
python run_scholarly.py
```
This will update `data/stats/gscholar.json`.

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
