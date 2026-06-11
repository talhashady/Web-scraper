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
    
    # Configure BrowserConfig
    browser_config = BrowserConfig(
        headless=True,  # Test in headless mode first
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
    
    session_id = "indeed_scrape_session_no_fromage"
    
    async with AsyncWebCrawler(config=browser_config) as crawler:
        for page in range(5):
            start = page * 10
            url = f"https://pk.indeed.com/jobs?q=Python&start={start}"
            print(f"Fetching Page {page + 1}: {url}")
            result = await crawler.arun(url=url, config=crawler_config, session_id=session_id)
            if not result or not result.success:
                print(f"Page {page + 1} fetch failed: {result.error_message if result else 'No result'}")
                break
                
            title_match = re.search(r"<title>(.*?)</title>", result.html, re.IGNORECASE)
            title = title_match.group(1) if title_match else "No Title"
            print(f"Page {page + 1} Title: {title}")
            
            # Save raw html for debugging if 0 listings extracted
            listings = scraper._parse_search_results(result.html)
            print(f"Page {page + 1}: Extracted {len(listings)} jobs")
            
            if len(listings) == 0:
                filename = f"debug_page_{page + 1}.html"
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(result.html)
                print(f"Saved HTML to {filename} for debugging")
                break
                
            print("Sleeping 3 seconds...")
            await asyncio.sleep(3)

if __name__ == "__main__":
    asyncio.run(main())
