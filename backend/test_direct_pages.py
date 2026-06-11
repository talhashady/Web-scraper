import asyncio
import os
import sys
import re

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Add backend directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from scraper import IndeedScraper
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig

async def test_page(page_num, start):
    scraper = IndeedScraper()
    
    # Configure BrowserConfig
    browser_config = BrowserConfig(
        headless=True,
        browser_type="chromium",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        viewport_width=1920,
        viewport_height=1080,
    )
    
    # Configure CrawlerRunConfig with anti-bot evasion
    crawler_config = CrawlerRunConfig(
        cache_mode="bypass",
        page_timeout=30000,
        wait_until="domcontentloaded",
        magic=True,
        simulate_user=True,
        override_navigator=True,
    )
    
    url = f"https://pk.indeed.com/jobs?q=Python&start={start}"
    print(f"Fetching URL directly: {url}")
    
    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(url=url, config=crawler_config)
        if not result or not result.success:
            print(f"Page {page_num} direct fetch failed!")
            return 0
            
        title_match = re.search(r"<title>(.*?)</title>", result.html, re.IGNORECASE)
        title = title_match.group(1) if title_match else "No Title"
        print(f"Page {page_num} Title: {title}")
        
        listings = scraper._parse_search_results(result.html)
        print(f"Page {page_num}: Extracted {len(listings)} jobs")
        return len(listings)

async def main():
    total_jobs = 0
    for i in range(5):
        start = i * 10
        print(f"\n--- Starting fetch for Page {i+1} (start={start}) ---")
        jobs_count = await test_page(i+1, start)
        total_jobs += jobs_count
        print(f"Total jobs collected so far: {total_jobs}")
        print("Sleeping 10 seconds before next fetch...")
        await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())
