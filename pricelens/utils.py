"""
Utility functions for the pricelens app.
"""

import datetime

from django.db import IntegrityError

from .models import Investigation, InvestigationStatus


def log_investigation_event(event_dt: datetime.datetime, supid: int, reason, stage: str, file_path: str, extra=None):
    """
    Safely logs an investigation event, avoiding duplicates.
    'reason' can be an Enum member or an integer.
    """
    try:
        # Use get_or_create for atomicity and to prevent race conditions
        Investigation.objects.get_or_create(
            event_dt=event_dt,
            supid=supid,
            error_id=reason.value if hasattr(reason, "value") else int(reason),
            defaults={
                "error_text": reason.name if hasattr(reason, "name") else str(reason),
                "stage": stage,
                "file_path": file_path,
                "status": InvestigationStatus.OPEN,
            },
        )
    except IntegrityError:
        # This can happen in a race condition if two processes try to create the exact
        # same record simultaneously. The first one succeeds, the second one fails
        # the unique constraint. We can safely ignore this error.
        pass
