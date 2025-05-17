"""
Tests for cross-dock views with Celery integration.

This module contains tests for the cross-dock views that use Celery for asynchronous processing.
"""

from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from cross_dock.models import CrossDockTask

User = get_user_model()


@pytest.fixture
def authenticated_user(client):
    """Create an authenticated user."""
    user = User.objects.create_user(username="testuser", password="testpass")
    client.login(username="testuser", password="testpass")
    return user


@pytest.fixture
def excel_file():
    """Create a simple Excel file for testing."""
    content = b"PK\x03\x04\x14\x00\x00\x00\x08\x00\x00\x00!\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    return SimpleUploadedFile(
        "test.xlsx", content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@pytest.mark.django_db
def test_process_file_view_with_celery(client, authenticated_user, excel_file):
    """Test that the process_file view creates a task and submits a Celery task."""
    with (
        mock.patch("cross_dock.views.process_file_task.delay") as mock_delay,
        mock.patch("cross_dock.services.clickhouse_service.get_clickhouse_client") as mock_client,
    ):
        # Mock ClickHouse client
        mock_client_instance = mock.MagicMock()
        mock_client_instance.__enter__.return_value.execute.return_value = [(1,)]
        mock_client.return_value = mock_client_instance

        # Mock Celery task
        mock_delay.return_value = mock.MagicMock(id="test-celery-task-id")

        # Make the request
        response = client.post(
            reverse("cross_dock:process_file"), {"file_upload": excel_file, "supplier_list": "ОПТ-2"}
        )

        # Check redirect
        assert response.status_code == 302
        assert response.url == reverse("cross_dock:task_list")

        # Check that a task was created
        assert CrossDockTask.objects.count() == 1
        task = CrossDockTask.objects.first()
        assert task.status == "PENDING"
        assert task.filename == "test.xlsx"
        assert task.supplier_group == "ОПТ-2"
        assert task.user == authenticated_user

        # Check that Celery task was called
        mock_delay.assert_called_once()
        args, kwargs = mock_delay.call_args
        assert kwargs["supplier_list"] == "ОПТ-2"
        assert kwargs["task_id"] == str(task.id)
        assert "file_path" in kwargs


@pytest.mark.django_db
def test_process_file_view_db_error(client, authenticated_user, excel_file):
    """Test that the process_file view handles database connection errors."""
    with (
        mock.patch("cross_dock.services.clickhouse_service.get_clickhouse_client") as mock_client,
        mock.patch("cross_dock.views.os.remove") as mock_remove,
    ):
        # Mock ClickHouse client to raise an exception
        mock_client_instance = mock.MagicMock()
        mock_client_instance.__enter__.side_effect = Exception("DB connection error")
        mock_client.return_value = mock_client_instance

        # Make the request
        response = client.post(
            reverse("cross_dock:process_file"), {"file_upload": excel_file, "supplier_list": "ОПТ-2"}
        )

        # Check redirect
        assert response.status_code == 302
        assert response.url == reverse("cross_dock:task_list")

        # Check that no task was created
        assert CrossDockTask.objects.count() == 0

        # Check that the file was cleaned up
        mock_remove.assert_called_once()


@pytest.mark.django_db
def test_task_detail_view(client, authenticated_user):
    """Test the task_detail view."""
    # Create a task
    task = CrossDockTask.objects.create(
        status="SUCCESS",
        filename="test.xlsx",
        supplier_group="ОПТ-2",
        user=authenticated_user,
        result_url="/media/exports/test_result.xlsx",
    )

    # Get the task detail page
    response = client.get(reverse("cross_dock:task_detail", kwargs={"task_id": task.id}))

    # Check response
    assert response.status_code == 200
    assert "task" in response.context
    assert response.context["task"] == task
    assert "comments" in response.context

    # Check that the task ID is in the content
    content = response.content.decode("utf-8")
    assert str(task.id) in content
    assert "test.xlsx" in content
    assert "ОПТ-2" in content
    assert "Success" in content


@pytest.mark.django_db
def test_task_detail_view_add_comment(client, authenticated_user):
    """Test adding a comment to a task."""
    # Create a task
    task = CrossDockTask.objects.create(
        status="SUCCESS",
        filename="test.xlsx",
        supplier_group="ОПТ-2",
        user=authenticated_user,
        result_url="/media/exports/test_result.xlsx",
    )

    # Add a comment
    response = client.post(
        reverse("cross_dock:task_detail", kwargs={"task_id": task.id}), {"comment_text": "Test comment"}
    )

    # Check redirect
    assert response.status_code == 302
    assert response.url == reverse("cross_dock:task_detail", kwargs={"task_id": task.id})

    # Check that the comment was added
    assert task.comments.count() == 1
    comment = task.comments.first()
    assert comment.text == "Test comment"
    assert comment.user == authenticated_user
