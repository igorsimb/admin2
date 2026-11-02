"""Verify profile email actions against the upgraded allauth verification flow."""

from allauth.account.models import EmailAddress
from django.urls import reverse


def test_verification_sends_to_current_email_and_respects_rate_limit(client, authenticated_user, mailoutbox):
    response = client.get(reverse("email_verify"))
    client.get(reverse("email_verify"))

    assert response.status_code == 302
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == [authenticated_user.email]
    assert not EmailAddress.objects.get(user=authenticated_user, email=authenticated_user.email).verified


def test_verified_address_does_not_receive_another_confirmation(client, authenticated_user, mailoutbox):
    EmailAddress.objects.filter(user=authenticated_user).update(verified=True)

    response = client.get(reverse("email_verify"))

    assert response.status_code == 302
    assert not mailoutbox


def test_email_change_sends_confirmation_to_new_address(client, authenticated_user, mailoutbox):
    EmailAddress.objects.filter(user=authenticated_user).update(verified=True)

    response = client.post(reverse("email_change"), {"email": "changed@example.com"})

    assert response.status_code == 302
    authenticated_user.refresh_from_db()
    assert authenticated_user.email == "changed@example.com"
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["changed@example.com"]
    assert not EmailAddress.objects.get(user=authenticated_user, email="changed@example.com").verified
