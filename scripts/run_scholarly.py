from scholarly import scholarly, ProxyGenerator
from pathlib import Path
import json
import datetime

# Set up proxy to avoid blocking in CI environments
try:
    print("Setting up proxy...")
    pg = ProxyGenerator()
    pg.FreeProxies()
    scholarly.use_proxy(pg)
    print("Proxy setup complete.")
except Exception as e:
    print(f"Failed to set up proxy: {e}")

my_id = "n3LTk-UAAAAJ"
this_file = Path(__file__).resolve()
f_out = "../data/stats/gscholar.json"
parent_dir = Path(__file__).resolve().parent.parent
file_path = parent_dir /  "data" / "stats" / "gscholar.json"

print(f"Starting to fetch data for {my_id} at {datetime.datetime.today()}")

author = scholarly.search_author_id(my_id)

# Retrieve all the details for the author
#author = scholarly.fill(first_author_result)
author = scholarly.fill(
    author, 
    sections=['basics', 'indices']
    )

print(f"Data fetched for {my_id} at {datetime.datetime.today()}")
print(f"got dictionary with keys: {author.keys()}")

#scholarly.pprint(author)
#print(author)

author['date_retrieval'] = datetime.datetime.today().strftime('%Y-%m-%d')

json.dump(author, open(file_path, "w"), indent=2)

print(f"Data saved to {file_path} at {datetime.datetime.today()}")