"""Storefront login contract: the login form posts {email, password}."""
import pytest
from django.contrib.auth.models import User

pytestmark = pytest.mark.django_db
URL = "/api/accounts/login/"


def test_login_with_email(api_client, user):
    r = api_client.post(URL, {"email": user.email, "password": "TestPass123!"}, format="json")
    assert r.status_code == 200
    assert r.data["access"] and r.data["refresh"]


def test_refresh_rotates_token_and_blacklists_previous_refresh(api_client, user):
    login = api_client.post(URL, {"email": user.email, "password": "TestPass123!"}, format="json")
    assert login.status_code == 200
    old_refresh = login.data["refresh"]

    refreshed = api_client.post(
        "/api/accounts/token/refresh/",
        {"refresh": old_refresh},
        format="json",
    )
    assert refreshed.status_code == 200
    assert refreshed.data["refresh"] != old_refresh

    reused = api_client.post(
        "/api/accounts/token/refresh/",
        {"refresh": old_refresh},
        format="json",
    )
    assert reused.status_code == 401

    next_refresh = api_client.post(
        "/api/accounts/token/refresh/",
        {"refresh": refreshed.data["refresh"]},
        format="json",
    )
    assert next_refresh.status_code == 200


def test_login_with_email_is_case_insensitive(api_client, user):
    r = api_client.post(URL, {"email": user.email.upper(), "password": "TestPass123!"}, format="json")
    assert r.status_code == 200


def test_login_with_username_still_works(api_client, user):
    r = api_client.post(URL, {"username": user.username, "password": "TestPass123!"}, format="json")
    assert r.status_code == 200


def test_login_wrong_password_is_401(api_client, user):
    r = api_client.post(URL, {"email": user.email, "password": "nope"}, format="json")
    assert r.status_code == 401


def test_login_unknown_email_is_same_401(api_client, user):
    bad_pw = api_client.post(URL, {"email": user.email, "password": "nope"}, format="json")
    unknown = api_client.post(URL, {"email": "ghost@example.com", "password": "nope"}, format="json")
    assert unknown.status_code == 401
    assert unknown.data == bad_pw.data  # no account enumeration


def test_login_requires_email_or_username(api_client):
    r = api_client.post(URL, {"password": "x"}, format="json")
    assert r.status_code == 400


def test_login_inactive_user_rejected(api_client, create_user):
    create_user(username="gone", email="gone@example.com", is_active=False)
    r = api_client.post(URL, {"email": "gone@example.com", "password": "TestPass123!"}, format="json")
    assert r.status_code == 401


def test_login_picks_matching_account_when_emails_differ_by_case(api_client, create_user):
    create_user(username="a1", email="Dup@Example.com", password="PassOne123!")
    create_user(username="a2", email="dup@example.com", password="PassTwo123!")
    r = api_client.post(URL, {"email": "dup@example.com", "password": "PassTwo123!"}, format="json")
    assert r.status_code == 200


# ---- email uniqueness is case-insensitive (+ password reset tolerates legacy duplicates)
def _register(api_client, username, email):
    return api_client.post("/api/accounts/register/", {
        "username": username, "email": email, "password": "Str0ng!Passw0rd#1",
        "password_confirm": "Str0ng!Passw0rd#1", "birth_date": "1990-05-05",
    }, format="json")


def test_register_rejects_email_differing_only_by_case(api_client):
    assert _register(api_client, "ci1", "Case@Example.com").status_code == 201
    assert _register(api_client, "ci2", "case@example.com").status_code == 400
    assert _register(api_client, "ci3", "CASE@EXAMPLE.COM").status_code == 400


def test_register_stores_email_lowercase(api_client):
    _register(api_client, "ci4", "MiXeD@Example.com")
    assert User.objects.get(username="ci4").email == "mixed@example.com"


def test_password_reset_with_legacy_case_duplicates_is_202_and_mails_both(api_client, create_user):
    from django.core import mail
    create_user(username="l1", email="Dup@Example.com")
    create_user(username="l2", email="dup@example.com")
    r = api_client.post("/api/accounts/password/reset/", {"email": "dup@example.com"}, format="json")
    assert r.status_code == 202
    assert len(mail.outbox) == 2


# ---- brute-force brake + profile DOB rule
def test_login_is_rate_limited(api_client, user):
    codes = [
        api_client.post(URL, {"email": user.email, "password": f"bad{i}"}, format="json").status_code
        for i in range(14)
    ]
    assert codes[:10] == [401] * 10
    assert 429 in codes[10:]


def test_profile_cannot_be_set_to_under_13(authenticated_client):
    r = authenticated_client.patch("/api/accounts/me/", {"date_of_birth": "2024-01-01"}, format="json")
    assert r.status_code == 400


def test_profile_accepts_valid_date_of_birth(authenticated_client):
    r = authenticated_client.patch("/api/accounts/me/", {"date_of_birth": "1990-05-05"}, format="json")
    assert r.status_code == 200
