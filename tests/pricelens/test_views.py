import pytest
from django.urls import reverse

from pricelens.models import BucketChoices
from tests.factories import CadenceProfileFactory, UserFactory


@pytest.mark.django_db
class TestCadenceView:
    @pytest.fixture
    def user(self):
        """Fixture for creating a user."""
        return UserFactory()

    @pytest.fixture
    def cadence_profiles(self):
        """Fixture for creating a batch of cadence profiles for testing filtering."""
        CadenceProfileFactory.create_batch(5, bucket=BucketChoices.CONSISTENT)
        CadenceProfileFactory.create_batch(3, bucket=BucketChoices.INCONSISTENT)
        CadenceProfileFactory.create_batch(2, bucket=BucketChoices.DEAD)

    def test_cadence_view_get_success(self, client, user):
        """Test that the CadenceView returns a 200 OK response."""
        client.force_login(user)
        url = reverse("pricelens:cadence")
        response = client.get(url)
        assert response.status_code == 200

    @pytest.mark.parametrize(
        "bucket, expected_count",
        [
            ("consistent", 5),
            ("inconsistent", 3),
            ("dead", 2),
            ("all", 10),
        ],
    )
    def test_cadence_view_filtering(self, client, user, cadence_profiles, bucket, expected_count):
        """Test that the CadenceView correctly filters by bucket."""
        client.force_login(user)
        url = reverse("pricelens:cadence")
        response = client.get(url, {"bucket": bucket})
        assert response.status_code == 200
        assert len(response.context["profiles"]) == expected_count

    def test_cadence_view_sorting(self, client, user):
        """Test that the CadenceView correctly sorts by days_since_last."""
        client.force_login(user)
        CadenceProfileFactory.create(days_since_last=10)
        CadenceProfileFactory.create(days_since_last=5)
        CadenceProfileFactory.create(days_since_last=20)

        url = reverse("pricelens:cadence")
        response = client.get(url)

        assert response.status_code == 200
        profiles = response.context["profiles"]
        assert len(profiles) == 3
        assert profiles[0].days_since_last == 5
        assert profiles[1].days_since_last == 10
        assert profiles[2].days_since_last == 20

    def test_cadence_view_pagination(self, client, user):
        """Test that pagination works correctly in the CadenceView."""
        client.force_login(user)
        CadenceProfileFactory.create_batch(60)

        url = reverse("pricelens:cadence")
        response = client.get(url)

        assert response.status_code == 200
        assert len(response.context["profiles"]) == 50
        assert response.context["is_paginated"]
        assert response.context["page_obj"].number == 1

        # Check the second page
        response = client.get(url + "?page=2")
        assert response.status_code == 200
        assert len(response.context["profiles"]) == 10
        assert response.context["page_obj"].number == 2
