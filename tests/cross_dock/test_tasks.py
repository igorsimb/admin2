"""
Tests for cross-dock Celery tasks.

This module contains tests for the Celery tasks used in the cross-dock app.
"""

import os
import tempfile
import uuid
from unittest import mock

import pandas as pd
import pytest
from django.conf import settings
from django.contrib.auth import get_user_model

from cross_dock.models import CrossDockTask
from cross_dock.tasks import process_file_task

User = get_user_model()


@pytest.fixture
def sample_excel_file():
    """Create a sample Excel file for testing."""
    # Create a temporary file
    fd, path = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)

    # Create a sample DataFrame
    df = pd.DataFrame({"Бренд": ["TOYOTA", "NISSAN", "HONDA"], "Артикул": ["12345", "67890", "ABCDE"]})

    # Save to Excel
    df.to_excel(path, index=False)

    yield path

    # Clean up
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def task_record():
    """Create a sample task record."""
    user = User.objects.create(username="testuser")
    task = CrossDockTask.objects.create(status="PENDING", filename="test.xlsx", user=user)
    yield task
    task.delete()
    user.delete()


@pytest.mark.django_db
def test_process_file_task_success(sample_excel_file, task_record):
    """Test successful file processing."""
    with mock.patch("cross_dock.services.excel_service.process_cross_dock_data_from_file") as mock_process:
        # Setup mock
        output_path = os.path.join(settings.MEDIA_ROOT, "exports", f"result_{uuid.uuid4()}.xlsx")
        mock_process.return_value = output_path

        # Call the task
        result = process_file_task(sample_excel_file, "ОПТ-2", str(task_record.id))

        # Assertions
        assert result["status"] == "success"
        assert "output_url" in result

        # Check that the task was updated
        task_record.refresh_from_db()
        assert task_record.status == "SUCCESS"
        assert task_record.result_url is not None


@pytest.mark.django_db
def test_process_file_task_failure(sample_excel_file, task_record):
    """Test file processing failure."""
    with mock.patch("cross_dock.tasks.process_cross_dock_data_from_file") as mock_process:
        # Setup mock to raise an exception
        mock_process.side_effect = Exception("Test error")

        # Call the task and expect it to raise an exception
        with pytest.raises(Exception) as excinfo:
            process_file_task(sample_excel_file, "ОПТ-2", str(task_record.id))

        # Verify the exception message
        assert "Test error" in str(excinfo.value)

        # Check that the task was marked as failed
        task_record.refresh_from_db()
        assert task_record.status == "FAILURE"
        assert "Test error" in task_record.error_message
