"""
Celery configuration for the project.

This module configures Celery for the project, including the broker URL,
result backend, and task discovery.
"""

import os

from celery import Celery

# Use the DJANGO_SETTINGS_MODULE environment variable if set
# If not set, determine from DJANGO_ENVIRONMENT
if "DJANGO_SETTINGS_MODULE" not in os.environ:
    django_env = os.environ.get("DJANGO_ENVIRONMENT")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", f"config.django_config.{django_env}")

app = Celery("admin2")

# Use a string here to avoid namespace issues
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load tasks from all registered Django app configs
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    """
    Debug task to verify Celery is working.

    This task simply prints the request information.
    """
    print(f"Request: {self.request!r}")
