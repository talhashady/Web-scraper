import asyncio
import os
import sys

# Configure UTF-8 encoding for Windows console before importing crawl4ai/rich
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Add backend directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from scraper import IndeedScraper
from crawl4ai import AsyncWebCrawler

async def main():
    scraper = IndeedScraper()
    browser_config = scraper._get_browser_config()
    crawler_config = scraper._get_crawler_config()
    
    url = "https://pk.indeed.com/jobs?q=Python&fromage=7&start=10"
    print(f"Fetching: {url}")
    
    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(url=url, config=crawler_config)
        if not result or not result.success:
            print("Failed to fetch!")
            if result:
                print(f"Error: {result.error_message}")
            return
            
        print("Fetch successful!")
        html_content = result.html
        
        # Save HTML
        with open("page2_raw.html", "w", encoding="utf-8") as f:
            f.write(html_content)
        print("Saved HTML to page2_raw.html")
        
        # Parse it
        listings = scraper._parse_search_results(html_content)
        print(f"Number of listings extracted: {len(listings)}")
        
        has_next = scraper._has_next_page(html_content)
        print(f"Has next page? {has_next}")

if __name__ == "__main__":
    asyncio.run(main())
