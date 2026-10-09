"""
Unit tests for Category Wise sheets in Excel and Google Sheets.
Tests detect_job_category, green/orange styling, and sync_all_category_sheets.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock
from src.models import JobApplication, ApplicationStatus, JobCategory, detect_job_category, CATEGORY_HEADERS
from src.excel_manager import ExcelManager, CATEGORY_SHEETS


def test_detect_job_category_mappings():
    assert detect_job_category("Senior Data Analyst") == JobCategory.DATA_ANALYST.value
    assert detect_job_category("BI & Analytics Engineer") == JobCategory.DATA_ANALYST.value
    assert detect_job_category("Tableau Developer") == JobCategory.DATA_ANALYST.value
    assert detect_job_category("MIS Executive") == JobCategory.DATA_ANALYST.value

    assert detect_job_category("Business Analyst") == JobCategory.BUSINESS_ANALYST.value
    assert detect_job_category("Operations Analyst") == JobCategory.BUSINESS_ANALYST.value
    assert detect_job_category("Strategy Analyst") == JobCategory.BUSINESS_ANALYST.value

    assert detect_job_category("AI Product Owner") == JobCategory.AI_PRODUCT.value
    assert detect_job_category("Associate Product Manager") == JobCategory.AI_PRODUCT.value

    assert detect_job_category("Data Engineer") == JobCategory.DATA_ENGINEERING.value
    assert detect_job_category("Data Scientist (ML)") == JobCategory.DATA_ENGINEERING.value

    assert detect_job_category("Full Stack Developer") == JobCategory.OTHER.value


def test_excel_category_sheets_creation_and_styling(tmp_path):
    test_file = tmp_path / "test_cat_tracker.xlsx"
    em = ExcelManager(file_path=str(test_file))

    # All category sheets must exist
    wb = em._load_workbook(data_only=True)
    for cat in CATEGORY_SHEETS:
        assert cat in wb.sheetnames
        ws = wb[cat]
        headers = [c.value for c in ws[1]]
        assert headers == CATEGORY_HEADERS
    wb.close()

    # Append an Auto Applied application (should be Green in category tab)
    auto_app = JobApplication(
        app_id="AUTO-001",
        company="Zomato",
        job_title="Data Analyst",
        platform="Naukri.com",
        status=ApplicationStatus.APPLIED,
        notes="Auto-applied match 90%"
    )
    em.append_application(auto_app, match_pct=90.0, chance="High")

    # Append a Manual application (should be Orange in category tab)
    man_app = JobApplication(
        app_id="MAN-002",
        company="Uber",
        job_title="Business Analyst",
        platform="Company Site",
        status=ApplicationStatus.MANUAL_APPLY_NEEDED,
        notes="Manual apply needed"
    )
    em.append_manual_application(man_app, match_pct=85.0, chance="High")

    # Verify rows in category sheets
    da_rows = em.get_all_rows(JobCategory.DATA_ANALYST.value)
    assert len(da_rows) == 1
    assert da_rows[0]["Company"] == "Zomato"
    assert da_rows[0]["Apply Mode"] == "Auto Applied"

    ba_rows = em.get_all_rows(JobCategory.BUSINESS_ANALYST.value)
    assert len(ba_rows) == 1
    assert ba_rows[0]["Company"] == "Uber"
    assert ba_rows[0]["Apply Mode"] == "Manual"

    # Verify stats
    stats = em.get_category_stats()
    assert stats[JobCategory.DATA_ANALYST.value]["total"] == 1
    assert stats[JobCategory.DATA_ANALYST.value]["auto_applied"] == 1
    assert stats[JobCategory.DATA_ANALYST.value]["manual"] == 0

    assert stats[JobCategory.BUSINESS_ANALYST.value]["total"] == 1
    assert stats[JobCategory.BUSINESS_ANALYST.value]["auto_applied"] == 0
    assert stats[JobCategory.BUSINESS_ANALYST.value]["manual"] == 1


def test_excel_sync_all_category_sheets(tmp_path):
    test_file = tmp_path / "test_sync_cat.xlsx"
    em = ExcelManager(file_path=str(test_file))

    records = [
        {"app_id": "A1", "company": "Company A", "job_title": "Data Analyst", "apply_mode": "Auto Applied"},
        {"app_id": "A2", "company": "Company B", "job_title": "Data Analyst", "apply_mode": "Manual"},
        {"app_id": "B1", "company": "Company C", "job_title": "Business Analyst", "apply_mode": "Auto Applied"},
        {"app_id": "C1", "company": "Company D", "job_title": "Data Engineer", "apply_mode": "Auto Applied"},
    ]

    counts = em.sync_all_category_sheets(records)
    assert counts[JobCategory.DATA_ANALYST.value] == 2
    assert counts[JobCategory.BUSINESS_ANALYST.value] == 1
    assert counts[JobCategory.DATA_ENGINEERING.value] == 1

    stats = em.get_category_stats()
    assert stats[JobCategory.DATA_ANALYST.value]["auto_applied"] == 1
    assert stats[JobCategory.DATA_ANALYST.value]["manual"] == 1
