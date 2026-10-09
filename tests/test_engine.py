import pytest
from unittest.mock import patch, MagicMock
from src.autonomous_engine import AutonomousEngine
from src.excel_manager import ExcelManager


def test_engine_initialization(tmp_path):
    test_excel = tmp_path / "tracker.xlsx"
    with patch("src.autonomous_engine.ExcelManager") as mock_excel_cls:
        mock_instance = MagicMock()
        mock_instance.get_all_rows.return_value = [{"Company": "TestCo"}]
        mock_excel_cls.return_value = mock_instance

        engine = AutonomousEngine()
        assert engine.stats["total_applied"] == 1
        assert "avg_jobs_per_cycle" in engine.stats
        assert "cycle_duration_minutes" in engine.stats


def test_engine_run_pipeline_respects_limit(tmp_path):
    test_excel = tmp_path / "tracker_limit.xlsx"
    excel_mgr = ExcelManager(file_path=str(test_excel))

    from src.state_manager import SeenJobsManager
    seen_mgr = SeenJobsManager(file_path=str(tmp_path / "seen_limit.json"))
    engine = AutonomousEngine(excel_mgr=excel_mgr, seen_mgr=seen_mgr)
    engine.sheets_mgr = None
    engine.tracker = None
    engine.follow_up_mgr = None
    engine.notifier = None
    engine.stats["cycles_completed"] = 0

    mock_naukri_jobs = [
        {"title": f"Data Analyst {i}", "company": f"Comp{i}", "url": f"https://naukri.com/job{i}", "min_lpa": 5.0 + i, "description": "Python, SQL, Power BI, Excel"}
        for i in range(10)
    ]

    with patch("src.scraper.scrape_naukri_live_jobs", return_value=mock_naukri_jobs), \
         patch("src.scraper.scrape_indeed_live_jobs", return_value=[]), \
         patch("time.sleep"):

        # Test limit of 3 jobs
        res = engine.run_pipeline(max_limit=3, keyword="data analyst", duration_minutes=15, dry_run=True)
        assert res["applied"] == 3
        assert engine.stats["total_applied"] == 3
        assert engine.stats["avg_jobs_per_cycle"] == 3.0

        # Verify Chance column in Excel rows
        rows = excel_mgr.get_all_rows()
        assert len(rows) == 3
        for r in rows:
            assert r["Chance"] in ["High", "Mid"]


def test_engine_company_site_manual_sheet_routing(tmp_path):
    from src.models import JobApplication, ApplicationStatus
    test_excel = tmp_path / "tracker_manual.xlsx"
    excel_mgr = ExcelManager(file_path=str(test_excel))

    from src.state_manager import SeenJobsManager
    seen_mgr = SeenJobsManager(file_path=str(tmp_path / "seen_manual.json"))
    engine = AutonomousEngine(excel_mgr=excel_mgr, seen_mgr=seen_mgr)
    engine.sheets_mgr = None
    engine.notifier = None

    mock_jobs = [
        {
            "title": "Data Analyst (Analytics)",
            "company": "Amazon",
            "url": "https://naukri.com/amazon-job",
            "min_lpa": 8.0,
            "description": "Python, SQL, Power BI, Statistics, EDA, Machine Learning"  # High match > 80%
        },
        {
            "title": "Data Analyst Junior",
            "company": "Flipkart",
            "url": "https://naukri.com/flipkart-job",
            "min_lpa": 6.0,
            "description": "Python, SQL, Power BI"  # Direct apply match >= 65%
        }
    ]

    mock_applier_amazon = MagicMock()
    mock_applier_amazon.apply.return_value = JobApplication(
        app_id="MAN-AMZ-01",
        company="Amazon",
        job_title="Data Analyst (Analytics)",
        platform="Naukri (Company Site)",
        status=ApplicationStatus.MANUAL_APPLY_NEEDED,
        job_url="https://amazon.jobs/123",
    )

    mock_applier_flipkart = MagicMock()
    mock_applier_flipkart.apply.return_value = JobApplication(
        app_id="NAU-FLP-01",
        company="Flipkart",
        job_title="Data Analyst Junior",
        platform="Naukri.com",
        status=ApplicationStatus.APPLIED,
        job_url="https://naukri.com/flipkart-job",
    )

    def mock_get_applier(url, profile, **kwargs):
        if "amazon" in url:
            return mock_applier_amazon
        return mock_applier_flipkart

    with patch("src.scraper.scrape_naukri_live_jobs", return_value=mock_jobs), \
         patch("src.scraper.scrape_indeed_live_jobs", return_value=[]), \
         patch("src.autonomous_engine.get_applier_for_url", side_effect=mock_get_applier), \
         patch("time.sleep"):

        res = engine.run_pipeline(max_limit=10, keyword="data analyst", duration_minutes=10, dry_run=False)

        # 1. Only Flipkart should be counted towards applied total! Amazon must NOT be counted.
        assert res["applied"] == 1

        # 2. Unfilled external job must NOT be copied into sheets until filled (per manual-apply removal directive)
        manual_rows = excel_mgr.get_all_rows(sheet_name="Manual")
        assert len(manual_rows) == 0

        # 3. Only Flipkart is in 'All Applications'
        all_rows = excel_mgr.get_all_rows(sheet_name="All Applications")
        assert len(all_rows) == 1
        assert all_rows[0]["Company"] == "Flipkart"

        # 4. Amazon is recorded in seen cache with cooldown to prevent repetitive pagination copying
        assert seen_mgr.is_seen("https://naukri.com/amazon-job") is True


def test_engine_seen_cache_bypasses_cached_jobs(tmp_path):
    test_excel = tmp_path / "tracker_seen.xlsx"
    excel_mgr = ExcelManager(file_path=str(test_excel))

    from src.state_manager import SeenJobsManager
    seen_mgr = SeenJobsManager(file_path=str(tmp_path / "seen_bypass.json"))
    engine = AutonomousEngine(excel_mgr=excel_mgr, seen_mgr=seen_mgr)
    engine.sheets_mgr = None
    engine.notifier = None

    # Pre-populate seen cache with a specific job URL
    cached_url = "https://naukri.com/cached-job-1"
    new_url = "https://naukri.com/new-job-2"
    engine.seen_mgr.record_job(cached_url, "CachedCo", "Data Analyst", "APPLIED", 85.0)

    mock_jobs = [
        {
            "title": "Data Analyst",
            "company": "CachedCo",
            "url": cached_url,
            "min_lpa": 6.0,
            "description": "Python, SQL, Power BI",
            "is_direct_apply": True
        },
        {
            "title": "Data Analyst",
            "company": "NewCo",
            "url": new_url,
            "min_lpa": 7.0,
            "description": "Python, SQL, Power BI",
            "is_direct_apply": True
        }
    ]

    with patch("src.scraper.scrape_naukri_live_jobs", return_value=mock_jobs), \
         patch("src.scraper.scrape_indeed_live_jobs", return_value=[]), \
         patch("time.sleep"):

        res = engine.run_pipeline(max_limit=10, keyword="data analyst", duration_minutes=10, dry_run=True)
        # CachedCo was bypassed immediately by the seen cache, only NewCo is processed
        assert res["applied"] == 1
        all_rows = excel_mgr.get_all_rows(sheet_name="All Applications")
        assert len(all_rows) == 1
        assert all_rows[0]["Company"] == "NewCo"


