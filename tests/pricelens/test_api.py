"""
Tests for the Pricelens API.
"""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from tests.factories import SupplierFactory

User = get_user_model()


@pytest.fixture
def api_client(db):
    """Provides an authenticated API client."""
    user = User.objects.create_user(username="apiuser", password="apipassword")
    token = Token.objects.create(user=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


class TestLogEventAPI:
    """Tests for the /api/v1/pricelens/log_event/ endpoint."""

    def test_unauthenticated_request_is_rejected(self, db):
        """Verify that anonymous users cannot access the endpoint."""
        client = APIClient()
        url = reverse("pricelens-api:log-event")
        response = client.post(url, data={}, content_type="application/json")
        assert response.status_code == 401

    def test_valid_request_creates_investigation(self, api_client):
        """Verify that a valid POST request creates an Investigation record."""
        supplier = SupplierFactory()
        url = reverse("pricelens-api:log-event")
        data = {
            "event_dt": datetime.datetime.now(datetime.UTC).isoformat(),
            "supid": supplier.supid,
            "reason": "FILE_READ_ERROR",
            "stage": "load_mail",
            "file_path": "/path/to/file.csv",
        }
        response = api_client.post(url, data=data, content_type="application/json")
        assert response.status_code == 201

    def test_invalid_data_returns_400(self, api_client):
        """Verify that invalid data returns a 400 Bad Request response."""
        url = reverse("pricelens-api:log-event")
        data = {
            "event_dt": "not-a-date",
            "supid": "not-an-integer",
        }
        response = api_client.post(url, data=data, content_type="application/json")
        assert response.status_code == 400
