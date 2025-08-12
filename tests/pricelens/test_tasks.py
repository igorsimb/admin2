"""
Unit tests for the Pricelens Celery tasks.

These tests verify the logic of the asynchronous tasks in `pricelens.tasks`,
ensuring they correctly process data and interact with the database.
"""

import pytest
from unittest.mock import MagicMock, patch

import pandas as pd

from common.models import Supplier
from pricelens.models import CadenceProfile, Investigation
from pricelens.tasks import backfill_suppliers_task, refresh_cadence_profiles_task, backfill_investigations_task
from tests.factories import SupplierFactory, InvestigationFactory, FailReasonFactory


class TestBackfillSuppliersTask:
    def test_creates_and_updates_suppliers_correctly(self, monkeypatch):
        """Verify that the task creates new suppliers and updates existing ones."""
        existing_supplier = SupplierFactory(supid=1, name="Old Name")

        mock_ch_data = [(1, "New Name"), (2, "New Supplier")]

        mock_client = MagicMock()
        mock_client.execute.return_value = mock_ch_data

        mock_get_client = MagicMock()
        mock_get_client.return_value.__enter__.return_value = mock_client

        monkeypatch.setattr("pricelens.tasks.get_clickhouse_client", mock_get_client)

        backfill_suppliers_task.delay()

        assert Supplier.objects.count() == 2
        updated_supplier = Supplier.objects.get(supid=1)
        assert updated_supplier.name == "New Name"
        new_supplier = Supplier.objects.get(supid=2)
        assert new_supplier.name == "New Supplier"


class TestRefreshCadenceProfilesTask:
    def test_creates_profile_for_new_supplier(self, monkeypatch):
        """Verify that a new cadence profile is created with the correct bucket."""
        SupplierFactory(supid=1)

        mock_df = pd.DataFrame({
            "supid": [1],
            "med_gap": [5.0],
            "sd_gap": [2.0],
            "days_since_last": [3],
            "last_success_date": [pd.to_datetime("today").date()],
            "total_gaps": [10],
            "bad_gaps": [1]
        })

        mock_client = MagicMock()
        mock_client.query_dataframe.return_value = mock_df

        mock_get_client = MagicMock()
        mock_get_client.return_value.__enter__.return_value = mock_client

        monkeypatch.setattr("pricelens.tasks.get_clickhouse_client", mock_get_client)

        refresh_cadence_profiles_task.delay()

        assert CadenceProfile.objects.count() == 1
        profile = CadenceProfile.objects.get(supplier_id=1)
        assert profile.bucket == "consistent"

    def test_identifies_dead_supplier(self, monkeypatch):
        """Verify that a supplier with no recent data is marked as dead."""
        SupplierFactory(supid=1)

        mock_df = pd.DataFrame({
            "supid": [1],
            "med_gap": [5.0],
            "sd_gap": [2.0],
            "days_since_last": [30],
            "last_success_date": [pd.to_datetime("today").date() - pd.Timedelta(days=30)],
            "total_gaps": [10],
            "bad_gaps": [1]
        })

        mock_client = MagicMock()
        mock_client.query_dataframe.return_value = mock_df

        mock_get_client = MagicMock()
        mock_get_client.return_value.__enter__.return_value = mock_client

        monkeypatch.setattr("pricelens.tasks.get_clickhouse_client", mock_get_client)

        refresh_cadence_profiles_task.delay()

        profile = CadenceProfile.objects.get(supplier_id=1)
        assert profile.bucket == "dead"

    def test_identifies_inconsistent_supplier(self, monkeypatch):
        """Verify that a supplier with high deviation is marked as inconsistent."""
        SupplierFactory(supid=1)

        mock_df = pd.DataFrame({
            "supid": [1],
            "med_gap": [5.0],
            "sd_gap": [8.0],
            "days_since_last": [3],
            "last_success_date": [pd.to_datetime("today").date()],
            "total_gaps": [10],
            "bad_gaps": [4]  # 40% bad gaps
        })

        mock_client = MagicMock()
        mock_client.query_dataframe.return_value = mock_df

        mock_get_client = MagicMock()
        mock_get_client.return_value.__enter__.return_value = mock_client

        monkeypatch.setattr("pricelens.tasks.get_clickhouse_client", mock_get_client)

        refresh_cadence_profiles_task.delay()

        profile = CadenceProfile.objects.get(supplier_id=1)
        assert profile.bucket == "inconsistent"

    def test_handles_new_supplier_with_one_success(self, monkeypatch):
        """Verify that a supplier with one success is put in the 'new' bucket."""
        SupplierFactory(supid=1)

        mock_df = pd.DataFrame({
            "supid": [1],
            "days": [[pd.to_datetime("today").date()]],
            "med_gap": [None],
            "sd_gap": [None],
            "days_since_last": [1],
            "last_success_date": [pd.to_datetime("today").date()],
            "total_gaps": [0],
            "bad_gaps": [0]
        })

        mock_client = MagicMock()
        mock_client.query_dataframe.return_value = mock_df

        mock_get_client = MagicMock()
        mock_get_client.return_value.__enter__.return_value = mock_client

        monkeypatch.setattr("pricelens.tasks.get_clickhouse_client", mock_get_client)

        refresh_cadence_profiles_task.delay()

        profile = CadenceProfile.objects.get(supplier_id=1)
        assert profile.bucket == "new"
        assert profile.median_gap_days is None
        assert profile.sd_gap is None


class TestBackfillInvestigationsTask:
    def test_backfills_missing_investigations(self, monkeypatch):
        """Verify that the task adds new investigations and ignores existing ones."""
        supplier = SupplierFactory(supid=1)
        reason = FailReasonFactory(code="Test Error")
        InvestigationFactory(
            supplier=supplier,
            fail_reason=reason,
            event_dt=pd.to_datetime("2025-08-06 10:00:00").tz_localize("Europe/Moscow")
        )

        mock_df = pd.DataFrame({
            "event_dt": [pd.to_datetime("2025-08-06 10:00:00"), pd.to_datetime("2025-08-06 12:00:00")],
            "supid": [1, 1],
            "error_text": ["Test Error", "New Error"]
        })

        mock_client = MagicMock()
        mock_client.query_dataframe.return_value = mock_df

        mock_get_client = MagicMock()
        mock_get_client.return_value.__enter__.return_value = mock_client

        monkeypatch.setattr("pricelens.tasks.get_clickhouse_client", mock_get_client)

        backfill_investigations_task.delay()

        assert Investigation.objects.count() == 2
        assert Investigation.objects.filter(fail_reason__code="New Error").exists()
