import os
import json
import pytest
from unittest.mock import MagicMock
from pathlib import Path

from src.models import CandidateProfile, ApplicationStatus
from src.config import load_candidate_profile
from src.applier.submission_resolver import (
    NaukriSubmissionResolver,
    SubmissionResult,
    FAILURES_LOG_FILE,
)


@pytest.fixture
def profile():
    return load_candidate_profile()


@pytest.fixture
def resolver(profile):
    return NaukriSubmissionResolver(profile)


def test_submission_result_to_dict():
    res = SubmissionResult(
        success=True,
        attempt_used=1,
        status=ApplicationStatus.APPLIED,
        verification_source="ACP_URL_NAVIGATION",
        notes="Landed on confirmation page",
    )
    d = res.to_dict()
    assert d["success"] is True
    assert d["attempt_used"] == 1
    assert d["status"] == "Applied"
    assert d["verification_source"] == "ACP_URL_NAVIGATION"


def test_field_solver_heuristics(resolver):
    assert resolver._solve_field_value("years of experience in data analytics") == "0"
    assert resolver._solve_field_value("notice period days required") == "0"
    assert resolver._solve_field_value("current ctc in inr") == "0"
    assert resolver._solve_field_value("expected ctc in lpa") == "6"
    assert resolver._solve_field_value("current city location") == "Gurugram"
    assert resolver._solve_field_value("college or university") == "JECRC UNIVERSITY"


def test_verify_status_acp_url(resolver):
    mock_page = MagicMock()
    mock_page.url = "https://www.naukri.com/myapply/showAcp?jquery=1&file=221124503740"
    mock_page.evaluate.return_value = "You have successfully applied to Data Analyst"
    mock_page.query_selector.return_value = None

    is_confirmed, source, note = resolver._verify_application_status(mock_page, [])
    assert is_confirmed is True
    assert source == "ACP_URL_NAVIGATION"


def test_verify_status_redirect_to_company_site(resolver):
    mock_page = MagicMock()
    mock_page.url = "https://www.naukri.com/myapply/showAcp?file=123"
    mock_page.evaluate.return_value = "You were redirected to the company website for completing your job application"
    mock_page.query_selector.return_value = None

    is_confirmed, source, note = resolver._verify_application_status(mock_page, [])
    assert is_confirmed is False
    assert source == "REDIRECTED_TO_COMPANY_SITE"


def test_verify_status_network_api(resolver):
    mock_page = MagicMock()
    mock_page.url = "https://www.naukri.com/job-listings-test-123"
    mock_page.query_selector.return_value = None

    signals = [{
        "url": "https://www.naukri.com/cloudgateway-workflow/workflow-services/apply-workflow/v1",
        "status": 200,
        "body": '{"statusCode": 0, "jobs": [{"status": 200, "message": "You have successfully applied to this job."}]}',
    }]

    is_confirmed, source, note = resolver._verify_application_status(mock_page, signals)
    assert is_confirmed is True
    assert source == "NETWORK_API_OK"


def test_verify_status_dom_applied_badge(resolver):
    mock_page = MagicMock()
    mock_page.url = "https://www.naukri.com/job-listings-test-123"
    mock_badge = MagicMock()
    mock_badge.is_visible.return_value = True
    mock_badge.inner_text.return_value = "Applied"
    mock_page.query_selector.side_effect = lambda sel: mock_badge if "#already-applied" in sel or "Applied" in sel else None

    is_confirmed, source, note = resolver._verify_application_status(mock_page, [])
    assert is_confirmed is True
    assert source == "DOM_APPLIED_BADGE"


def test_dry_run_resolution(resolver):
    mock_page = MagicMock()
    res = resolver.resolve_submission(
        page=mock_page,
        company="Acme Corp",
        job_title="Data Analyst",
        job_url="https://www.naukri.com/job-123",
        dry_run=True,
    )
    assert res.success is True
    assert res.attempt_used == 0
    assert res.verification_source == "DRY_RUN"


def test_collect_failure_data(resolver, tmp_path):
    mock_page = MagicMock()
    mock_page.url = "https://www.naukri.com/job-failed-123"
    mock_page.evaluate.side_effect = [
        [{"className": "modal-dialog", "innerText": "Please answer questions"}],
        [{"tag": "INPUT", "type": "text", "name": "custom_q", "value": ""}],
    ]

    record = resolver._collect_failure_data(
        page=mock_page,
        company="TestCompany",
        job_title="Analyst",
        job_url="https://www.naukri.com/job-failed-123",
        screenshot_path="scratch/fail.png",
        attempts_log=[{"attempt": 1, "error": "No button"}],
        network_signals=[],
    )

    assert record["company"] == "TestCompany"
    assert record["job_title"] == "Analyst"
    assert len(record["active_modals"]) == 1
    assert len(record["unfilled_inputs"]) == 1
    assert FAILURES_LOG_FILE.exists()
