import urllib.request
import json
import os

def fetch_and_save(url, target_dir, is_list=True, base_url=""):
    try:
        req = urllib.request.urlopen(url)
        data = json.loads(req.read().decode())
        
        packages = data if is_list else [data]
        
        for p in packages:
            name = p.get("Package", "")
            if not name:
                continue
                
            releases = p.get("_releases", [])
            date_sub = releases[0]["date"] if releases else "Unknown"
            downloads = p.get("_downloads", {}).get("count", 0) if p.get("_downloads") else 0
            title = p.get("Title", "")
            description = p.get("Description", "")
            
            pkg_data = {
                "title": name,
                "description": title,
                "date_of_submission": date_sub,
                "number_of_downloads": downloads,
                "link": f"{base_url}/{name}"
            }
            
            with open(os.path.join(target_dir, f"{name}.json"), "w") as f:
                json.dump(pkg_data, f, indent=4)
        print(f"Successfully processed {url}")
    except Exception as e:
        print(f"Error processing {url}: {e}")

if __name__ == '__main__':
    # Define the output directory
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_dir = os.path.join(project_root, "data", "code", "r")
    os.makedirs(target_dir, exist_ok=True)
    
    # 1. msperlin packages
    fetch_and_save(
        "https://msperlin.r-universe.dev/api/packages", 
        target_dir, 
        is_list=True, 
        base_url="https://msperlin.r-universe.dev"
    )
    
    # 2. yfR from ropensci
    fetch_and_save(
        "https://ropensci.r-universe.dev/api/packages/yfR", 
        target_dir, 
        is_list=False, 
        base_url="https://ropensci.r-universe.dev"
    )
    
    # 3. eodhdR2 from eodhistoricaldata
    fetch_and_save(
        "https://eodhistoricaldata.r-universe.dev/api/packages/eodhdR2", 
        target_dir, 
        is_list=False, 
        base_url="https://eodhistoricaldata.r-universe.dev"
    )
