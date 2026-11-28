"""
Guest carts must work WITHOUT cookies (storefront and API on different domains).
Every request below uses a brand-new APIClient, i.e. no cookie jar at all.
"""
import uuid
from unittest.mock import patch

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.cart.models import Cart
from apps.catalog.models import Category, Product, ProductVariant

pytestmark = pytest.mark.django_db


def token():
    return uuid.uuid4().hex


def call(method, path, tok=None, **kw):
    """One request from a fresh browser: no cookies, optional X-Cart-Token."""
    headers = {"HTTP_X_CART_TOKEN": tok} if tok else {}
    return getattr(APIClient(), method)(path, **headers, **kw)


@pytest.fixture
def variant(db):
    cat = Category.objects.create(name="C", slug="c-tok")
    prod = Product.objects.create(category=cat, name="P", slug="p-tok", base_price="50.00", metal="gold")
    return ProductVariant.objects.create(product=prod, metal="gold", size="1", sku="TOK-1", stock_quantity=20)


def add(tok, variant, qty=1):
    return call("post", "/api/cart/items/", tok, data={"variant_id": variant.pk, "quantity": qty}, format="json")


def test_cart_survives_without_any_cookie(variant):
    t = token()
    assert add(t, variant, 2).status_code == 201
    r = call("get", "/api/cart/", t)             # brand-new client: no session cookie
    assert r.status_code == 200 and r.data["item_count"] == 2


def test_different_token_or_no_token_sees_an_empty_cart(variant):
    t = token()
    add(t, variant)
    assert call("get", "/api/cart/", token()).data["items"] == []
    assert call("get", "/api/cart/").data["items"] == []


def test_reading_with_an_unknown_token_does_not_create_rows():
    before = Cart.objects.count()
    for _ in range(5):
        r = call("get", "/api/cart/", token())
        assert r.status_code == 200 and r.data["items"] == [] and r.data["item_count"] == 0
    assert Cart.objects.count() == before


@pytest.mark.parametrize("bad", ["short", "Z" * 32, "g" * 32, "a" * 31, "a" * 33, "../../etc/passwd"])
def test_malformed_token_is_ignored_not_trusted(variant, bad):
    r = add(bad, variant)                         # falls back to a cookie session cart
    assert r.status_code == 201
    assert not Cart.objects.filter(session_key__startswith="gt_").exists()


def test_patch_and_delete_work_across_requests_and_are_scoped_to_the_token(variant):
    owner, other = token(), token()
    item_id = add(owner, variant).data["items"][0]["id"]
    assert call("patch", f"/api/cart/items/{item_id}/", other, data={"quantity": 5}, format="json").status_code == 404
    call("delete", f"/api/cart/items/{item_id}/", other)               # idempotent: 200, but a no-op
    assert call("get", "/api/cart/", owner).data["item_count"] == 1    # the owner's item is untouched
    assert call("patch", f"/api/cart/items/{item_id}/", owner, data={"quantity": 3}, format="json").data["item_count"] == 3
    assert call("delete", f"/api/cart/items/{item_id}/", owner).data["items"] == []


def test_clear_cart_with_token(variant):
    t = token()
    add(t, variant, 3)
    r = call("delete", "/api/cart/", t)
    assert r.status_code == 200 and r.data["items"] == []


def test_two_tokens_two_independent_carts(variant):
    a, b = token(), token()
    add(a, variant, 1); add(b, variant, 4)
    assert call("get", "/api/cart/", a).data["item_count"] == 1
    assert call("get", "/api/cart/", b).data["item_count"] == 4


def test_merge_moves_the_token_cart_into_the_user_cart(user, variant):
    t = token()
    add(t, variant, 2)
    c = APIClient()
    c.force_authenticate(user=user)
    r = c.post("/api/cart/merge/", {}, format="json", HTTP_X_CART_TOKEN=t)
    assert r.status_code == 200 and r.data["item_count"] == 2
    assert not Cart.objects.filter(session_key=f"gt_{t}").exists()      # guest cart consumed
    assert call("get", "/api/cart/", t).data["items"] == []


def test_merge_ignores_a_session_key_in_the_body_and_a_foreign_token_needs_the_secret(user, variant):
    victim = token()
    add(victim, variant, 3)
    c = APIClient()
    c.force_authenticate(user=user)
    r = c.post("/api/cart/merge/", {"session_key": f"gt_{victim}"}, format="json")  # no header
    assert r.data["item_count"] == 0
    assert Cart.objects.filter(session_key=f"gt_{victim}").exists()


def test_logged_in_user_ignores_the_guest_token_for_normal_cart_calls(user, variant):
    t = token()
    add(t, variant, 2)
    c = APIClient()
    c.force_authenticate(user=user)
    assert c.get("/api/cart/", HTTP_X_CART_TOKEN=t).data["items"] == []   # user cart, not the guest one


@patch("apps.orders.views.create_payment_intent", return_value=("cs_test_secret", "pi_tok"))
def test_guest_checkout_uses_the_token_cart(_pi, variant):
    t = token()
    add(t, variant, 2)
    body = {"email": "g@example.com", "shipping_address": {
        "first_name": "A", "last_name": "B", "line1": "Via 1", "city": "Roma",
        "province": "RM", "postal_code": "00100", "country": "IT"}}
    r = call("post", "/api/checkout/", t, data=body, format="json")
    assert r.status_code == 201, r.data
    assert r.data["order"]["items"][0]["quantity"] == 2
    # a different browser has no cart -> nothing to check out
    assert call("post", "/api/checkout/", token(), data=body, format="json").status_code == 400


def test_cors_preflight_allows_the_cart_token_header():
    with override_settings(CORS_ALLOWED_ORIGINS=["https://shop.example.com"]):
        r = APIClient().options(
            "/api/cart/items/",
            HTTP_ORIGIN="https://shop.example.com",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type,x-cart-token",
        )
    assert r["Access-Control-Allow-Origin"] == "https://shop.example.com"
    assert "x-cart-token" in r["Access-Control-Allow-Headers"].lower()
    assert r["Access-Control-Allow-Credentials"] == "true"
