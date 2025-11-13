import pytest
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from tests.factories import UserFactory

User = get_user_model()


@pytest.fixture
def user(db):
    """
    Fixture to create a user.
    """
    return UserFactory()


@pytest.fixture
def authenticated_user(client, user):
    """
    Fixture to create and authenticate a user.
    """
    client.force_login(user)
    return user


@pytest.fixture
def api_client(db):
    """
    Provides an authenticated API client.
    """
    user = User.objects.create_user(username="apiuser", password="apipassword")
    token = Token.objects.create(user=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client
