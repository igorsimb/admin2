"""
Celery configuration for the project.

This module configures Celery for the project, including the broker URL,
result backend, and task discovery.
"""

import os

# Set default environment for Celery if not specified.
# This is crucial for running the worker directly.
os.environ.setdefault("DJANGO_ENVIRONMENT", "staging")

from celery import Celery
from celery.schedules import crontab

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


app.conf.beat_schedule = {
    "backfill_suppliers_task": {
        "task": "pricelens.tasks.backfill_suppliers_task",
        "schedule": crontab(hour=5, minute=0, day_of_week="monday"),  # 05:00 MSK on Mondays
    },
    "refresh_cadence_profiles": {
        "task": "pricelens.tasks.refresh_cadence_profiles_task",
        "schedule": crontab(hour=6, minute=30, day_of_week="*"),  # 06:30 MSK daily
    },
    "backfill_investigations": {
        "task": "pricelens.tasks.backfill_investigations_task",
        "schedule": crontab(hour=6, minute=35, day_of_week="*"),  # 06:35 MSK daily
    },
}


@app.task(bind=True)
def debug_task(self):
    """
    Debug task to verify Celery is working.

    This task simply prints the request information.
    """
    print(f"Request: {self.request!r}")
