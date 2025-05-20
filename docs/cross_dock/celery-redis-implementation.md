# Celery/Redis Implementation Plan for Cross-Dock Task Management

This document outlines the detailed implementation plan for adding Celery and Redis to the Cross-Dock functionality in the admin2 project. This implementation will enable asynchronous processing of large files, improving user experience and system reliability.

## 1. Overview

The Cross-Dock functionality currently processes files synchronously, which creates poor UX for large files (100k+ lines) as users wait without feedback. This implementation will:

1. Use Celery for background task processing
2. Use Redis as the message broker
3. Track task status in the existing CrossDockTask model
4. Provide real-time feedback to users on task progress

## 2. Model Updates

It's a good idea to define a BaseModel, that you can inherit (source https://github.com/HackSoftware/Django-Styleguide?tab=readme-ov-file#base-model)

Usually, fields like created_at and updated_at are perfect candidates to go into a BaseModel.

Here's an example BaseModel:

from django.db import models
from django.utils import timezone

```
class BaseModel(models.Model):
    created_at = models.DateTimeField(db_index=True, default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
```

After that make sure that TaskComment and CrossDockTask inherit from the BaseModel and remove the created_at and 
updated_at fields from these models since it's already inherited from the BaseModel.

### TaskComment Model

Instead of adding a task_note field to the CrossDockTask model, we'll create a separate TaskComment model to allow multiple comments per task:

```python
# cross_dock/models.py
class TaskComment(BaseModel):
    """Model for comments on cross-dock tasks."""

    # Using Django's default auto-incrementing ID
    task = models.ForeignKey(
        CrossDockTask,
        on_delete=models.CASCADE,
        related_name="comments",
        help_text="Task this comment belongs to"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cross_dock_comments",
        help_text="User who created this comment"
    )
    text = models.TextField(help_text="Comment text")

    def __str__(self):
        return f"Comment on {self.task.id} by {self.user or 'Anonymous'}"

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["task"]),
            models.Index(fields=["user"]),
            models.Index(fields=["created_at"]),
        ]
```

Notes:
- We will NOT add a separate task_id field to CrossDockTask since we can use the existing UUID id field as the Celery task ID
- We will NOT add a progress field as constantly updating progress percentages in Postgres would be inefficient
- We will NOT add a meta JSONField at this time
- We WILL create a separate TaskComment model for better data modeling and to allow multiple comments per task
- The CrossDockTask model already has a user ForeignKey to track who created the task

## 3. Dependencies

The following dependencies to pyproject.toml are added:
celery django-celery-results redis

## 4. Celery Configuration

Following the HackSoftware Django-Styleguide, we'll create a new module for third-party configurations:

### 4.1. Directory Structure

```
config/
├── __init__.py
├── django_config/
│   ├── __init__.py
│   ├── base.py
│   ├── production.py
│   └── staging.py
├── third_party_config/
│   ├── __init__.py
│   └── celery.py
├── urls.py
├── env.py
├── wsgi.py
└── asgi.py
```

### 4.2. Celery Configuration File

```python
# config/third_party_config/celery.py
import os
from celery import Celery
from django.conf import settings

# Set the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.django_config.base')

app = Celery('admin2')

# Use a string here to avoid namespace issues
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load tasks from all registered Django app configs
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
```

### 4.3. Update Config Init File

```python
# config/__init__.py
# This will make sure the app is always imported when Django starts
from config.third_party_config.celery import app as celery_app

__all__ = ('celery_app',)
```

## 5. Settings Updates

### 5.1. Base Settings

Add the following to config/django_config/base.py:

```python
# Celery settings
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6378/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6378/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes

# Add django-celery-results to INSTALLED_APPS
INSTALLED_APPS += ["django_celery_results"]
```

### 5.2. Environment Variables

Update .env.example with:

```
# Redis/Celery settings
CELERY_BROKER_URL=redis://localhost:6378/0
CELERY_RESULT_BACKEND=redis://localhost:6378/0
```

## 6. Task Definition

Create a new file for Celery tasks:

```python
# cross_dock/tasks.py
import logging
import os
from celery import shared_task
from django.conf import settings

from cross_dock.models import CrossDockTask
from cross_dock.services.excel_service import process_cross_dock_data_from_file

logger = logging.getLogger(__name__)

@shared_task(bind=True)
def process_file_task(self, file_path, supplier_list, task_id):
    """
    Process the uploaded file in the background.

    Args:
        file_path: Path to the uploaded file
        supplier_list: Selected supplier list
        task_id: UUID of the CrossDockTask record
    """
    try:
        # Get the task record
        task = CrossDockTask.objects.get(id=task_id)

        # Mark as running
        task.mark_as_running()

        # Process the file
        output_file_path = process_cross_dock_data_from_file(file_path, supplier_list)
        output_filename = os.path.basename(output_file_path)
        output_url = f"{settings.MEDIA_URL}exports/{output_filename}"

        # Mark as success
        task.mark_as_success(output_url)

        return {
            "status": "success",
            "task_id": task_id,
            "output_url": output_url
        }

    except Exception as e:
        logger.exception(f"Error processing file: {e}")

        # Mark as failed
        try:
            task = CrossDockTask.objects.get(id=task_id)
            task.mark_as_failed(str(e))
        except Exception as task_error:
            logger.exception(f"Error updating task status: {task_error}")

        return {
            "status": "error",
            "task_id": task_id,
            "error": str(e)
        }
    finally:
        # Clean up the uploaded file
        try:
            os.remove(file_path)
            logger.info(f"Removed temporary upload file: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to remove temporary upload file {file_path}: {e}")
```

## 7. View Updates

### 7.1. Update Process File View

```python
# cross_dock/views.py
import logging
import os
import uuid

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.urls import reverse

from cross_dock.models import CrossDockTask
from cross_dock.tasks import process_file_task

logger = logging.getLogger(__name__)

def process_file(request):
    """
    Process the uploaded Excel file and selected supplier list.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        uploaded_file = request.FILES.get("file_upload")
        if not uploaded_file:
            return JsonResponse({"error": "No file uploaded"}, status=400)

        if not uploaded_file.name.lower().endswith((".xlsx", ".xls")):
            return JsonResponse({"error": "Invalid file format. Only Excel files are allowed."}, status=400)

        supplier_list = request.POST.get("supplier_list")
        if not supplier_list:
            return JsonResponse({"error": "No supplier list selected"}, status=400)

        filename = f"cross_dock_{uuid.uuid4().hex}.xlsx"

        # Ensure directories exist
        upload_dir = os.path.join(settings.MEDIA_ROOT, "uploads")
        export_dir = os.path.join(settings.MEDIA_ROOT, "exports")

        try:
            os.makedirs(upload_dir, exist_ok=True)
            os.makedirs(export_dir, exist_ok=True)
            logger.info(f"Created directories: {upload_dir}, {export_dir}")
        except Exception as e:
            logger.error(f"Error creating directories: {e}")
            return JsonResponse({"error": f"Error creating directories: {e}"}, status=500)

        file_path = os.path.join(upload_dir, filename)

        with open(file_path, "wb+") as destination:
            for chunk in uploaded_file.chunks():
                destination.write(chunk)

        try:
            from cross_dock.services.clickhouse_service import get_clickhouse_client

            try:
                with get_clickhouse_client() as client:
                    # Test the connection with a simple query
                    test_result = client.execute("SELECT 1")
                    logger.info(f"ClickHouse connection test successful: {test_result}")
            except Exception as db_error:
                logger.error(f"ClickHouse connection error: {db_error}")
                return JsonResponse(
                    {
                        "error": f"Could not connect to the database. Please check your connection settings or try again later. Error: {db_error!s}"
                    },
                    status=500,
                )

            # Create task record
            task = CrossDockTask.objects.create(
                status="PENDING",
                filename=uploaded_file.name,
                user=request.user if request.user.is_authenticated else None,
            )

            # Submit Celery task
            celery_task = process_file_task.delay(
                file_path=file_path,
                supplier_list=supplier_list,
                task_id=str(task.id)
            )

            # Redirect to task list
            return redirect(reverse('cross_dock:task_list'))

        except Exception as e:
            logger.exception(f"Error processing file: {e}")
            return JsonResponse({"error": str(e)}, status=500)

    except Exception as e:
        logger.exception(f"Error processing file: {e}")
        return JsonResponse({"error": str(e)}, status=500)
```

### 7.2. Add Task List View

```python
# cross_dock/views.py (additional function)
def task_list(request):
    """
    Display a list of all tasks.
    """
    tasks = CrossDockTask.objects.all().order_by('-created_at')
    return render(request, "cross_dock/task_list.html", {"tasks": tasks})
```

### 7.3. Add Task Detail View

```python
# cross_dock/views.py (additional function)
from django.shortcuts import get_object_or_404

def task_detail(request, task_id):
    """
    Display details for a specific task.
    """
    task = get_object_or_404(CrossDockTask, id=task_id)

    # Handle task note updates
    if request.method == "POST" and request.user.is_authenticated:
        task_note = request.POST.get("task_note")
        if task_note is not None:
            task.task_note = task_note
            task.save(update_fields=["task_note", "updated_at"])

    return render(request, "cross_dock/task_detail.html", {"task": task})
```

## 8. URL Updates

Update the URLs to include the new views:

```python
# cross_dock/urls.py
from django.urls import path
from . import views

app_name = "cross_dock"
urlpatterns = [
    path("", views.index, name="index"),
    path("process/", views.process_file, name="process_file"),
    path("tasks/", views.task_list, name="task_list"),
    path("tasks/<uuid:task_id>/", views.task_detail, name="task_detail"),
]
```

## 9. Template Updates

### 9.1. Task List Template

```html
<!-- cross_dock/templates/cross_dock/task_list.html -->
{% extends "base.html" %}

{% block title %}Cross-Dock Tasks{% endblock %}

{% block content %}
<div class="container mx-auto px-4 py-8">
    <h1 class="text-2xl font-bold mb-6">Cross-Dock Tasks</h1>

    <div class="mb-4">
        <a href="{% url 'cross_dock:index' %}" class="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded">
            New Task
        </a>
    </div>

    <div class="overflow-x-auto">
        <table class="min-w-full bg-white border border-gray-200">
            <thead>
                <tr>
                    <th class="px-4 py-2 border-b">ID</th>
                    <th class="px-4 py-2 border-b">Status</th>
                    <th class="px-4 py-2 border-b">Filename</th>
                    <th class="px-4 py-2 border-b">Created</th>
                    <th class="px-4 py-2 border-b">Updated</th>
                    <th class="px-4 py-2 border-b">Actions</th>
                </tr>
            </thead>
            <tbody>
                {% for task in tasks %}
                <tr class="{% cycle 'bg-gray-50' '' %}"
                    hx-get="{% url 'cross_dock:task_detail' task.id %}"
                    hx-trigger="{% if task.status == 'PENDING' or task.status == 'RUNNING' %}every 5s{% endif %}">
                    <td class="px-4 py-2 border-b">{{ task.id|truncatechars:8 }}</td>
                    <td class="px-4 py-2 border-b">
                        {% if task.status == 'PENDING' %}
                        <span class="bg-yellow-100 text-yellow-800 px-2 py-1 rounded-full text-xs">Pending</span>
                        {% elif task.status == 'RUNNING' %}
                        <span class="bg-blue-100 text-blue-800 px-2 py-1 rounded-full text-xs">Running</span>
                        {% elif task.status == 'SUCCESS' %}
                        <span class="bg-green-100 text-green-800 px-2 py-1 rounded-full text-xs">Success</span>
                        {% elif task.status == 'FAILURE' %}
                        <span class="bg-red-100 text-red-800 px-2 py-1 rounded-full text-xs">Failed</span>
                        {% endif %}
                    </td>
                    <td class="px-4 py-2 border-b">{{ task.filename|default:"N/A" }}</td>
                    <td class="px-4 py-2 border-b">{{ task.created_at|date:"Y-m-d H:i:s" }}</td>
                    <td class="px-4 py-2 border-b">{{ task.updated_at|date:"Y-m-d H:i:s" }}</td>
                    <td class="px-4 py-2 border-b">
                        <a href="{% url 'cross_dock:task_detail' task.id %}" class="text-blue-500 hover:text-blue-700">
                            View
                        </a>
                        {% if task.status == 'SUCCESS' and task.result_url %}
                        <a href="{{ task.result_url }}" class="ml-2 text-green-500 hover:text-green-700">
                            Download
                        </a>
                        {% endif %}
                    </td>
                </tr>
                {% empty %}
                <tr>
                    <td colspan="6" class="px-4 py-2 text-center">No tasks found.</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>
{% endblock %}
```

### 9.2. Task Detail Template

```html
<!-- cross_dock/templates/cross_dock/task_detail.html -->
{% extends "base.html" %}

{% block title %}Task Details{% endblock %}

{% block content %}
<div class="container mx-auto px-4 py-8">
    <div class="mb-4">
        <a href="{% url 'cross_dock:task_list' %}" class="text-blue-500 hover:text-blue-700">
            &larr; Back to Task List
        </a>
    </div>

    <h1 class="text-2xl font-bold mb-6">Task Details</h1>

    <div class="bg-white shadow-md rounded px-8 pt-6 pb-8 mb-4">
        <div class="mb-4">
            <h2 class="text-xl font-semibold mb-2">Task Information</h2>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                    <p><strong>ID:</strong> {{ task.id }}</p>
                    <p><strong>Status:</strong>
                        {% if task.status == 'PENDING' %}
                        <span class="bg-yellow-100 text-yellow-800 px-2 py-1 rounded-full text-xs">Pending</span>
                        {% elif task.status == 'RUNNING' %}
                        <span class="bg-blue-100 text-blue-800 px-2 py-1 rounded-full text-xs">Running</span>
                        {% elif task.status == 'SUCCESS' %}
                        <span class="bg-green-100 text-green-800 px-2 py-1 rounded-full text-xs">Success</span>
                        {% elif task.status == 'FAILURE' %}
                        <span class="bg-red-100 text-red-800 px-2 py-1 rounded-full text-xs">Failed</span>
                        {% endif %}
                    </p>
                    <p><strong>Filename:</strong> {{ task.filename|default:"N/A" }}</p>
                    <p><strong>Created by:</strong> {{ task.user.username|default:"Anonymous" }}</p>
                </div>
                <div>
                    <p><strong>Created:</strong> {{ task.created_at|date:"Y-m-d H:i:s" }}</p>
                    <p><strong>Updated:</strong> {{ task.updated_at|date:"Y-m-d H:i:s" }}</p>
                    {% if task.created_at != task.updated_at %}
                    <p><strong>Execution time:</strong> {{ task.execution_time }}</p>
                    {% endif %}
                </div>
            </div>
        </div>

        {% if task.status == 'SUCCESS' and task.result_url %}
        <div class="mb-4">
            <h2 class="text-xl font-semibold mb-2">Result</h2>
            <a href="{{ task.result_url }}" class="bg-green-500 hover:bg-green-700 text-white font-bold py-2 px-4 rounded">
                Download Result
            </a>
        </div>
        {% endif %}

        {% if task.status == 'FAILURE' and task.error_message %}
        <div class="mb-4">
            <h2 class="text-xl font-semibold mb-2">Error</h2>
            <div class="bg-red-50 border border-red-200 text-red-800 px-4 py-3 rounded">
                {{ task.error_message }}
            </div>
        </div>
        {% endif %}

        <div class="mb-4">
            <h2 class="text-xl font-semibold mb-2">Task Note</h2>
            {% if user.is_authenticated %}
            <form method="post" action="{% url 'cross_dock:task_detail' task.id %}">
                {% csrf_token %}
                <div class="mb-4">
                    <textarea name="task_note" class="shadow appearance-none border rounded w-full py-2 px-3 text-gray-700 leading-tight focus:outline-none focus:shadow-outline" rows="3">{{ task.task_note|default:"" }}</textarea>
                </div>
                <div>
                    <button type="submit" class="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded">
                        Save Note
                    </button>
                </div>
            </form>
            {% else %}
            <div class="bg-gray-50 border border-gray-200 px-4 py-3 rounded">
                {{ task.task_note|default:"No notes available." }}
            </div>
            {% endif %}
        </div>
    </div>
</div>
{% endblock %}
```

## 10. Migration for Model Updates

Do not Create a migration for the CrossDockTask model updates. User will do it manually.

```bash
python manage.py makemigrations cross_dock
```

## 11. Testing

### 11.1. Unit Tests

Create tests for the Celery task:

```python
# cross_dock/tests/test_tasks.py
import os
import tempfile
import uuid
from unittest.mock import patch

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
    fd, path = tempfile.mkstemp(suffix='.xlsx')
    os.close(fd)

    # Create a sample DataFrame
    df = pd.DataFrame({
        'Бренд': ['TOYOTA', 'NISSAN', 'HONDA'],
        'Артикул': ['12345', '67890', 'ABCDE']
    })

    # Save to Excel
    df.to_excel(path, index=False)

    yield path

    # Clean up
    if os.path.exists(path):
        os.remove(path)

@pytest.fixture
def task_record():
    """Create a sample task record."""
    user = User.objects.create(username='testuser')
    task = CrossDockTask.objects.create(
        status='PENDING',
        filename='test.xlsx',
        user=user
    )
    yield task
    task.delete()
    user.delete()

@pytest.mark.django_db
def test_process_file_task_success(sample_excel_file, task_record):
    """Test successful file processing."""
    with patch('cross_dock.services.excel_service.process_cross_dock_data_from_file') as mock_process:
        # Setup mock
        output_path = os.path.join(settings.MEDIA_ROOT, 'exports', f'result_{uuid.uuid4()}.xlsx')
        mock_process.return_value = output_path

        # Call the task
        result = process_file_task(sample_excel_file, 'ОПТ-2', str(task_record.id))

        # Assertions
        assert result['status'] == 'success'
        assert 'output_url' in result

        # Check that the task was updated
        task_record.refresh_from_db()
        assert task_record.status == 'SUCCESS'
        assert task_record.result_url is not None

@pytest.mark.django_db
def test_process_file_task_failure(sample_excel_file, task_record):
    """Test file processing failure."""
    with patch('cross_dock.services.excel_service.process_cross_dock_data_from_file') as mock_process:
        # Setup mock to raise an exception
        mock_process.side_effect = Exception('Test error')

        # Call the task
        result = process_file_task(sample_excel_file, 'ОПТ-2', str(task_record.id))

        # Assertions
        assert result['status'] == 'error'
        assert 'error' in result

        # Check that the task was updated
        task_record.refresh_from_db()
        assert task_record.status == 'FAILURE'
        assert task_record.error_message is not None
```

### 11.2. Integration Tests

Create integration tests for the views:

```python
# cross_dock/tests/test_views.py
import os
import tempfile
from unittest.mock import patch

import pandas as pd
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from cross_dock.models import CrossDockTask

User = get_user_model()

@pytest.fixture
def sample_excel_file():
    """Create a sample Excel file for testing."""
    # Create a temporary file
    fd, path = tempfile.mkstemp(suffix='.xlsx')
    os.close(fd)

    # Create a sample DataFrame
    df = pd.DataFrame({
        'Бренд': ['TOYOTA', 'NISSAN', 'HONDA'],
        'Артикул': ['12345', '67890', 'ABCDE']
    })

    # Save to Excel
    df.to_excel(path, index=False)

    yield path

    # Clean up
    if os.path.exists(path):
        os.remove(path)

@pytest.fixture
def authenticated_client(client):
    """Create an authenticated client."""
    user = User.objects.create_user(username='testuser', password='password')
    client.login(username='testuser', password='password')
    yield client
    user.delete()

@pytest.mark.django_db
def test_process_file_view(authenticated_client, sample_excel_file):
    """Test the process_file view."""
    with open(sample_excel_file, 'rb') as f:
        with patch('cross_dock.tasks.process_file_task.delay') as mock_task:
            # Setup mock
            mock_task.return_value.id = 'test-task-id'

            # Make the request
            response = authenticated_client.post(
                reverse('cross_dock:process_file'),
                {
                    'file_upload': f,
                    'supplier_list': 'ОПТ-2'
                }
            )

            # Assertions
            assert response.status_code == 302  # Redirect
            assert response.url == reverse('cross_dock:task_list')

            # Check that a task was created
            assert CrossDockTask.objects.count() == 1
            task = CrossDockTask.objects.first()
            assert task.status == 'PENDING'
            assert task.user is not None

@pytest.mark.django_db
def test_task_list_view(authenticated_client):
    """Test the task_list view."""
    # Create some tasks
    user = User.objects.get(username='testuser')
    CrossDockTask.objects.create(status='SUCCESS', filename='test1.xlsx', user=user)
    CrossDockTask.objects.create(status='FAILURE', filename='test2.xlsx', user=user)

    # Make the request
    response = authenticated_client.get(reverse('cross_dock:task_list'))

    # Assertions
    assert response.status_code == 200
    assert 'tasks' in response.context
    assert len(response.context['tasks']) == 2

@pytest.mark.django_db
def test_task_detail_view(authenticated_client):
    """Test the task_detail view."""
    # Create a task
    user = User.objects.get(username='testuser')
    task = CrossDockTask.objects.create(status='SUCCESS', filename='test.xlsx', user=user)

    # Make the request
    response = authenticated_client.get(reverse('cross_dock:task_detail', args=[task.id]))

    # Assertions
    assert response.status_code == 200
    assert 'task' in response.context
    assert response.context['task'].id == task.id

    # Test updating the task note
    response = authenticated_client.post(
        reverse('cross_dock:task_detail', args=[task.id]),
        {'task_note': 'Test note'}
    )

    # Assertions
    assert response.status_code == 200
    task.refresh_from_db()
    assert task.task_note == 'Test note'
```

## 12. Deployment Considerations

### 12.1. Redis Configuration

Ensure Redis is installed and running on the server:

```bash
# Install Redis (Ubuntu)
sudo apt-get update
sudo apt-get install redis-server

# Start Redis
sudo systemctl start redis-server
sudo systemctl enable redis-server
```

### 12.2. Celery Worker Configuration

Create a systemd service file for the Celery worker:

```ini
# /etc/systemd/system/celery.service
[Unit]
Description=Celery Worker Service
After=network.target

[Service]
Type=forking
User=www-data
Group=www-data
WorkingDirectory=/path/to/admin2
ExecStart=/bin/sh -c '/path/to/venv/bin/celery -A config worker --loglevel=info'
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl enable celery.service
sudo systemctl start celery.service
```

### 12.3. Environment Variables

Ensure the following environment variables are set in production:

```
CELERY_BROKER_URL=redis://redis-host:6378/0
CELERY_RESULT_BACKEND=redis://redis-host:6378/0
```

## 13. Implementation Timeline

1. **Day 1**: Set up dependencies and Celery configuration
2. **Day 2**: Update CrossDockTask model and create migrations
3. **Day 3**: Implement Celery tasks and update views
4. **Day 4**: Create templates and update URLs
5. **Day 5**: Write tests and fix any issues
6. **Day 6**: Deploy and test in staging environment
7. **Day 7**: Deploy to production and monitor

## 14. Monitoring and Maintenance

### 14.1. Monitoring

- Use Flower for Celery task monitoring: `pip install flower`
- Start Flower: `celery -A config flower --port=5555`
- Monitor Redis using Redis CLI: `redis-cli info`

### 14.2. Maintenance

- Regularly check Celery logs for errors
- Monitor Redis memory usage
- Set up alerts for failed tasks
- Implement periodic cleanup of old task records

## 15. Conclusion

This implementation plan provides a comprehensive approach to adding Celery and Redis to the Cross-Dock functionality. By following this plan, we will improve the user experience for large file processing and make the system more robust and scalable.
