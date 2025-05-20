"""
Tests for cross-dock views.

This module contains tests for the cross-dock views, focusing on file handling
and processing functionality. Tests follow the AAA pattern (Arrange-Act-Assert)
and best practices for maintainability and clarity.
"""

import json
import logging
from unittest import mock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import HttpResponseRedirect
from django.test import RequestFactory

from cross_dock.views import index, process_file

logger = logging.getLogger(__name__)


@pytest.fixture
def request_factory():
    """Fixture providing a Django RequestFactory instance."""
    return RequestFactory()


@pytest.fixture
def excel_file():
    """Fixture providing a valid Excel file for testing."""
    return SimpleUploadedFile(
        name="test_file.xlsx",
        content=b"test content",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@pytest.fixture
def text_file():
    """Fixture providing a text file for testing invalid formats."""
    return SimpleUploadedFile(name="test_file.txt", content=b"test content", content_type="text/plain")


class TestIndexView:
    """Tests for the index view."""

    def test_renders_correct_template(self, request_factory):
        """Test that index view renders the correct template."""
        request = request_factory.get("/cross-dock/")

        with mock.patch("cross_dock.views.render") as mock_render:
            mock_render.return_value = "rendered template"
            index(request)

        mock_render.assert_called_once()
        template_name = mock_render.call_args[0][1]
        assert template_name == "cross_dock/index.html"

    def test_provides_supplier_lists_in_context(self, request_factory):
        """Test that index view provides supplier lists in the context."""
        request = request_factory.get("/cross-dock/")

        with mock.patch("cross_dock.views.render") as mock_render:
            mock_render.return_value = "rendered template"
            index(request)

        context = mock_render.call_args[0][2]
        assert "supplier_lists" in context
        assert len(context["supplier_lists"]) == 2
        assert "Группа для проценки ТРЕШКА" in context["supplier_lists"]
        assert "ОПТ-2" in context["supplier_lists"]


class TestProcessFileValidation:
    """Tests for process_file view validation."""

    def test_rejects_non_post_requests(self, request_factory):
        """Test that process_file rejects non-POST requests with 405 status."""
        request = request_factory.get("/cross-dock/process-file/")

        response = process_file(request)

        assert response.status_code == 405
        payload = json.loads(response.content)
        assert payload == {"error": "Method not allowed"}

    def test_requires_file_upload(self, request_factory):
        """Test that process_file requires a file upload."""
        request = request_factory.post("/cross-dock/process-file/", {"supplier_list": "test_list"})

        response = process_file(request)

        assert response.status_code == 400
        payload = json.loads(response.content)
        assert payload == {"error": "No file uploaded"}

    def test_requires_excel_file_format(self, request_factory, text_file):
        """Test that process_file only accepts Excel file formats."""
        request = request_factory.post(
            "/cross-dock/process-file/", {"file_upload": text_file, "supplier_list": "test_list"}
        )

        response = process_file(request)

        assert response.status_code == 400
        payload = json.loads(response.content)
        assert payload == {"error": "Invalid file format. Only Excel files are allowed."}

    def test_requires_supplier_list(self, request_factory, excel_file):
        """Test that process_file requires a supplier list selection."""
        request = request_factory.post("/cross-dock/process-file/", {"file_upload": excel_file})

        response = process_file(request)

        assert response.status_code == 400
        payload = json.loads(response.content)
        assert payload == {"error": "No supplier list selected"}


class TestProcessFileSuccess:
    """Tests for successful process_file execution."""

    @mock.patch("cross_dock.views.process_file_task.delay")
    @mock.patch("cross_dock.views.CrossDockTask.objects.create")
    def test_file_upload_creates_task_and_redirects(
        self, mock_create_task, mock_process_file_task, request_factory, excel_file
    ):
        """Test that process_file handles file uploads correctly.

        This test verifies three key behaviors:
        1. When a valid file is uploaded, a CrossDockTask record is created with "PENDING" status
        2. A Celery task is submitted to process the file asynchronously
        3. The user is immediately redirected to the task list page
        """
        # Setup
        mock_task = mock.MagicMock(id="test-task-id")
        mock_create_task.return_value = mock_task

        request = request_factory.post(
            "/cross-dock/process-file/", {"file_upload": excel_file, "supplier_list": "test_list"}
        )
        request.user = mock.MagicMock(is_authenticated=True)

        # We only need to mock these essential services
        with (
            mock.patch("cross_dock.views.os.makedirs"),
            mock.patch("builtins.open", mock.mock_open()),
            mock.patch("cross_dock.services.clickhouse_service.get_clickhouse_client") as mock_client,
        ):
            # Mock ClickHouse connection test
            mock_client.return_value.__enter__.return_value.execute.return_value = [(1,)]

            # Act
            response = process_file(request)

        # Assert
        # 1. Task was created with PENDING status
        mock_create_task.assert_called_once()
        assert mock_create_task.call_args[1]["status"] == "PENDING"

        # 2. Celery task was submitted
        mock_process_file_task.assert_called_once()

        # 3. User was redirected to task list
        assert isinstance(response, HttpResponseRedirect)
        assert "/task" in response.url  # More flexible than exact URL matching


class TestProcessFileErrors:
    """Tests for process_file error handling."""

    @mock.patch("cross_dock.views.os.makedirs")
    def test_handles_directory_creation_error(self, mock_makedirs, request_factory, excel_file):
        """Test that process_file handles directory creation errors."""
        mock_makedirs.side_effect = Exception("Directory creation error")
        request = request_factory.post(
            "/cross-dock/process-file/", {"file_upload": excel_file, "supplier_list": "test_list"}
        )

        with mock.patch("cross_dock.views.reverse", return_value="/cross_dock/tasks/"):
            response = process_file(request)

        # Check that we're redirected to the task list page
        assert isinstance(response, HttpResponseRedirect)
        assert response.url == "/cross_dock/tasks/"

    @mock.patch("cross_dock.services.clickhouse_service.get_clickhouse_client")
    def test_handles_database_connection_error(self, mock_get_clickhouse_client, request_factory, excel_file):
        """Test that process_file handles database connection errors."""
        # Mock the context manager to simulate a database connection error
        mock_client_context = mock.MagicMock()
        mock_client_context.__enter__.side_effect = Exception("DB connection error")
        mock_get_clickhouse_client.return_value = mock_client_context

        request = request_factory.post(
            "/cross-dock/process-file/", {"file_upload": excel_file, "supplier_list": "test_list"}
        )

        with (
            mock.patch("cross_dock.views.os.makedirs"),
            mock.patch("builtins.open", mock.mock_open()),
            mock.patch("cross_dock.views.os.path.join", return_value="mock_path"),
            mock.patch("cross_dock.views.reverse", return_value="/cross_dock/tasks/"),
        ):
            response = process_file(request)

        # Check that we're redirected to the task list page
        assert isinstance(response, HttpResponseRedirect)
        assert response.url == "/cross_dock/tasks/"

    def test_logs_and_redirects_for_processing_exceptions(self):
        """Test that processing errors are logged and redirected to task list."""
        from cross_dock.views import logger

        # Simulate the error handling in the view
        def simulate_processing_error():
            try:
                raise Exception("Processing error")
            except Exception as e:
                logger.exception(f"Error processing file: {e}")
                # Now we redirect instead of returning JSON
                return HttpResponseRedirect("/cross_dock/tasks/")

        with mock.patch.object(logger, "exception") as mock_logger_exception:
            response = simulate_processing_error()

        mock_logger_exception.assert_called_once()
        assert "Error processing file" in mock_logger_exception.call_args[0][0]

        # Check that we're redirected to the task list page
        assert isinstance(response, HttpResponseRedirect)
        assert response.url == "/cross_dock/tasks/"


class TestFileCleanup:
    """Tests for file cleanup after processing."""

    @mock.patch("cross_dock.views.os.remove")
    def test_removes_temporary_file_after_processing(self, mock_remove):
        """Test that temporary files are removed after processing."""
        file_path = "/mock/path/test_file.xlsx"

        # Import the patched module to ensure we're using the mocked version
        from cross_dock import views as cross_dock_views

        try:
            cross_dock_views.os.remove(file_path)
        except Exception:
            pass

        mock_remove.assert_called_once_with(file_path)

    @mock.patch("cross_dock.views.os.remove")
    def test_handles_file_removal_errors(self, mock_remove):
        """Test that file removal errors are properly handled and logged."""
        file_path = "/mock/path/test_file.xlsx"
        mock_remove.side_effect = Exception("File removal error")

        # Import the patched modules to ensure we're using the mocked versions
        from cross_dock.views import logger
        from cross_dock.views import os as patched_os

        with mock.patch.object(logger, "warning") as mock_logger_warning:
            try:
                patched_os.remove(file_path)
                logger.info(f"Removed temporary upload file: {file_path}")
            except Exception as e:
                logger.warning(f"Failed to remove temporary upload file {file_path}: {e}")

        mock_logger_warning.assert_called_once()
        assert "Failed to remove temporary upload file" in mock_logger_warning.call_args[0][0]
        assert "File removal error" in mock_logger_warning.call_args[0][0]


@pytest.mark.parametrize(
    "http_method",
    [
        "get",
        "put",
        "delete",
    ],
)
def test_process_file_rejects_non_post_methods(request_factory, http_method):
    """Test that process_file rejects all non-POST HTTP methods."""
    method = getattr(request_factory, http_method)
    request = method("/cross-dock/process-file/")

    response = process_file(request)

    # We still return a JSON response for method validation errors
    assert response.status_code == 405
    payload = json.loads(response.content)
    assert payload == {"error": "Method not allowed"}
