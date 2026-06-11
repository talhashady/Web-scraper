"""
Async SQLite database operations for job listings.
"""

import aiosqlite
import uuid
import os
from datetime import datetime
from typing import Optional

from config import DB_PATH, DATA_DIR
from models import JobListing, EmailAlert, EmailAlertCreate, Schedule, ScheduleCreate
import json


async def init_db():
    """Create the database and tables if they don't exist."""
    os.makedirs(DATA_DIR, exist_ok=True)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                company TEXT DEFAULT '',
                location TEXT DEFAULT '',
                date_posted TEXT DEFAULT '',
                job_type TEXT DEFAULT '',
                description TEXT DEFAULT '',
                apply_link TEXT DEFAULT '',
                source_url TEXT UNIQUE NOT NULL,
                scraped_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_source_url ON jobs(source_url)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_scraped_at ON jobs(scraped_at)
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS email_alerts (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                keyword TEXT NOT NULL,
                match_title BOOLEAN DEFAULT 1,
                match_description BOOLEAN DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                created_at TEXT NOT NULL,
                last_triggered TEXT DEFAULT NULL,
                times_triggered INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS schedules (
                id TEXT PRIMARY KEY,
                keyword TEXT NOT NULL,
                frequency TEXT NOT NULL,
                proxies TEXT DEFAULT NULL,
                is_active BOOLEAN DEFAULT 1,
                created_at TEXT NOT NULL,
                next_run_at TEXT DEFAULT NULL,
                last_run_at TEXT DEFAULT NULL
            )
        """)
        await db.commit()


async def job_exists(source_url: str) -> bool:
    """Check if a job with this source URL already exists (deduplication)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM jobs WHERE source_url = ?", (source_url,)
        )
        row = await cursor.fetchone()
        return row is not None


async def insert_job(job: JobListing) -> bool:
    """
    Insert a job listing into the database.
    Returns True if inserted, False if duplicate (skipped).
    """
    if await job_exists(job.source_url):
        return False

    job_id = str(uuid.uuid4())
    scraped_at = datetime.now().isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                """
                INSERT INTO jobs (id, title, company, location, date_posted, job_type,
                                  description, apply_link, source_url, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    job.title,
                    job.company,
                    job.location,
                    job.date_posted,
                    job.job_type,
                    job.description,
                    job.apply_link,
                    job.source_url,
                    scraped_at,
                ),
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            # Duplicate source_url — race condition safeguard
            return False


async def get_all_jobs(keyword: Optional[str] = None) -> list[JobListing]:
    """Fetch all jobs, optionally filtered by keyword in title."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        if keyword:
            cursor = await db.execute(
                """
                SELECT * FROM jobs
                WHERE title LIKE ?
                ORDER BY scraped_at DESC
                """,
                (f"%{keyword}%",),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM jobs ORDER BY scraped_at DESC"
            )

        rows = await cursor.fetchall()
        return [
            JobListing(
                id=row["id"],
                title=row["title"],
                company=row["company"],
                location=row["location"],
                date_posted=row["date_posted"],
                job_type=row["job_type"],
                description=row["description"],
                apply_link=row["apply_link"],
                source_url=row["source_url"],
                scraped_at=row["scraped_at"],
            )
            for row in rows
        ]


async def get_job_count() -> int:
    """Get total number of stored jobs."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM jobs")
        row = await cursor.fetchone()
        return row[0] if row else 0


async def get_unique_companies() -> int:
    """Get count of unique company names."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(DISTINCT company) FROM jobs WHERE company != ''"
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


async def get_latest_scrape_time() -> Optional[str]:
    """Get the timestamp of the most recent scrape."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT MAX(scraped_at) FROM jobs"
        )
        row = await cursor.fetchone()
        return row[0] if row and row[0] else None


async def clear_all_jobs():
    """Delete all job records."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM jobs")
        await db.commit()


async def get_analytics() -> dict:
    """Get aggregated analytics data for charts."""
    async with aiosqlite.connect(DB_PATH) as db:
        # 1. Jobs by Location (Top 10)
        cursor = await db.execute("""
            SELECT location, COUNT(*) as count 
            FROM jobs 
            WHERE location != '' AND location IS NOT NULL
            GROUP BY location 
            ORDER BY count DESC 
            LIMIT 10
        """)
        locations = await cursor.fetchall()

        # 2. Jobs by Type
        cursor = await db.execute("""
            SELECT job_type, COUNT(*) as count 
            FROM jobs 
            WHERE job_type != '' AND job_type IS NOT NULL
            GROUP BY job_type 
            ORDER BY count DESC
        """)
        job_types = await cursor.fetchall()
        
        return {
            "locations": [{"label": row[0], "count": row[1]} for row in locations],
            "job_types": [{"label": row[0], "count": row[1]} for row in job_types]
        }


# ── Email Alerts CRUD ──────────────────────────────────────────────

async def create_alert(alert_data: EmailAlertCreate) -> EmailAlert:
    """Create a new email alert."""
    alert_id = str(uuid.uuid4())
    created_at = datetime.now().isoformat()
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO email_alerts (id, email, keyword, match_title, match_description, is_active, created_at, times_triggered)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alert_id,
                alert_data.email,
                alert_data.keyword,
                int(alert_data.match_title),
                int(alert_data.match_description),
                1,
                created_at,
                0
            )
        )
        await db.commit()
        
    return EmailAlert(
        id=alert_id,
        email=alert_data.email,
        keyword=alert_data.keyword,
        match_title=alert_data.match_title,
        match_description=alert_data.match_description,
        is_active=True,
        created_at=created_at,
        last_triggered=None,
        times_triggered=0
    )


async def get_all_alerts() -> list[EmailAlert]:
    """Fetch all email alerts."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM email_alerts ORDER BY created_at DESC")
        rows = await cursor.fetchall()
        return [
            EmailAlert(
                id=row["id"],
                email=row["email"],
                keyword=row["keyword"],
                match_title=bool(row["match_title"]),
                match_description=bool(row["match_description"]),
                is_active=bool(row["is_active"]),
                created_at=row["created_at"],
                last_triggered=row["last_triggered"],
                times_triggered=row["times_triggered"]
            )
            for row in rows
        ]


async def get_active_alerts() -> list[EmailAlert]:
    """Fetch all active email alerts."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM email_alerts WHERE is_active = 1")
        rows = await cursor.fetchall()
        return [
            EmailAlert(
                id=row["id"],
                email=row["email"],
                keyword=row["keyword"],
                match_title=bool(row["match_title"]),
                match_description=bool(row["match_description"]),
                is_active=bool(row["is_active"]),
                created_at=row["created_at"],
                last_triggered=row["last_triggered"],
                times_triggered=row["times_triggered"]
            )
            for row in rows
        ]


async def delete_alert(alert_id: str) -> bool:
    """Delete an email alert."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM email_alerts WHERE id = ?", (alert_id,))
        await db.commit()
        return cursor.rowcount > 0


async def update_alert_triggered(alert_id: str):
    """Update last_triggered and increment times_triggered for an alert."""
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE email_alerts 
            SET last_triggered = ?, times_triggered = times_triggered + 1
            WHERE id = ?
            """,
            (now, alert_id)
        )
        await db.commit()


# ── Schedules CRUD ─────────────────────────────────────────────────

async def create_schedule(schedule_data: ScheduleCreate) -> Schedule:
    """Create a new scrape schedule."""
    schedule_id = str(uuid.uuid4())
    created_at = datetime.now().isoformat()
    proxies_json = json.dumps(schedule_data.proxies) if schedule_data.proxies else None
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO schedules (id, keyword, frequency, proxies, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                schedule_id,
                schedule_data.keyword,
                schedule_data.frequency,
                proxies_json,
                1,
                created_at
            )
        )
        await db.commit()
        
    return Schedule(
        id=schedule_id,
        keyword=schedule_data.keyword,
        frequency=schedule_data.frequency,
        proxies=proxies_json,
        is_active=True,
        created_at=created_at
    )


async def get_all_schedules() -> list[Schedule]:
    """Fetch all schedules."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM schedules ORDER BY created_at DESC")
        rows = await cursor.fetchall()
        return [
            Schedule(
                id=row["id"],
                keyword=row["keyword"],
                frequency=row["frequency"],
                proxies=row["proxies"],
                is_active=bool(row["is_active"]),
                created_at=row["created_at"],
                next_run_at=row["next_run_at"],
                last_run_at=row["last_run_at"]
            )
            for row in rows
        ]


async def delete_schedule(schedule_id: str) -> bool:
    """Delete a schedule."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
        await db.commit()
        return cursor.rowcount > 0


async def update_schedule_run(schedule_id: str, next_run: str):
    """Update last_run_at and next_run_at for a schedule."""
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE schedules 
            SET last_run_at = ?, next_run_at = ?
            WHERE id = ?
            """,
            (now, next_run, schedule_id)
        )
        await db.commit()

