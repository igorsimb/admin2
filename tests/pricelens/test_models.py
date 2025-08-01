"""
Tests for pricelens models.
"""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import override_settings

from common.models import Supplier
from pricelens.models import (
    BucketChoices,
    CadenceDaily,
    CadenceProfile,
    Investigation,
    InvestigationStatus,
)

User = get_user_model()
pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    """Provides a user instance for foreign key relations."""
    return User.objects.create_user(username="testuser", password="testpassword")


@pytest.fixture
def supplier():
    """Provides a supplier instance for foreign key relations."""
    return Supplier.objects.create(supid=1234, name="Test Supplier")


class TestInvestigationModel:
    """Tests for the Investigation model."""

    def test_create_investigation(self, user, supplier):
        """Test that an Investigation instance can be created successfully."""
        investigation = Investigation.objects.create(
            supplier=supplier,
            event_dt=datetime.datetime.now(datetime.UTC),
            error_id=1,
            error_text="FILE_READ_ERROR",
            stage="load_mail",
            file_path="/path/to/file.csv",
            status=InvestigationStatus.OPEN,
            investigator=user,
        )
        assert Investigation.objects.count() == 1
        assert investigation.supplier == supplier
        assert investigation.status == InvestigationStatus.OPEN
        assert investigation.investigator == user
        assert investigation.created_at is not None

    def test_default_values(self, supplier):
        """Test that default values are set correctly."""
        investigation = Investigation.objects.create(
            supplier=supplier,
            event_dt=datetime.datetime.now(datetime.UTC),
            error_id=1,
            error_text="Default test",
            stage="test",
        )
        assert investigation.status == InvestigationStatus.OPEN
        assert investigation.note == ""
        assert investigation.file_path == ""

    @override_settings(PRICELENS_FILE_SERVER_URL="http://files.example.com/")
    def test_get_download_url_with_setting(self):
        """Test that the download URL is constructed correctly when the setting is present."""
        inv = Investigation(
            file_path="/mail_backup/supplier-abc/price.xlsx",
        )
        expected = "http://files.example.com/mail_backup/supplier-abc/price.xlsx"
        assert inv.get_download_url == expected

    @override_settings(PRICELENS_FILE_SERVER_URL="http://files.example.com")
    def test_get_download_url_with_special_chars(self):
        """Test URL encoding for special characters in the file path."""
        inv = Investigation(
            file_path="/mail_backup/supplier abc/price list (new).xlsx",
        )
        expected = "http://files.example.com/mail_backup/supplier%20abc/price%20list%20%28new%29.xlsx"
        assert inv.get_download_url == expected

    @override_settings(PRICELENS_FILE_SERVER_URL=None)
    def test_get_download_url_without_setting(self):
        """Test that an empty string is returned if the setting is not configured."""
        inv = Investigation(file_path="/path/to/file.csv")
        assert inv.get_download_url == ""

    @override_settings(PRICELENS_FILE_SERVER_URL="http://files.example.com")
    def test_get_download_url_with_empty_path(self):
        """Test that an empty string is returned if the file_path is empty."""
        inv = Investigation(file_path="")
        assert inv.get_download_url == ""


class TestCadenceModels:
    """Tests for the CadenceDaily and CadenceProfile models."""

    def test_create_cadence_daily(self, supplier):
        """Test that a CadenceDaily instance can be created successfully."""
        CadenceDaily.objects.create(supplier=supplier, date=datetime.date.today(), had_file=True, attempts=1, errors=0)
        assert CadenceDaily.objects.count() == 1

    def test_cadence_daily_unique_together_constraint(self, supplier):
        """Test that the unique_together constraint on date and supid is enforced."""
        today = datetime.date.today()
        # Create the first entry
        CadenceDaily.objects.create(supplier=supplier, date=today)
        # Attempt to create a duplicate
        with pytest.raises(IntegrityError):
            CadenceDaily.objects.create(supplier=supplier, date=today)

    def test_create_cadence_profile(self, supplier):
        """Test that a CadenceProfile instance can be created successfully."""
        profile = CadenceProfile.objects.create(
            supplier=supplier,
            median_gap_days=3,
            sd_gap=1.5,
            days_since_last=2,
            last_success_date=datetime.date.today(),
            bucket=BucketChoices.CONSISTENT,
        )
        assert CadenceProfile.objects.count() == 1
        assert profile.bucket == BucketChoices.CONSISTENT
        assert profile.created_at is not None
        assert profile.updated_at is not None
