import smtplib
from email.message import EmailMessage
import logging
from typing import List
import asyncio

from config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, SMTP_USE_TLS
from models import JobListing

logger = logging.getLogger("indeed_scraper")

def send_alert_email_sync(to_email: str, keyword: str, matched_jobs: List[JobListing]):
    """Synchronously send an email using smtplib."""
    if not SMTP_USER or not SMTP_PASSWORD:
        logger.warning(f"Cannot send email to {to_email}. SMTP credentials not configured.")
        return

    from_email = SMTP_FROM if SMTP_FROM else SMTP_USER
    
    msg = EmailMessage()
    msg['Subject'] = f"Job Alert: {len(matched_jobs)} new jobs for '{keyword}'"
    msg['From'] = from_email
    msg['To'] = to_email

    # Plain text content
    content = f"Found {len(matched_jobs)} new job(s) matching your alert for '{keyword}':\n\n"
    for job in matched_jobs:
        content += f"- {job.title} at {job.company}\n"
        content += f"  Location: {job.location}\n"
        content += f"  Link: {job.apply_link if job.apply_link else job.source_url}\n\n"
    
    msg.set_content(content)

    # HTML content
    html_content = f"<h2>Found {len(matched_jobs)} new job(s) matching your alert for '{keyword}'</h2><ul>"
    for job in matched_jobs:
        link = job.apply_link if job.apply_link else job.source_url
        html_content += f"<li><b>{job.title}</b> at {job.company}<br>Location: {job.location}<br><a href='{link}'>Apply Here</a></li>"
    html_content += "</ul>"
    
    msg.add_alternative(html_content, subtype='html')

    try:
        if SMTP_USE_TLS:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
        logger.info(f"Alert email sent successfully to {to_email} for keyword '{keyword}'")
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")

async def send_alert_email(to_email: str, keyword: str, matched_jobs: List[JobListing]):
    """Run the synchronous email sending in a background thread."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, send_alert_email_sync, to_email, keyword, matched_jobs)
