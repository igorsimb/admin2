"""
Tests for cross-dock views with Celery integration.

This module contains tests for the cross-dock views that use Celery for asynchronous processing.
"""

from io import BytesIO
from types import SimpleNamespace
from unittest import mock

import pytest
from clickhouse_connect.driver.httpclient import HttpClient
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from openpyxl import Workbook

from cross_dock.models import CrossDockTask

User = get_user_model()


@pytest.fixture
def excel_file():
    """Create a simple Excel file for testing."""
    workbook = Workbook()
    workbook.active.append(["Бренд", "Артикул"])
    workbook.active.append(["BOSCH", 12345])
    stream = BytesIO()
    workbook.save(stream)
    return SimpleUploadedFile(
        "test.xlsx", stream.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


def test_process_file_view_with_celery(client, authenticated_user, excel_file):
    """Test that the process_file view creates a task and submits a Celery task."""
    with (
        mock.patch("cross_dock.views.process_file_task.delay") as mock_delay,
        mock.patch("common.utils.clickhouse.get_clickhouse_client") as mock_client,
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

        mock_client.assert_not_called()

        # Check that a task was created
        assert CrossDockTask.objects.count() == 1
        task = CrossDockTask.objects.first()
        assert task.status == "PENDING"
        assert task.filename == "test.xlsx"
        assert task.supplier_group == "ОПТ-2"
        assert task.user == authenticated_user

        # Check that Celery task was called
        mock_delay.assert_called_once()
        kwargs = mock_delay.call_args.kwargs
        assert kwargs["supplier_list"] == "ОПТ-2"
        assert kwargs["task_id"] == str(task.id)
        assert "file_path" in kwargs


@pytest.mark.parametrize(
    ("use_mv", "failure_stage"),
    [(mode, stage) for mode in ("0", "1") for stage in ("normalization", "connection", "suppliers", "offers")],
)
def test_clickhouse_failure_remains_visible_in_task_list(
    client, authenticated_user, excel_file, settings, tmp_path, use_mv, failure_stage
):
    settings.MEDIA_ROOT = tmp_path
    mock_http = mock.create_autospec(HttpClient, instance=True, spec_set=True)
    error = RuntimeError("ClickHouse unavailable")
    with (
        mock.patch("cross_dock.services.clickhouse_service.get_clickhouse_client") as mock_get,
        mock.patch("cross_dock.services.normalization.get_clickhouse_client") as mock_normalization_get,
    ):
        normalization_client = mock_normalization_get.return_value.__enter__.return_value
        normalization_client.query.return_value = SimpleNamespace(result_rows=[])
        if failure_stage == "normalization":
            normalization_client.query.side_effect = error
        if failure_stage == "connection":
            mock_get.return_value.__enter__.side_effect = error
        else:
            mock_get.return_value.__enter__.return_value = mock_http
            mock_http.query.side_effect = (
                [error] if failure_stage == "suppliers" else [SimpleNamespace(result_rows=[(1,)]), error]
            )
        response = client.post(
            reverse("cross_dock:process_file"), {"file_upload": excel_file, "supplier_list": "ОПТ-2", "use_mv": use_mv}
        )

    assert response.status_code == 302
    task = CrossDockTask.objects.get()
    assert task.status == "FAILURE"
    assert task.error_message == "ClickHouse unavailable"
    assert not task.result_url
    assert not list((tmp_path / "uploads").iterdir())
    listing = client.get(response.url)
    assert task in listing.context["tasks"]


@pytest.mark.parametrize("use_mv", [False, True])
def test_upload_queries_and_exports_numeric_article(client, authenticated_user, excel_file, settings, tmp_path, use_mv):
    settings.MEDIA_ROOT = tmp_path
    mock_http = mock.create_autospec(HttpClient, instance=True, spec_set=True)
    mock_http.query.side_effect = [
        SimpleNamespace(result_rows=[]),
        SimpleNamespace(result_rows=[(1,)]),
        SimpleNamespace(result_rows=[(123.5, 4, "Supplier A", "BOSCH", "12345")]),
    ]
    with (
        mock.patch("cross_dock.services.clickhouse_service.get_clickhouse_client") as mock_get,
        mock.patch("cross_dock.services.normalization.get_clickhouse_client") as mock_normalization_get,
    ):
        mock_normalization_get.return_value.__enter__.return_value = mock_http
        mock_get.return_value.__enter__.return_value = mock_http
        response = client.post(
            reverse("cross_dock:process_file"),
            {"file_upload": excel_file, "supplier_list": "ОПТ-2", "use_mv": "1" if use_mv else "0"},
        )

    assert response.status_code == 302
    task = CrossDockTask.objects.get()
    assert task.status == "SUCCESS"
    parameters = mock_http.query.call_args.kwargs["parameters"]
    assert parameters["brand_sku_pairs"] == [("BOSCH", "12345")]
    from openpyxl import load_workbook

    workbook = load_workbook(next((tmp_path / "exports").glob("*.xlsx")))
    expected_article = "12345"
    assert list(workbook.active.values)[1][:6] == ("BOSCH|12345", "BOSCH", expected_article, 123.5, 4, "Supplier A")


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
