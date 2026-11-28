"""Newsletter opt-in, token, cooldown, and enumeration protections."""
from unittest.mock import patch
import uuid

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone

from apps.newsletter.models import NewsletterSubscriber
from apps.newsletter.tokens import make_confirmation_token, make_unsubscribe_token

SUBSCRIBE_URL = "/api/newsletter/subscribe/"
CONFIRM_URL = "/api/newsletter/confirm/"
UNSUBSCRIBE_URL = "/api/newsletter/unsubscribe/"


@pytest.mark.django_db(transaction=True)
def test_subscribe_response_is_identical_for_new_pending_and_confirmed(api_client):
    NewsletterSubscriber.objects.create(
        email="already-confirmed@example.com",
        is_active=True,
        is_confirmed=True,
    )
    with patch("apps.newsletter.views.send_confirmation_email.delay") as send_email:
        new = api_client.post(
            SUBSCRIBE_URL,
            {"email": "new@example.com"},
            format="json",
        )
        pending = api_client.post(
            SUBSCRIBE_URL,
            {"email": "new@example.com"},
            format="json",
        )
        confirmed = api_client.post(
            SUBSCRIBE_URL,
            {"email": "already-confirmed@example.com"},
            format="json",
        )

    assert all(
        response.status_code == 202 and response.data == new.data
        for response in (new, pending, confirmed)
    )
    assert send_email.call_count == 1
    subscriber = NewsletterSubscriber.objects.get(email="new@example.com")
    assert subscriber.is_active and not subscriber.is_confirmed
    assert subscriber.confirmation_sent_at is not None


@pytest.mark.django_db(transaction=True)
def test_confirmation_is_explicit_and_idempotent(api_client):
    subscriber = NewsletterSubscriber.objects.create(
        email="confirm-me@example.com",
        is_active=True,
        is_confirmed=False,
    )
    token = make_confirmation_token(
        subscriber.email, str(subscriber.confirmation_nonce)
    )

    first = api_client.post(CONFIRM_URL, {"token": token}, format="json")
    second = api_client.post(CONFIRM_URL, {"token": token}, format="json")

    assert first.status_code == second.status_code == 200
    assert first.data == second.data
    subscriber.refresh_from_db()
    assert subscriber.is_confirmed


@pytest.mark.django_db(transaction=True)
def test_forged_expired_and_stale_confirmation_tokens_are_rejected(api_client):
    subscriber = NewsletterSubscriber.objects.create(
        email="token@example.com",
        is_active=True,
        is_confirmed=False,
    )
    forged = api_client.post(
        CONFIRM_URL,
        {"token": "forged-token"},
        format="json",
    )
    assert forged.status_code == 400

    token = make_confirmation_token(
        subscriber.email, str(subscriber.confirmation_nonce)
    )
    expired = api_client.post(
        CONFIRM_URL,
        {"token": _expired_confirmation_token(subscriber)},
        format="json",
    )
    assert expired.status_code == 410

    api_client.post(
        UNSUBSCRIBE_URL,
        {"token": make_unsubscribe_token(subscriber.email)},
        format="json",
    )
    stale = api_client.post(CONFIRM_URL, {"token": token}, format="json")
    assert stale.status_code == 400
    subscriber.refresh_from_db()
    assert not subscriber.is_active
    assert not subscriber.is_confirmed


def _expired_confirmation_token(subscriber):
    from django.core import signing
    from apps.newsletter.tokens import CONFIRMATION_MAX_AGE, CONFIRMATION_SALT

    old_timestamp = timezone.now().timestamp() - CONFIRMATION_MAX_AGE - 1
    with patch("django.core.signing.time.time", return_value=old_timestamp):
        return signing.dumps(
            {
                "email": subscriber.email,
                "nonce": str(subscriber.confirmation_nonce),
            },
            salt=CONFIRMATION_SALT,
        )


@pytest.mark.django_db(transaction=True)
def test_resubscribe_after_unsubscribe_requires_a_new_confirmation(api_client):
    subscriber = NewsletterSubscriber.objects.create(
        email="resubscribe@example.com",
        is_active=True,
        is_confirmed=True,
    )
    old_nonce = str(subscriber.confirmation_nonce)
    old_token = make_confirmation_token(subscriber.email, old_nonce)
    api_client.post(
        UNSUBSCRIBE_URL,
        {"token": make_unsubscribe_token(subscriber.email)},
        format="json",
    )

    with patch("apps.newsletter.views.send_confirmation_email.delay") as send_email:
        response = api_client.post(
            SUBSCRIBE_URL,
            {"email": subscriber.email},
            format="json",
        )

    assert response.status_code == 202
    send_email.assert_called_once()
    subscriber.refresh_from_db()
    assert subscriber.is_active and not subscriber.is_confirmed
    assert str(subscriber.confirmation_nonce) != old_nonce
    assert api_client.post(
        CONFIRM_URL, {"token": old_token}, format="json"
    ).status_code == 400


@pytest.mark.django_db(transaction=True)
@override_settings(NEWSLETTER_CONFIRMATION_COOLDOWN_MINUTES=15)
def test_confirmation_email_has_per_address_cooldown(api_client):
    with patch("apps.newsletter.views.send_confirmation_email.delay") as send_email:
        first = api_client.post(
            SUBSCRIBE_URL,
            {"email": "cooldown@example.com"},
            format="json",
        )
        subscriber = NewsletterSubscriber.objects.get(
            email="cooldown@example.com"
        )
        sent_at = subscriber.confirmation_sent_at

        second = api_client.post(
            SUBSCRIBE_URL,
            {"email": "cooldown@example.com"},
            format="json",
        )

    assert first.status_code == second.status_code == 202
    send_email.assert_called_once()
    subscriber.refresh_from_db()
    assert subscriber.confirmation_sent_at == sent_at


@pytest.mark.django_db(transaction=True)
def test_subscribe_is_rate_limited_per_client_ip(api_client):
    cache.clear()
    try:
        responses = [
            api_client.post(
                SUBSCRIBE_URL,
                {"email": f"throttle-{uuid.uuid4().hex}@example.com"},
                format="json",
            )
            for _ in range(6)
        ]
    finally:
        cache.clear()

    assert [response.status_code for response in responses] == [
        202, 202, 202, 202, 202, 429
    ]
