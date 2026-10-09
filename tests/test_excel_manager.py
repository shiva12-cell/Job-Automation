import os
from pathlib import Path
import pytest
from src.excel_manager import ExcelManager, EXCEL_HEADERS
from src.models import JobApplication, ApplicationStatus


def test_excel_manager_lifecycle(tmp_path):
    test_file = tmp_path / "test_tracker.xlsx"
    manager = ExcelManager(file_path=str(test_file))

    assert test_file.exists()

    app = JobApplication(
        app_id="EX-001",
        date_applied="2026-10-06",
        company="Swiggy",
        job_title="Data Analyst",
        location="Gurugram",
        platform="Naukri",
        status=ApplicationStatus.APPLIED,
        notes="Applied with 85% match",
    )

    manager.append_application(app, match_pct=85.0, follow_up_date="2026-10-10")

    rows = manager.get_all_rows()
    assert len(rows) == 1
    assert rows[0]["Company"] == "Swiggy"
    assert rows[0]["Job Title"] == "Data Analyst"
    assert rows[0]["Match %"] == "85%"
    assert rows[0]["Chance"] == "High"
    assert rows[0]["Follow-Up Date"] == "2026-10-10"

    # Verify is_already_applied detection
    assert manager.is_already_applied("Swiggy", "Data Analyst") is True
    assert manager.is_already_applied("swiggy", "data analyst") is True
    assert manager.is_already_applied("Google", "Data Analyst") is False

    # Attempt to append duplicate to same company & same designation
    app_dup = JobApplication(
        app_id="EX-002",
        date_applied="2026-10-06",
        company="Swiggy",
        job_title="Data Analyst",
        location="Gurugram",
        platform="Indeed",
        status=ApplicationStatus.APPLIED,
    )
    manager.append_application(app_dup)

    # Should still only be 1 row
    rows_after = manager.get_all_rows()
    assert len(rows_after) == 1


def test_excel_manager_manual_tab(tmp_path):
    test_file = tmp_path / "test_manual_tracker.xlsx"
    manager = ExcelManager(file_path=str(test_file))

    # 1. Job with match <= 80% should be skipped from Manual tab
    app_low = JobApplication(
        app_id="MAN-001",
        date_applied="2026-10-06",
        company="LowMatch Corp",
        job_title="Business Analyst",
        location="Bengaluru",
        platform="Naukri (Company Site)",
        status=ApplicationStatus.MANUAL_APPLY_NEEDED,
    )
    manager.append_manual_application(app_low, match_pct=75.0, chance="Mid")
    manual_rows = manager.get_all_rows(sheet_name="Manual")
    assert len(manual_rows) == 0

    # 2. Job with match > 80% should be added to Manual tab ONLY
    app_high = JobApplication(
        app_id="MAN-002",
        date_applied="2026-10-06",
        company="Zomato",
        job_title="Lead Data Analyst",
        location="Gurugram",
        job_url="https://zomato.careers/job/123",
        platform="Naukri (Company Site)",
        status=ApplicationStatus.MANUAL_APPLY_NEEDED,
    )
    manager.append_manual_application(app_high, match_pct=88.0, chance="High")

    # Verify present in Manual tab
    manual_rows = manager.get_all_rows(sheet_name="Manual")
    assert len(manual_rows) == 1
    assert manual_rows[0]["Company"] == "Zomato"
    assert manual_rows[0]["Match %"] == "88%"
    assert manual_rows[0]["Status"] == "Manual Apply Needed"
    assert manual_rows[0]["Chance"] == "High"

    # Verify strictly NOT included in 'All Applications', 'Naukri Jobs', or 'Indeed Jobs'
    all_rows = manager.get_all_rows(sheet_name="All Applications")
    assert len(all_rows) == 0
    naukri_rows = manager.get_all_rows(sheet_name="Naukri Jobs")
    assert len(naukri_rows) == 0
    indeed_rows = manager.get_all_rows(sheet_name="Indeed Jobs")
    assert len(indeed_rows) == 0

    # Verify duplicate prevention in Manual tab
    assert manager.is_already_in_manual("Zomato", "Lead Data Analyst") is True
    assert manager.is_already_in_manual("Swiggy", "Data Analyst") is False
    manager.append_manual_application(app_high, match_pct=90.0, chance="High")
    assert len(manager.get_all_rows(sheet_name="Manual")) == 1


def test_excel_manager_delete_and_reset(tmp_path):
    test_file = tmp_path / "test_reset_tracker.xlsx"
    manager = ExcelManager(file_path=str(test_file))

    app1 = JobApplication(
        app_id="DEL-001",
        date_applied="2026-10-06",
        company="Flipkart",
        job_title="Data Analyst",
        location="Bengaluru",
        platform="Naukri",
        status=ApplicationStatus.APPLIED,
    )
    app2 = JobApplication(
        app_id="DEL-002",
        date_applied="2026-10-06",
        company="Amazon",
        job_title="Business Analyst",
        location="Hyderabad",
        platform="Naukri",
        status=ApplicationStatus.APPLIED,
    )

    manager.append_application(app1)
    manager.append_application(app2)

    assert len(manager.get_all_rows(sheet_name="All Applications")) == 2
    assert len(manager.get_all_rows(sheet_name="Naukri Jobs")) == 2

    # 1. Test single entry deletion
    deleted = manager.delete_entry("DEL-001")
    assert deleted is True
    assert len(manager.get_all_rows(sheet_name="All Applications")) == 1
    assert len(manager.get_all_rows(sheet_name="Naukri Jobs")) == 1
    assert manager.get_all_rows(sheet_name="All Applications")[0]["Application ID"] == "DEL-002"

    # 2. Test backup and reset for specific sheet or all sheets
    backup_file = manager.backup_and_reset()
    assert backup_file != ""
    assert (tmp_path / backup_file).exists()

    # Data rows should now be empty while headers remain
    assert len(manager.get_all_rows(sheet_name="All Applications")) == 0
    assert len(manager.get_all_rows(sheet_name="Naukri Jobs")) == 0


def test_purge_manual_applications(tmp_path):
    excel_path = tmp_path / "test_purge.xlsx"
    manager = ExcelManager(file_path=excel_path)

    # Add 1 auto application
    app_auto = JobApplication(
        app_id="AUTO-001",
        date_applied="2026-10-08",
        company="Google",
        job_title="Data Analyst",
        location="Bengaluru",
        platform="Naukri.com",
        status=ApplicationStatus.APPLIED,
    )
    manager.append_application(app_auto)

    # Add 1 manual application
    app_manual = JobApplication(
        app_id="MAN-999",
        date_applied="2026-10-08",
        company="Manual Co",
        job_title="Data Analyst",
        location="Delhi",
        platform="Naukri (Company Site)",
        status=ApplicationStatus.MANUAL_APPLY_NEEDED,
    )
    manager.append_manual_application(app_manual, match_pct=90.0, chance="High")

    assert len(manager.get_all_rows(sheet_name="Manual")) == 1
    assert len(manager.get_all_rows(sheet_name="All Applications")) == 1

    purged = manager.purge_manual_applications()
    assert purged >= 1
    assert len(manager.get_all_rows(sheet_name="Manual")) == 0
    # Auto applied row is untouched
    assert len(manager.get_all_rows(sheet_name="All Applications")) == 1



