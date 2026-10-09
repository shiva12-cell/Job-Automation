import pytest
from unittest.mock import MagicMock, patch
from src.autonomous_engine import AutonomousEngine
from src.excel_manager import ExcelManager
from src.state_manager import SeenJobsManager
from src.models import JobApplication, ApplicationStatus

def test_company_site_only_mode_filters_direct_jobs(tmp_path):
    test_excel = tmp_path / "tracker_pathway.xlsx"
    excel_mgr = ExcelManager(file_path=str(test_excel))
    seen_mgr = SeenJobsManager(file_path=str(tmp_path / "seen_pathway.json"))
    engine = AutonomousEngine(excel_mgr=excel_mgr, seen_mgr=seen_mgr)
    engine.sheets_mgr = None
    engine.notifier = None

    mock_jobs = [
        {
            "title": "Data Analyst (Direct Role)",
            "company": "DirectCorp",
            "url": "https://naukri.com/direct-job",
            "min_lpa": 6.0,
            "description": "Python, SQL, Power BI, Statistics",
            "is_direct_apply": True
        },
        {
            "title": "Data Analyst (Portal Role)",
            "company": "PortalCorp",
            "url": "https://naukri.com/portal-job",
            "min_lpa": 7.0,
            "description": "Python, SQL, Tableau, Statistics",
            "is_direct_apply": True
        }
    ]

    mock_direct_applier = MagicMock()
    # Simulates applier discovering it's a Direct Apply posting and bypassing when in company_site_only mode
    mock_direct_applier.apply.return_value = JobApplication(
        app_id="SKIP-01",
        company="DirectCorp",
        job_title="Data Analyst (Direct Role)",
        platform="Naukri.com",
        status=ApplicationStatus.SKIPPED,
        job_url="https://naukri.com/direct-job",
        notes="Skipped: Direct Apply posting while in Company Site Only mode"
    )

    mock_portal_applier = MagicMock()
    # Simulates successful automated submission on company website
    mock_portal_applier.apply.return_value = JobApplication(
        app_id="ACW-PORTAL-01",
        company="PortalCorp",
        job_title="Data Analyst (Portal Role)",
        platform="Naukri (Company Site)",
        status=ApplicationStatus.APPLIED,
        job_url="https://portalcorp.jobs/apply",
        notes="Automated Company Site application (85% match)"
    )

    def mock_get_applier(url, profile, **kwargs):
        if "direct" in url:
            return mock_direct_applier
        return mock_portal_applier

    with patch("src.scraper.scrape_naukri_live_jobs", return_value=mock_jobs), \
         patch("src.scraper.scrape_indeed_live_jobs", return_value=[]), \
         patch("src.autonomous_engine.get_applier_for_url", side_effect=mock_get_applier), \
         patch("time.sleep"):

        res = engine.run_pipeline(
            max_limit=10,
            keyword="data analyst",
            duration_minutes=10,
            dry_run=False,
            apply_mode="company_site_only"
        )

        # 1. Only PortalCorp should be counted as applied
        assert res["applied"] == 1

        # 2. PortalCorp is recorded in ACW sheet
        wb = excel_mgr._load_workbook()
        acw_sheet = [s for s in wb.sheetnames if s.startswith("ACW(")][0]
        acw_rows = excel_mgr.get_all_rows(sheet_name=acw_sheet)
        assert len(acw_rows) == 1
        assert acw_rows[0]["Company"] == "PortalCorp"
        assert acw_rows[0]["Status"] == "Applied"

        # 3. DirectCorp was bypassed without being copied into any sheet
        all_rows = excel_mgr.get_all_rows(sheet_name="All Applications")
        assert len(all_rows) == 1
        assert all_rows[0]["Company"] == "PortalCorp"

def test_unfilled_company_site_never_copied_to_sheets(tmp_path):
    test_excel = tmp_path / "tracker_unfilled.xlsx"
    excel_mgr = ExcelManager(file_path=str(test_excel))
    seen_mgr = SeenJobsManager(file_path=str(tmp_path / "seen_unfilled.json"))
    engine = AutonomousEngine(excel_mgr=excel_mgr, seen_mgr=seen_mgr)
    engine.sheets_mgr = None
    engine.notifier = None

    mock_jobs = [
        {
            "title": "Data Analyst (Captcha Portal)",
            "company": "CaptchaCorp",
            "url": "https://naukri.com/captcha-job",
            "min_lpa": 8.0,
            "description": "Python, SQL, Power BI, Statistics, EDA, Machine Learning"
        }
    ]

    mock_captcha_applier = MagicMock()
    # Simulates external company website requiring CAPTCHA or candidate login wall
    mock_captcha_applier.apply.return_value = JobApplication(
        app_id="ACW-CAPTCHA-01",
        company="CaptchaCorp",
        job_title="Data Analyst (Captcha Portal)",
        platform="Company Portal (CAPTCHA)",
        status=ApplicationStatus.MANUAL_APPLY_NEEDED,
        job_url="https://captchacorp.jobs/apply",
        notes="Form pre-filled. CAPTCHA verification required"
    )

    with patch("src.scraper.scrape_naukri_live_jobs", return_value=mock_jobs), \
         patch("src.scraper.scrape_indeed_live_jobs", return_value=[]), \
         patch("src.autonomous_engine.get_applier_for_url", return_value=mock_captcha_applier), \
         patch("time.sleep"):

        res = engine.run_pipeline(
            max_limit=10,
            keyword="data analyst",
            duration_minutes=10,
            dry_run=False,
            apply_mode="all"
        )

        # 1. 0 applied
        assert res["applied"] == 0

        # 2. No unfilled row in All Applications
        all_rows = excel_mgr.get_all_rows(sheet_name="All Applications")
        assert len(all_rows) == 0

        # 3. No row in Manual sheet
        manual_rows = excel_mgr.get_all_rows(sheet_name="Manual")
        assert len(manual_rows) == 0

        # 4. Seen cache records cooldown to prevent infinite pagination duplicate copies
        assert seen_mgr.is_seen("https://naukri.com/captcha-job") is True
