"""
Crawl4AI-based scraper for pk.indeed.com.

Handles:
- Search result pagination
- Detail page extraction (full description + apply link)
- Rate limiting with random delays
- Proxy rotation
- Progress tracking
- Retry logic
"""

import asyncio
import random
import logging
import uuid
import re
import html
import json
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urljoin, urlencode, quote_plus

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

from config import (
    BASE_URL,
    SEARCH_URL,
    MIN_DELAY,
    MAX_DELAY,
    MAX_RETRIES,
    MAX_PAGES,
    DAYS_FILTER,
    LOG_DIR,
    LOG_FILE,
)
from models import JobListing, ScrapeStatus
from database import insert_job

import os

# ── Logging Setup ──────────────────────────────────────────────────
os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger("indeed_scraper")
logger.setLevel(logging.INFO)

# File handler
file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
file_handler.setFormatter(
    logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s")
)
logger.addHandler(file_handler)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(
    logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s")
)
logger.addHandler(console_handler)


# ── In-memory scrape tracking ─────────────────────────────────────
scrape_jobs: dict[str, ScrapeStatus] = {}


def get_scrape_status(scrape_id: str) -> Optional[ScrapeStatus]:
    """Get the current status of a scrape job."""
    return scrape_jobs.get(scrape_id)


def build_search_url(keyword: str, start: int = 0) -> str:
    """Build Indeed search URL with keyword and pagination."""
    params = {
        "q": keyword,
        "fromage": DAYS_FILTER,  # Last 7 days
        "start": start,  # Pagination (0, 10, 20, ...)
    }
    return f"{SEARCH_URL}?{urlencode(params)}"


class IndeedScraper:
    """Crawl4AI-powered scraper for pk.indeed.com."""

    def __init__(self, proxies: Optional[list[str]] = None):
        self.proxies = proxies or []
        self.proxy_index = 0

    def _get_next_proxy(self) -> Optional[str]:
        """Round-robin proxy selection."""
        if not self.proxies:
            return None
        proxy = self.proxies[self.proxy_index % len(self.proxies)]
        self.proxy_index += 1
        return proxy

    def _get_browser_config(self) -> BrowserConfig:
        """Create browser config, optionally with proxy."""
        proxy = self._get_next_proxy()

        config = BrowserConfig(
            headless=True,
            browser_type="chromium",
            proxy=proxy,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport_width=1920,
            viewport_height=1080,
        )
        return config

    def _get_crawler_config(self) -> CrawlerRunConfig:
        """Create crawl run config."""
        return CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            page_timeout=30000,
            wait_until="domcontentloaded",
        )

    async def _rate_limit(self):
        """Sleep for a random delay to be polite."""
        delay = random.uniform(MIN_DELAY, MAX_DELAY)
        logger.info(f"Rate limiting: sleeping {delay:.1f}s")
        await asyncio.sleep(delay)

    async def _fetch_with_retry(
        self, crawler: AsyncWebCrawler, url: str, config: CrawlerRunConfig, retries: int = MAX_RETRIES
    ):
        """Fetch a URL with retry logic."""
        for attempt in range(retries + 1):
            try:
                result = await crawler.arun(url=url, config=config)
                if result.success:
                    return result
                else:
                    logger.warning(
                        f"Attempt {attempt + 1}/{retries + 1} failed for {url}: {result.error_message}"
                    )
            except Exception as e:
                logger.warning(
                    f"Attempt {attempt + 1}/{retries + 1} exception for {url}: {e}"
                )

            if attempt < retries:
                await asyncio.sleep(2 * (attempt + 1))  # Exponential backoff

        logger.error(f"All {retries + 1} attempts failed for {url}")
        return None

    def _parse_search_results(self, html: str) -> list[dict]:
        """
        Parse job cards from Indeed search results HTML.
        Extracts: title, company, location, date_posted, job_type, detail URL.
        """
        listings = []

        # 1. Try JSON extraction first (highly robust, complete, and accurate)
        try:
            # Search sequentially for providerData first, then initialData/initialState to get complete search results list
            script_match = re.search(
                r'window\.mosaic\.providerData\[[\'"]mosaic-provider-jobcards[\'"]\]\s*=\s*(\{.*)',
                html,
                re.DOTALL | re.IGNORECASE
            )
            if not script_match:
                script_match = re.search(
                    r'window\.mosaic\.initialData\s*=\s*(\{.*)',
                    html,
                    re.DOTALL | re.IGNORECASE
                )
            if not script_match:
                script_match = re.search(
                    r'window\._initialData\s*=\s*(\{.*)',
                    html,
                    re.DOTALL | re.IGNORECASE
                )
            if not script_match:
                script_match = re.search(
                    r'(?:_initialData|initialData)\s*=\s*(\{.*)',
                    html,
                    re.DOTALL | re.IGNORECASE
                )
                
            if script_match:
                script_text = script_match.group(1).strip()
                # Find the JSON boundaries using custom brace matcher
                start_idx = script_text.find('{')
                if start_idx != -1:
                    json_str = _extract_json_object(script_text, start_idx)
                    if json_str:

                        
                        data = json.loads(json_str)
                        
                        # Find results list
                        results = []
                        if 'metaData' in data and 'mosaicProviderJobCardsModel' in data['metaData']:
                            results = data['metaData']['mosaicProviderJobCardsModel'].get('results', [])
                        elif 'hostQueryExecutionResult' in data:
                            results = data['hostQueryExecutionResult'].get('data', {}).get('jobData', {}).get('results', [])
                        elif 'results' in data:
                            results = data['results']
                            
                        if results:
                            logger.info(f"Successfully extracted {len(results)} jobs from JSON provider data.")
                            for job in results:
                                # Sometimes the results list contains wrapper objects (e.g. {"job": {...}})
                                if isinstance(job, dict) and 'job' in job:
                                    job_data = job['job']
                                else:
                                    job_data = job
                                    
                                if not isinstance(job_data, dict):
                                    continue
                                    
                                title = _clean_html(job_data.get('title', ''))
                                company = job_data.get('company', '') or job_data.get('companyName', '') or job_data.get('sourceEmployerName', '') or job_data.get('truncatedCompany', '') or ''
                                company = _clean_html(str(company))
                                location = _clean_html(job_data.get('formattedLocation', '') or job_data.get('location', '') or '')
                                
                                raw_date = _clean_html(job_data.get('formattedRelativeTime', '') or job_data.get('formattedRelativeDate', '') or '')
                                date_posted = _normalize_relative_date(raw_date)
                                
                                job_types_list = job_data.get('jobTypes', []) or job_data.get('jobType', []) or []
                                if isinstance(job_types_list, list):
                                    job_types_list = [str(jt).capitalize() for jt in job_types_list if jt]
                                    job_type = ", ".join(job_types_list)
                                elif isinstance(job_types_list, str):
                                    job_type = _parse_job_type(job_types_list)
                                else:
                                    job_type = ""
                                    
                                jobkey = job_data.get('jobkey', '') or job_data.get('jobKey', '') or ''
                                if jobkey:
                                    detail_url = f"https://pk.indeed.com/viewjob?jk={jobkey}"
                                else:
                                    link = job_data.get('link', '')
                                    detail_url = urljoin(BASE_URL, link)
                                    
                                listings.append({
                                    "title": title,
                                    "company": company,
                                    "location": location,
                                    "date_posted": date_posted,
                                    "job_type": job_type,
                                    "detail_url": detail_url,
                                })
                            
                            if listings:
                                return listings
        except Exception as e:
            logger.warning(f"Failed to extract search results from JSON: {e}. Falling back to HTML parsing.")

        # 2. Fallback to HTML card-by-card parsing
        # Split html by job card containers to parse card-by-card (robust strategy)
        card_chunks = re.split(r'<div[^>]*?class="[^"]*?(?:job_seen_beacon|cardOutline|resultContent)[^"]*?"', html)
        
        if len(card_chunks) > 1:
            logger.info(f"Attempting card-by-card HTML fallback parsing on {len(card_chunks) - 1} blocks")
            for chunk in card_chunks[1:]:
                # CRITICAL: Strip style and script tags to avoid false positives (e.g. matching 'active' in CSS styles)
                chunk = re.sub(r'<script[^>]*?>.*?</script>', '', chunk, flags=re.DOTALL | re.IGNORECASE)
                chunk = re.sub(r'<style[^>]*?>.*?</style>', '', chunk, flags=re.DOTALL | re.IGNORECASE)
                
                # Extract Title and Link
                title_match = re.search(
                    r'<a[^>]*?class="[^"]*?jcs-JobTitle[^"]*?"[^>]*?href="([^"]*?)"[^>]*?>(.*?)</a>',
                    chunk,
                    re.DOTALL | re.IGNORECASE
                )
                if not title_match:
                    title_match = re.search(
                        r'<a[^>]*?href="([^"]*?(?:/rc/clk|/pagead/clk|/company/[^"]*?/jobs/[^"]*?)[^"]*?)"[^>]*?>(.*?)</a>',
                        chunk,
                        re.DOTALL | re.IGNORECASE
                    )
                
                if not title_match:
                    continue
                
                href = title_match.group(1)
                if "abcdef" in href or "123456" in href:
                    continue
                    
                raw_title = title_match.group(2)
                title = _clean_html(raw_title)
                if not title:
                    continue
                
                detail_url = urljoin(BASE_URL, href)
                
                # Extract Company
                company_match = re.search(
                    r'<span[^>]*?data-testid="company-name"[^>]*?>(.*?)</span>',
                    chunk,
                    re.DOTALL | re.IGNORECASE
                )
                if not company_match:
                    company_match = re.search(
                        r'class="[^"]*?companyName[^"]*?"[^>]*?>(.*?)</(?:span|a)>',
                        chunk,
                        re.DOTALL | re.IGNORECASE
                    )
                company = _clean_html(company_match.group(1)) if company_match else ""
                
                # Extract Location
                location_match = re.search(
                    r'<div[^>]*?data-testid="text-location"[^>]*?>(.*?)</div>',
                    chunk,
                    re.DOTALL | re.IGNORECASE
                )
                if not location_match:
                    location_match = re.search(
                        r'class="[^"]*?companyLocation[^"]*?"[^>]*?>(.*?)</div>',
                        chunk,
                        re.DOTALL | re.IGNORECASE
                    )
                location = _clean_html(location_match.group(1)) if location_match else ""
                
                # Extract Job Type
                job_type = _parse_job_type(chunk)
                
                # Extract Date Posted (Relative Date Parser)
                date_match = re.search(
                    r'data-testid="myJobsStateDate"[^>]*?>(.*?)</(?:span|div|td)>',
                    chunk,
                    re.DOTALL | re.IGNORECASE
                )
                if not date_match:
                    date_match = re.search(
                        r'<(?:span|div|td)[^>]*?class="[^"]*?(?:date|myJobsStateDate|css-175)[^"]*?"[^>]*?>(.*?)</(?:span|div|td)>',
                        chunk,
                        re.DOTALL | re.IGNORECASE
                    )
                if not date_match:
                    date_match = re.search(
                        r'<(?:span|div|td)[^>]*?>(.*?(?:just\s+posted|today|yesterday|ago|\d+\+?\s+days?|active).*?)</(?:span|div|td)>',
                        chunk,
                        re.DOTALL | re.IGNORECASE
                    )
                
                raw_date = ""
                if date_match:
                    raw_date = _clean_html(date_match.group(1))
                else:
                    # Fallback to searching the entire cleaned chunk text
                    cleaned_chunk = _clean_html(chunk)
                    pattern = re.compile(
                        r'\b(?:posted|active)?\s*('
                        r'just\s+posted|'
                        r'today|'
                        r'yesterday|'
                        r'\d+\+?\s+days?\s+ago|'
                        r'30\+\s+days?\s+ago|'
                        r'a\s+day\s+ago'
                        r')\b',
                        re.IGNORECASE
                    )
                    match = pattern.search(cleaned_chunk)
                    if match:
                        raw_date = match.group(0).strip()
                
                date_posted = _normalize_relative_date(raw_date)
                
                listings.append({
                    "title": title,
                    "company": company,
                    "location": location,
                    "date_posted": date_posted,
                    "job_type": job_type,
                    "detail_url": detail_url,
                })

        # 3. Fallback to the old list-based findall parser if card-by-card HTML found nothing
        if not listings:
            logger.info("Card-by-card HTML parsing returned no results. Falling back to global list search.")
            title_links = re.findall(
                r'<a[^>]*?href="(/rc/clk[^"]*?|/pagead/clk[^"]*?|/company/[^"]*?/jobs/[^"]*?)"[^>]*?>\s*<span[^>]*?>(.*?)</span>',
                html,
                re.DOTALL | re.IGNORECASE,
            )

            if not title_links:
                title_links = re.findall(
                    r'<a[^>]*?class="[^"]*?jcs-JobTitle[^"]*?"[^>]*?href="([^"]*?)"[^>]*?>\s*(?:<span[^>]*?>)?(.*?)(?:</span>)?\s*</a>',
                    html,
                    re.DOTALL | re.IGNORECASE,
                )

            if not title_links:
                title_links = re.findall(
                    r'href="(/rc/clk\?[^"]+)"[^>]*>.*?<span[^>]*>(.*?)</span>',
                    html,
                    re.DOTALL | re.IGNORECASE,
                )

            companies = re.findall(
                r'<span[^>]*?data-testid="company-name"[^>]*?>(.*?)</span>',
                html,
                re.DOTALL | re.IGNORECASE,
            )

            if not companies:
                companies = re.findall(
                    r'class="[^"]*?companyName[^"]*?"[^>]*?>(.*?)</(?:span|a)>',
                    html,
                    re.DOTALL | re.IGNORECASE,
                )

            locations = re.findall(
                r'<div[^>]*?data-testid="text-location"[^>]*?>(.*?)</div>',
                html,
                re.DOTALL | re.IGNORECASE,
            )

            if not locations:
                locations = re.findall(
                    r'class="[^"]*?companyLocation[^"]*?"[^>]*?>(.*?)</div>',
                    html,
                    re.DOTALL | re.IGNORECASE,
                )

            dates = re.findall(
                r'<span[^>]*?class="[^"]*?date[^"]*?"[^>]*?>(.*?)</span>',
                html,
                re.DOTALL | re.IGNORECASE,
            )

            if not dates:
                dates = re.findall(
                    r'data-testid="myJobsStateDate"[^>]*?>(.*?)</span>',
                    html,
                    re.DOTALL | re.IGNORECASE,
                )

            job_types = re.findall(
                r'<div[^>]*?class="[^"]*?metadata[^"]*?"[^>]*?>\s*<div[^>]*?>(.*?)</div>',
                html,
                re.DOTALL | re.IGNORECASE,
            )

            for i, (href, raw_title) in enumerate(title_links):
                title = _clean_html(raw_title)
                if not title:
                    continue

                detail_url = urljoin(BASE_URL, href)

                raw_date = _clean_html(dates[i]) if i < len(dates) else ""
                date_posted = _normalize_relative_date(raw_date)

                raw_job_type = _clean_html(job_types[i]) if i < len(job_types) else ""
                job_type = _parse_job_type(raw_job_type) if raw_job_type else ""

                listing = {
                    "title": title,
                    "company": _clean_html(companies[i]) if i < len(companies) else "",
                    "location": _clean_html(locations[i]) if i < len(locations) else "",
                    "date_posted": date_posted,
                    "job_type": job_type,
                    "detail_url": detail_url,
                }
                listings.append(listing)

        logger.info(f"Parsed {len(listings)} job cards from search page")
        return listings

    def _has_next_page(self, html: str) -> bool:
        """Check if there's a next page of results."""
        # Look for the next page navigation link
        has_next = bool(re.search(
            r'<a[^>]*?aria-label="Next Page"[^>]*?>|'
            r'<a[^>]*?data-testid="pagination-page-next"[^>]*?>|'
            r'<nav[^>]*?>.*?<a[^>]*?aria-label="Next"[^>]*?>',
            html,
            re.DOTALL | re.IGNORECASE,
        ))
        return has_next

    async def _scrape_detail_page(
        self, crawler: AsyncWebCrawler, url: str, config: CrawlerRunConfig
    ) -> dict:
        """
        Scrape a job detail page for full description and apply link.
        """
        # Detail pages need to wait for description elements to load.
        # We construct a specific CrawlerRunConfig for the detail page.
        from crawl4ai import CrawlerRunConfig, CacheMode
        
        detail_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            page_timeout=30000,
            wait_until="networkidle",
            wait_for="css:#jobDescriptionText, .jobsearch-JobComponent-description, #jobDetailsSection",
        )
        
        result = None
        # Try fetching with detail_config first
        try:
            result = await self._fetch_with_retry(crawler, url, detail_config, retries=1)
        except Exception as e:
            logger.warning(f"Error fetching detail page with wait_for for {url}: {e}. Retrying without wait_for.")
            
        # If it failed or result was not successful, retry with basic config
        if not result or not result.success:
            logger.info(f"Retrying detail page fetch with basic config: {url}")
            result = await self._fetch_with_retry(crawler, url, config, retries=1)
            
        if not result or not result.html:
            logger.warning(f"Failed to scrape detail page completely: {url}")
            return {"description": "", "apply_link": url}
            
        html_content = result.html or ""
        
        # 1. Parse description with fallback regex patterns
        description = ""
        # Selector 1: Standard Indeed jobDescriptionText
        desc_match = re.search(
            r'<div[^>]*?id="jobDescriptionText"[^>]*?>(.*?)</div>',
            html_content,
            re.DOTALL | re.IGNORECASE,
        )
        if desc_match:
            description = _clean_html(desc_match.group(1), keep_newlines=True)
            
        # Selector 2: Alternative description class
        if not description:
            desc_match = re.search(
                r'<div[^>]*?class="[^"]*?jobsearch-JobComponent-description[^"]*?"[^>]*?>(.*?)</div>',
                html_content,
                re.DOTALL | re.IGNORECASE,
            )
            if desc_match:
                description = _clean_html(desc_match.group(1), keep_newlines=True)
                
        # Selector 3: Generic jobDescription class
        if not description:
            desc_match = re.search(
                r'<div[^>]*?class="[^"]*?jobDescription[^"]*?"[^>]*?>(.*?)</div>',
                html_content,
                re.DOTALL | re.IGNORECASE,
            )
            if desc_match:
                description = _clean_html(desc_match.group(1), keep_newlines=True)
                
        # Selector 4: Details section fallback
        if not description:
            desc_match = re.search(
                r'<section[^>]*?class="[^"]*?jobsearch-JobDetailsSection[^"]*?"[^>]*?>(.*?)</section>',
                html_content,
                re.DOTALL | re.IGNORECASE,
            )
            if desc_match:
                description = _clean_html(desc_match.group(1), keep_newlines=True)
                
        if not description:
            logger.warning(f"Warning: Extracted description is empty for: {url}")

        # 2. Extract and validate apply link
        apply_link = _parse_apply_link(html_content, url)
        if not apply_link:
            logger.warning(f"Warning: Direct apply link not found for {url}. Defaulting to job details URL.")
            apply_link = url
            
        return {"description": description, "apply_link": apply_link}

    async def run_full_scrape(self, keyword: str) -> str:
        """
        Run the complete scraping pipeline.
        Returns the scrape_id for status tracking.
        """
        scrape_id = str(uuid.uuid4())
        status = ScrapeStatus(
            scrape_id=scrape_id,
            status="running",
            keyword=keyword,
            started_at=datetime.now().isoformat(),
        )
        scrape_jobs[scrape_id] = status

        logger.info(f"═══ Starting scrape [{scrape_id}] for keyword: '{keyword}' ═══")

        browser_config = self._get_browser_config()
        crawler_config = self._get_crawler_config()

        try:
            async with AsyncWebCrawler(config=browser_config) as crawler:
                page = 0
                start = 0
                all_listings = []

                # ── Phase 1: Scrape search result pages ────────────
                while page < MAX_PAGES:
                    url = build_search_url(keyword, start)
                    logger.info(f"Scraping search page {page + 1}: {url}")

                    result = await self._fetch_with_retry(crawler, url, crawler_config)

                    if not result or not result.html:
                        logger.warning(f"No HTML returned for page {page + 1}, stopping pagination")
                        break

                    listings = self._parse_search_results(result.html)

                    if not listings:
                        logger.info(f"No listings found on page {page + 1}, stopping pagination")
                        break

                    all_listings.extend(listings)
                    page += 1
                    status.pages_scraped = page
                    status.jobs_found = len(all_listings)

                    # Check for next page
                    if not self._has_next_page(result.html):
                        logger.info("No next page found, stopping pagination")
                        break

                    start += 10  # Indeed shows 10-15 results per page
                    await self._rate_limit()

                logger.info(
                    f"Phase 1 complete: {len(all_listings)} listings from {page} pages"
                )

                # ── Phase 2: Scrape detail pages ───────────────────
                for i, listing in enumerate(all_listings):
                    logger.info(
                        f"Scraping detail page {i + 1}/{len(all_listings)}: {listing['title']}"
                    )

                    try:
                        detail = await self._scrape_detail_page(
                            crawler, listing["detail_url"], crawler_config
                        )

                        job = JobListing(
                            title=listing["title"],
                            company=listing["company"],
                            location=listing["location"],
                            date_posted=listing["date_posted"],
                            job_type=listing["job_type"],
                            description=detail["description"],
                            apply_link=detail["apply_link"],
                            source_url=listing["detail_url"],
                        )

                        was_inserted = await insert_job(job)
                        if was_inserted:
                            status.jobs_saved += 1
                            logger.info(f"  ✓ Saved: {job.title} at {job.company}")
                        else:
                            logger.info(f"  ⊘ Duplicate skipped: {job.title}")

                    except Exception as e:
                        status.errors += 1
                        logger.error(f"  ✗ Error on detail page: {e}")

                    await self._rate_limit()

            # ── Scrape complete ────────────────────────────────────
            status.status = "completed"
            status.completed_at = datetime.now().isoformat()
            status.message = (
                f"Completed: {status.jobs_saved} new jobs saved "
                f"({status.jobs_found} found, {status.errors} errors)"
            )
            logger.info(f"═══ Scrape [{scrape_id}] completed: {status.message} ═══")

        except Exception as e:
            status.status = "failed"
            status.completed_at = datetime.now().isoformat()
            status.message = f"Scrape failed: {str(e)}"
            logger.error(f"═══ Scrape [{scrape_id}] FAILED: {e} ═══")

        return scrape_id


def _normalize_relative_date(raw_date: str) -> str:
    """
    Normalizes raw date text from Indeed to standardized YYYY-MM-DD.
    Handles relative terms like: "Just posted", "Today", "Yesterday", "1 day ago",
    "30+ days ago", "active N days ago", etc.
    """
    if not raw_date:
        return ""
    
    text = raw_date.strip().lower()
    
    # Clean up common prefixes/suffixes
    text = re.sub(r'\b(?:employer|posted|active|state|myjobsstatedate)\b', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    
    ref_date = datetime.now()
    
    # Check for just/today/yesterday
    if "just" in text or "today" in text:
        delta_days = 0
    elif "yesterday" in text:
        delta_days = 1
    elif "30+" in text or "30+ days" in text:
        delta_days = 30
    else:
        # Look for numbers in the string (e.g. "3 days ago", "1 day ago", "14 days")
        digits = re.findall(r'(\d+)', text)
        if digits:
            delta_days = int(digits[0])
        elif "a day" in text or "one day" in text:
            delta_days = 1
        else:
            # Fallback if no days found but it's active / posted
            return ""

    result_date = ref_date - timedelta(days=delta_days)
    return result_date.strftime("%Y-%m-%d")


def _parse_job_type(chunk: str) -> str:
    """
    Extracts job type (Full-time, Internship, Remote, Contract, Hybrid, etc.)
    from the card chunk using metadata containers or content fallback.
    """
    if not chunk:
        return ""
    # Look for metadata / attribute elements
    potential_texts = []
    
    # 1. Matches data-testid attributes
    for match in re.finditer(r'data-testid="attribute_card_secondary_[^"]+"[^>]*?>(.*?)</(?:div|span|td)>', chunk, re.DOTALL | re.IGNORECASE):
        potential_texts.append(_clean_html(match.group(1)))
        
    # 2. Matches class containing metadata, attribute, jobType, workplace, or css-
    for match in re.finditer(r'<(?:div|span|td)[^>]*?class="[^"]*?(?:metadata|attribute|jobType|workplace|css-)[^"]*?"[^>]*?>(.*?)</(?:div|span|td)>', chunk, re.DOTALL | re.IGNORECASE):
        txt = match.group(1)
        if len(txt) < 150:  # Only short strings are metadata
            potential_texts.append(_clean_html(txt))
            
    # Check against known job types
    valid_types = ["full-time", "part-time", "contract", "internship", "temporary", "remote", "hybrid", "on-site", "freelance"]
    found_types = []
    
    for text in potential_texts:
        text_lower = text.lower()
        for vt in valid_types:
            if re.search(rf'\b{re.escape(vt)}\b', text_lower):
                cap_vt = vt.capitalize()
                if cap_vt not in found_types:
                    found_types.append(cap_vt)
                    
    if found_types:
        return ", ".join(found_types)
        
    # Fallback: search the cleaned chunk text directly
    cleaned_chunk = _clean_html(chunk).lower()
    for vt in valid_types:
        if re.search(rf'\b{re.escape(vt)}\b', cleaned_chunk):
            cap_vt = vt.capitalize()
            if cap_vt not in found_types:
                found_types.append(cap_vt)
                
    return ", ".join(found_types) if found_types else ""


def _clean_html(text: str, keep_newlines: bool = False) -> str:
    """Strip HTML tags and clean whitespace."""
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<p[^>]*?>", "\n", text)
    text = re.sub(r"</p>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    if keep_newlines:
        text = re.sub(r"[ \t\r\f\v]+", " ", text)
        text = re.sub(r"\n\s*\n", "\n\n", text)
    else:
        text = re.sub(r"\s+", " ", text)
    return text.strip()


def _is_valid_url(url: str) -> bool:
    """Validates that a string is a properly formatted URL or mailto link, excluding static assets and generic helper pages."""
    if not url:
        return False
    url = url.strip()
    if url.startswith("mailto:"):
        return True
    
    # Ignore static asset files
    if any(url.lower().split('?')[0].endswith(ext) for ext in [".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".json", ".xml"]):
        return False
        
    # Ignore generic indeed navigation/help/footer pages
    blocklist = [
        "/browsejobs", "/support", "/legal", "/promo", "/hire", "/preferences", "/cookies", "/contact",
        "support.indeed.com", "secure.indeed.com", "apis.indeed.com", "indeed.com/legal", "indeed.com/promo",
        "indeed.com/hire", "indeed.com/support", "indeed.com/contact", "indeed.com/preferences", "indeed.com/cookies"
    ]
    if any(term in url.lower() for term in blocklist):
        return False
        
    return bool(re.match(r'^https?://[^\s/$.?#].[^\s]*$', url, re.IGNORECASE))


def _parse_apply_link(html_content: str, detail_url: str) -> str:
    """Extracts the direct application link or email from the detail page HTML."""
    if not html_content:
        return ""
        
    # 1. Look for standard indeed apply API or job target URL
    apply_match = re.search(
        r'data-indeed-apply-joburl="([^"]+)"',
        html_content,
        re.IGNORECASE
    )
    if apply_match:
        url = apply_match.group(1).strip()
        if _is_valid_url(url):
            return url
            
    apply_match = re.search(
        r'data-indeed-apply-apiurl="([^"]+)"',
        html_content,
        re.IGNORECASE
    )
    if apply_match:
        url = apply_match.group(1).strip()
        if _is_valid_url(url):
            return url

    # 2. Look for standard indeed apply button classes
    apply_match = re.search(
        r'<a[^>]*?class="[^"]*?(?:apply-button|indeed-apply-button|jobsearch-IndeedApplyButton)[^"]*?"[^>]*?href="([^"]*?)"',
        html_content,
        re.IGNORECASE
    )
    if apply_match:
        url = apply_match.group(1).strip()
        if _is_valid_url(url):
            return url

    # 3. Look for buttons inside call-to-action containers
    apply_match = re.search(
        r'class="[^"]*?CallToActionButton[^"]*?".*?href="([^"]*?)"',
        html_content,
        re.DOTALL | re.IGNORECASE
    )
    if apply_match:
        url = apply_match.group(1).strip()
        if _is_valid_url(url):
            return url
            
    # 4. Look for links containing "apply", "mailto", or "jobs" in their href
    apply_matches = re.findall(
        r'href="(https?://[^"]*?(?:apply|mailto|jobs)[^"]*?)"',
        html_content,
        re.IGNORECASE
    )
    for url in apply_matches:
        if _is_valid_url(url):
            return url

    # 5. Fallback: search for email address in description or html
    email_match = re.search(
        r'[\w.+-]+@[\w-]+\.[\w.-]+',
        html_content,
    )
    if email_match:
        return f"mailto:{email_match.group(0)}"

    return ""


def _extract_json_object(text: str, start_pos: int) -> str:
    """Finds the matching closing brace for the opening brace at start_pos."""
    brace_count = 0
    in_string = False
    escape = False
    quote_char = None
    
    for idx in range(start_pos, len(text)):
        char = text[idx]
        
        if escape:
            escape = False
            continue
            
        if char == '\\':
            escape = True
            continue
            
        if char in ['"', "'"]:
            if not in_string:
                in_string = True
                quote_char = char
            elif char == quote_char:
                in_string = False
                quote_char = None
            continue
            
        if not in_string:
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    return text[start_pos:idx+1]
                    
    return ""
