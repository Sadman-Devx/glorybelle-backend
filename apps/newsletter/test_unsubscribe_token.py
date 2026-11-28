"""Newsletter: only a signed link can unsubscribe an address; every e-mail carries that link."""
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

from apps.newsletter.models import NewsletterSubscriber
from apps.newsletter.tasks import send_newsletter
from apps.newsletter.tokens import make_unsubscribe_token, read_unsubscribe_token, unsubscribe_url

pytestmark = pytest.mark.django_db
URL = "/api/newsletter/unsubscribe/"


def _sub(email, active=True):
    return NewsletterSubscriber.objects.create(email=email, is_active=active)


def test_bare_email_can_no_longer_unsubscribe_anyone(api_client):
    sub = _sub("victim@example.com")
    r = api_client.post(URL, {"email": "victim@example.com"}, format="json")
    assert r.status_code == 400
    sub.refresh_from_db()
    assert sub.is_active is True


def test_valid_token_unsubscribes(api_client):
    sub = _sub("me@example.com")
    r = api_client.post(URL, {"token": make_unsubscribe_token("me@example.com")}, format="json")
    assert r.status_code == 200
    sub.refresh_from_db()
    assert sub.is_active is False and sub.unsubscribed_at is not None


def test_token_is_case_insensitive_on_the_address(api_client):
    sub = _sub("mixed@example.com")
    api_client.post(URL, {"token": make_unsubscribe_token("MiXeD@Example.com")}, format="json")
    sub.refresh_from_db()
    assert sub.is_active is False


def test_unsubscribing_twice_is_idempotent(api_client):
    _sub("twice@example.com")
    token = make_unsubscribe_token("twice@example.com")
    assert api_client.post(URL, {"token": token}, format="json").status_code == 200
    assert api_client.post(URL, {"token": token}, format="json").status_code == 200


@pytest.mark.parametrize("bad", ["garbage", "", "a.b.c", "x" * 400])
def test_forged_or_garbage_token_is_rejected(api_client, bad):
    sub = _sub("safe@example.com")
    r = api_client.post(URL, {"token": bad}, format="json")
    assert r.status_code == 400
    sub.refresh_from_db()
    assert sub.is_active is True


def test_token_cannot_be_reused_for_another_address(api_client):
    a, b = _sub("a@example.com"), _sub("b@example.com")
    api_client.post(URL, {"token": make_unsubscribe_token("a@example.com")}, format="json")
    a.refresh_from_db(); b.refresh_from_db()
    assert a.is_active is False and b.is_active is True


def test_token_signed_with_another_salt_is_rejected():
    from django.core import signing

    foreign = signing.dumps("x@example.com", salt="some.other.feature")
    assert read_unsubscribe_token(foreign) is None


def test_token_roundtrip_and_url():
    assert read_unsubscribe_token(make_unsubscribe_token("Rt@Example.com")) == "rt@example.com"
    with override_settings(FRONTEND_URL="https://glorybelle.it/"):
        url = unsubscribe_url("rt@example.com")
    assert url.startswith("https://glorybelle.it/newsletter/annulla-iscrizione?token=")


# ---------------------------------------------------------------- the e-mails themselves
@override_settings(SENDGRID_API_KEY="SG.test", FRONTEND_URL="https://glorybelle.it")
@patch("sendgrid.SendGridAPIClient")
def test_every_newsletter_carries_its_own_unsubscribe_link(sendgrid_cls):
    _sub("one@example.com"); _sub("two@example.com"); _sub("gone@example.com", active=False)
    assert send_newsletter.apply(args=("Novità", "<p>Ciao</p>")).get() == 2

    sent = [call.args[0] for call in sendgrid_cls.return_value.send.call_args_list]
    assert len(sent) == 2
    by_recipient = {m.get()["personalizations"][0]["to"][0]["email"]: m for m in sent}
    assert set(by_recipient) == {"one@example.com", "two@example.com"}
    for email, message in by_recipient.items():
        body = message.get()
        html = body["content"][0]["value"]
        link = unsubscribe_url(email)
        assert link in html                                   # in the visible footer
        assert body["headers"]["List-Unsubscribe"] == f"<{link}>"  # and in the header
        assert read_unsubscribe_token(link.split("token=")[1]) == email


@override_settings(SENDGRID_API_KEY="SG.test")
@patch("sendgrid.SendGridAPIClient")
def test_one_failing_recipient_does_not_stop_or_duplicate_the_rest(sendgrid_cls):
    for e in ("a@example.com", "b@example.com", "c@example.com"):
        _sub(e)
    calls = {"n": 0}

    def flaky(message):
        calls["n"] += 1
        if calls["n"] == 2:
            raise ConnectionError("bounce")

    sendgrid_cls.return_value.send.side_effect = flaky
    assert send_newsletter.apply(args=("S", "<p>x</p>")).get() == 2   # 2 delivered, no batch retry
    assert calls["n"] == 3                                            # nobody was mailed twice
