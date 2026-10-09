from unittest.mock import MagicMock
import pytest
from src.google_services.sheets_manager import SheetsManager, SHEET_HEADERS
from src.models import JobApplication, ApplicationStatus


@pytest.fixture
def mock_sheets_manager():
    mock_client = MagicMock()
    mock_spreadsheet = MagicMock()
    mock_worksheet = MagicMock()

    mock_client.open_by_key.return_value = mock_spreadsheet
    mock_spreadsheet.worksheet.return_value = mock_worksheet

    # Simulate existing sheet with header and one row
    mock_worksheet.get_all_values.return_value = [
        SHEET_HEADERS,
        [
            "APP-100",
            "2026-10-01",
            "Datadog",
            "Senior Backend Engineer",
            "Remote",
            "https://datadog.com/jobs/1",
            "Lever",
            "Applied",
            "2026-10-01 10:00",
            "thread-12345",
            "Applied via portal",
        ],
    ]

    manager = SheetsManager(mock_client, spreadsheet_id="test_sheet_id", worksheet_name="Job Applications")
    manager._worksheet = mock_worksheet
    return manager, mock_worksheet


def test_get_all_applications(mock_sheets_manager):
    manager, _ = mock_sheets_manager
    apps = manager.get_all_applications()
    assert len(apps) == 1
    row_idx, app = apps[0]
    assert row_idx == 2
    assert app.company == "Datadog"
    assert app.status == ApplicationStatus.APPLIED


def test_find_matching_application_by_thread(mock_sheets_manager):
    manager, _ = mock_sheets_manager
    match = manager.find_matching_application(company="Datadog", thread_id="thread-12345")
    assert match is not None
    row_idx, app = match
    assert row_idx == 2
    assert app.company == "Datadog"


def test_find_matching_application_by_company(mock_sheets_manager):
    manager, _ = mock_sheets_manager
    match = manager.find_matching_application(company="Datadog Inc")
    assert match is not None
    row_idx, app = match
    assert row_idx == 2


def test_update_application_status(mock_sheets_manager):
    manager, mock_worksheet = mock_sheets_manager
    mock_worksheet.acell.return_value.value = "Applied via portal"

    manager.update_application_status(
        row_idx=2,
        new_status=ApplicationStatus.INTERVIEW,
        notes_addition="Interview scheduled for next Tuesday",
        gmail_thread_id="thread-12345",
    )

    assert mock_worksheet.batch_update.called
    updates = mock_worksheet.batch_update.call_args[0][0]
    # Check that status was updated to 'Interview Scheduled'
    assert any(u["range"] == "H2" and u["values"] == [["Interview Scheduled"]] for u in updates)
