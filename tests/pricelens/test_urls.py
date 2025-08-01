"""
Tests for pricelens URLs.
"""

import uuid

from django.urls import resolve, reverse


def test_dashboard_url():
    """Test that the dashboard URL resolves correctly."""
    url = reverse("pricelens:dashboard")
    assert resolve(url).view_name == "pricelens:dashboard"


def test_queue_url():
    """Test that the queue URL resolves correctly."""
    url = reverse("pricelens:queue")
    assert resolve(url).view_name == "pricelens:queue"


def test_investigation_detail_url():
    """Test that the investigation detail URL resolves correctly."""
    test_uuid = uuid.uuid4()
    url = reverse("pricelens:investigate", kwargs={"pk": test_uuid})
    assert resolve(url).view_name == "pricelens:investigate"
