"""
Gmail Tracker & Google Sheets Auto-Updater.
Scans inbox for job application emails and automatically updates Google Sheet rows.
"""

import base64
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from googleapiclient.discovery import Resource
from src.models import ApplicationStatus, EmailJobEvent, JobApplication
from src.parser.email_classifier import EmailClassifier
from src.google_services.sheets_manager import SheetsManager


class GmailTracker:
    """Monitors Gmail for job application communications and synchronizes with Google Sheets."""

    def __init__(
        self,
        gmail_service: Resource,
        sheets_manager: SheetsManager,
        processed_label: Optional[str] = "JobTracker/Processed",
    ):
        self.gmail = gmail_service
        self.sheets = sheets_manager
        self.processed_label = processed_label
        self._label_id: Optional[str] = None

    def _ensure_label_exists(self) -> Optional[str]:
        """Creates or gets the Gmail label ID used to tag processed messages."""
        if not self.processed_label:
            return None
        if self._label_id:
            return self._label_id

        try:
            results = self.gmail.users().labels().list(userId="me").execute()
            labels = results.get("labels", [])
            for lbl in labels:
                if lbl["name"].lower() == self.processed_label.lower():
                    self._label_id = lbl["id"]
                    return self._label_id

            # Create new label
            created = (
                self.gmail.users()
                .labels()
                .create(userId="me", body={"name": self.processed_label})
                .execute()
            )
            self._label_id = created["id"]
            return self._label_id
        except Exception as e:
            print(f"[Warning] Could not manage Gmail label: {e}")
            return None

    def _decode_body(self, payload: Dict[str, Any]) -> str:
        """Recursively decodes message payload body (text/plain or text/html)."""
        body_text = ""

        if "parts" in payload:
            for part in payload["parts"]:
                body_text += self._decode_body(part)
        else:
            data = payload.get("body", {}).get("data")
            if data:
                try:
                    decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                    body_text += decoded
                except Exception:
                    pass

        return body_text

    def fetch_job_emails(
        self,
        lookback_days: int = 14,
        max_results: int = 50,
        custom_query: Optional[str] = None,
    ) -> List[EmailJobEvent]:
        """
        Queries Gmail for recent job-related messages and returns parsed EmailJobEvents.
        """
        after_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y/%m/%d")

        # Build query
        base_query = (
            f"after:{after_date} ("
            f'subject:("thank you for applying" OR "application received" OR "application confirmation" '
            f'OR "application sent" OR "application submitted" OR "recruiter viewed" OR "shortlisted" '
            f'OR "interview" OR "next steps" OR "offer" OR "status of your application" OR "update on your application" '
            f'OR "unfortunately" OR "regret to inform") '
            f"OR from:(naukri.com OR naukrialerts.com OR mailer.naukri.com OR indeed.com OR indeedapply.com OR greenhouse.io OR lever.co OR myworkday.com OR smartrecruiters.com OR ashbyhq.com)"
            f")"
        )
        query = custom_query or base_query

        print(f"[Gmail] Querying messages with filter: {query}")
        events: List[EmailJobEvent] = []

        try:
            response = (
                self.gmail.users()
                .messages()
                .list(userId="me", q=query, maxResults=max_results)
                .execute()
            )
            messages = response.get("messages", [])

            print(f"[Gmail] Found {len(messages)} potential matching messages.")

            for item in messages:
                msg_id = item["id"]
                msg = (
                    self.gmail.users()
                    .messages()
                    .get(userId="me", id=msg_id, format="full")
                    .execute()
                )

                payload = msg.get("payload", {})
                headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}

                subject = headers.get("subject", "")
                sender = headers.get("from", "")
                date_str = headers.get("date", "")
                thread_id = msg.get("threadId", "")

                # Decode date
                try:
                    from email.utils import parsedate_to_datetime
                    date_received = parsedate_to_datetime(date_str)
                except Exception:
                    date_received = datetime.now()

                body_text = self._decode_body(payload)
                if not body_text:
                    body_text = msg.get("snippet", "")

                event = EmailClassifier.parse_message(
                    message_id=msg_id,
                    thread_id=thread_id,
                    date_received=date_received,
                    sender=sender,
                    subject=subject,
                    body_text=body_text,
                )

                if event:
                    events.append(event)

        except Exception as e:
            print(f"[Error] Failed to fetch emails from Gmail: {e}")

        return events

    def sync_to_sheets(self, lookback_days: int = 14) -> Dict[str, int]:
        """
        Fetches job emails and updates or creates corresponding rows in Google Sheets.
        Returns counts of updated and newly added records.
        """
        events = self.fetch_job_emails(lookback_days=lookback_days)
        updated_count = 0
        added_count = 0

        # Sort events chronologically so latest status wins
        events.sort(key=lambda x: x.date_received)

        for event in events:
            match = self.sheets.find_matching_application(
                company=event.detected_company,
                job_title=event.detected_job_title,
                thread_id=event.thread_id,
            )

            note_entry = f"[{event.date_received.strftime('%b %d')}] {event.status.value}: {event.subject}"

            if match:
                row_idx, existing_app = match
                # Update if status changed or thread ID missing
                if existing_app.status != event.status or not existing_app.gmail_thread_id:
                    self.sheets.update_application_status(
                        row_idx=row_idx,
                        new_status=event.status,
                        notes_addition=note_entry,
                        gmail_thread_id=event.thread_id,
                    )
                    updated_count += 1
            else:
                # Add as a newly discovered application
                new_app = JobApplication(
                    app_id=f"AUTO-{event.message_id[:8]}",
                    date_applied=event.date_received.strftime("%Y-%m-%d"),
                    company=event.detected_company,
                    job_title=event.detected_job_title or "Position Applied",
                    platform="Auto-Detected (Email)",
                    status=event.status,
                    gmail_thread_id=event.thread_id,
                    notes=note_entry,
                )
                self.sheets.add_application(new_app)
                print(f"[Sheets] Added new auto-detected application: {new_app.company} - {new_app.job_title} ({new_app.status.value})")
                added_count += 1

        print(f"\n[Sync Completed] {updated_count} applications updated, {added_count} new applications added.")
        return {"updated": updated_count, "added": added_count}
