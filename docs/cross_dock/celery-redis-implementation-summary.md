# Celery/Redis Implementation for Cross-Dock Task Management

This document summarizes the implementation of Celery and Redis for Cross-Dock Task Management in the admin2 project.

## 1. Overview

The Cross-Dock functionality now uses Celery for background task processing, which enables asynchronous processing of large files, improving user experience and system reliability.

## 2. Implementation Details

### 2.1. Model Updates

1. Created a BaseModel class in common/models.py with created_at and updated_at fields
2. Updated CrossDockTask to inherit from BaseModel
3. Added a TaskComment model for task comments

```python
# common/models.py
class BaseModel(models.Model):
    created_at = models.DateTimeField(db_index=True, default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

# cross_dock/models.py
class TaskComment(BaseModel):
    task = models.ForeignKey(CrossDockTask, on_delete=models.CASCADE, related_name="comments")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    text = models.TextField()
    
    class Meta:
        ordering = ["-created_at"]
```

### 2.2. Celery Configuration

1. Created config/third_party_config/celery.py for Celery configuration
2. Updated config/__init__.py to import the Celery app
3. Added Celery settings to config/django_config/base.py

```python
# config/third_party_config/celery.py
app = Celery('admin2')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# config/django_config/base.py
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6378/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6378/0")
```

### 2.3. Task Definition

Created a Celery task for processing files in cross_dock/tasks.py:

```python
@shared_task(bind=True)
def process_file_task(self, file_path, supplier_list, task_id):
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
        # Mark as failed
        task.mark_as_failed(str(e))
        raise
```

### 2.4. View Updates

1. Updated the process_file view to use Celery
2. Added a task_detail view for displaying task details and comments

```python
def process_file(request):
    # ... validation code ...
    
    # Create task record with PENDING status
    task = CrossDockTask.objects.create(
        status="PENDING",
        filename=uploaded_file.name,
        supplier_group=supplier_list,
        user=request.user if request.user.is_authenticated else None,
    )
    
    # Submit Celery task
    celery_task = process_file_task.delay(
        file_path=file_path,
        supplier_list=supplier_list,
        task_id=str(task.id)
    )
    
    return redirect(reverse("cross_dock:task_list"))
```

### 2.5. Template Updates

1. Created a task_detail.html template for displaying task details and comments
2. Added a form for adding comments to tasks

### 2.6. URL Updates

Added a URL pattern for the task_detail view:

```python
path("tasks/<uuid:task_id>/", views.task_detail, name="task_detail")
```

### 2.7. Tests

Added tests for the Celery task and views:

1. tests/cross_dock/test_tasks.py - Tests for the Celery task
2. tests/cross_dock/test_celery_views.py - Tests for the views with Celery integration

## 3. Already Implemented

1. Run migrations to update the database schema (done)
   ```bash
   python manage.py makemigrations cross_dock
   python manage.py migrate
   ```

2. Set up Redis for the Celery broker:
   ```bash
   # Install Redis (Ubuntu)
   sudo apt-get update
   sudo apt-get install redis-server
   
   # Start Redis
   sudo systemctl start redis-server
   sudo systemctl enable redis-server
   ```

3. Start Celery worker:
   ```bash
   celery -A config worker --loglevel=info
   ```

4. Update the .env file with Redis settings:
   ```
   CELERY_BROKER_URL=redis://localhost:6378/0
   CELERY_RESULT_BACKEND=redis://localhost:6378/0
   ```

## 4. Benefits

1. **Improved User Experience**: Users no longer have to wait for file processing to complete
2. **Better Resource Management**: Long-running tasks don't block web server threads
3. **Increased Reliability**: Task failures are properly tracked and can be retried
4. **Task History**: All tasks are stored in the database with their status and results
5. **Comments System**: Users can add comments to tasks for better collaboration

## 5. Next Steps

0. Create a Materialized View for the query in query_supplier_data
   - This will allow us to query the data in a more efficient way
   - The view will be used to display the data in the UI
   - We will keep the original query as a backup in case the view doesn't work as expected
   - We will query the view instead of the original query in the UI

1. Implement proper progress tracking using Celery and Redis
   - Store progress percentage in Redis
   - Update task progress in real-time
   - Add Celery signals to track task progress

2. Improve UI for progress reporting
   - Show percentage number together with progress bar in the Progress table cell
   - Ensure elapsed time is updated on the front-end without requiring page refresh
   - Add more granular progress indicators for multi-stage tasks

3. Additional enhancements
   - Implement task cancellation
   - Add task retry functionality
   - Add ability to delete and edit task comments
   - UI: remove "Add notes or comments about this task." section from the task detail page, it takes up too much space
