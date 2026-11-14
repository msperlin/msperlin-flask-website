from scholarly import scholarly, ProxyGenerator
from pathlib import Path
import json
import datetime
import sys

my_id = "n3LTk-UAAAAJ"
parent_dir = Path(__file__).resolve().parent.parent
file_path = parent_dir / "data" / "stats" / "gscholar.json"

print(f"Starting to fetch data for {my_id} at {datetime.datetime.today()}")

def fetch_data():
    print(f"Fetching author ID {my_id}...")
    author = scholarly.search_author_id(my_id)
    print("Filling author details (basics, indices)...")
    author = scholarly.fill(
        author, 
        sections=['basics', 'indices']
    )
    return author

author = None
try:
    print("Attempting to fetch data directly (without proxy)...")
    author = fetch_data()
    print("Direct fetch successful!")
except Exception as e:
    print(f"Direct fetch failed: {e}")
    print("Falling back to FreeProxies setup...")
    try:
        pg = ProxyGenerator()
        pg.FreeProxies()
        scholarly.use_proxy(pg)
        print("Proxy setup complete. Retrying fetch with proxy...")
        author = fetch_data()
        print("Fetch with proxy successful!")
    except Exception as proxy_err:
        print(f"Proxy setup or fetch with proxy failed: {proxy_err}")

if author:
    print(f"Data fetched for {my_id} at {datetime.datetime.today()}")
    print(f"got dictionary with keys: {author.keys()}")
    
    author['date_retrieval'] = datetime.datetime.today().strftime('%Y-%m-%d')

    # Preserve the site-owned citation history across runs and append this month.
    stamp = datetime.date.today().strftime('%Y-%m')
    history = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            previous = json.load(f)
        history = previous.get('history') or []
    except (OSError, ValueError):
        pass

    history = [entry for entry in history if entry.get('date') != stamp]
    history.append({
        'date': stamp,
        'citedby': author.get('citedby', 0),
        'hindex': author.get('hindex', 0),
        'i10index': author.get('i10index', 0),
    })
    history.sort(key=lambda entry: entry['date'])
    author['history'] = history[-36:]

    # Ensure parent directory exists
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(file_path, "w") as f:
        json.dump(author, f, indent=2)
    
    print(f"Data saved to {file_path} at {datetime.datetime.today()}")
else:
    print("Error: Could not retrieve author data. Exiting with failure.", file=sys.stderr)
    sys.exit(1)