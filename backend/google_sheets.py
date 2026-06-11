import os
from typing import List
import logging
from models import JobListing
import gspread

logger = logging.getLogger("indeed_scraper")

CREDENTIALS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials.json")

def export_to_google_sheets(jobs: List[JobListing], sheet_name: str = "Indeed Scraper Results") -> str:
    """Exports data to a new Google Sheet and returns the URL."""
    if not os.path.exists(CREDENTIALS_FILE):
        raise FileNotFoundError(f"Google Service Account credentials not found at {CREDENTIALS_FILE}. Please obtain them from Google Cloud Console and place them in the backend directory.")
    
    try:
        # Authenticate
        gc = gspread.service_account(filename=CREDENTIALS_FILE)
        
        # Create a new spreadsheet
        sh = gc.create(sheet_name)
        
        # Share it with anyone with the link (so the user can view it easily)
        sh.share('', role='reader', type='anyone')
        
        worksheet = sh.sheet1
        worksheet.title = "Jobs"
        
        headers = [
            "Job Title",
            "Company",
            "Location",
            "Date Posted",
            "Job Type",
            "Description",
            "Apply Link",
            "Source URL",
            "Scraped At",
        ]
        
        # Prepare data rows
        rows = [headers]
        for job in jobs:
            row = [
                job.title,
                job.company,
                job.location,
                job.date_posted,
                job.job_type,
                job.description[:5000] if job.description else "",
                job.apply_link,
                job.source_url,
                job.scraped_at or "",
            ]
            rows.append(row)
            
        worksheet.append_rows(rows)
        
        # Format headers
        worksheet.format("A1:I1", {
            "backgroundColor": {"red": 0.3, "green": 0.6, "blue": 0.9},
            "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}}
        })
        
        logger.info(f"Successfully exported {len(jobs)} jobs to Google Sheet: {sh.id}")
        return f"https://docs.google.com/spreadsheets/d/{sh.id}/edit"
        
    except Exception as e:
        logger.error(f"Error exporting to Google Sheets: {e}")
        raise
