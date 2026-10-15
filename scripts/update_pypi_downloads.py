import urllib.request
import urllib.error
import json
import os
import glob
import datetime

def fetch_pypi_downloads(package_name):
    """Return (downloads_last_month, total_downloads) for a PyPI package.

    Uses the pypistats.org API. Downloads are counted 'without_mirrors' to
    avoid double counting CDN mirrors. Returns None when the package has no
    data available.
    """
    url = f"https://pypistats.org/api/packages/{package_name}/overall"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
    except Exception as e:
        print(f"Error fetching pypistats for {package_name}: {e}")
        return None

    records = data.get("data", []) if isinstance(data, dict) else []
    if not records:
        return None

    without_mirrors = [r for r in records if r.get("category") == "without_mirrors"]
    if without_mirrors:
        records = without_mirrors

    total_downloads = sum(int(r.get("downloads", 0) or 0) for r in records)

    cutoff = datetime.date.today() - datetime.timedelta(days=30)
    downloads_last_month = 0
    for r in records:
        try:
            day = datetime.date.fromisoformat(r.get("date", ""))
        except ValueError:
            continue
        if day >= cutoff:
            downloads_last_month += int(r.get("downloads", 0) or 0)

    return downloads_last_month, total_downloads


def main():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_dir = os.path.join(project_root, "data", "code", "python")

    for filepath in glob.glob(os.path.join(target_dir, "*.json")):
        with open(filepath, "r") as f:
            pkg_data = json.load(f)

        pkg_name = pkg_data.get("name", "")
        if not pkg_name:
            continue

        result = fetch_pypi_downloads(pkg_name)
        if result is None:
            print(f"No PyPI download data available for {pkg_name}, skipping.")
            continue

        downloads_last_month, total_downloads = result

        # update fields
        pkg_data["number_of_downloads"] = downloads_last_month
        pkg_data["downloads_last_month"] = downloads_last_month
        pkg_data["total_downloads"] = total_downloads
        pkg_data["updated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(filepath, "w") as f:
            json.dump(pkg_data, f, indent=4)
            f.write("\n")
        print(f"Updated {pkg_name} with {downloads_last_month} downloads last month and {total_downloads} total downloads.")


if __name__ == '__main__':
    main()
