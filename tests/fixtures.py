"""
This module contains shared pytest fixtures for the entire test suite.

Fixtures defined here are automatically discovered by pytest and can be used in any test
without needing to be explicitly imported. This helps to reduce code duplication and improve
maintainability.

For more information on pytest fixtures, see:
https://docs.pytest.org/en/latest/how-to/fixtures.html
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from tests.factories import UserFactory

User = get_user_model()


@pytest.fixture
def user(db):
    """Provides a user instance."""
    return UserFactory()


@pytest.fixture
def authenticated_user(client, user):
    """Provides an authenticated user."""
    client.force_login(user)
    return user


@pytest.fixture
def api_client(db):
    """Provides an authenticated API client."""
    user = User.objects.create_user(username="apiuser", password="apipassword")
    token = Token.objects.create(user=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client
