"""
GLORYBELLE — Newsletter Tests.
"""
import pytest

from apps.newsletter.models import NewsletterSubscriber


@pytest.mark.django_db
class TestNewsletterSubscribe:
    def test_subscribe_success(self, api_client):
        response = api_client.post(
            "/api/newsletter/subscribe/",
            {"email": "cliente@glorybelle.it"},
            format="json",
        )
        assert response.status_code == 201
        assert NewsletterSubscriber.objects.filter(
            email="cliente@glorybelle.it", is_active=True
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
        assert response.status_code == 200
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
        # Unsubscribe
        api_client.post(
            "/api/newsletter/unsubscribe/",
            {"email": "cliente@glorybelle.it"},
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
        assert response.status_code == 200
        assert NewsletterSubscriber.objects.get(
            email="cliente@glorybelle.it"
        ).is_active


@pytest.mark.django_db
class TestNewsletterUnsubscribe:
    def test_unsubscribe_success(self, api_client):
        NewsletterSubscriber.objects.create(
            email="cliente@glorybelle.it", is_active=True
        )

        response = api_client.post(
            "/api/newsletter/unsubscribe/",
            {"email": "cliente@glorybelle.it"},
            format="json",
        )
        assert response.status_code == 200
        subscriber = NewsletterSubscriber.objects.get(
            email="cliente@glorybelle.it"
        )
        assert subscriber.is_active is False
        assert subscriber.unsubscribed_at is not None

    def test_unsubscribe_nonexistent_email(self, api_client):
        """Should not reveal whether the email was subscribed."""
        response = api_client.post(
            "/api/newsletter/unsubscribe/",
            {"email": "nonexistent@example.it"},
            format="json",
        )
        assert response.status_code == 200
