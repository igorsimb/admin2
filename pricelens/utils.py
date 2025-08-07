"""
Utility functions for the pricelens app.
"""

import datetime

from django.db import IntegrityError

from common.models import Supplier

from .models import FailReason, Investigation, InvestigationStatus


def log_investigation_event(
    event_dt: datetime.datetime, supid: int, reason: str, stage: str, file_path: str, extra=None
) -> None:
    """
    Safely logs an investigation event, avoiding duplicates.
    'reason' is the string code of the FailReason.

    This function will not create a new Supplier if one is not found. It will
    only log events for suppliers that already exist in the database.
    """
    try:
        supplier = Supplier.objects.get(supid=supid)
    except Supplier.DoesNotExist:
        return

    fail_reason, _ = FailReason.objects.get_or_create(code=reason, defaults={"name": reason, "description": ""})

    try:
        # Use get_or_create for atomicity and to prevent race conditions
        Investigation.objects.get_or_create(
            supplier=supplier,
            event_dt=event_dt,
            fail_reason=fail_reason,
            defaults={
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
