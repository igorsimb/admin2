from django.urls import reverse


def test_health_endpoint_returns_ok(client):
    response = client.get(reverse("health"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_endpoint_does_not_require_authentication(client):
    response = client.get("/health")

    assert response.status_code == 200
