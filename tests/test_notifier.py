from unittest.mock import MagicMock
import pytest
from src.self_notifier import SelfNotifier
from src.models import CandidateProfile, CandidatePersonalInfo, JobApplication, ApplicationStatus


@pytest.fixture
def mock_notifier():
    mock_gmail = MagicMock()
    # Mock label list
    mock_gmail.users().labels().list().execute.return_value = {
        "labels": [{"id": "Label_123", "name": "Job Applied"}]
    }
    # Mock message send
    mock_gmail.users().messages().send().execute.return_value = {"id": "msg_999"}
    # Mock message modify
    mock_gmail.users().messages().modify().execute.return_value = {"id": "msg_999"}

    profile = CandidateProfile(
        personal_info=CandidatePersonalInfo(
            first_name="Shiva",
            last_name="Upadhyay",
            email="shivaupadhyay8829@gmail.com",
            phone="+91 7668559852",
            location="Any Location",
        )
    )

    notifier = SelfNotifier(mock_gmail, profile, label_name="Job Applied")
    return notifier, mock_gmail


def test_notifier_sends_email_and_applies_label(mock_notifier):
    notifier, mock_gmail = mock_notifier

    app = JobApplication(
        app_id="TEST-001",
        date_applied="2026-10-06",
        company="Swiggy",
        job_title="Data Analyst",
        platform="Naukri",
        status=ApplicationStatus.APPLIED,
    )

    success = notifier.send_applied_notification(
        app=app,
        match_pct=75.0,
        matched_skills=["python", "sql", "excel"]
    )

    assert success is True
    # Verify send was called
    assert mock_gmail.users().messages().send.called
    # Verify modify was called to attach the label
    assert mock_gmail.users().messages().modify.called
    modify_args = mock_gmail.users().messages().modify.call_args[1]
    assert modify_args["body"]["addLabelIds"] == ["Label_123"]
