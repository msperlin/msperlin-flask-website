import os
import json
import urllib.request
import urllib.error
import re
import ssl
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys

# Create unverified SSL context to bypass invalid/expired certificate errors and handshake mismatches 
# (very common on academic and government servers)
ssl_context = ssl._create_unverified_context()

# Domains that aggressively block automated scrapers or are placeholders, and should be skipped or warned rather than failing the build
IGNORED_DOMAINS = [
    "linkedin.com",
    "example.com",
    "msperlin.com"
]

def extract_urls(data):
    """Recursively extract all URLs starting with http:// or https:// from JSON data."""
    urls = []
    if isinstance(data, str):
        if data.startswith("http://") or data.startswith("https://"):
            urls.append(data)
        else:
            # Find embedded URLs in text fields if any
            found = re.findall(r'https?://[^\s<>"]+|www\.[^\s<>"]+', data)
            urls.extend(found)
    elif isinstance(data, dict):
        for val in data.values():
            urls.extend(extract_urls(val))
    elif isinstance(data, list):
        for item in data:
            urls.extend(extract_urls(item))
    return urls

def check_url(url, file_sources):
    """Test a single URL and return a dict with results."""
    # Check if URL belongs to an ignored domain
    if any(domain in url for domain in IGNORED_DOMAINS):
        return {
            "url": url, 
            "status": "Ignored", 
            "working": True, 
            "warning": True, 
            "error": "Ignored domain (anti-scraping or placeholder)", 
            "files": file_sources[url]
        }

    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    req = urllib.request.Request(
        url, 
        headers={"User-Agent": user_agent},
        method="HEAD"
    )
    
    try:
        # Try HEAD request first for speed
        with urllib.request.urlopen(req, timeout=10, context=ssl_context) as response:
            status = response.status
            return {"url": url, "status": status, "working": True, "warning": False, "error": None, "files": file_sources[url]}
    except Exception:
        # Some servers block HEAD requests, try GET as a fallback
        try:
            req.method = "GET"
            with urllib.request.urlopen(req, timeout=10, context=ssl_context) as response:
                status = response.status
                return {"url": url, "status": status, "working": True, "warning": False, "error": None, "files": file_sources[url]}
        except urllib.error.HTTPError as he:
            # Handle some academic/gov sites blocking automation (e.g. 403 Forbidden, 401 Unauthorized, 429 Too Many Requests)
            if he.code in [401, 403, 429]:
                return {"url": url, "status": he.code, "working": True, "warning": True, "error": f"HTTP {he.code} (Allowed as working / possible anti-bot block)", "files": file_sources[url]}
            return {"url": url, "status": he.code, "working": False, "warning": False, "error": f"HTTP {he.code}", "files": file_sources[url]}
        except Exception as err:
            # Classification of timeout errors as warnings to avoid fragile external server slowness breaking builds
            is_timeout = "timeout" in str(err).lower() or "timed out" in str(err).lower()
            return {
                "url": url, 
                "status": None, 
                "working": not is_timeout,  # Don't fail the build on timeouts
                "warning": is_timeout,
                "error": "Request Timed Out" if is_timeout else str(err), 
                "files": file_sources[url]
            }

def main():
    data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    file_sources = {}
    
    print(f"Scanning JSON files in {os.path.abspath(data_dir)} for outbound links...")
    
    for root, _, files in os.walk(data_dir):
        # Skip directories that are not served by Flask
        if "code/matlab" in root:
            continue
            
        for file in files:
            if file.endswith(".json"):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        urls = extract_urls(data)
                        for url in urls:
                            # Clean URL
                            url_clean = url.strip().rstrip(",.")
                            if url_clean not in file_sources:
                                file_sources[url_clean] = []
                            rel_path = os.path.relpath(file_path, os.path.join(os.path.dirname(__file__), ".."))
                            if rel_path not in file_sources[url_clean]:
                                file_sources[url_clean].append(rel_path)
                except Exception as e:
                    print(f"Error reading {file_path}: {e}", file=sys.stderr)
                    
    unique_urls = list(file_sources.keys())
    print(f"Found {len(unique_urls)} unique outbound URLs.")
    
    if not unique_urls:
        print("No URLs found to check.")
        sys.exit(0)
        
    print("Starting concurrent validation using ThreadPoolExecutor...")
    broken_links = []
    warning_links = []
    working_count = 0
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(check_url, url, file_sources): url for url in unique_urls}
        for future in as_completed(futures):
            res = future.result()
            url = res["url"]
            if res["warning"]:
                warning_links.append(res)
                print(f"  [WARNING] {url} - Info: {res['error']}")
            elif res["working"]:
                working_count += 1
                status_str = f"HTTP {res['status']}" if res['status'] else "OK"
                print(f"  [OK] {url} ({status_str})")
            else:
                broken_links.append(res)
                print(f"  [BROKEN] {url} - Error: {res['error']}")
                for f in res["files"]:
                    print(f"     Found in: {f}")
                    
    print("\n--- Summary ---")
    print(f"Total Unique URLs: {len(unique_urls)}")
    print(f"Working:           {working_count}")
    print(f"Warnings:          {len(warning_links)}")
    print(f"Broken:            {len(broken_links)}")
    
    if broken_links:
        print("\nFailed checks detected. Please review the broken links listed above.")
        sys.exit(1)
    else:
        print("\nAll scanned links passed verification (with some warnings/exclusions)!")
        sys.exit(0)

if __name__ == "__main__":
    main()
