import os
import json
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
import sys
import re

# Add parent directory to path to import Flask app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app

def main():
    # 1. Use Flask test client to get dynamic sitemap
    print("Generating sitemap.xml dynamically using Flask test client...")
    client = app.test_client()
    try:
        response = client.get('/sitemap.xml')
        if response.status_code != 200:
            print(f"Error: Failed to fetch sitemap.xml. Status: {response.status_code}", file=sys.stderr)
            sys.exit(1)
        xml_content = response.data
    except Exception as e:
        print(f"Error fetching sitemap: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Parse URLs from sitemap
    try:
        root = ET.fromstring(xml_content)
        # XML namespace for sitemaps
        ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        urls = []
        for loc in root.findall('.//ns:loc', ns):
            url_text = loc.text
            # Replace local dev domains with production domain to prevent IndexNow 422 domain mismatch errors
            url_clean = re.sub(r'https?://(localhost|127\.0\.0\.1|test\.local)(:\d+)?', 'https://msperlin.com', url_text)
            urls.append(url_clean)
    except Exception as e:
        print(f"Error parsing sitemap XML: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(urls)} URLs in the generated sitemap.")

    if not urls:
        print("No URLs found in the sitemap. Skipping IndexNow submission.")
        sys.exit(0)

    # 3. Submit to IndexNow API
    host = "msperlin.com"
    key = "f6d89283e4a24c25bcf682e06180dfd3"
    endpoint = "https://api.indexnow.org/indexnow"

    payload = {
        "host": host,
        "key": key,
        "keyLocation": f"https://{host}/{key}.txt",
        "urlList": urls
    }

    print(f"Submitting {len(urls)} URLs to IndexNow via {endpoint}...")
    
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode('utf-8'),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            # According to IndexNow protocol, both 200 (Success) and 202 (Accepted) represent successful submissions
            if resp.status in [200, 202]:
                print(f"IndexNow submission successful! (HTTP {resp.status})")
                sys.exit(0)
            else:
                print(f"IndexNow submission returned status code: {resp.status}", file=sys.stderr)
                sys.exit(1)
    except urllib.error.HTTPError as he:
        print(f"IndexNow submission failed: HTTP {he.code} - {he.reason}", file=sys.stderr)
        try:
            print(he.read().decode('utf-8'), file=sys.stderr)
        except Exception:
            pass
        sys.exit(1)
    except Exception as e:
        print(f"IndexNow submission failed: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
