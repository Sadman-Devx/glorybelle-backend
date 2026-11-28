"""
GLORYBELLE — Newsletter Tests.
"""
import pytest

from apps.newsletter.models import NewsletterSubscriber
from apps.newsletter.tokens import make_unsubscribe_token


@pytest.mark.django_db
class TestNewsletterSubscribe:
    def test_subscribe_success(self, api_client):
        response = api_client.post(
            "/api/newsletter/subscribe/",
            {"email": "cliente@glorybelle.it"},
            format="json",
        )
        assert response.status_code == 202
        assert NewsletterSubscriber.objects.filter(
            email="cliente@glorybelle.it",
            is_active=True,
            is_confirmed=False,
        ).exists()

    def test_subscribe_duplicate_is_graceful(self, api_client):
        """Subscribing twice with the same email should not error."""
        api_client.post(
            "/api/newsletter/subscribe/",
            {"email": "cliente@glorybelle.it"},
            format="json",
        )
        response = api_client.post(
            "/api/newsletter/subscribe/",
            {"email": "cliente@glorybelle.it"},
            format="json",
        )
        assert response.status_code == 202
        assert NewsletterSubscriber.objects.filter(
            email="cliente@glorybelle.it"
        ).count() == 1

    def test_resubscribe_after_unsubscribe(self, api_client):
        """Re-subscribing should reactivate the subscriber."""
        # Subscribe
        api_client.post(
            "/api/newsletter/subscribe/",
            {"email": "cliente@glorybelle.it"},
            format="json",
        )
        # Unsubscribe (with the signed token from the e-mail link)
        api_client.post(
            "/api/newsletter/unsubscribe/",
            {"token": make_unsubscribe_token("cliente@glorybelle.it")},
            format="json",
        )
        assert not NewsletterSubscriber.objects.get(
            email="cliente@glorybelle.it"
        ).is_active

        # Re-subscribe
        response = api_client.post(
            "/api/newsletter/subscribe/",
            {"email": "cliente@glorybelle.it"},
            format="json",
        )
        subscriber = NewsletterSubscriber.objects.get(
            email="cliente@glorybelle.it"
        )
        assert response.status_code == 202
        assert subscriber.is_active
        assert not subscriber.is_confirmed


@pytest.mark.django_db
class TestNewsletterUnsubscribe:
    def test_unsubscribe_success(self, api_client):
        NewsletterSubscriber.objects.create(
            email="cliente@glorybelle.it", is_active=True
        )

        response = api_client.post(
            "/api/newsletter/unsubscribe/",
            {"token": make_unsubscribe_token("cliente@glorybelle.it")},
            format="json",
        )
        assert response.status_code == 200
        subscriber = NewsletterSubscriber.objects.get(
            email="cliente@glorybelle.it"
        )
        assert subscriber.is_active is False
        assert subscriber.unsubscribed_at is not None

    def test_unsubscribe_with_valid_token_for_unknown_email_is_still_200(self, api_client):
        """Should not reveal whether the email was subscribed."""
        response = api_client.post(
            "/api/newsletter/unsubscribe/",
            {"token": make_unsubscribe_token("nonexistent@example.it")},
            format="json",
        )
        assert response.status_code == 200
