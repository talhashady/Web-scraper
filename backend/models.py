"""
Pydantic models for request/response schemas.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ScrapeRequest(BaseModel):
    """Request body to start a scrape job."""
    keyword: str = Field(..., min_length=1, max_length=200, description="Job title keyword to search")
    proxies: Optional[list[str]] = Field(
        default=None,
        description="Optional list of proxy URLs (e.g. http://ip:port or http://user:pass@ip:port)"
    )


class ScrapeStatus(BaseModel):
    """Response model for scrape progress."""
    scrape_id: str
    status: str  # "running", "completed", "failed"
    keyword: str
    pages_scraped: int = 0
    jobs_found: int = 0
    jobs_saved: int = 0  # after dedup
    errors: int = 0
    message: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class JobListing(BaseModel):
    """A single scraped job listing."""
    id: Optional[str] = None
    title: str = ""
    company: str = ""
    location: str = ""
    date_posted: str = ""
    job_type: str = ""
    description: str = ""
    apply_link: str = ""
    source_url: str = ""
    scraped_at: Optional[str] = None


class JobListResponse(BaseModel):
    """Response model for listing jobs."""
    total: int
    jobs: list[JobListing]


class StatsResponse(BaseModel):
    """Dashboard statistics."""
    total_jobs: int
    unique_companies: int
    latest_scrape: Optional[str] = None


class EmailAlertCreate(BaseModel):
    """Request body to create an email alert rule."""
    email: str = Field(..., min_length=5, max_length=254, description="Recipient email address")
    keyword: str = Field(..., min_length=1, max_length=200, description="Keyword to watch for in job titles/descriptions")
    match_title: bool = Field(default=True, description="Match keyword in job title")
    match_description: bool = Field(default=False, description="Match keyword in job description")


class EmailAlert(BaseModel):
    """An email alert rule."""
    id: Optional[str] = None
    email: str = ""
    keyword: str = ""
    match_title: bool = True
    match_description: bool = False
    is_active: bool = True
    created_at: Optional[str] = None
    last_triggered: Optional[str] = None
    times_triggered: int = 0


class EmailConfigUpdate(BaseModel):
    """SMTP configuration for email alerts."""
    smtp_host: str = Field(default="smtp.gmail.com", description="SMTP server hostname")
    smtp_port: int = Field(default=587, description="SMTP server port")
    smtp_user: str = Field(default="", description="SMTP username/email")
    smtp_password: str = Field(default="", description="SMTP password or app password")
    smtp_from: str = Field(default="", description="From address (defaults to smtp_user)")
    use_tls: bool = Field(default=True, description="Use TLS/STARTTLS")


class ScheduleCreate(BaseModel):
    """Request body to create a scrape schedule."""
    keyword: str = Field(..., min_length=1, max_length=200, description="Job title keyword to schedule")
    frequency: str = Field(..., description="'daily' or 'weekly'")
    proxies: Optional[list[str]] = Field(default=None, description="Optional list of proxies")


class Schedule(BaseModel):
    """A saved schedule for scraping."""
    id: Optional[str] = None
    keyword: str = ""
    frequency: str = "daily"
    proxies: Optional[str] = None  # JSON encoded list of strings
    is_active: bool = True
    created_at: Optional[str] = None
    next_run_at: Optional[str] = None
    last_run_at: Optional[str] = None


class GoogleSheetsExportRequest(BaseModel):
    """Request body for Google Sheets export."""
    spreadsheet_id: str = Field(..., description="The ID of the Google Spreadsheet to export to")
    sheet_name: str = Field(default="Indeed PK Jobs", description="The name of the sheet tab to create/overwrite")
    credentials_json: Optional[str] = Field(default=None, description="Optional raw JSON string of the service account credentials")


class AnalyticsDataPoint(BaseModel):
    """A data point for analytics charts."""
    label: str
    count: int


class AnalyticsResponse(BaseModel):
    """Analytics data for charts."""
    locations: list[AnalyticsDataPoint]
    job_types: list[AnalyticsDataPoint]
