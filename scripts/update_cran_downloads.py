import urllib.request
import json
import os
import glob
import datetime

MAX_HISTORY = 24


def update_history(pkg_data, downloads_last_month, total_downloads):
    """Append/replace this month's snapshot so the site can chart a trend."""
    stamp = datetime.date.today().strftime("%Y-%m")
    history = [entry for entry in (pkg_data.get("history") or [])
               if entry.get("date") != stamp]
    history.append({
        "date": stamp,
        "downloads_last_month": int(downloads_last_month or 0),
        "total_downloads": int(total_downloads or 0),
    })
    history.sort(key=lambda entry: entry["date"])
    pkg_data["history"] = history[-MAX_HISTORY:]


def fetch_cran_downloads(package_name, start_date, end_date):
    url = f"https://cranlogs.r-pkg.org/downloads/total/{start_date}:{end_date}/{package_name}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            if isinstance(data, list) and len(data) > 0:
                return data[0].get("downloads", 0)
    except Exception as e:
        print(f"Error fetching cranlogs for {package_name} from {start_date} to {end_date}: {e}")
    return 0

def fetch_cran_downloads_last_month(package_name):
    url = f"https://cranlogs.r-pkg.org/downloads/total/last-month/{package_name}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            if isinstance(data, list) and len(data) > 0:
                return data[0].get("downloads", 0)
    except Exception as e:
        print(f"Error fetching cranlogs last-month for {package_name}: {e}")
    return 0

def main():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_dir = os.path.join(project_root, "data", "code", "r")
    
    # CRAN logs started around 2012-10-01
    start_date = "2012-10-01"
    end_date = datetime.date.today().isoformat()
    
    for filepath in glob.glob(os.path.join(target_dir, "*.json")):
        with open(filepath, "r") as f:
            pkg_data = json.load(f)
        
        pkg_name = pkg_data.get("title", "")
        if not pkg_name:
            continue
            
        downloads_last_month = fetch_cran_downloads_last_month(pkg_name)
        total_downloads = fetch_cran_downloads(pkg_name, start_date, end_date)
        
        # update fields
        pkg_data["number_of_downloads"] = downloads_last_month
        pkg_data["downloads_last_month"] = downloads_last_month
        pkg_data["total_downloads"] = total_downloads
        pkg_data["updated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        update_history(pkg_data, downloads_last_month, total_downloads)
        
        with open(filepath, "w") as f:
            json.dump(pkg_data, f, indent=4)
        print(f"Updated {pkg_name} with {downloads_last_month} downloads last month and {total_downloads} total downloads.")

if __name__ == '__main__':
    main()
