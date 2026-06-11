# Indeed PK Scraper Tasks

Here is the task list for the Indeed PK Scraper project. You can track the progress of tasks here.

## Core Scraper
- [x] Integrate Crawl4AI for pk.indeed.com scraping
- [x] Search page listing extraction (job title, company, location, date, job type)
- [x] Detailed page description extraction
- [x] Optional proxy rotation support
- [x] Rate limiting and polite delay configuration
- [x] Scraped result deduplication using SQLite

## Backend API (FastAPI)
- [x] POST `/api/scrape` — Start scrape job in thread
- [x] GET `/api/scrape/{id}/status` — Poll progress
- [x] GET `/api/results` — Fetch results list with keyword filter
- [x] GET `/api/results/export` — Stream Excel download
- [x] DELETE `/api/results` — Clear results
- [x] GET `/api/stats` — Scraping stats
- [x] GET `/api/logs` — Live scraper log retrieval

## Frontend Dashboard
- [x] Glassmorphism premium dark mode UI
- [x] Keyword search triggers and proxy input
- [x] Real-time log terminal viewer
- [x] Progress tracking bar/statistics panel
- [x] Excel download triggers
- [x] Table list view of scraped jobs

## Next Enhancements
- [ ] Add email alerts for specific keywords/jobs
- [ ] Automated daily/weekly scheduled scraping
- [ ] Direct export to Google Sheets
- [ ] Interactive analytical charts for job salaries/locations

## Current Quality Fixes
- [x] Implement robust date parsing and standardization (`YYYY-MM-DD`)
- [x] Improve job type extraction with selectors & scanning fallbacks
- [x] Fix HTML encoding using `html.unescape` and preserve description newlines
- [x] Add description retry logic, wait handling, and fallback selectors
- [x] Improve apply link extraction, validate URLs, and log missing apply links
