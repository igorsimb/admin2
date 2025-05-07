# parser-cross-dock separation



tldr: parser service to split into 3 apps: cross-dock, parser, common



# Django App Structure for Cross-dock and Parser Functionalities

This document outlines recommendations for structuring a Django project with separate apps for cross-dock (ClickHouse queries) and parser (website parsing) functionalities, while minimizing code duplication.

## Project Structure Overview

The project will consist of three main Django apps:

1. **core**: Entry point for the application
2. **cross\_dock**: ClickHouse query functionality
3. **parser**: Website parsing functionality
4. **common**: Shared utilities and models

## Configuration Approach

Following the HackSoftware Django Styleguide approach for settings:

```
config/
├── __init__.py
├── django_config/
│   ├── __init__.py
│   ├── base.py
│   ├── local.py
│   ├── production.py
│   └── test.py
├── third_party_config/
│   ├── __init__.py
│   ├── celery.py
│   ├── clickhouse.py
│   ├── cors.py
│   ├── sentry.py
│   └── sessions.py
├── urls.py
├── env.py
└── wsgi.py
├── asgi.py
```

## Shared Components Analysis

### 1. Database Connections

Both functionalities require database connections, but with different purposes:

* **Cross-dock**: Primarily uses ClickHouse for data queries
* **Parser**: Uses PostgreSQL for storing parsed data

### 2. Task Management

Task history will now be stored in PostgreSQL rather than Redis:

* Redis will only be used as a Celery broker
* Task history and metadata will be stored in PostgreSQL tables

### 3. Authentication

Both apps will need the same authentication mechanisms for API endpoints.

### 4. Utility Functions

Excel generation, file handling, and other utilities are used by both apps.

## Recommended App Structure

### Common App

```
common/
├── config/
│   ├── __init__.py
│   └── clickhouse.py  # ClickHouse connection settings
├── utils/
│   ├── __init__.py
│   ├── excel.py       # Excel file generation utilities
│   ├── auth.py        # Authentication utilities
│   └── file_utils.py  # File handling utilities
├── models/
│   ├── __init__.py
│   └── task.py        # Task-related models
└── middleware/
    ├── __init__.py
    └── auth.py        # Authentication middleware
```

### Core App (Entry Point)

```
core/
├── views/
│   ├── __init__.py
│   └── index.py       # Main index view
├── templates/
│   └── core/
│       └── index.html # Main index template with links
```

### Cross-dock App (ClickHouse Queries)

```
cross_dock/
├── views/
│   ├── __init__.py
│   └── percentage_cross.py  # Views for percentage cross functionality
├── services/
│   ├── __init__.py
│   └── clickhouse_service.py  # ClickHouse query services
├── tasks/
│   ├── __init__.py
│   └── query_tasks.py  # Celery tasks for queries
├── models/
│   ├── __init__.py
│   └── query_history.py  # Models for query history
└── templates/
    └── cross_dock/
        └── task_status.html  # Task status display
```

### Parser App (Website Parsing)

```
parser/
├── views/
│   ├── __init__.py
│   └── parser_views.py  # Views for parsing functionality
├── services/
│   ├── __init__.py
│   ├── emex_service.py
│   ├── part_kom_service.py
│   └── autopiter_service.py
├── tasks/
│   ├── __init__.py
│   └── parser_tasks.py  # Celery tasks for parsing
├── models/
│   ├── __init__.py
│   └── parsed_data.py  # Models for parsed data
└── templates/
    └── parser/
        └── parser_status.html  # Parser status display
```

## Key Models

### Task History Model

Instead of using Redis for task history, we'll implement a PostgreSQL model:

```python
# common/models/task.py
from django.db import models

class TaskHistory(models.Model):
    task_id = models.CharField(max_length=300, primary_key=True)
    source_type = models.CharField(max_length=50)  # 'parser', 'percentage_cross', etc.
    status = models.CharField(max_length=50)  # 'PENDING', 'RUNNING', 'SUCCESS', 'FAILURE'
    result_url = models.URLField(null=True, blank=True)  # URL to result file
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    args = models.JSONField(null=True, blank=True)  # Task arguments
    result = models.JSONField(null=True, blank=True)  # Task result
    error = models.TextField(null=True, blank=True)  # Error message if failed
    
    class Meta:
        db_table = 'task_history'
        indexes = [
            models.Index(fields=['source_type', 'status']),
            models.Index(fields=['created_at']),
        ]
```

## Shared Code Examples

### ClickHouse Connection

```python
# common/config/clickhouse.py
from django.conf import settings
from clickhouse_driver import Client

def get_clickhouse_client():
    return Client(
        settings.CLICKHOUSE_HOST,
        user=settings.CLICKHOUSE_USER,
        password=settings.CLICKHOUSE_PASSWORD
    )
```

### Authentication Middleware

```python
# common/middleware/auth.py
from django.conf import settings
from django.http import JsonResponse

class APIKeyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        
    def __call__(self, request):
        if request.path.startswith('/api/'):
            app_key = request.headers.get('App-Key')
            if app_key != settings.CLIENT_APP_KEY_ADMIN:
                return JsonResponse({"error": "Invalid app-key"}, status=403)
        return self.get_response(request)
```

### Excel Utilities

```python
# common/utils/excel.py
from openpyxl import Workbook
import os
from django.conf import settings

def create_workbook():
    wb = Workbook()
    # Setup code
    return wb
    
def save_workbook(wb, filename):
    path = os.path.join(settings.MEDIA_ROOT, 'exports', filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    wb.save(path)
    return os.path.join(settings.MEDIA_URL, 'exports', filename)
```

## Celery Task Integration

With Redis as the broker and PostgreSQL for task history:

```python
# config/third_party_config/celery.py
from celery import Celery
from django.conf import settings

app = Celery('project_name')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Task base class with history tracking
class TaskWithHistory(app.Task):
    def on_success(self, retval, task_id, args, kwargs):
        from common.models import TaskHistory
        TaskHistory.objects.filter(task_id=task_id).update(
            status='SUCCESS',
            result=retval
        )
        
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        from common.models import TaskHistory
        TaskHistory.objects.filter(task_id=task_id).update(
            status='FAILURE',
            error=str(exc)
        )
        
    def apply_async(self, args=None, kwargs=None, **options):
        from common.models import TaskHistory
        task = super().apply_async(args=args, kwargs=kwargs, **options)
        
        # Extract source_type from args
        source_type = args[0].get('source_type') if args and isinstance(args[0], dict) else 'unknown'
        
        TaskHistory.objects.create(
            task_id=task.id,
            source_type=source_type,
            status='PENDING',
            args=args
        )
        return task
```

## Conclusion

Creating separate Django apps for cross-dock and parser functionalities is feasible with a well-designed`common`app to handle shared code. The key points are:

1. **PostgreSQL for Task History**: Store all task history in PostgreSQL instead of Redis
2. **Redis as Celery Broker Only**: Use Redis solely as a message broker for Celery
3. **Shared Utilities in Common App**: Keep shared code in a dedicated app
4. **HackSoftware Settings Structure**: Organize settings following the recommended pattern

This structure provides clear separation of concerns while avoiding code duplication. Each app can focus on its specific functionality while leveraging common components when needed.

