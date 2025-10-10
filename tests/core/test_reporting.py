import time
from unittest.mock import Mock, patch

import pytest

from core.reporting import ProgressReporter, ReportStatus


@pytest.fixture
def mock_task():
    """Provides a mock task object with an update_state method."""
    task = Mock()
    task.update_state = Mock()
    return task


def test_report_step_basic_payload(mock_task):
    """Verify the basic payload shape for a step report."""
    reporter = ProgressReporter(task=mock_task)
    reporter.report_step(step="Test Step", status=ReportStatus.IN_PROGRESS)

    mock_task.update_state.assert_called_once()
    call_args = mock_task.update_state.call_args
    assert call_args.kwargs["state"] == "PROGRESS"
    assert call_args.kwargs["meta"] == {
        "step": "Test Step",
        "status": "IN_PROGRESS",
        "sub_step_name": None,
        "sub_step_index": None,
    }


def test_report_step_full_payload(mock_task):
    """Verify payload with all optional parameters."""
    reporter = ProgressReporter(task=mock_task)
    details_dict = {"error_code": 123}
    reporter.report_step(
        step="Complex Step",
        status=ReportStatus.SUCCESS,
        sub_step_name="Sub-process A",
        sub_step_index=0,
        details=details_dict,
        message="All good",
    )

    mock_task.update_state.assert_called_once()
    call_args = mock_task.update_state.call_args
    assert call_args.kwargs["meta"] == {
        "step": "Complex Step",
        "status": "SUCCESS",
        "sub_step_name": "Sub-process A",
        "sub_step_index": 0,
        "details": {"error_code": 123, "message": "All good"},
    }


def test_report_step_message_creates_details(mock_task):
    """Check that providing only a message creates the details dictionary."""
    reporter = ProgressReporter(task=mock_task)
    reporter.report_step(step="Info Step", status=ReportStatus.IN_PROGRESS, message="Just a message")

    mock_task.update_state.assert_called_once()
    call_args = mock_task.update_state.call_args
    assert call_args.kwargs["meta"]["details"] == {"message": "Just a message"}


def test_report_percentage_payload(mock_task):
    """Verify the payload for a percentage progress report."""
    reporter = ProgressReporter(task=mock_task)
    reporter.report_percentage(step="INSERTING", progress=50)

    mock_task.update_state.assert_called_once()
    call_args = mock_task.update_state.call_args
    assert call_args.kwargs["meta"] == {
        "step": "INSERTING",
        "status": "IN_PROGRESS",
        "progress": 50,
    }


def test_report_failure_payload(mock_task):
    """Verify that report_failure sends the correct status and details."""
    reporter = ProgressReporter(task=mock_task)
    error_details = {"reason": "External API timeout"}
    reporter.report_failure(step="API Call", details=error_details)

    mock_task.update_state.assert_called_once()
    call_args = mock_task.update_state.call_args
    assert call_args.kwargs["meta"] == {
        "step": "API Call",
        "status": "FAILURE",
        "sub_step_name": None,
        "sub_step_index": None,
        "details": {"reason": "External API timeout"},
    }


def test_finalize_returns_correct_structure():
    """Verify the structure of the final result payload."""
    reporter = ProgressReporter(task=Mock())
    result_data = {"files_processed": 1, "errors": 0}
    final_payload = reporter.finalize(result=result_data)

    assert final_payload == {
        "status": "COMPLETE",
        "result": {"files_processed": 1, "errors": 0},
    }


@patch("time.sleep")
def test_reporter_sleeps_when_delay_is_set(mock_sleep, mock_task):
    """Verify that time.sleep is called when a delay is configured."""
    reporter = ProgressReporter(task=mock_task, delay_between_report_steps_sec=0.5)
    reporter.report_step(step="Delayed Step", status=ReportStatus.IN_PROGRESS)

    mock_sleep.assert_called_once_with(0.5)


@patch("time.sleep")
def test_reporter_does_not_sleep_by_default(mock_sleep, mock_task):
    """Verify that time.sleep is NOT called by default."""
    reporter = ProgressReporter(task=mock_task)
    reporter.report_step(step="Quick Step", status=ReportStatus.IN_PROGRESS)

    mock_sleep.assert_not_called()


def test_custom_state_name(mock_task):
    """Verify that a custom state name is used when provided."""
    reporter = ProgressReporter(task=mock_task, state_name="CUSTOM_STATE")
    reporter.report_step(step="Custom State Step", status=ReportStatus.SUCCESS)

    mock_task.update_state.assert_called_once()
    call_args = mock_task.update_state.call_args
    assert call_args.kwargs["state"] == "CUSTOM_STATE"
