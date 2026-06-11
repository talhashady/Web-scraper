"""
Configuration constants for the Indeed PK scraper.
"""

import os

# ── Scraping Settings ──────────────────────────────────────────────
BASE_URL = "https://pk.indeed.com"
SEARCH_URL = f"{BASE_URL}/jobs"

# Rate limiting: random delay between requests (seconds)
MIN_DELAY = 2.0
MAX_DELAY = 4.0

# Maximum retries for a failed request
MAX_RETRIES = 2

# Maximum search result pages to scrape (safety cap)
MAX_PAGES = 20

# Only scrape jobs posted in the last N days
DAYS_FILTER = 7

# ── Database ───────────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DATA_DIR, "jobs.db")

# ── Export ─────────────────────────────────────────────────────────
EXPORT_DIR = os.path.join(DATA_DIR, "exports")

# ── Logging ────────────────────────────────────────────────────────
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
LOG_FILE = os.path.join(LOG_DIR, "scraper.log")

# ── Email Alerts ───────────────────────────────────────────────────
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "")  # Falls back to SMTP_USER if empty
SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").lower() == "true"
