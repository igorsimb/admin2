"""
Tests for pricelens utility functions.
"""

import datetime
from enum import Enum

import pytest

from pricelens.models import Investigation
from pricelens.utils import log_investigation_event


class FailReasons(int, Enum):
    FILE_READ_ERROR = 101
    SKU_FORMAT_INVALID = 202


@pytest.mark.django_db
class TestLogInvestigationEvent:
    """Tests for the log_investigation_event utility function."""

    def test_creates_new_investigation_record(self):
        """Verify that a new Investigation record is created on the first call."""
        assert Investigation.objects.count() == 0

        log_investigation_event(
            event_dt=datetime.datetime.now(datetime.UTC),
            supid=1234,
            reason=FailReasons.FILE_READ_ERROR,
            stage="load_mail",
            file_path="/path/to/file1.csv",
        )

        assert Investigation.objects.count() == 1
        investigation = Investigation.objects.first()
        assert investigation.supid == 1234
        assert investigation.error_id == FailReasons.FILE_READ_ERROR.value
        assert investigation.error_text == FailReasons.FILE_READ_ERROR.name

    def test_is_idempotent_and_avoids_duplicates(self):
        """Verify that calling the function with the same parameters does not create a duplicate."""
        event_time = datetime.datetime.now(datetime.UTC)
        params = {
            "event_dt": event_time,
            "supid": 5678,
            "reason": FailReasons.SKU_FORMAT_INVALID,
            "stage": "consolidate",
            "file_path": "/path/to/file2.csv",
        }

        # First call should create the record
        log_investigation_event(**params)
        assert Investigation.objects.count() == 1

        # Second call with the exact same data should do nothing
        log_investigation_event(**params)
        assert Investigation.objects.count() == 1
