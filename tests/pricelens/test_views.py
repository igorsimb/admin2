"""
Tests for pricelens views.
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from pricelens.models import Investigation
from tests.factories import SupplierFactory

User = get_user_model()


@pytest.fixture(scope="function")
def authenticated_client(db):
    """Provides a Django test client with a logged-in user."""
    user = User.objects.create_user(username="testuser", password="testpassword")
    client = Client()
    client.force_login(user)
    return client


class TestDashboardView:
    """Tests for the DashboardView."""

    def test_dashboard_view_returns_200(self, authenticated_client):
        """Test that the dashboard view returns a 200 OK status code."""
        url = reverse("pricelens:dashboard")
        response = authenticated_client.get(url)
        assert response.status_code == 200

    def test_dashboard_view_uses_correct_template(self, authenticated_client):
        """Test that the dashboard view uses the correct template."""
        url = reverse("pricelens:dashboard")
        response = authenticated_client.get(url)
        assert "pricelens/dashboard.html" in [t.name for t in response.templates]

    def test_dashboard_view_context_data(self, authenticated_client):
        """Test that the dashboard view provides the expected context data."""
        url = reverse("pricelens:dashboard")
        response = authenticated_client.get(url)
        # Based on the view's implementation, we expect these keys.
        assert "summary" in response.context
        assert "top_reasons" in response.context
        assert "buckets" in response.context
        assert "anomalies" in response.context


class TestQueueView:
    """Tests for the QueueView."""

    def test_queue_view_returns_200(self, authenticated_client):
        """Test that the queue view returns a 200 OK status code."""
        url = reverse("pricelens:queue")
        response = authenticated_client.get(url)
        assert response.status_code == 200

    def test_queue_view_uses_correct_template(self, authenticated_client):
        """Test that the queue view uses the correct template."""
        url = reverse("pricelens:queue")
        response = authenticated_client.get(url)
        assert "pricelens/queue.html" in [t.name for t in response.templates]

    def test_queue_view_context_data(self, authenticated_client):
        """Test that the queue view provides paginated investigation data."""
        supplier = SupplierFactory()
        Investigation.objects.create(event_dt=timezone.now(), supplier=supplier, error_id=1, error_text="test")
        url = reverse("pricelens:queue")
        response = authenticated_client.get(url)
        assert "object_list" in response.context  # ListView uses object_list
        assert "is_paginated" in response.context


@pytest.fixture
def test_investigation(db):
    """Creates a test Investigation object."""
    supplier = SupplierFactory()
    return Investigation.objects.create(
        event_dt=timezone.now(),
        supplier=supplier,
        error_id=404,
        error_text="File not found",
        stage="load_mail",
    )


class TestInvestigationDetailView:
    """Tests for the InvestigationDetailView."""

    def test_detail_view_returns_200(self, authenticated_client, test_investigation):
        """Test that the detail view returns a 200 OK status code for a GET request."""
        url = reverse("pricelens:investigate", kwargs={"pk": test_investigation.pk})
        response = authenticated_client.get(url)
        assert response.status_code == 200

    def test_detail_view_uses_correct_template(self, authenticated_client, test_investigation):
        """Test that the detail view uses the correct template."""
        url = reverse("pricelens:investigate", kwargs={"pk": test_investigation.pk})
        response = authenticated_client.get(url)
        assert "pricelens/investigate.html" in [t.name for t in response.templates]

    def test_detail_view_context_data(self, authenticated_client, test_investigation):
        """Test that the detail view provides the investigation object in the context."""
        url = reverse("pricelens:investigate", kwargs={"pk": test_investigation.pk})
        response = authenticated_client.get(url)
        # The view uses UpdateView, which puts the object in the context
        assert response.context["object"] == test_investigation

    def test_detail_view_post_redirects(self, authenticated_client, test_investigation):
        """Test that a POST request to the detail view redirects to the queue."""
        url = reverse("pricelens:investigate", kwargs={"pk": test_investigation.pk})
        response = authenticated_client.post(url, data={"note": "Test note", "action": "resolve"})
        assert response.status_code == 302
        assert response.url == reverse("pricelens:queue")
