"""Protect the styled account pages and single-click, CSRF-protected logout."""

from pathlib import Path

import pytest
from allauth.account.models import EmailAddress
from django.template.loader import get_template
from django.urls import reverse


@pytest.mark.parametrize("page", ["login", "logout"])
def test_account_templates_override_allauth_defaults(settings, page):
    template = get_template(f"account/{page}.html")

    assert Path(template.origin.name) == settings.BASE_DIR / "accounts" / "templates" / "account" / f"{page}.html"


@pytest.mark.parametrize("route", ["account_login", "account_signup", "account_reset_password"])
def test_account_entrance_pages_use_project_styles(client, route):
    response = client.get(reverse(route))

    assert response.status_code == 200
    html = response.content.decode()
    assert "daisyui@5" in html
    assert "card bg-base-100" in html
    assert 'name="csrfmiddlewaretoken"' in html


def test_login_preserves_next_and_authenticates(client, user):
    user.set_password("A-test-password-8271")
    user.save()
    EmailAddress.objects.filter(user=user).update(verified=True)
    destination = reverse("cross_dock:task_list")
    response = client.get(reverse("account_login"), {"next": destination})

    assert f'value="{destination}"' in response.content.decode()
    response = client.post(
        reverse("account_login"),
        {"login": user.email, "password": "A-test-password-8271", "next": destination},
    )

    assert response.status_code == 302
    assert response.url == destination
    assert client.session["_auth_user_id"] == str(user.pk)


def test_dropdown_logout_uses_post_with_csrf_and_ends_session(client, authenticated_user):
    client.handler.enforce_csrf_checks = True
    page = client.get(reverse("index"))
    html = page.content.decode()
    logout_url = reverse("account_logout")

    # Both desktop and mobile menus submit directly to the logout endpoint.
    assert html.count(f'<form method="post" action="{logout_url}"') == 2
    assert f'href="{logout_url}"' not in html
    assert client.post(logout_url).status_code == 403
    assert "_auth_user_id" in client.session

    response = client.post(logout_url, {"csrfmiddlewaretoken": client.cookies["csrftoken"].value})

    assert response.status_code == 302
    assert "_auth_user_id" not in client.session


def test_direct_logout_page_is_styled_and_does_not_logout_on_get(client, authenticated_user):
    response = client.get(reverse("account_logout"))

    assert response.status_code == 200
    assert "daisyui@5" in response.content.decode()
    assert "card bg-base-100" in response.content.decode()
    assert "_auth_user_id" in client.session
