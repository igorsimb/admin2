"""
Tests for pricelens utility functions.
"""

import datetime

import pytest

from common.models import Supplier
from pricelens.models import FailReason, Investigation
from pricelens.utils import log_investigation_event


@pytest.mark.django_db
class TestLogInvestigationEvent:
    """Tests for the log_investigation_event utility function."""

    def test_creates_new_investigation_record(self):
        """Verify that a new Investigation record is created on the first call."""
        assert Investigation.objects.count() == 0
        supplier = Supplier.objects.create(supid=1234, name="Test Supplier")
        reason_code = "FILE_READ_ERROR"

        log_investigation_event(
            event_dt=datetime.datetime.now(datetime.UTC),
            supid=supplier.supid,
            reason=reason_code,
            stage="load_mail",
            file_path="/path/to/file1.csv",
        )

        assert Investigation.objects.count() == 1
        investigation = Investigation.objects.first()
        assert investigation.supplier == supplier
        assert investigation.fail_reason.code == reason_code

    def test_is_idempotent_and_avoids_duplicates(self):
        """Verify that calling the function with the same parameters does not create a duplicate."""
        supplier = Supplier.objects.create(supid=5678, name="Another Supplier")
        event_time = datetime.datetime.now(datetime.UTC)
        reason_code = "SKU_FORMAT_INVALID"
        params = {
            "event_dt": event_time,
            "supid": supplier.supid,
            "reason": reason_code,
            "stage": "consolidate",
            "file_path": "/path/to/file2.csv",
        }

        # First call should create the record
        log_investigation_event(**params)
        assert Investigation.objects.count() == 1

        # Second call with the exact same data should do nothing
        log_investigation_event(**params)
        assert Investigation.objects.count() == 1

    def test_creates_fail_reason_if_not_exists(self):
        """Verify that a new FailReason is created if the code is unknown."""
        initial_reason_count = FailReason.objects.count()
        supplier = Supplier.objects.create(supid=9999, name="New Supplier")
        reason_code = "A_BRAND_NEW_ERROR"

        log_investigation_event(
            event_dt=datetime.datetime.now(datetime.UTC),
            supid=supplier.supid,
            reason=reason_code,
            stage="airflow",
            file_path="/path/to/new_file.zip",
        )

        assert Investigation.objects.count() == 1
        assert FailReason.objects.count() == initial_reason_count + 1
        new_reason = FailReason.objects.get(code=reason_code)
        assert new_reason.name == reason_code  # Defaults to code
