import pytest
from src.models import JobApplication, ApplicationStatus, CandidateProfile, CandidatePersonalInfo


def test_job_application_sheet_serialization():
    app = JobApplication(
        app_id="APP-001",
        date_applied="2026-10-06",
        company="Google",
        job_title="Staff Software Engineer",
        location="Mountain View, CA",
        job_url="https://google.com/jobs/123",
        platform="Direct",
        status=ApplicationStatus.INTERVIEW,
        last_updated="2026-10-06 12:00",
        gmail_thread_id="thread_xyz",
        notes="First round scheduled",
    )

    row = app.to_sheet_row()
    assert row[0] == "APP-001"
    assert row[2] == "Google"
    assert row[3] == "Staff Software Engineer"
    assert row[7] == "Interview Scheduled"

    # Test roundtrip
    restored = JobApplication.from_sheet_row(row)
    assert restored.app_id == app.app_id
    assert restored.company == app.company
    assert restored.job_title == app.job_title
    assert restored.status == ApplicationStatus.INTERVIEW
    assert restored.gmail_thread_id == "thread_xyz"
