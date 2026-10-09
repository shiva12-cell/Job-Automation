import pytest
from pathlib import Path
from src.state_manager import SeenJobsManager


@pytest.fixture
def temp_seen_manager(tmp_path):
    file_path = tmp_path / "test_seen_jobs.json"
    return SeenJobsManager(file_path=file_path)


def test_record_and_is_seen(temp_seen_manager):
    url = "https://www.naukri.com/job-listings-data-analyst-12345"
    assert not temp_seen_manager.is_seen(url)

    temp_seen_manager.record_job(
        url=url,
        company="Acme Corp",
        title="Data Analyst",
        status="APPLIED",
        match_pct=85.0
    )

    assert temp_seen_manager.is_seen(url)
    # Check normalized url matching
    assert temp_seen_manager.is_seen(url + "?source=srp&k=test")


def test_pagination_cursor_advance(temp_seen_manager):
    kw = "data analyst"
    assert temp_seen_manager.get_cursor(kw) == 1

    p2 = temp_seen_manager.advance_cursor(kw, max_pages=3)
    assert p2 == 2
    assert temp_seen_manager.get_cursor(kw) == 2

    p3 = temp_seen_manager.advance_cursor(kw, max_pages=3)
    assert p3 == 3

    # Wraps around
    p1 = temp_seen_manager.advance_cursor(kw, max_pages=3)
    assert p1 == 1


def test_keyword_rotation(temp_seen_manager):
    kws = ["data analyst", "business analyst", "product owner"]
    first = temp_seen_manager.get_next_rotated_keyword(kws)
    second = temp_seen_manager.get_next_rotated_keyword(kws)
    third = temp_seen_manager.get_next_rotated_keyword(kws)
    fourth = temp_seen_manager.get_next_rotated_keyword(kws)

    assert first == "data analyst"
    assert second == "business analyst"
    assert third == "product owner"
    assert fourth == "data analyst"


def test_purge_manual_seen_jobs(temp_seen_manager):
    temp_seen_manager.record_job("https://test.com/1", "CompA", "Role", "APPLIED")
    temp_seen_manager.record_job("https://test.com/2", "CompB", "Role", "MANUAL_SAVED")
    temp_seen_manager.record_job("https://test.com/3", "CompC", "Role", "MANUAL_SAVED")

    assert temp_seen_manager.is_seen("https://test.com/2") is True
    assert len(temp_seen_manager.data["seen_jobs"]) == 3

    purged = temp_seen_manager.purge_manual_seen_jobs()
    assert purged == 2
    assert len(temp_seen_manager.data["seen_jobs"]) == 1
    assert "https://test.com/1" in temp_seen_manager.data["seen_jobs"]
    assert "https://test.com/2" not in temp_seen_manager.data["seen_jobs"]

