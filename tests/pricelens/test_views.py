import pytest
from django.urls import reverse

from pricelens.models import BucketChoices, InvestigationStatus
from tests.factories import CadenceProfileFactory, InvestigationFactory, UserFactory


class TestDashboardView:
    @pytest.fixture
    def user(self):
        return UserFactory()

    def test_dashboard_view_get_success(self, client, user):
        """Test that the DashboardView returns a 200 OK response."""
        client.force_login(user)
        url = reverse("pricelens:dashboard")
        response = client.get(url)
        assert response.status_code == 200
        assert "pricelens/dashboard.html" in [t.name for t in response.templates]

    def test_dashboard_view_context_data(self, client, user):
        """Test that the dashboard view provides the expected context data."""
        client.force_login(user)
        url = reverse("pricelens:dashboard")
        response = client.get(url)
        assert "summary" in response.context
        assert "top_reasons" in response.context
        assert "buckets" in response.context
        assert "anomalies" in response.context
        assert "investigation_stats" in response.context


@pytest.mark.django_db
class TestQueueView:
    @pytest.fixture
    def user(self):
        return UserFactory()

    def test_queue_view_get_success(self, client, user):
        """Test that the QueueView returns a 200 OK response."""
        client.force_login(user)
        url = reverse("pricelens:queue")
        response = client.get(url)
        assert response.status_code == 200
        assert "pricelens/queue.html" in [t.name for t in response.templates]

    @pytest.mark.parametrize(
        "status, expected_count",
        [
            (InvestigationStatus.OPEN, 5),
            (InvestigationStatus.RESOLVED, 3),
            (InvestigationStatus.UNRESOLVED, 2),
            ("all", 10),
        ],
    )
    def test_queue_view_filtering(self, client, user, status, expected_count):
        """Test that the QueueView correctly filters by status."""
        client.force_login(user)
        InvestigationFactory.create_batch(5, status=InvestigationStatus.OPEN)
        InvestigationFactory.create_batch(3, status=InvestigationStatus.RESOLVED)
        InvestigationFactory.create_batch(2, status=InvestigationStatus.UNRESOLVED)

        url = reverse("pricelens:queue")
        # The view expects the integer value of the status enum
        status_val = status if status == "all" else status.value
        response = client.get(url, {"status": status_val})
        assert response.status_code == 200
        assert len(response.context["investigations"]) == expected_count

    def test_queue_view_pagination(self, client, user):
        """Test that pagination works correctly in the QueueView."""
        client.force_login(user)
        InvestigationFactory.create_batch(60)

        url = reverse("pricelens:queue")
        response = client.get(url)

        assert response.status_code == 200
        assert len(response.context["investigations"]) == 50
        assert response.context["is_paginated"]
        assert response.context["page_obj"].number == 1

        response = client.get(url + "?page=2")
        assert response.status_code == 200
        assert len(response.context["investigations"]) == 10
        assert response.context["page_obj"].number == 2


@pytest.mark.django_db
class TestInvestigationDetailView:
    @pytest.fixture
    def user(self):
        return UserFactory()

    @pytest.fixture
    def investigation(self):
        return InvestigationFactory()

    def test_investigation_detail_view_get_success(self, client, user, investigation):
        """Test that the InvestigationDetailView returns a 200 OK response."""
        client.force_login(user)
        url = reverse("pricelens:investigate", kwargs={"pk": investigation.pk})
        response = client.get(url)
        assert response.status_code == 200
        assert "pricelens/investigate.html" in [t.name for t in response.templates]

    def test_investigation_detail_view_context_data(self, client, user, investigation):
        """Test that the detail view provides the investigation object in the context."""
        client.force_login(user)
        url = reverse("pricelens:investigate", kwargs={"pk": investigation.pk})
        response = client.get(url)
        assert response.context["investigation"] == investigation

    def test_investigation_detail_view_update(self, client, user, investigation):
        """Test that the InvestigationDetailView correctly updates the investigation."""
        client.force_login(user)
        url = reverse("pricelens:investigate", kwargs={"pk": investigation.pk})
        data = {
            "note": "This is a test note.",
            "action": "resolve",
        }
        response = client.post(url, data)
        assert response.status_code == 302
        assert response.url == reverse("pricelens:queue")

        investigation.refresh_from_db()
        assert investigation.note == "This is a test note."
        assert investigation.status == InvestigationStatus.RESOLVED
        assert investigation.investigator == user


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
        assert "pricelens/cadence.html" in [t.name for t in response.templates]

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
