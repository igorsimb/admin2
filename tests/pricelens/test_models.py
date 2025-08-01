"""
Tests for pricelens models.
"""

import datetime

import pytest
from django.contrib.auth import get_user_model

from pricelens.models import BucketChoices, CadenceDaily, CadenceProfile, Investigation, InvestigationStatus

User = get_user_model()
pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    """Provides a user instance for foreign key relations."""
    return User.objects.create_user(username="testuser", password="testpassword")


class TestInvestigationModel:
    """Tests for the Investigation model."""

    def test_create_investigation(self, user):
        """Test that an Investigation instance can be created successfully."""
        investigation = Investigation.objects.create(
            event_dt=datetime.datetime.now(datetime.UTC),
            supid=1234,
            error_id=1,
            error_text="FILE_READ_ERROR",
            stage="load_mail",
            file_path="/path/to/file.csv",
            status=InvestigationStatus.OPEN,
            investigator=user,
        )
        assert Investigation.objects.count() == 1
        assert investigation.supid == 1234
        assert investigation.status == InvestigationStatus.OPEN
        assert investigation.investigator == user
        assert investigation.created_at is not None


class TestCadenceModels:
    """Tests for the CadenceDaily and CadenceProfile models."""

    def test_create_cadence_daily(self):
        """Test that a CadenceDaily instance can be created successfully."""
        CadenceDaily.objects.create(date=datetime.date.today(), supid=5678, had_file=True, attempts=1, errors=0)
        assert CadenceDaily.objects.count() == 1

    def test_create_cadence_profile(self):
        """Test that a CadenceProfile instance can be created successfully."""
        profile = CadenceProfile.objects.create(
            supid=5678,
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
