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

async def main():
    scraper = IndeedScraper()
    
    # Configure BrowserConfig to use local headful Chrome!
    browser_config = BrowserConfig(
        headless=False,  # Run in headful mode
        browser_type="chromium",
        channel="chrome",  # Local Chrome installation
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
    
    session_id = "indeed_scrape_session_chrome_headful"
    
    async with AsyncWebCrawler(config=browser_config) as crawler:
        # 1. Fetch Page 1
        url1 = "https://pk.indeed.com/jobs?q=Python&start=0"
        print(f"Fetching Page 1: {url1}")
        result1 = await crawler.arun(url=url1, config=crawler_config, session_id=session_id)
        if not result1 or not result1.success:
            print(f"Page 1 fetch failed: {result1.error_message if result1 else 'No result'}")
            return
            
        print("Page 1 fetch successful!")
        title1 = re.search(r"<title>(.*?)</title>", result1.html, re.IGNORECASE)
        print(f"Page 1 Title: {title1.group(1) if title1 else 'No Title'}")
        listings1 = scraper._parse_search_results(result1.html)
        print(f"Page 1: Extracted {len(listings1)} jobs")
        
        # Polite delay
        print("Sleeping 5 seconds...")
        await asyncio.sleep(5)
        
        # 2. Fetch Page 2
        url2 = "https://pk.indeed.com/jobs?q=Python&start=10"
        print(f"Fetching Page 2: {url2}")
        result2 = await crawler.arun(url=url2, config=crawler_config, session_id=session_id)
        if not result2 or not result2.success:
            print(f"Page 2 fetch failed: {result2.error_message if result2 else 'No result'}")
            return
            
        print("Page 2 fetch successful!")
        title2 = re.search(r"<title>(.*?)</title>", result2.html, re.IGNORECASE)
        print(f"Page 2 Title: {title2.group(1) if title2 else 'No Title'}")
        listings2 = scraper._parse_search_results(result2.html)
        print(f"Page 2: Extracted {len(listings2)} jobs")

if __name__ == "__main__":
    asyncio.run(main())
