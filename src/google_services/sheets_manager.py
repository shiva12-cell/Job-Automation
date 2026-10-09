"""
Google Sheets Manager.
Handles reading, creating, and updating job applications in Google Sheets.
"""

import re
from datetime import datetime
from typing import List, Optional, Tuple, Dict, Any
import gspread
from gspread.exceptions import WorksheetNotFound
from src.models import (
    ApplicationStatus,
    JobApplication,
    JobCategory,
    CATEGORY_HEADERS,
    detect_job_category,
    is_manual_application,
)

# Expected column headers in Google Sheets
SHEET_HEADERS = [
    "Application ID",
    "Date Applied",
    "Company",
    "Job Title",
    "Location",
    "Job URL",
    "Platform",
    "Status",
    "Last Updated",
    "Gmail Thread ID",
    "Notes",
]

CATEGORY_SHEETS = [
    JobCategory.DATA_ANALYST.value,
    JobCategory.BUSINESS_ANALYST.value,
    JobCategory.AI_PRODUCT.value,
    JobCategory.DATA_ENGINEERING.value,
    JobCategory.OTHER.value,
]

# Color themes for Category headers in Google Sheets
CATEGORY_HEADER_COLORS = {
    JobCategory.DATA_ANALYST.value: {"red": 0.12, "green": 0.31, "blue": 0.47},        # Navy
    JobCategory.BUSINESS_ANALYST.value: {"red": 0.04, "green": 0.35, "blue": 0.79},    # Deep Blue
    JobCategory.AI_PRODUCT.value: {"red": 0.29, "green": 0.0, "blue": 0.51},          # Indigo / Violet
    JobCategory.DATA_ENGINEERING.value: {"red": 0.0, "green": 0.37, "blue": 0.45},      # Teal / Cyan
    JobCategory.OTHER.value: {"red": 0.29, "green": 0.33, "blue": 0.41},               # Slate
}

# Soft Green background for Auto Applied & Soft Orange for Manual
COLOR_GREEN_ROW = {"red": 0.88, "green": 0.96, "blue": 0.89}   # #E2F0D9
COLOR_ORANGE_ROW = {"red": 0.99, "green": 0.89, "blue": 0.84}  # #FCE4D6
COLOR_GREEN_TEXT = {"red": 0.0, "green": 0.38, "blue": 0.0}    # #006100
COLOR_ORANGE_TEXT = {"red": 0.61, "green": 0.39, "blue": 0.0}  # #9C6500


class SheetsManager:
    """Manages CRUD operations on Google Sheets for Job Applications."""

    def __init__(self, gspread_client: gspread.Client, spreadsheet_id: str, worksheet_name: str = "Job Applications"):
        self.client = gspread_client
        # Extract clean spreadsheet ID if user supplied full Google Sheet URL
        if "spreadsheets/d/" in spreadsheet_id:
            match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", spreadsheet_id)
            if match:
                spreadsheet_id = match.group(1)
        self.spreadsheet_id = spreadsheet_id.strip()
        self.worksheet_name = worksheet_name
        self._sheet: Optional[gspread.Spreadsheet] = None
        self._worksheet: Optional[gspread.Worksheet] = None

    @property
    def sheet(self) -> gspread.Spreadsheet:
        """Lazily initialize and return the spreadsheet."""
        if self._sheet is None:
            self._sheet = self.client.open_by_key(self.spreadsheet_id)
        return self._sheet

    @property
    def worksheet(self) -> gspread.Worksheet:
        """Lazily initialize and return the worksheet."""
        if self._worksheet is None:
            self._ensure_worksheet()
        return self._worksheet

    def _ensure_worksheet(self) -> None:
        """Finds or creates the worksheet and formats header columns if needed."""
        self._sheet = self.client.open_by_key(self.spreadsheet_id)
        try:
            self._worksheet = self._sheet.worksheet(self.worksheet_name)
        except WorksheetNotFound:
            print(f"Worksheet '{self.worksheet_name}' not found. Creating it...")
            self._worksheet = self._sheet.add_worksheet(
                title=self.worksheet_name, rows=1000, cols=len(SHEET_HEADERS)
            )

        # Check existing headers
        existing_values = self._worksheet.get_all_values()
        if not existing_values or existing_values[0] != SHEET_HEADERS:
            if not existing_values:
                self._worksheet.append_row(SHEET_HEADERS)
            else:
                # Update top row
                self._worksheet.update("A1:K1", [SHEET_HEADERS])

            # Apply pretty formatting to headers
            try:
                self._worksheet.format("A1:K1", {
                    "textFormat": {"bold": True, "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}},
                    "backgroundColor": {"red": 0.12, "green": 0.44, "blue": 0.70},
                    "horizontalAlignment": "CENTER",
                })
                self._worksheet.freeze(rows=1)
            except Exception as e:
                print(f"[Notice] Header styling skipped: {e}")

    def get_all_applications(self) -> List[Tuple[int, JobApplication]]:
        """
        Returns all applications currently in the sheet along with their 1-based row index.
        Row indices start from 2 (since row 1 is header).
        """
        all_rows = self.worksheet.get_all_values()
        if len(all_rows) <= 1:
            return []

        apps = []
        for idx, row in enumerate(all_rows[1:], start=2):
            if not any(row):  # Skip empty rows
                continue
            try:
                app = JobApplication.from_sheet_row(row)
                apps.append((idx, app))
            except Exception as e:
                print(f"[Warning] Failed to parse row {idx}: {e}")
        return apps

    def is_already_applied(self, company: str, job_title: str) -> bool:
        """Returns True if an application with matching company and job title already exists in the sheet."""
        match = self.find_matching_application(company=company, job_title=job_title)
        return match is not None

    def add_application(self, app: JobApplication) -> int:
        """
        Appends a new application to the Google Sheet if not already present.
        Returns the row index.
        """
        existing = self.find_matching_application(company=app.company, job_title=app.job_title)
        if existing:
            row_idx, _ = existing
            return row_idx

        row_data = app.to_sheet_row()
        self.worksheet.append_row(row_data, value_input_option="USER_ENTERED")
        
        # Also sync to corresponding Category worksheet with GREEN styling
        try:
            self.append_to_category_worksheet(app, apply_mode="Auto Applied")
        except Exception:
            pass

        return len(self.worksheet.get_all_values())

    def get_manual_worksheet(self) -> gspread.Worksheet:
        """Finds or creates the 'Manual' worksheet in Google Sheets."""
        if self._sheet is None:
            self._sheet = self.client.open_by_key(self.spreadsheet_id)
        try:
            ws = self._sheet.worksheet("Manual")
        except WorksheetNotFound:
            ws = self._sheet.add_worksheet(title="Manual", rows=500, cols=len(SHEET_HEADERS))
            ws.append_row(SHEET_HEADERS)
            try:
                ws.format("A1:K1", {
                    "textFormat": {"bold": True, "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}},
                    "backgroundColor": {"red": 0.77, "green": 0.35, "blue": 0.07},
                    "horizontalAlignment": "CENTER",
                })
                ws.freeze(rows=1)
            except Exception:
                pass
        return ws

    def add_manual_application(self, app: JobApplication) -> int:
        """
        Appends an application to the 'Manual' Google Sheet tab.
        Strictly separated from the main 'Job Applications' tab.
        """
        m_ws = self.get_manual_worksheet()
        all_vals = m_ws.get_all_values()
        clean_comp = app.company.strip().lower()
        clean_title = app.job_title.strip().lower()

        # Check for duplicates in Manual sheet
        if len(all_vals) > 1:
            for r in all_vals[1:]:
                if len(r) >= 4:
                    c = r[2].strip().lower()
                    t = r[3].strip().lower()
                    if (clean_comp == c or clean_comp in c or c in clean_comp) and (clean_title == t or clean_title in t or t in clean_title):
                        return -1

        row_data = app.to_sheet_row()
        m_ws.append_row(row_data, value_input_option="USER_ENTERED")

        # Also sync to corresponding Category worksheet with ORANGE styling
        try:
            self.append_to_category_worksheet(app, apply_mode="Manual")
        except Exception:
            pass

        return len(m_ws.get_all_values())

    def get_category_worksheet(self, category: str) -> gspread.Worksheet:
        """Finds or creates a Job Category worksheet in Google Sheets with styled headers."""
        if self._sheet is None:
            self._sheet = self.client.open_by_key(self.spreadsheet_id)
        try:
            ws = self._sheet.worksheet(category)
        except WorksheetNotFound:
            ws = self._sheet.add_worksheet(title=category, rows=500, cols=len(CATEGORY_HEADERS))
            ws.append_row(CATEGORY_HEADERS)
            color = CATEGORY_HEADER_COLORS.get(category, {"red": 0.12, "green": 0.31, "blue": 0.47})
            try:
                ws.format("A1:P1", {
                    "textFormat": {"bold": True, "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}},
                    "backgroundColor": color,
                    "horizontalAlignment": "CENTER",
                })
                ws.freeze(rows=1)
            except Exception:
                pass
        return ws

    def append_to_category_worksheet(
        self,
        app: JobApplication,
        apply_mode: str = "Auto Applied",
        match_pct: str = "85%",
        chance: str = "High",
        follow_up_date: str = ""
    ) -> None:
        """Appends an application to its categorized Google Sheet tab with green/orange styling."""
        cat_name = detect_job_category(app.job_title, app.notes)
        c_ws = self.get_category_worksheet(cat_name)

        # Check for duplicates
        clean_comp = app.company.strip().lower()
        clean_title = app.job_title.strip().lower()
        all_vals = c_ws.get_all_values()
        if len(all_vals) > 1:
            for r in all_vals[1:]:
                if len(r) >= 4:
                    c = r[2].strip().lower()
                    t = r[3].strip().lower()
                    if (clean_comp == c or clean_comp in c or c in clean_comp) and (clean_title == t or clean_title in t or t in clean_title):
                        return

        row_data = [
            app.app_id,
            app.date_applied or datetime.now().strftime("%Y-%m-%d"),
            app.company,
            app.job_title,
            cat_name,
            app.location,
            app.job_url,
            app.platform,
            app.status.value,
            apply_mode,
            match_pct,
            chance,
            app.last_updated or datetime.now().strftime("%Y-%m-%d %H:%M"),
            follow_up_date,
            app.gmail_thread_id,
            app.notes,
        ]
        c_ws.append_row(row_data, value_input_option="USER_ENTERED")
        row_idx = len(c_ws.get_all_values())

        # Format row: Green for Auto Applied, Orange for Manual
        is_auto = "auto" in apply_mode.lower()
        row_color = COLOR_GREEN_ROW if is_auto else COLOR_ORANGE_ROW
        text_color = COLOR_GREEN_TEXT if is_auto else COLOR_ORANGE_TEXT
        try:
            c_ws.format(f"A{row_idx}:P{row_idx}", {
                "backgroundColor": row_color,
            })
            c_ws.format(f"I{row_idx}:J{row_idx}", {
                "textFormat": {"bold": True, "foregroundColor": text_color},
            })
        except Exception:
            pass

    def sync_all_category_sheets(self, unified_records: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Populates all 5 Job Category sheets in Google Sheets in batch with green/orange styling.
        """
        if self._sheet is None:
            self._sheet = self.client.open_by_key(self.spreadsheet_id)

        # Group by category
        by_cat: Dict[str, List[Dict[str, Any]]] = {c: [] for c in CATEGORY_SHEETS}
        for item in unified_records:
            title = item.get("job_title", "")
            comp = item.get("company", "")
            if not title or not comp:
                continue
            cat = detect_job_category(title, item.get("notes", ""))
            by_cat.setdefault(cat, []).append(item)

        counts = {}
        for cat_name, items in by_cat.items():
            ws = self.get_category_worksheet(cat_name)
            header_color = CATEGORY_HEADER_COLORS.get(cat_name, {"red": 0.12, "green": 0.31, "blue": 0.47})

            # Prepare rows
            rows_data = [CATEGORY_HEADERS]
            for item in items:
                title = item.get("job_title", "")
                comp = item.get("company", "")
                apply_mode = item.get("apply_mode", "Auto Applied")
                rows_data.append([
                    item.get("app_id", ""),
                    item.get("date_applied", datetime.now().strftime("%Y-%m-%d")),
                    comp,
                    title,
                    cat_name,
                    item.get("location", "India"),
                    item.get("job_url", ""),
                    item.get("platform", "Naukri.com"),
                    item.get("status", "Applied"),
                    apply_mode,
                    item.get("match_pct", "85%"),
                    item.get("chance", "High"),
                    item.get("last_updated", datetime.now().strftime("%Y-%m-%d %H:%M")),
                    item.get("follow_up_date", ""),
                    item.get("gmail_thread_id", ""),
                    item.get("notes", ""),
                ])

            # Clear worksheet and write all rows in one shot
            ws.clear()
            ws.update(values=rows_data, range_name=f"A1:P{len(rows_data)}", value_input_option="USER_ENTERED")

            # Format Header
            try:
                ws.format("A1:P1", {
                    "textFormat": {"bold": True, "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}},
                    "backgroundColor": header_color,
                    "horizontalAlignment": "CENTER",
                })
                ws.freeze(rows=1)
            except Exception:
                pass

            # Format data rows in batch
            batch_formats = []
            for idx, item in enumerate(items, start=2):
                apply_mode = item.get("apply_mode", "Auto Applied")
                is_auto = "auto" in apply_mode.lower()
                row_color = COLOR_GREEN_ROW if is_auto else COLOR_ORANGE_ROW
                text_color = COLOR_GREEN_TEXT if is_auto else COLOR_ORANGE_TEXT
                batch_formats.append({
                    "range": f"A{idx}:P{idx}",
                    "format": {"backgroundColor": row_color}
                })
                batch_formats.append({
                    "range": f"I{idx}:J{idx}",
                    "format": {"textFormat": {"bold": True, "foregroundColor": text_color}}
                })

            if batch_formats:
                try:
                    ws.batch_format(batch_formats)
                except Exception as e:
                    print(f"[Sheets Warning] Category batch format note for {cat_name}: {e}")

            counts[cat_name] = len(items)

        return counts

    def find_matching_application(
        self,
        company: str,
        job_title: Optional[str] = None,
        thread_id: Optional[str] = None
    ) -> Optional[Tuple[int, JobApplication]]:
        """
        Finds an existing application by Gmail Thread ID, or by matching company name.
        """
        apps = self.get_all_applications()
        clean_company = company.strip().lower()

        # 1. Match by thread ID if provided
        if thread_id:
            for row_idx, app in apps:
                if app.gmail_thread_id and app.gmail_thread_id.strip() == thread_id.strip():
                    return (row_idx, app)

        # 2. Match by exact or partial company name
        for row_idx, app in apps:
            app_comp = app.company.strip().lower()
            if not app_comp:
                continue

            # Check if company names are substrings or match
            if clean_company == app_comp or clean_company in app_comp or app_comp in clean_company:
                # If job title provided, verify it loosely matches
                if job_title and app.job_title:
                    clean_title = job_title.strip().lower()
                    app_title = app.job_title.strip().lower()
                    if clean_title in app_title or app_title in clean_title or "engineer" in clean_title:
                        return (row_idx, app)
                return (row_idx, app)

        return None

    def update_application_status(
        self,
        row_idx: int,
        new_status: ApplicationStatus,
        notes_addition: Optional[str] = None,
        gmail_thread_id: Optional[str] = None,
    ) -> None:
        """
        Updates the status, last updated timestamp, and notes for a given row.
        """
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")

        # Column indices (1-based):
        # 8: Status, 9: Last Updated, 10: Gmail Thread ID, 11: Notes
        status_cell = f"H{row_idx}"
        last_updated_cell = f"I{row_idx}"
        thread_id_cell = f"J{row_idx}"
        notes_cell = f"K{row_idx}"

        updates = [
            {"range": status_cell, "values": [[new_status.value]]},
            {"range": last_updated_cell, "values": [[current_time]]},
        ]

        if gmail_thread_id:
            updates.append({"range": thread_id_cell, "values": [[gmail_thread_id]]})

        if notes_addition:
            # Fetch existing notes to append rather than overwrite
            existing_note = self.worksheet.acell(notes_cell).value or ""
            updated_note = f"{existing_note} | {notes_addition}".strip(" |")
            updates.append({"range": notes_cell, "values": [[updated_note]]})

        self.worksheet.batch_update(updates)
        print(f"[Sheets] Updated row {row_idx} -> Status: {new_status.value}")
