"""
FastAPI application — API routes for the Indeed PK scraper.

On Windows, Playwright/Crawl4AI requires a SelectorEventLoop for subprocess
spawning, but uvicorn uses ProactorEventLoop. We solve this by running the
scraper in a dedicated thread with its own SelectorEventLoop.
"""

import asyncio
import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import logging
import threading
import traceback
import uuid
from datetime import datetime

from fastapi import FastAPI, BackgroundTasks, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from config import LOG_FILE
from database import (
    init_db,
    get_all_jobs,
    get_job_count,
    get_unique_companies,
    get_latest_scrape_time,
    clear_all_jobs,
    create_alert,
    get_all_alerts,
    delete_alert,
    get_active_alerts,
    update_alert_triggered,
    create_schedule,
    get_all_schedules,
    delete_schedule,
    update_schedule_run,
    get_analytics,
)
from models import (
    ScrapeRequest, ScrapeStatus, JobListResponse, StatsResponse,
    EmailAlertCreate, EmailAlert, ScheduleCreate, Schedule,
    AnalyticsResponse
)
from scraper import IndeedScraper, get_scrape_status, scrape_jobs
from export import generate_excel
from google_sheets import export_to_google_sheets
import json
from datetime import datetime, timedelta

logger = logging.getLogger("indeed_scraper")


# ── App Setup ──────────────────────────────────────────────────────
app = FastAPI(
    title="Indeed PK Scraper",
    description="Web scraper for pk.indeed.com powered by Crawl4AI",
    version="1.0.0",
)

# CORS — allow frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount frontend static files
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


# ── Helper: run async code in a new thread with ProactorEventLoop ──
def _run_in_scraper_thread(coro_func):
    """
    Run an async function in a dedicated thread with its own
    ProactorEventLoop (required for Playwright subprocess on Windows).
    Uvicorn's main loop conflicts with Playwright's subprocess spawning,
    so we isolate it in a fresh thread with a clean event loop.
    """
    def _thread_target():
        if sys.platform == "win32":
            # ProactorEventLoop supports subprocesses on Windows
            loop = asyncio.ProactorEventLoop()
        else:
            loop = asyncio.new_event_loop()

        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(coro_func())
        except Exception as e:
            logger.error(f"Scraper thread error: {type(e).__name__}: {e}")
        finally:
            loop.close()

    thread = threading.Thread(target=_thread_target, daemon=True)
    thread.start()


@app.on_event("startup")
async def startup():
    """Initialize database on startup and start scheduler."""
    await init_db()
    logger.info("Database initialized, app started")
    asyncio.create_task(schedule_runner())

async def schedule_runner():
    """Background task to run automated scraping."""
    while True:
        try:
            schedules = await get_all_schedules()
            now = datetime.now()
            for sched in schedules:
                if not sched.is_active:
                    continue
                
                run_now = False
                if not sched.next_run_at:
                    run_now = True
                else:
                    next_run = datetime.fromisoformat(sched.next_run_at)
                    if now >= next_run:
                        run_now = True

                if run_now:
                    logger.info(f"Triggering scheduled scrape for '{sched.keyword}'")
                    # Calculate next run time
                    if sched.frequency == "daily":
                        next_time = now + timedelta(days=1)
                    elif sched.frequency == "weekly":
                        next_time = now + timedelta(days=7)
                    else:
                        next_time = now + timedelta(days=1) # default
                        
                    await update_schedule_run(sched.id, next_time.isoformat())
                    
                    # parse proxies if any
                    proxies = None
                    if sched.proxies:
                        try:
                            proxies = json.loads(sched.proxies)
                        except:
                            pass
                    
                    req = ScrapeRequest(keyword=sched.keyword, proxies=proxies)
                    try:
                        # start_scrape might raise 409 if already running
                        await start_scrape(req)
                    except HTTPException as e:
                        logger.warning(f"Scheduled scrape skipped: {e.detail}")
                    except Exception as e:
                        logger.error(f"Error starting scheduled scrape: {e}")

        except Exception as e:
            logger.error(f"Scheduler error: {e}")
            
        await asyncio.sleep(60) # check every minute


# ── Routes: Scraping ──────────────────────────────────────────────
@app.post("/api/scrape", response_model=ScrapeStatus)
async def start_scrape(request: ScrapeRequest):
    """
    Start a new scrape job.
    The scrape runs in a dedicated thread; poll /api/scrape/{scrape_id}/status for progress.
    """
    # Check if there's already a running scrape
    for sid, st in scrape_jobs.items():
        if st.status == "running":
            raise HTTPException(
                status_code=409,
                detail=f"A scrape is already running (ID: {sid}). Please wait for it to complete.",
            )

    scrape_id = str(uuid.uuid4())
    status = ScrapeStatus(
        scrape_id=scrape_id,
        status="starting",
        keyword=request.keyword,
        started_at=datetime.now().isoformat(),
    )
    scrape_jobs[scrape_id] = status

    # Define the scrape coroutine
    async def _do_scrape():
        """Full scrape pipeline — runs in its own thread & event loop."""
        from scraper import build_search_url, _clean_html
        from config import MAX_PAGES
        from database import insert_job
        from models import JobListing
        from crawl4ai import AsyncWebCrawler

        scraper = IndeedScraper(proxies=request.proxies)
        status.status = "running"

        browser_config = scraper._get_browser_config()
        crawler_config = scraper._get_crawler_config()

        try:
            async with AsyncWebCrawler(config=browser_config) as crawler:
                page = 0
                start = 0
                all_listings = []
                inserted_jobs = []

                # Phase 1: Search pages
                while page < MAX_PAGES:
                    url = build_search_url(request.keyword, start)
                    logger.info(f"[{scrape_id}] Scraping search page {page + 1}: {url}")

                    result = await scraper._fetch_with_retry(crawler, url, crawler_config)

                    if not result or not result.html:
                        logger.warning(f"[{scrape_id}] No HTML for page {page + 1}, stopping")
                        break

                    listings = scraper._parse_search_results(result.html)
                    if not listings:
                        logger.info(f"[{scrape_id}] No listings on page {page + 1}, stopping")
                        break

                    all_listings.extend(listings)
                    page += 1
                    status.pages_scraped = page
                    status.jobs_found = len(all_listings)

                    if not scraper._has_next_page(result.html):
                        logger.info(f"[{scrape_id}] No next page, stopping")
                        break

                    start += 10
                    await scraper._rate_limit()

                logger.info(
                    f"[{scrape_id}] Phase 1 done: {len(all_listings)} listings from {page} pages"
                )

                # Phase 2: Detail pages
                for i, listing in enumerate(all_listings):
                    logger.info(
                        f"[{scrape_id}] Detail {i + 1}/{len(all_listings)}: {listing['title']}"
                    )
                    try:
                        detail = await scraper._scrape_detail_page(
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
                            inserted_jobs.append(job)
                            logger.info(f"[{scrape_id}]   ✓ Saved: {job.title}")
                        else:
                            logger.info(f"[{scrape_id}]   ⊘ Duplicate: {job.title}")

                    except Exception as e:
                        status.errors += 1
                        logger.error(f"[{scrape_id}] Detail error: {e}")

                    await scraper._rate_limit()

            status.status = "completed"
            status.completed_at = datetime.now().isoformat()
            status.message = (
                f"Completed: {status.jobs_saved} new jobs saved "
                f"({status.jobs_found} found, {status.errors} errors)"
            )
            logger.info(f"[{scrape_id}] ═══ COMPLETED: {status.message} ═══")

            # Check email alerts
            if inserted_jobs:
                from email_utils import send_alert_email
                active_alerts = await get_active_alerts()
                for alert in active_alerts:
                    matched = []
                    for j in inserted_jobs:
                        k = alert.keyword.lower()
                        if alert.match_title and k in j.title.lower():
                            matched.append(j)
                        elif alert.match_description and k in j.description.lower():
                            matched.append(j)
                    
                    if matched:
                        logger.info(f"[{scrape_id}] Alert '{alert.keyword}' matched {len(matched)} jobs. Sending email to {alert.email}.")
                        try:
                            await send_alert_email(alert.email, alert.keyword, matched)
                            await update_alert_triggered(alert.id)
                        except Exception as e:
                            logger.error(f"[{scrape_id}] Failed to send alert email: {e}")

        except Exception as e:
            tb = traceback.format_exc()
            status.status = "failed"
            status.completed_at = datetime.now().isoformat()
            status.message = f"Scrape failed: {type(e).__name__}: {str(e)}"
            logger.error(f"[{scrape_id}] FAILED: {type(e).__name__}: {e}\n{tb}")

    # Launch scraper in a dedicated thread with SelectorEventLoop
    _run_in_scraper_thread(_do_scrape)

    return status


@app.get("/api/scrape/{scrape_id}/status", response_model=ScrapeStatus)
async def get_status(scrape_id: str):
    """Get the current status of a scrape job."""
    status = scrape_jobs.get(scrape_id)
    if not status:
        raise HTTPException(status_code=404, detail="Scrape job not found")
    return status


# ── Routes: Results ───────────────────────────────────────────────
@app.get("/api/results", response_model=JobListResponse)
async def list_results(keyword: str = Query(default=None, description="Filter by keyword in title")):
    """List all scraped job results."""
    jobs = await get_all_jobs(keyword)
    return JobListResponse(total=len(jobs), jobs=jobs)


@app.get("/api/results/export")
async def export_results(keyword: str = Query(default=None)):
    """Download results as an Excel file."""
    jobs = await get_all_jobs(keyword)

    if not jobs:
        raise HTTPException(status_code=404, detail="No jobs to export")

    buffer = generate_excel(jobs)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"indeed_pk_jobs_{timestamp}.xlsx"

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/results/export/sheets")
async def export_results_to_sheets(keyword: str = Query(default=None)):
    """Export results directly to a Google Sheet."""
    jobs = await get_all_jobs(keyword)

    if not jobs:
        raise HTTPException(status_code=404, detail="No jobs to export")

    try:
        url = export_to_google_sheets(jobs)
        return {"url": url}
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to export to Google Sheets: {e}")
        raise HTTPException(status_code=500, detail="Failed to export to Google Sheets")


@app.delete("/api/results")
async def delete_results():
    """Clear all scraped job results."""
    await clear_all_jobs()
    return {"message": "All results cleared successfully"}


# ── Routes: Stats ─────────────────────────────────────────────────
@app.get("/api/stats", response_model=StatsResponse)
async def get_stats():
    """Get dashboard statistics."""
    total = await get_job_count()
    companies = await get_unique_companies()
    latest = await get_latest_scrape_time()
    return StatsResponse(
        total_jobs=total,
        unique_companies=companies,
        latest_scrape=latest,
    )


@app.get("/api/analytics", response_model=AnalyticsResponse)
async def api_get_analytics():
    """Get analytics data for charts."""
    return await get_analytics()


# ── Routes: Alerts ────────────────────────────────────────────────
@app.post("/api/alerts", response_model=EmailAlert)
async def api_create_alert(alert: EmailAlertCreate):
    """Create a new email alert."""
    return await create_alert(alert)


@app.get("/api/alerts", response_model=list[EmailAlert])
async def api_get_alerts():
    """Get all email alerts."""
    return await get_all_alerts()


@app.delete("/api/alerts/{alert_id}")
async def api_delete_alert(alert_id: str):
    """Delete an email alert."""
    success = await delete_alert(alert_id)
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"message": "Alert deleted"}


# ── Routes: Schedules ─────────────────────────────────────────────
@app.post("/api/schedules", response_model=Schedule)
async def api_create_schedule(schedule: ScheduleCreate):
    """Create a new scrape schedule."""
    return await create_schedule(schedule)


@app.get("/api/schedules", response_model=list[Schedule])
async def api_get_schedules():
    """Get all scrape schedules."""
    return await get_all_schedules()


@app.delete("/api/schedules/{schedule_id}")
async def api_delete_schedule(schedule_id: str):
    """Delete a schedule."""
    success = await delete_schedule(schedule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"message": "Schedule deleted"}


# ── Routes: Logs ──────────────────────────────────────────────────
@app.get("/api/logs")
async def get_logs(lines: int = Query(default=100, le=500)):
    """Get the last N lines of the scraper log."""
    if not os.path.exists(LOG_FILE):
        return {"logs": "No logs yet."}

    with open(LOG_FILE, "r", encoding="utf-8") as f:
        all_lines = f.readlines()
        recent = all_lines[-lines:]

    return {"logs": "".join(recent)}


# ── Serve Frontend ────────────────────────────────────────────────
@app.get("/")
async def serve_frontend():
    """Serve the frontend dashboard."""
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Frontend not found. Place index.html in ../frontend/"}
