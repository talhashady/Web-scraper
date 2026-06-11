# 🕷️ Indeed PK Scraper

A web application that scrapes job listings from [pk.indeed.com](https://pk.indeed.com) using **Crawl4AI**. Search by keyword, view results in a premium dashboard, and export to Excel.

## Features

- 🔍 **Keyword Search** — Search by any job title
- 📅 **7-Day Filter** — Only scrapes recent listings
- 📄 **Full Detail Scraping** — Extracts complete job descriptions
- 🔄 **Proxy Rotation** — Optional proxy support to avoid IP blocks
- ⏱️ **Rate Limiting** — Polite scraping with random delays
- 🚫 **Deduplication** — Skips already-scraped listings
- 📊 **Excel Export** — Download results as `.xlsx`
- 📝 **Live Logging** — Track scrape progress in real-time
- 🎨 **Modern Dashboard** — Dark theme with glassmorphism UI

## Data Extracted

| Field | Source |
|-------|--------|
| Job Title | Search results |
| Company Name | Search results |
| Location | Search results |
| Date Posted | Search results |
| Job Type | Search results |
| Full Description | Detail page |
| Apply Link / Email | Detail page |

## Tech Stack

- **Backend**: FastAPI + Crawl4AI + SQLite
- **Frontend**: Vanilla HTML/CSS/JS
- **Export**: openpyxl

## Setup & Run

### 1. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2. Install Crawl4AI Browser

```bash
crawl4ai-setup
```

### 3. Start the Server

```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Open the Dashboard

Navigate to [http://localhost:8000](http://localhost:8000) in your browser.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/scrape` | Start a scrape job |
| `GET` | `/api/scrape/{id}/status` | Check scrape progress |
| `GET` | `/api/results` | List all results |
| `GET` | `/api/results/export` | Download Excel file |
| `DELETE` | `/api/results` | Clear all results |
| `GET` | `/api/stats` | Dashboard statistics |
| `GET` | `/api/logs` | View scraper logs |

## Configuration

Edit `backend/config.py` to adjust:

```python
MIN_DELAY = 2.0   # Min seconds between requests
MAX_DELAY = 4.0   # Max seconds between requests
MAX_RETRIES = 2   # Retry failed requests
MAX_PAGES = 20    # Max search result pages
DAYS_FILTER = 7   # Only last N days
```

## Proxy Usage

Enter proxies in the dashboard (one per line):
```
http://ip:port
http://user:pass@ip:port
socks5://ip:port
```

## License

MIT
