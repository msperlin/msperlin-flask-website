# 2026-01-13 Doesnt work!!

import asyncio
from playwright.async_api import async_playwright

async def fetch_scopus_author(author_id):
    url = f"https://www.scopus.com/authid/detail.uri?authorId={author_id}"
    
    async with async_playwright() as p:
        # Launch browser (headless=True is faster)
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        # Navigate and wait for content
        await page.goto(url, wait_until="domcontentloaded")
        
        # Wait for a specific metric to ensure JS has rendered
        try:
            await page.wait_for_selector('div[data-testid="un-auth-author-metrics-details"]', timeout=10000)
            
            data = {
                "name": await page.inner_text('h1[data-testid="un-auth-author-name"]'),
                "documents": await page.inner_text('span[data-testid="un-auth-author-metrics-documents-count"]'),
                "h_index": await page.inner_text('span[data-testid="un-auth-author-metrics-hindex-count"]'),
                "citations": await page.inner_text('span[data-testid="un-auth-author-metrics-citations-count"]')
            }
            print(data)
            
        except Exception as e:
            print(f"Timeout or Error: {e}")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(fetch_scopus_author("31767585500"))