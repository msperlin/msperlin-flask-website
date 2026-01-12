from scholarly import scholarly
from pathlib import Path
import json
import datetime

my_id = "n3LTk-UAAAAJ"
this_file = Path(__name__).resolve()
f_out = "../data/stats/gscholar.json"
parent_dir = Path(__name__).resolve().parent
file_path = parent_dir /  "data" / "stats" / "gscholar.json"

author = scholarly.search_author_id(my_id)

# Retrieve all the details for the author
#author = scholarly.fill(first_author_result)
author = scholarly.fill(
    author, 
    sections=['basics', 'indices']
    )

scholarly.pprint(author)

print(author)

author['date_retrieval'] = datetime.datetime.today().strftime('%Y-%m-%d')

json.dump(author, open(file_path, "w"), indent=2)