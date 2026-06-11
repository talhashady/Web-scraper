import asyncio
import os
import sys
import re
import json
from urllib.parse import urljoin

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Add backend directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from playwright.async_api import async_playwright
from playwright_stealth import stealth_async
from scraper import IndeedScraper

async def parse_and_print_jobs(html_content, scraper, page_num):
    listings = scraper._parse_search_results(html_content)
    print(f"Page {page_num}: Extracted {len(listings)} jobs")
    for i, listing in enumerate(listings[:3]):
        print(f"  Job {i+1}: {listing['title']} at {listing['company']}")
    return listings

async def main():
    scraper = IndeedScraper()
    
    async with async_playwright() as p:
        print("Launching browser...")
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-sandbox",
            ]
        )
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US,en;q=0.9",
        )
        
        page = await context.new_page()
        
        # Apply Playwright Stealth!
        await stealth_async(page)
        
        # Go to page 1
        url = "https://pk.indeed.com/jobs?q=Python"
        print(f"Navigating to page 1: {url}")
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        
        html1 = await page.content()
        title1 = await page.title()
        print(f"Page 1 Title: {title1}")
        
        if "Security Check" in title1:
            print("Blocked on page 1!")
            await browser.close()
            return
            
        listings1 = await parse_and_print_jobs(html1, scraper, 1)
        
        # Look for next page button
        next_button_selectors = [
            'a[aria-label="Next Page"]',
            'a[data-testid="pagination-page-next"]',
            'a[aria-label="Next"]',
            'a:has-text("Next")'
        ]
        
        next_btn = None
        for sel in next_button_selectors:
            try:
                el = page.locator(sel)
                if await el.count() > 0 and await el.first.is_visible():
                    next_btn = el.first
                    print(f"Found next button with selector: {sel}")
                    break
            except Exception as e:
                pass
                
        if next_btn:
            # Click next button
            print("Clicking next button...")
            await next_btn.click()
            
            # Wait for navigation / content update
            print("Waiting for page load...")
            await page.wait_for_timeout(5000)
            
            html2 = await page.content()
            title2 = await page.title()
            print(f"Page 2 Title: {title2}")
            
            listings2 = await parse_and_print_jobs(html2, scraper, 2)
        else:
            print("Next page button not found or not visible!")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
