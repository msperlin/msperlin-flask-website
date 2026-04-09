
import sys
import os

# Add parent directory to path to import app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app
import re

def verify_seo():
    client = app.test_client()
    
    # 1. Check Home Page
    print("Checking Home Page (/) ...")
    response = client.get('/')
    content = response.data.decode('utf-8')
    
    if '<meta name="description"' in content and 'Academic website of Marcelo S. Perlin' in content:
        print("  [PASS] Meta Description found")
    else:
        print("  [FAIL] Meta Description missing or incorrect")
        
    if 'og:title' in content and 'og:image' in content:
        print("  [PASS] Open Graph tags found")
    else:
        print("  [FAIL] Open Graph tags missing")
        
    if 'application/ld+json' in content and 'Person' in content and 'WebSite' in content:
        print("  [PASS] JSON-LD Schema (Person/WebSite) found")
    else:
        print("  [FAIL] JSON-LD Schema missing")

    # 2. Check Books Page
    print("\nChecking Books Page (/books) ...")
    response = client.get('/books')
    content = response.data.decode('utf-8')
    
    if '<meta name="description"' in content and 'Books authored by Marcelo S. Perlin' in content:
         print("  [PASS] Meta Description found")
    else:
         print("  [FAIL] Meta Description missing or incorrect")

    if 'application/ld+json' in content and 'ItemList' in content and 'Book' in content:
        print("  [PASS] JSON-LD Schema (Book List) found")
    else:
        print("  [FAIL] JSON-LD Schema missing")

if __name__ == "__main__":
    verify_seo()
