"""
Automated 4-Day Follow-Up Sender via Gmail API.
Detects applications submitted 4 or more days ago without updates and sends a polite inquiry.
"""

import base64
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from googleapiclient.discovery import Resource
from src.models import CandidateProfile, JobApplication, ApplicationStatus
from src.google_services.sheets_manager import SheetsManager
from src.excel_manager import ExcelManager


class FollowUpSender:
    """Manages scheduling and sending 4-day polite follow-up emails for applied jobs."""

    def __init__(
        self,
        gmail_service: Resource,
        profile: CandidateProfile,
        sheets_manager: Optional[SheetsManager] = None,
        excel_manager: Optional[ExcelManager] = None,
    ):
        self.gmail = gmail_service
        self.profile = profile
        self.sheets = sheets_manager
        self.excel = excel_manager

    def find_eligible_applications(self, applications: List[JobApplication]) -> List[JobApplication]:
        """Filters applications that are >= 4 days old and have no updates or previous follow-up."""
        eligible = []
        now = datetime.now()

        for app in applications:
            # Only follow up on active 'Applied' or 'Under Review' status
            if app.status not in [ApplicationStatus.APPLIED, ApplicationStatus.UNDER_REVIEW]:
                continue

            # Check if already followed up
            if "follow-up sent" in app.notes.lower() or "followed up" in app.notes.lower():
                continue

            # Parse date_applied
            try:
                applied_dt = datetime.strptime(app.date_applied, "%Y-%m-%d")
                days_elapsed = (now - applied_dt).days
                if days_elapsed >= 4:
                    eligible.append(app)
            except Exception:
                continue

        return eligible

    def create_follow_up_email(self, app: JobApplication) -> MIMEText:
        """Constructs a polite, professional follow-up email."""
        candidate = self.profile.personal_info
        subject = f"Following up: Application for {app.job_title} - {candidate.full_name}"

        body = f"""Dear Hiring Team at {app.company},

I hope this message finds you well.

I am writing to follow up on my application for the {app.job_title} position submitted on {app.date_applied}. 

I remain very excited about this opportunity and believe my background in Data Analysis, SQL, Python, and BI dashboards aligns well with your team's goals.

Please let me know if there are any additional details, portfolio links, or questions I can provide to support my application.

Thank you very much for your time and consideration.

Best regards,
{candidate.full_name}
{candidate.phone} | {candidate.email}
LinkedIn: {candidate.linkedin_url or ''}
"""
        message = MIMEText(body)
        message["to"] = f"jobs@{app.company.lower().replace(' ', '')}.com"
        message["from"] = candidate.email
        message["subject"] = subject
        return message

    def process_and_send_follow_ups(self, applications: List[JobApplication], dry_run: bool = False) -> int:
        """
        Sends automated follow-ups for all eligible applications and records notes.
        """
        eligible = self.find_eligible_applications(applications)
        if not eligible:
            print("[Follow-Up] No applications currently requiring 4-day follow-up.")
            return 0

        sent_count = 0
        today_str = datetime.now().strftime("%Y-%m-%d")

        for app in eligible:
            print(f"[Follow-Up] Preparing 4-day follow-up for: {app.company} - {app.job_title} (Applied: {app.date_applied})")

            if dry_run:
                print(f"[Follow-Up] DRY RUN: Would send polite follow-up email for {app.company}.")
                sent_count += 1
                continue

            try:
                msg = self.create_follow_up_email(app)
                raw_bytes = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
                send_payload = {"raw": raw_bytes}

                # If thread ID exists, append to thread
                if app.gmail_thread_id:
                    send_payload["threadId"] = app.gmail_thread_id

                self.gmail.users().messages().send(userId="me", body=send_payload).execute()
                print(f"[Follow-Up] ✓ Sent follow-up email for {app.company}!")

                # Update notes in Google Sheet
                note_update = f"Follow-up sent on {today_str}"
                if self.sheets:
                    match = self.sheets.find_matching_application(app.company, app.job_title, app.gmail_thread_id)
                    if match:
                        row_idx, _ = match
                        self.sheets.update_application_status(
                            row_idx=row_idx,
                            new_status=app.status,
                            notes_addition=note_update,
                        )

                app.notes = f"{app.notes} | {note_update}".strip(" |")
                sent_count += 1
            except Exception as e:
                print(f"[Follow-Up Error] Could not send email for {app.company}: {e}")

        return sent_count
