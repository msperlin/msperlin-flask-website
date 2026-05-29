import os
import re
import json
import urllib.request
import urllib.error
import time
from pathlib import Path
from datetime import datetime

# Set up paths
PARENT_DIR = Path(__file__).resolve().parent.parent
BOOKS_DIR = PARENT_DIR / "data" / "books"
STATS_DIR = PARENT_DIR / "data" / "stats"
OUTPUT_FILE = STATS_DIR / "amazon_books.json"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9,pt-BR;q=0.8,pt;q=0.7',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1'
}

def parse_rating(html):
    """
    Parses the average star rating (e.g. 4.7) from the Amazon product HTML.
    """
    # Pattern 1: id="acrPopover" title="4,7 de 5 estrelas" or "4.7 out of 5 stars"
    popover_match = re.search(r'id="acrPopover"[^>]*title="([^"]+)"', html)
    if popover_match:
        text = popover_match.group(1)
        rating_match = re.search(r'(\d[,\.]\d|\d)', text)
        if rating_match:
            val = rating_match.group(1).replace(',', '.')
            return float(val)

    # Pattern 2: a-icon-alt with star rating
    icon_alt_matches = re.findall(r'class="a-icon-alt">([^<]+)</span>', html)
    for text in icon_alt_matches:
        if "de 5" in text or "out of 5" in text:
            rating_match = re.search(r'(\d[,\.]\d|\d)', text)
            if rating_match:
                val = rating_match.group(1).replace(',', '.')
                return float(val)
                
    return None

def parse_ratings_count(html):
    """
    Parses the total ratings count (e.g. 238) from the Amazon product HTML.
    """
    # Pattern: id="acrCustomerReviewText" >(238)</span> or >238 ratings</span>
    reviews_match = re.search(r'id="acrCustomerReviewText"[^>]*>([^<]+)</span>', html)
    if reviews_match:
        text = reviews_match.group(1)
        # Clean non-digits (remove parentheses, periods, commas, spaces)
        # Handle cases like "1,234" or "1.234" by removing commas/periods
        digits_only = re.sub(r'\D', '', text)
        if digits_only:
            return int(digits_only)
            
    return None

def main():
    print(f"[{datetime.now()}] Starting Amazon Book Ratings fetcher...")
    
    # Load existing stats if available to prevent losing data on failure
    existing_stats = {}
    if OUTPUT_FILE.exists():
        try:
            with open(OUTPUT_FILE, 'r') as f:
                existing_stats = json.load(f)
            print(f"Loaded existing stats with {len(existing_stats.get('books', {}))} books.")
        except Exception as e:
            print(f"Could not load existing stats: {e}")
            
    stats = existing_stats.get("books", {})
    
    # Get all book JSON files
    book_files = sorted(list(BOOKS_DIR.glob("*.json")))
    print(f"Found {len(book_files)} books in data/books/.")
    
    for book_file in book_files:
        book_key = book_file.stem
        try:
            with open(book_file, 'r') as f:
                book_data = json.load(f)
        except Exception as e:
            print(f"Failed to read book file {book_file.name}: {e}")
            continue
            
        link_amazon = book_data.get("link_amazon")
        if not link_amazon:
            print(f"[{book_file.name}] No link_amazon defined, skipping.")
            continue
            
        print(f"[{book_file.name}] Fetching {link_amazon}...")
        try:
            req = urllib.request.Request(link_amazon, headers=HEADERS)
            # Add a slight delay between requests to be nice to Amazon
            time.sleep(2)
            
            with urllib.request.urlopen(req, timeout=15) as response:
                html = response.read().decode('utf-8', errors='ignore')
                
                # Check for bot detection
                if "api-services-support@amazon.com" in html or "Type the characters you see below" in html:
                    print(f"[{book_file.name}] Warning: Amazon bot/CAPTCHA page detected. Using cached data if available.")
                    continue
                    
                rating = parse_rating(html)
                ratings_count = parse_ratings_count(html)
                
                if rating is not None and ratings_count is not None:
                    stats[book_key] = {
                        "rating": rating,
                        "ratings_count": ratings_count,
                        "title": book_data.get("title"),
                        "link_amazon": link_amazon,
                        "last_updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                    print(f"[{book_file.name}] Successfully fetched! Rating: {rating}, Reviews: {ratings_count}")
                else:
                    print(f"[{book_file.name}] Could not parse rating/reviews. Rating parsed: {rating}, Reviews parsed: {ratings_count}")
                    
        except Exception as e:
            print(f"[{book_file.name}] Failed to fetch Amazon page: {e}")
            
    # Write stats back to file
    final_data = {
        "books": stats,
        "date_retrieval": datetime.now().strftime('%Y-%m-%d')
    }
    
    STATS_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(final_data, f, indent=2)
        
    print(f"[{datetime.now()}] Finished! Saved ratings stats to {OUTPUT_FILE}.")

if __name__ == "__main__":
    main()
